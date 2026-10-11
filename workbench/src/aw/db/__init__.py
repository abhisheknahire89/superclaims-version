"""Database access.

All SQL in the application uses PostgreSQL-style positional parameters ($1, $2, ...).
Every tenant-scoped unit of work runs inside `Database.tenant_tx(tenant_id)`, which opens a
transaction and sets `app.tenant_id` with `set_config(..., is_local => true)` so the row-level
security policies in migrations/0001 apply. The application connects as a role without
BYPASSRLS (see migrations/0002 and scripts/dev_db.sh).

Driver selection: psycopg 3 if importable (the default install), otherwise the stdlib client in
`aw.db.pgwire` (environments without a package index). AW_DB_DRIVER=pgwire forces the wire client.
Both drivers raise the same exceptions: server errors as `PgError` (with sqlstate and constraint),
connection problems as `InterfaceError`. The test suite runs on both (ADR-13).
"""
from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from .pgwire import Connection as _WireConnection, Json, PgError, InterfaceError  # noqa: F401

try:
    import psycopg  # type: ignore
    from psycopg.types.json import Jsonb  # type: ignore
    _HAVE_PSYCOPG = True
except Exception:  # noqa: BLE001
    _HAVE_PSYCOPG = False


def _as_pg_error(e) -> PgError:
    """psycopg error -> the wire client's PgError, so callers see one error type regardless of driver."""
    d = e.diag
    fields = {"C": e.sqlstate or "XX000", "M": d.message_primary or str(e)}
    if d.constraint_name:
        fields["n"] = d.constraint_name
    if d.message_detail:
        fields["D"] = d.message_detail
    return PgError(fields)


def driver_name() -> str:
    forced = os.environ.get("AW_DB_DRIVER")
    if forced in ("pgwire", "psycopg"):
        if forced == "psycopg" and not _HAVE_PSYCOPG:
            raise RuntimeError("AW_DB_DRIVER=psycopg but psycopg is not installed")
        return forced
    return "psycopg" if _HAVE_PSYCOPG else "pgwire"


_PARAM_RE = re.compile(r"\$(\d+)")


class Conn:
    """Thin facade so application code does not depend on the driver."""

    def __init__(self, raw, driver: str):
        self.raw = raw
        self.driver = driver

    # -- wire driver path
    def _run(self, sql: str, params: tuple):
        if self.driver == "pgwire":
            return self.raw.execute(sql, params)
        return self._run_psycopg(sql, params)

    def _run_psycopg(self, sql: str, params: tuple):
        order: list[int] = []

        def sub(m):
            order.append(int(m.group(1)) - 1)
            return "%s"

        q = _PARAM_RE.sub(sub, sql.replace("%", "%%"))
        args = [Jsonb(params[i].obj) if isinstance(params[i], Json) else params[i] for i in order]
        try:
            cur = self.raw.execute(q, args)
        except psycopg.OperationalError as e:
            if e.sqlstate is None:          # connection-level failure: same contract as the wire client
                raise InterfaceError(str(e)) from e
            raise _as_pg_error(e) from e
        except psycopg.Error as e:
            raise _as_pg_error(e) from e
        cols = [d.name for d in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []
        from .pgwire import Result
        return Result(cols, [tuple(r) for r in rows], cur.statusmessage or "")

    def execute(self, sql: str, *params: Any) -> int:
        return self._run(sql, params).rowcount

    def fetch_all(self, sql: str, *params: Any) -> list[dict]:
        r = self._run(sql, params)
        return [dict(zip(r.columns, row)) for row in r.rows]

    def fetch_one(self, sql: str, *params: Any) -> dict | None:
        rows = self.fetch_all(sql, *params)
        return rows[0] if rows else None

    def fetch_val(self, sql: str, *params: Any):
        r = self._run(sql, params)
        return r.rows[0][0] if r.rows else None

    def script(self, sql: str) -> None:
        if self.driver == "pgwire":
            self.raw.script(sql)
        else:
            try:
                self.raw.execute(sql)
            except psycopg.Error as e:
                raise _as_pg_error(e) from e

    def close(self):
        self.raw.close()


class Database:
    def __init__(self, dsn: str, pool_size: int = 8):
        self.dsn = dsn
        self.pool_size = pool_size
        self._pool: list[Conn] = []
        self._lock = threading.Lock()
        self.driver = driver_name()

    def _new(self) -> Conn:
        if self.driver == "psycopg":
            try:
                return Conn(psycopg.connect(self.dsn, autocommit=True), "psycopg")
            except psycopg.OperationalError as e:
                raise InterfaceError(str(e)) from e
        return Conn(_WireConnection(self.dsn), "pgwire")

    def acquire(self) -> Conn:
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self._new()

    def release(self, conn: Conn, broken: bool = False):
        if broken:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            return
        with self._lock:
            if len(self._pool) < self.pool_size:
                self._pool.append(conn)
                return
        conn.close()

    @contextmanager
    def connection(self) -> Iterator[Conn]:
        conn = self.acquire()
        broken = False
        try:
            yield conn
        except (InterfaceError, OSError):
            broken = True
            raise
        finally:
            self.release(conn, broken)

    @contextmanager
    def tenant_tx(self, tenant_id: str) -> Iterator[Conn]:
        """One transaction with RLS scoped to `tenant_id`. Rolls back on any exception."""
        with self.connection() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except Exception:  # noqa: BLE001
                    pass
                raise

    @contextmanager
    def system_tx(self) -> Iterator[Conn]:
        """Transaction without a tenant (only for migrations and cross-tenant job polling by the owner role)."""
        with self.connection() as conn:
            conn.execute("BEGIN")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except Exception:  # noqa: BLE001
                    pass
                raise

    def close(self):
        with self._lock:
            for c in self._pool:
                try:
                    c.close()
                except Exception:  # noqa: BLE001
                    pass
            self._pool.clear()
