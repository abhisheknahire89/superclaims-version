"""Development server: the HTTP API, the reviewer UI and one background job worker in a single process.

    eval "$(AW_DEV_DIR=/tmp/aw-devdb scripts/dev_db.sh start)"
    PYTHONPATH=src python3 -m aw.server --seed-demo          # then open http://127.0.0.1:8080/

Production runs the API (uvicorn/gunicorn workers) and the job workers as separate processes; see docs/ADR-12.
The server binds to 127.0.0.1 by default and refuses a non-loopback address unless AW_ENV=prod or AW_BIND_ANY=1
(the container image sets AW_BIND_ANY; docker-compose.yml publishes the port on the host's loopback only).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from . import demo, handlers, jobs
from .api.app import create_app
from .context import build
from .db import Database
from .settings import load

log = logging.getLogger("aw.server")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aw.server", description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--seed-demo", action="store_true", help="seed the synthetic demo tenant and load the three demo claims (needs AW_OWNER_DSN)")
    ap.add_argument("--no-worker", action="store_true", help="do not start the in-process job worker")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    settings = load()
    if settings.environment != "prod" and args.host not in ("127.0.0.1", "localhost", "::1") and os.environ.get("AW_BIND_ANY") != "1":
        print("refusing to bind a development server to a non-loopback address (inside a container set AW_BIND_ANY=1 and"
              " publish the port on the host's loopback only)", file=sys.stderr)
        return 2
    if not settings.database_url:
        print("AW_DATABASE_URL is not set (see scripts/dev_db.sh)", file=sys.stderr)
        return 2
    ctx = build(settings)
    worker = None
    if not args.no_worker:
        if ctx.worker_db is None:
            print("AW_WORKER_DSN is not set; pass --no-worker to run the API alone", file=sys.stderr)
            return 2
        worker = jobs.Worker(ctx.worker_db, ctx.db, handlers.build(ctx))
    if args.seed_demo:
        owner_dsn = os.environ.get("AW_OWNER_DSN")
        if not owner_dsn:
            print("--seed-demo needs AW_OWNER_DSN", file=sys.stderr)
            return 2
        loaded = demo.prepare(ctx, Database(owner_dsn), worker)
        log.info("demo tenant ready; documents loaded for %s", ", ".join(loaded) or "no new claims")
    if worker is not None:
        threading.Thread(target=worker.forever, name="aw-worker", daemon=True).start()

    import uvicorn  # imported late so `--help` works without it
    uvicorn.run(create_app(ctx), host=args.host, port=args.port, log_level="info", proxy_headers=False, server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
