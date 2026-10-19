"""Test support: a throwaway PostgreSQL 16 cluster shared by the test run, a fresh database per test class,
and an in-process ASGI client (no httpx needed).

Requires PostgreSQL 16 server binaries (initdb, pg_ctl). If they are missing, DB tests are skipped.
"""
from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from aw.db import Database  # noqa: E402
from aw.db.migrate import migrate  # noqa: E402

def _pgbin() -> Path:
    if os.environ.get("PGBIN"):
        return Path(os.environ["PGBIN"])
    try:  # same detection as the dev scripts: prefers PostgreSQL 16 over whatever initdb is first on PATH
        out = subprocess.run([str(ROOT / "scripts" / "find_pg.sh")], capture_output=True, text=True, check=True).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, OSError):
        found = shutil.which("initdb")
        return Path(found).parent if found else Path("/usr/lib/postgresql/16/bin")


PGBIN = _pgbin()
APP_PW, WK_PW = "test-app-pw", "test-worker-pw"


class _Cluster:
    _lock = threading.Lock()
    _instance: "_Cluster | None" = None

    def __init__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="aw-test-", dir="/tmp"))
        self.port = 55600 + os.getpid() % 300
        self.as_postgres = os.geteuid() == 0
        if self.as_postgres:
            shutil.chown(self.dir, "postgres")
        self._run([str(PGBIN / "initdb"), "-D", str(self.dir / "data"), "-U", "postgres", "-A", "trust", "--auth-host=scram-sha-256",
                   "-E", "UTF8", "--locale=C"])
        self._run([str(PGBIN / "pg_ctl"), "-D", str(self.dir / "data"), "-o",
                   f"-p {self.port} -k {self.dir} -c listen_addresses=127.0.0.1 -c fsync=off -c synchronous_commit=off -c full_page_writes=off",
                   "-l", str(self.dir / "log"), "-w", "start"])
        atexit.register(self.stop)
        self.counter = 0
        owner = Database(self.owner_dsn("postgres"), pool_size=1)
        with owner.connection() as c:
            c.execute(f"CREATE ROLE aw_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{APP_PW}'")
            c.execute(f"CREATE ROLE aw_worker LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{WK_PW}'")
        owner.close()

    def _run(self, cmd: list[str]):
        if self.as_postgres:
            cmd = ["su", "postgres", "-c", " ".join(f"'{c}'" if " " in c else c for c in cmd)]
        # macOS: without a valid LC_ALL the postmaster aborts with "became multithreaded during startup"
        env = {**os.environ, "LC_ALL": os.environ.get("LC_ALL") or "C"}
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    def owner_dsn(self, db: str) -> str:
        return f"postgresql://postgres@localhost:{self.port}/{db}?host={self.dir}"

    def fresh(self) -> dict:
        with self._lock:
            self.counter += 1
            name = f"aw_t{self.counter}"
        owner = Database(self.owner_dsn("postgres"), pool_size=1)
        with owner.connection() as c:
            c.execute(f"CREATE DATABASE {name}")
        owner.close()
        migrate(self.owner_dsn(name), ROOT / "migrations")
        return {
            "owner": self.owner_dsn(name),
            "app": f"postgresql://aw_app:{APP_PW}@127.0.0.1:{self.port}/{name}?sslmode=disable",
            "worker": f"postgresql://aw_worker:{WK_PW}@127.0.0.1:{self.port}/{name}?sslmode=disable",
        }

    def stop(self):
        try:
            self._run([str(PGBIN / "pg_ctl"), "-D", str(self.dir / "data"), "-m", "immediate", "stop"])
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    @classmethod
    def get(cls) -> "_Cluster":
        with cls._lock:
            if cls._instance is None:
                cls._instance = _Cluster()
            return cls._instance


def have_postgres() -> bool:
    return (PGBIN / "initdb").exists()


def fresh_database() -> dict:
    return _Cluster.get().fresh()


class DbTestCase(unittest.TestCase):
    """Each test class gets its own migrated database."""

    @classmethod
    def setUpClass(cls):
        if not have_postgres():
            if os.environ.get("AW_REQUIRE_DB"):
                raise RuntimeError(f"PostgreSQL binaries not found in {PGBIN}; set PGBIN")
            raise unittest.SkipTest("PostgreSQL 16 binaries not available (set PGBIN)")
        cls.dsns = fresh_database()
        cls.owner = Database(cls.dsns["owner"])
        cls.db = Database(cls.dsns["app"])
        cls.worker_db = Database(cls.dsns["worker"])

    @classmethod
    def tearDownClass(cls):
        for d in (cls.db, cls.worker_db, cls.owner):
            d.close()


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- minimal ASGI client
class AsgiClient:
    """Calls an ASGI app in-process. Supports JSON and raw bodies; returns (status, headers, body)."""

    def __init__(self, app):
        self.app = app

    def request(self, method: str, path: str, *, json_body=None, body: bytes | None = None, headers: dict | None = None):
        import asyncio
        from urllib.parse import urlsplit

        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs.setdefault("content-type", "application/json")
        body = body or b""
        parts = urlsplit(path)
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method.upper(),
            "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
            "root_path": "", "headers": [(k.encode(), str(v).encode()) for k, v in hdrs.items()] + [(b"content-length", str(len(body)).encode())],
            "client": ("127.0.0.1", 50000), "server": ("testserver", 80),
        }
        sent = {"status": None, "headers": [], "body": b""}
        done = {"body": False}

        async def receive():
            if not done["body"]:
                done["body"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.start":
                sent["status"] = msg["status"]
                sent["headers"] = msg.get("headers", [])
            elif msg["type"] == "http.response.body":
                sent["body"] += msg.get("body", b"")

        asyncio.run(self.app(scope, receive, send))
        headers_out = {k.decode().lower(): v.decode() for k, v in sent["headers"]}
        return Response(sent["status"], headers_out, sent["body"])

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)


class Response:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body or b"null")

    def __repr__(self):
        return f"<Response {self.status} {self.body[:200]!r}>"
