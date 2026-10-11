"""Job handlers: EXTRACT (per document) -> RECONCILE (per claim) -> EVALUATE (per claim)."""
from __future__ import annotations

from . import evaluations, facts
from .exports import LocalFileExporter
from .extraction import pipeline


def build(ctx) -> dict:
    def extract(conn, job):
        pipeline.run_extraction(conn, ctx, job["tenant_id"], job["subject_id"])

    def reconcile(conn, job):
        facts.run_reconcile(conn, job["tenant_id"], job["subject_id"])

    def evaluate(conn, job):
        evaluations.evaluate_claim(conn, job["tenant_id"], job["subject_id"], trigger=job["payload"].get("trigger", "NEW_EVIDENCE"))

    return {"EXTRACT": extract, "RECONCILE": reconcile, "EVALUATE": evaluate, "EXPORT": LocalFileExporter(ctx.store)}
