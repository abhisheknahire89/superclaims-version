"""PostgreSQL-backed job queue (ADR-02): SELECT … FOR UPDATE SKIP LOCKED, leases, retries with backoff.

The worker polls as the `aw_worker` role (which may see every tenant's jobs, and nothing else),
then does the work in a tenant-scoped transaction as the application role. Jobs are idempotent by
(tenant, kind, idempotency_key); enqueueing the same key twice is a no-op.
"""
from __future__ import annotations

import logging
import socket
import time
import traceback
from datetime import timedelta
from typing import Callable

from .db import Conn, Database, Json

log = logging.getLogger("aw.jobs")
BACKOFF_SECONDS = [30, 120, 600, 1800, 3600]


def enqueue(conn: Conn, tenant_id: str, kind: str, subject_id: str, idempotency_key: str, payload: dict | None = None,
            max_attempts: int = 5) -> str | None:
    row = conn.fetch_one(
        "INSERT INTO processing_job (tenant_id, job_kind, subject_id, idempotency_key, state, payload, max_attempts)"
        " VALUES ($1,$2,$3,$4,'QUEUED',$5::jsonb,$6) ON CONFLICT (tenant_id, job_kind, idempotency_key) DO NOTHING RETURNING job_id",
        tenant_id, kind, subject_id, idempotency_key, Json(payload or {}), max_attempts)
    return row["job_id"] if row else None


class Worker:
    def __init__(self, poll_db: Database, app_db: Database, handlers: dict[str, Callable[[Conn, dict], None]],
                 lease_seconds: int = 300):
        self.poll_db, self.app_db, self.handlers = poll_db, app_db, handlers
        self.name = f"{socket.gethostname()}:{id(self)}"
        self.lease = lease_seconds

    def _claim(self) -> dict | None:
        with self.poll_db.system_tx() as c:
            return c.fetch_one(
                "UPDATE processing_job SET state = 'RUNNING', attempts = attempts + 1, locked_by = $1,"
                " locked_until = now() + make_interval(secs => $2) WHERE job_id = ("
                "  SELECT job_id FROM processing_job WHERE (state IN ('QUEUED','FAILED_RETRYABLE') AND run_after <= now())"
                "     OR (state = 'RUNNING' AND locked_until < now())"
                "  ORDER BY run_after, created_at FOR UPDATE SKIP LOCKED LIMIT 1)"
                " RETURNING job_id, tenant_id, job_kind, subject_id, payload, attempts, max_attempts",
                self.name, self.lease)

    def _finish(self, job: dict, ok: bool, error_code: str | None = None):
        with self.poll_db.system_tx() as c:
            if ok:
                c.execute("UPDATE processing_job SET state='SUCCEEDED', locked_by=NULL, locked_until=NULL, finished_at=now()"
                          " WHERE job_id=$1", job["job_id"])
            else:
                final = job["attempts"] >= job["max_attempts"]
                delay = BACKOFF_SECONDS[min(job["attempts"] - 1, len(BACKOFF_SECONDS) - 1)]
                c.execute("UPDATE processing_job SET state=$2, last_error_code=$3, locked_by=NULL, locked_until=NULL,"
                          " run_after = now() + make_interval(secs => $4), finished_at = CASE WHEN $2 = 'FAILED_FINAL' THEN now() END"
                          " WHERE job_id=$1",
                          job["job_id"], "FAILED_FINAL" if final else "FAILED_RETRYABLE", error_code, delay)

    def run_once(self) -> bool:
        job = self._claim()
        if not job:
            return False
        handler = self.handlers.get(job["job_kind"])
        try:
            if handler is None:
                raise RuntimeError(f"no handler for {job['job_kind']}")
            with self.app_db.tenant_tx(job["tenant_id"]) as conn:
                handler(conn, job)
            self._finish(job, True)
        except Exception as e:  # noqa: BLE001
            code = type(e).__name__
            log.warning("job %s %s failed: %s", job["job_id"], job["job_kind"], code)
            log.debug("%s", traceback.format_exc())
            self._finish(job, False, code)
        return True

    def drain(self, max_jobs: int = 10_000) -> int:
        n = 0
        while n < max_jobs and self.run_once():
            n += 1
        return n

    def forever(self, idle_sleep: float = 1.0):  # pragma: no cover - long-running loop
        while True:
            if not self.run_once():
                time.sleep(idle_sleep)


__all__ = ["enqueue", "Worker", "timedelta"]
