"""Minimal PostgreSQL wire-protocol (v3) client.

Why this exists: the build environment for Phase 1 had no access to a package index, so psycopg could
not be installed. This module lets the application and its integration tests run against a real
PostgreSQL 16 server using only the standard library. Production deployments should install
psycopg 3 (see pyproject.toml); `aw.db` picks psycopg automatically when it is importable.

Scope (deliberately small):
  * startup over TCP or a Unix socket, optional TLS (sslmode=require / verify-full)
  * authentication: trust, cleartext, MD5, SCRAM-SHA-256
  * extended query protocol with text-format parameters and results
  * simple query protocol for multi-statement scripts (migrations)
  * text-format decoding of the types this application uses
Not supported: COPY, binary formats, pipelining, notifications, cancellation.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import ssl
import struct
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable


class PgError(Exception):
    """Server-side error. `sqlstate`, `constraint` and `detail` come from the ErrorResponse fields."""

    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        self.sqlstate = fields.get("C")
        self.constraint = fields.get("n")
        self.detail = fields.get("D")
        self.message = fields.get("M", "")
        super().__init__(f"{self.sqlstate}: {self.message}" + (f" ({self.constraint})" if self.constraint else ""))


class InterfaceError(Exception):
    """Client-side protocol or connection problem."""


class Json:
    """Wrap a Python object to send it as JSON text (use with a ::jsonb cast in SQL)."""

    __slots__ = ("obj",)

    def __init__(self, obj: Any):
        self.obj = obj


@dataclass
class Result:
    columns: list[str]
    rows: list[tuple]
    command: str

    @property
    def rowcount(self) -> int:
        parts = self.command.split()
        return int(parts[-1]) if parts and parts[-1].isdigit() else -1


# ---------------------------------------------------------------- encoding
def _array_literal(values: Iterable[Any]) -> str:
    out = []
    for v in values:
        if v is None:
            out.append("NULL")
        else:
            s = str(v).replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'"{s}"')
    return "{" + ",".join(out) + "}"


def encode_param(v: Any) -> bytes | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return b"true" if v else b"false"
    if isinstance(v, Json):
        return json.dumps(v.obj, sort_keys=True, default=str).encode()
    if isinstance(v, (dict,)):
        return json.dumps(v, sort_keys=True, default=str).encode()
    if isinstance(v, (list, tuple, set, frozenset)):
        return _array_literal(sorted(v) if isinstance(v, (set, frozenset)) else v).encode()
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat().encode()
    if isinstance(v, (date, int, Decimal, float)):
        return str(v).encode() if not isinstance(v, date) else v.isoformat().encode()
    if isinstance(v, bytes):
        return b"\\x" + v.hex().encode()
    return str(v).encode()


# ---------------------------------------------------------------- decoding
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2}(?::?\d{2})?)?$")


def _parse_ts(s: str) -> datetime:
    m = _TS_RE.match(s)
    if not m:
        raise InterfaceError(f"unrecognised timestamp {s!r}")
    d, t, tz = m.groups()
    if "." in t:
        main, frac = t.split(".")
        t = f"{main}.{(frac + '000000')[:6]}"
    if tz:
        if ":" not in tz:
            tz = tz + ":00" if len(tz) == 3 else tz[:3] + ":" + tz[3:]
        return datetime.fromisoformat(f"{d}T{t}{tz}")
    return datetime.fromisoformat(f"{d}T{t}")


def _parse_array(s: str, conv) -> list:
    # handles one-dimensional arrays as produced by PostgreSQL text output
    if s == "{}":
        return []
    inner = s[1:-1]
    items, buf, quoted, i = [], [], False, 0
    was_quoted = False
    while i < len(inner):
        c = inner[i]
        if quoted:
            if c == "\\":
                i += 1
                buf.append(inner[i])
            elif c == '"':
                quoted = False
            else:
                buf.append(c)
        else:
            if c == '"':
                quoted, was_quoted = True, True
            elif c == ",":
                tok = "".join(buf)
                items.append(None if (tok == "NULL" and not was_quoted) else conv(tok))
                buf, was_quoted = [], False
            else:
                buf.append(c)
        i += 1
    tok = "".join(buf)
    items.append(None if (tok == "NULL" and not was_quoted) else conv(tok))
    return items


_DECODERS = {
    16: lambda s: s == "t",
    20: int, 21: int, 23: int, 26: int,
    700: float, 701: float,
    1700: Decimal,
    114: json.loads, 3802: json.loads,
    1082: date.fromisoformat,
    1114: _parse_ts, 1184: _parse_ts,
    1000: lambda s: _parse_array(s, lambda x: x == "t"),
    1005: lambda s: _parse_array(s, int), 1007: lambda s: _parse_array(s, int), 1016: lambda s: _parse_array(s, int),
    1009: lambda s: _parse_array(s, str), 1015: lambda s: _parse_array(s, str),
    1231: lambda s: _parse_array(s, Decimal),
}


def decode_value(oid: int, raw: bytes | None):
    if raw is None:
        return None
    s = raw.decode("utf-8")
    fn = _DECODERS.get(oid)
    return fn(s) if fn else s


# ---------------------------------------------------------------- connection
def parse_dsn(dsn: str) -> dict:
    """postgresql://user:password@host:port/dbname?host=/socket/dir&sslmode=require"""
    from urllib.parse import urlparse, parse_qs, unquote

    u = urlparse(dsn)
    if u.scheme not in ("postgresql", "postgres"):
        raise InterfaceError("DSN must start with postgresql://")
    q = {k: v[-1] for k, v in parse_qs(u.query).items()}
    return {
        "user": unquote(u.username or os.environ.get("PGUSER", "postgres")),
        "password": unquote(u.password) if u.password else os.environ.get("PGPASSWORD"),
        "host": q.get("host") or u.hostname or "localhost",
        "port": int(q.get("port") or u.port or 5432),
        "database": (u.path or "/postgres").lstrip("/") or "postgres",
        "sslmode": q.get("sslmode", "prefer" if not (q.get("host", "") or "").startswith("/") else "disable"),
        "sslrootcert": q.get("sslrootcert"),
        "application_name": q.get("application_name", "adjudication-workbench"),
    }


class Connection:
    def __init__(self, dsn: str, timeout: float = 30.0):
        self.params = parse_dsn(dsn)
        self.timeout = timeout
        self.sock: socket.socket | ssl.SSLSocket | None = None
        self.txn_status = "I"
        self.server_params: dict[str, str] = {}
        self._buf = b""
        self._connect()

    # ---- low-level I/O
    def _send(self, data: bytes):
        assert self.sock is not None
        self.sock.sendall(data)

    def _msg(self, kind: bytes, payload: bytes = b"") -> bytes:
        return kind + struct.pack("!I", len(payload) + 4) + payload

    def _read_exact(self, n: int) -> bytes:
        assert self.sock is not None
        while len(self._buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self._buf)))
            if not chunk:
                raise InterfaceError("server closed the connection")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_msg(self) -> tuple[bytes, bytes]:
        head = self._read_exact(5)
        kind, length = head[:1], struct.unpack("!I", head[1:])[0]
        return kind, self._read_exact(length - 4)

    @staticmethod
    def _cstr(s: str) -> bytes:
        return s.encode() + b"\x00"

    @staticmethod
    def _error_fields(payload: bytes) -> dict[str, str]:
        fields, i = {}, 0
        while i < len(payload) and payload[i] != 0:
            code = chr(payload[i])
            end = payload.index(b"\x00", i + 1)
            fields[code] = payload[i + 1:end].decode("utf-8", "replace")
            i = end + 1
        return fields

    # ---- startup and authentication
    def _connect(self):
        p = self.params
        host = p["host"]
        if host.startswith("/"):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect(os.path.join(host, f".s.PGSQL.{p['port']}"))
        else:
            s = socket.create_connection((host, p["port"]), timeout=self.timeout)
            if p["sslmode"] != "disable":
                s.sendall(struct.pack("!II", 8, 80877103))
                answer = s.recv(1)
                if answer == b"S":
                    ctx = ssl.create_default_context(cafile=p.get("sslrootcert"))
                    if p["sslmode"] in ("require", "prefer"):
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=host)
                elif p["sslmode"] in ("require", "verify-ca", "verify-full"):
                    raise InterfaceError("server does not support TLS but sslmode requires it")
        self.sock = s
        body = struct.pack("!I", 196608)
        for k, v in (("user", p["user"]), ("database", p["database"]), ("application_name", p["application_name"]),
                     ("client_encoding", "UTF8"), ("DateStyle", "ISO, YMD"), ("TimeZone", "UTC")):
            body += self._cstr(k) + self._cstr(v)
        body += b"\x00"
        self._send(struct.pack("!I", len(body) + 4) + body)
        self._authenticate()

    def _authenticate(self):
        p = self.params
        scram = None
        while True:
            kind, payload = self._read_msg()
            if kind == b"R":
                code = struct.unpack("!I", payload[:4])[0]
                if code == 0:
                    continue
                if code == 3:
                    self._send(self._msg(b"p", self._cstr(p["password"] or "")))
                elif code == 5:
                    salt = payload[4:8]
                    inner = hashlib.md5(((p["password"] or "") + p["user"]).encode()).hexdigest()
                    outer = "md5" + hashlib.md5(inner.encode() + salt).hexdigest()
                    self._send(self._msg(b"p", self._cstr(outer)))
                elif code == 10:
                    mechs = payload[4:].split(b"\x00")
                    if b"SCRAM-SHA-256" not in mechs:
                        raise InterfaceError(f"unsupported SASL mechanisms {mechs}")
                    scram = _Scram(p["password"] or "")
                    first = scram.client_first().encode()
                    self._send(self._msg(b"p", self._cstr("SCRAM-SHA-256") + struct.pack("!I", len(first)) + first))
                elif code == 11:
                    assert scram is not None
                    self._send(self._msg(b"p", scram.client_final(payload[4:].decode()).encode()))
                elif code == 12:
                    assert scram is not None
                    scram.verify_server(payload[4:].decode())
                else:
                    raise InterfaceError(f"unsupported authentication method {code}")
            elif kind == b"S":
                k, v, _ = payload.split(b"\x00", 2)
                self.server_params[k.decode()] = v.decode()
            elif kind == b"K":
                pass
            elif kind == b"E":
                raise PgError(self._error_fields(payload))
            elif kind == b"N":
                pass
            elif kind == b"Z":
                self.txn_status = payload.decode()
                return

    # ---- queries
    def execute(self, sql: str, params: Iterable[Any] = ()) -> Result:
        params = list(params)
        enc = [encode_param(v) for v in params]
        bind = self._cstr("") + self._cstr("") + struct.pack("!H", 0) + struct.pack("!H", len(enc))
        for e in enc:
            bind += struct.pack("!i", -1) if e is None else struct.pack("!i", len(e)) + e
        bind += struct.pack("!H", 0)
        out = (self._msg(b"P", self._cstr("") + self._cstr(sql) + struct.pack("!H", 0))
               + self._msg(b"B", bind)
               + self._msg(b"D", b"P" + self._cstr(""))
               + self._msg(b"E", self._cstr("") + struct.pack("!I", 0))
               + self._msg(b"S"))
        self._send(out)
        cols, oids, rows, command, error = [], [], [], "", None
        while True:
            kind, payload = self._read_msg()
            if kind == b"T":
                cols, oids = self._row_description(payload)
            elif kind == b"D":
                rows.append(self._data_row(payload, oids))
            elif kind == b"C":
                command = payload.rstrip(b"\x00").decode()
            elif kind == b"E":
                error = PgError(self._error_fields(payload))
            elif kind == b"Z":
                self.txn_status = payload.decode()
                break
            # ParseComplete, BindComplete, NoData, Notice, ParameterStatus: ignore
            elif kind == b"S":
                k, v, _ = payload.split(b"\x00", 2)
                self.server_params[k.decode()] = v.decode()
        if error:
            raise error
        return Result(cols, rows, command)

    def script(self, sql: str) -> None:
        """Run one or more statements with the simple query protocol (no parameters)."""
        self._send(self._msg(b"Q", self._cstr(sql)))
        error = None
        while True:
            kind, payload = self._read_msg()
            if kind == b"E":
                error = PgError(self._error_fields(payload))
            elif kind == b"Z":
                self.txn_status = payload.decode()
                break
        if error:
            raise error

    @staticmethod
    def _row_description(payload: bytes):
        n = struct.unpack("!H", payload[:2])[0]
        i, cols, oids = 2, [], []
        for _ in range(n):
            end = payload.index(b"\x00", i)
            cols.append(payload[i:end].decode())
            i = end + 1
            _table, _col, oid, _size, _mod, _fmt = struct.unpack("!IHIhiH", payload[i:i + 18])
            oids.append(oid)
            i += 18
        return cols, oids

    @staticmethod
    def _data_row(payload: bytes, oids: list[int]) -> tuple:
        n = struct.unpack("!H", payload[:2])[0]
        i, vals = 2, []
        for k in range(n):
            ln = struct.unpack("!i", payload[i:i + 4])[0]
            i += 4
            if ln == -1:
                vals.append(None)
            else:
                vals.append(decode_value(oids[k], payload[i:i + ln]))
                i += ln
        return tuple(vals)

    def close(self):
        if self.sock:
            try:
                self._send(self._msg(b"X"))
            except OSError:
                pass
            self.sock.close()
            self.sock = None


class _Scram:
    def __init__(self, password: str):
        self.password = password
        self.nonce = base64.b64encode(os.urandom(18)).decode()
        self.client_first_bare = f"n=,r={self.nonce}"
        self.server_signature = b""

    def client_first(self) -> str:
        return "n,," + self.client_first_bare

    def client_final(self, server_first: str) -> str:
        attrs = dict(kv.split("=", 1) for kv in server_first.split(","))
        r, s, i = attrs["r"], base64.b64decode(attrs["s"]), int(attrs["i"])
        if not r.startswith(self.nonce):
            raise InterfaceError("SCRAM nonce mismatch")
        salted = hashlib.pbkdf2_hmac("sha256", self.password.encode(), s, i)
        client_key = hmac.new(salted, b"Client Key", "sha256").digest()
        stored_key = hashlib.sha256(client_key).digest()
        without_proof = f"c=biws,r={r}"
        auth_message = f"{self.client_first_bare},{server_first},{without_proof}".encode()
        signature = hmac.new(stored_key, auth_message, "sha256").digest()
        proof = bytes(a ^ b for a, b in zip(client_key, signature))
        server_key = hmac.new(salted, b"Server Key", "sha256").digest()
        self.server_signature = hmac.new(server_key, auth_message, "sha256").digest()
        return f"{without_proof},p={base64.b64encode(proof).decode()}"

    def verify_server(self, server_final: str):
        attrs = dict(kv.split("=", 1) for kv in server_final.split(","))
        if base64.b64decode(attrs.get("v", "")) != self.server_signature:
            raise InterfaceError("SCRAM server signature mismatch")
