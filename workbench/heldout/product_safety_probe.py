"""Bounded native-document pipeline/decision probe in a throwaway database."""
from pathlib import Path
import json
import tempfile
import argparse
from dataclasses import replace
from support import fresh_database, _Cluster
from aw.db import Database
from aw.context import AppContext
from aw.settings import Settings
from aw.storage import LocalWormStore
from aw.extraction.providers import HeuristicProvider
from aw import seed, ingest, handlers, jobs, evaluations, auth, decisions

PACK = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--directory", default="workbench/heldout/challenge/out")
parser.add_argument("--claims", nargs="+", default=["CLM-CHALLENGE-03-01", "CLM-CHALLENGE-04-01", "CLM-CHALLENGE-03-04"])
parser.add_argument("--evidence-file", default="product-abstention-probe.json")
args = parser.parse_args()
DIRECTORY = PACK / args.directory
OUT = PACK / "workbench/evidence/2026-10-12" / args.evidence_file
T = seed.TENANT
report = dict(synthetic_only=True, isolated_database=True, scope="Bounded synthetic native-PDF bundles; not an extraction accuracy estimate", claims=[])
dsns = fresh_database()
owner, db, worker_db = (Database(dsns[key]) for key in ("owner", "app", "worker"))
try:
    with tempfile.TemporaryDirectory(prefix="aw-independent-probe-") as objects:
        settings = Settings(dsns["app"], dsns["worker"], Path(objects), "local", "test-only-probe-secret", "heuristic", None, PACK, "test", "tesseract", None, None)
        ctx = AppContext(settings, db, worker_db, LocalWormStore(Path(objects)), HeuristicProvider())
        seed.seed(owner, db)
        worker = jobs.Worker(worker_db, db, handlers.build(ctx))
        source = seed._fixture("trace-1-straightforward")
        manifest = json.loads((DIRECTORY / "manifest.json").read_text())
        for cid in args.claims:
            records = [r for r in manifest["documents"] if r["claim_id"] == cid and r["format"] == "native_pdf"]
            name = records[0]["fields"]["patient.name"]
            # Align seeded member identity to the printed synthetic name, to avoid
            # using an unrelated demo-person mismatch as evidence of safety.
            with owner.tenant_tx(T) as c:
                c.execute("UPDATE member SET full_name=$3,name_normalised=$4,gender='M' WHERE tenant_id=$1 AND member_id=$2", T, source["member"]["member_id"], name, name.upper())
            with db.tenant_tx(T) as c:
                ingest.create_claim(c, T, dict(claim_id=cid, external_ref="PROBE-" + cid, workflow="IPD_REIMBURSEMENT", policy_no=source["policy"]["policy_no"], member_id=source["member"]["member_id"], hospital_id=source["hospital_id"]), "USER:PROC-07")
            duplicate_uploads = 0
            for row in records:
                with db.tenant_tx(T) as c:
                    uploaded = ingest.add_document(c, ctx.store, T, cid, (DIRECTORY / row["path"]).read_bytes(), declared_type=None, source_channel="API", actor="USER:PROC-07")
                    duplicate_uploads += bool(uploaded.get("duplicate"))
            drained = worker.drain(max_jobs=50)
            with db.tenant_tx(T) as c:
                evaluation = evaluations.current(c, T, cid)
                docs = c.fetch_all("SELECT classified_type,status FROM document WHERE tenant_id=$1 AND claim_id=$2 ORDER BY classified_type", T, cid)
                failures = c.fetch_all("SELECT state,last_error_code FROM processing_job WHERE tenant_id=$1 AND state<>'SUCCEEDED'", T)
                principal = auth.load_principal(c, T, "PROC-07")
            result = evaluation["result"] if evaluation else None
            denied = None
            if evaluation:
                try:
                    with db.tenant_tx(T) as c:
                        decisions.decide(c, principal, ctx.schema_dir, cid, dict(evaluation_id=evaluation["evaluation_id"], disposition="APPROVED_PARTIAL", approved_payable="1.00"))
                    denied = False
                except decisions.DecisionError as error:
                    denied = error.code
            with db.tenant_tx(T) as c:
                decision_count = c.fetch_val("SELECT count(*) FROM decision WHERE tenant_id=$1 AND claim_id=$2", T, cid)
            report["claims"].append(dict(claim_id=cid, documents=len(records), duplicate_uploads=duplicate_uploads, stored_documents=len(docs), jobs_drained=drained, document_statuses=docs, non_success_jobs=failures, evaluation_status=evaluation["status"] if evaluation else None, recommendation=result["recommendation"] if result else None, findings=[dict(kind=f["kind"], blocking=f.get("blocking")) for f in result["findings"]] if result else [], attempted_approval_result=denied, persisted_decisions=decision_count))
        report["counts"] = dict(claims=len(report["claims"]), documents=sum(c["documents"] for c in report["claims"]), blocked=sum(c["evaluation_status"] == "BLOCKED" for c in report["claims"]), approvals_refused=sum(isinstance(c["attempted_approval_result"], str) for c in report["claims"]), decisions=sum(c["persisted_decisions"] for c in report["claims"]))
        report["counts"]["duplicate_uploads"] = sum(c["duplicate_uploads"] for c in report["claims"])
        report["counts"]["stored_documents"] = sum(c["stored_documents"] for c in report["claims"])
        report["result"] = "PASS" if report["counts"]["blocked"] == len(args.claims) and report["counts"]["approvals_refused"] == len(args.claims) and not report["counts"]["decisions"] else "FAIL"
finally:
    for database in (worker_db, db, owner):
        database.close()
    _Cluster.get().stop()
OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
print(json.dumps(report, indent=2, default=str))
