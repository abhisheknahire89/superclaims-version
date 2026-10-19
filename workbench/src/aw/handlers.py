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
        if job["payload"].get("force_evaluation"):
            from . import jobs
            jobs.enqueue(conn,job["tenant_id"],"EVALUATE",job["subject_id"],"query-evaluate:"+str(job["job_id"]),{"trigger":"NEW_EVIDENCE"})

    def evaluate(conn, job):
        evaluations.evaluate_claim(conn, job["tenant_id"], job["subject_id"], trigger=job["payload"].get("trigger", "NEW_EVIDENCE"))

    def anchor(conn,job):
        from .anchors import anchor
        anchor(conn,ctx.store,job['tenant_id'],job['subject_id'])
    def deadline(conn,job):
        from .maintenance import scan
        scan(conn,job['tenant_id'])
    return {"AUDIT_ANCHOR":anchor,"DEADLINE_SCAN":deadline,"EXTRACT": extract, "RECONCILE": reconcile, "EVALUATE": evaluate, "EXPORT": LocalFileExporter(ctx.store)}
