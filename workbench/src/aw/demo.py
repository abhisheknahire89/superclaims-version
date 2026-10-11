"""End-to-end demonstration on synthetic documents: the three demo claims go from PDF upload to decision through
the real pipeline (ingest -> extract -> grounding -> resolve -> rules -> review -> decision -> worksheet -> export),
and the result is compared with the research pack's verified traces.

    python -m aw.demo     (needs AW_OWNER_DSN, AW_DATABASE_URL, AW_WORKER_DSN; see scripts/dev_db.sh)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import auth, decisions, handlers, ingest, jobs, queries, review, seed, synthetic
from .db import Database

PACK = Path(__file__).resolve().parents[3]
T = seed.TENANT


def _principal(app: Database, user: str) -> auth.Principal:
    with app.tenant_tx(T) as c:
        return auth.load_principal(c, T, user)


def _upload(ctx, claim_id: str, docs, actor: str, supersedes: dict | None = None) -> dict:
    ids = {}
    for name, dtype, data in docs:
        with ctx.db.tenant_tx(T) as c:
            sup = (supersedes or {}).get(name)
            d = ingest.add_document(c, ctx.store, T, claim_id, data, declared_type=dtype, source_channel="PORTAL_UPLOAD", actor=actor,
                                    supersedes_document_id=ids.get(sup) or sup)
            ids[name] = d["document_id"]
    return ids


def _current(ctx, claim_id: str) -> dict:
    with ctx.db.tenant_tx(T) as c:
        return c.fetch_one("SELECT e.* FROM evaluation e JOIN claim c ON c.tenant_id=e.tenant_id AND c.current_evaluation_id=e.evaluation_id"
                           " WHERE c.tenant_id=$1 AND c.claim_id=$2", T, claim_id)


def _adjustment_map(result: dict) -> dict:
    return {f"{a['line_id'] or 'CLAIM'}|{a['rule_id']}": a["amount"] for a in result["adjustments"]}


def compare_with_pack(result: dict, trace: str) -> dict:
    ref = json.loads((PACK / "fixtures" / "claims" / f"{trace}.output.json").read_text(encoding="utf-8"))
    ours, theirs = _adjustment_map(result), _adjustment_map(ref)
    return {
        "trace": trace,
        "recommendation_matches": result["recommendation"] == ref["recommendation"],
        "adjustments_match": ours == theirs,
        "finding_kinds_match": sorted(f["kind"] for f in result["findings"]) == sorted(f["kind"] for f in ref["findings"]),
        "payable": result["recommendation"]["recommended_payable"],
        "pack_payable": ref["recommendation"]["recommended_payable"],
        "differences": sorted(set(ours.items()) ^ set(theirs.items())),
    }


def prepare(ctx, owner: Database, worker: jobs.Worker | None = None) -> list[str]:
    """Seed the demo tenant and upload the synthetic documents of the three demo claims, leaving every claim
    undecided (for the reviewer UI). Safe to call again: claims that already have documents are left alone."""
    seed.seed(owner, ctx.db)
    docs = synthetic.claim_documents()
    loaded = []
    for cid, name, ext in seed.DEMO:
        f = seed._fixture(name)
        with ctx.db.tenant_tx(T) as c:
            if not ingest.get_claim(c, T, cid):
                ingest.create_claim(c, T, {"claim_id": cid, "external_ref": ext, "workflow": "IPD_REIMBURSEMENT", "policy_no": f["policy"]["policy_no"],
                                           "member_id": f["member"]["member_id"], "hospital_id": f["hospital_id"]}, "USER:PROC-07")
            has_docs = c.fetch_val("SELECT count(*) FROM document WHERE tenant_id=$1 AND claim_id=$2", T, cid)
        if not has_docs:
            _upload(ctx, cid, docs[cid], "USER:PROC-07")
            loaded.append(cid)
    if worker is not None:
        worker.drain()
    return loaded


def run(ctx, owner: Database) -> dict:
    worker = jobs.Worker(ctx.worker_db, ctx.db, handlers.build(ctx))
    docs = synthetic.claim_documents()
    report: dict = {"claims": {}}
    prepare(ctx, owner, worker)

    # ---- claim 1: within PROC-07's limit, no second approval
    e1 = _current(ctx, "CLM-DEMO-0001")
    p07 = _principal(ctx.db, "PROC-07")
    with ctx.db.tenant_tx(T) as c:
        d1 = decisions.decide(c, p07, ctx.schema_dir, "CLM-DEMO-0001", {"evaluation_id": e1["evaluation_id"], "disposition": "APPROVED_PARTIAL",
                                                                        "approved_payable": e1["result"]["recommendation"]["recommended_payable"]})
    report["claims"]["CLM-DEMO-0001"] = {"compare": compare_with_pack(e1["result"], "trace-1-straightforward"), "decision": d1}

    # ---- claim 2: deductions > 30% of billed -> second approval by SUP-02
    e2 = _current(ctx, "CLM-DEMO-0002")
    p11, sup = _principal(ctx.db, "PROC-11"), _principal(ctx.db, "SUP-02")
    payable2 = e2["result"]["recommendation"]["recommended_payable"]
    try:
        with ctx.db.tenant_tx(T) as c:
            decisions.decide(c, p11, ctx.schema_dir, "CLM-DEMO-0002", {"evaluation_id": e2["evaluation_id"], "disposition": "APPROVED_PARTIAL",
                                                                       "approved_payable": payable2})
        needed = None
    except decisions.DecisionError as e:
        needed = {"code": e.code, **e.extra}
    with ctx.db.tenant_tx(T) as c:
        ar = decisions.request_approval(c, p11, "CLM-DEMO-0002", {"evaluation_id": e2["evaluation_id"], "proposed_disposition": "APPROVED_PARTIAL",
                                                                  "proposed_payable": payable2, "approver_user_id": "SUP-02"})
    with ctx.db.tenant_tx(T) as c:
        d2 = decisions.approve_request(c, sup, ctx.schema_dir, ar["approval_request_id"])
    report["claims"]["CLM-DEMO-0002"] = {"compare": compare_with_pack(e2["result"], "trace-2-interacting-adjustments"),
                                         "second_approval": needed, "decision": d2}

    # ---- claim 3: blocked -> queries -> corrected bill + admission record -> date conflict resolved -> REFER_MEDICAL
    e3a = _current(ctx, "CLM-DEMO-0003")
    p04 = _principal(ctx.db, "PROC-04")
    with ctx.db.tenant_tx(T) as c:
        letters = queries.draft_from_evaluation(c, p04, "CLM-DEMO-0003", e3a["evaluation_id"])
        for q in letters:
            queries.approve(c, p04, q["query_id"])
    with ctx.db.tenant_tx(T) as c:
        sb = c.fetch_one("SELECT document_id FROM document WHERE tenant_id=$1 AND claim_id='CLM-DEMO-0003' AND classified_type='FINAL_BILL_SUMMARY'", T)
    _upload(ctx, "CLM-DEMO-0003", docs["CLM-DEMO-0003:after-query"], "USER:PROC-04", supersedes={"final-bill-corrected": sb["document_id"]})
    worker.drain()
    e3_mid = _current(ctx, "CLM-DEMO-0003")
    with ctx.db.tenant_tx(T) as c:
        ar_fact = c.fetch_one("SELECT f.fact_id FROM extracted_fact f JOIN extraction_run r ON r.tenant_id=f.tenant_id AND r.extraction_run_id=f.extraction_run_id"
                              " JOIN document d ON d.tenant_id=r.tenant_id AND d.document_id=r.document_id WHERE f.tenant_id=$1 AND f.claim_id='CLM-DEMO-0003'"
                              " AND d.classified_type='ADMISSION_RECORD' AND f.field_path='admission.date'", T)
        review.record(c, p04, "CLM-DEMO-0003", {"action": "RESOLVE_CONFLICT", "target": {"type": "conflict", "id": "admission.date"},
                                                "after_value": {"value": "2026-09-02", "evidence_fact_id": ar_fact["fact_id"]},
                                                "reason_code": "ADMISSION_RECORD_CONFIRMS",
                                                "comment": "Admission record shows admission at 23:40 on 02/09; the discharge summary used the next calendar day."})
    worker.drain()
    e3b = _current(ctx, "CLM-DEMO-0003")
    report["claims"]["CLM-DEMO-0003"] = {
        "first_run": compare_with_pack(e3a["result"], "trace-3a-insufficient-conflicting"),
        "queries_sent": [{"addressed_to": q["addressed_to"], "items": len(q["items"])} for q in letters],
        "after_new_documents": {"recommendation": e3_mid["result"]["recommendation"]["type"], "blocked_scopes": e3_mid["result"]["recommendation"]["blocked_scopes"]},
        "after_conflict_resolution": compare_with_pack(e3b["result"], "trace-3b-after-new-evidence"),
    }
    worker.drain()  # exports
    with ctx.db.tenant_tx(T) as c:
        from . import audit
        report["audit_chains"] = {cid: audit.verify_chain(c, T, cid) for cid, _, _ in seed.DEMO}
        report["claim_status"] = {r["claim_id"]: r["status"] for r in c.fetch_all("SELECT claim_id, status FROM claim WHERE claim_id LIKE 'CLM-DEMO-000%' ORDER BY 1")}
    return report


if __name__ == "__main__":
    from .context import build
    from .settings import load
    ctx = build(load())
    out = run(ctx, Database(os.environ["AW_OWNER_DSN"]))
    print(json.dumps(out, indent=1, default=str))
    checks = [c for v in out["claims"].values() for k, c in v.items() if k in ("compare", "first_run", "after_conflict_resolution")]
    ok = len(checks) == 4 and all(c["recommendation_matches"] and c["adjustments_match"] and c["finding_kinds_match"] for c in checks) \
        and all(r["verified"] for r in out["audit_chains"].values())
    sys.exit(0 if ok else 1)
