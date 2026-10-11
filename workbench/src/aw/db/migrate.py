"""Apply SQL migrations in order. Each file runs once; applied versions are recorded with a checksum.

Usage: python -m aw.db.migrate <owner_dsn> [migrations_dir]
The owner DSN must be the schema owner (not the RLS-restricted application role).
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from . import Database

DEFAULT_DIR = Path(__file__).resolve().parents[3] / "migrations"


def migrate(owner_dsn: str, migrations_dir: Path = DEFAULT_DIR) -> list[str]:
    db = Database(owner_dsn, pool_size=1)
    applied_now: list[str] = []
    try:
        with db.connection() as conn:
            conn.script("CREATE TABLE IF NOT EXISTS schema_migration (version TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            done = {r["version"]: r["sha256"] for r in conn.fetch_all("SELECT version, sha256 FROM schema_migration")}
            for f in sorted(migrations_dir.glob("*.sql")):
                body = f.read_text(encoding="utf-8")
                digest = hashlib.sha256(body.encode()).hexdigest()
                if f.name in done:
                    if done[f.name] != digest:
                        raise RuntimeError(f"migration {f.name} changed after it was applied (checksum mismatch)")
                    continue
                conn.script(body)
                conn.execute("INSERT INTO schema_migration (version, sha256) VALUES ($1, $2)", f.name, digest)
                applied_now.append(f.name)
    finally:
        db.close()
    return applied_now


if __name__ == "__main__":
    dsn = sys.argv[1]
    d = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_DIR
    print("applied:", migrate(dsn, d) or "nothing (up to date)")
