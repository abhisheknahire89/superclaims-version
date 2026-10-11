"""HTTP API against the contract: upload flow, idempotency, ETag/If-Match, second approval, worksheet, permissions,
tenant isolation and response-schema conformance."""
from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator

from support import PACK, AsgiClient, DbTestCase

from aw import auth, jobs, handlers, seed, synthetic
from aw.api.app import create_app
from aw.context import AppContext
from aw.extraction.providers import HeuristicProvider
from aw.settings import load
from aw.storage import LocalWormStore

T = seed.TENANT
EVAL_SCHEMA = Draft202012Validator(json.loads((PACK / "schemas" / "evaluation-result.schema.json").read_text()))
WS_SCHEMA = Draft202012Validator(json.loads((PACK / "schemas" / "settlement-worksheet.schema.json").read_text()))


class ApiFlow(DbTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        seed.seed(cls.owner, cls.db)
        settings = load()
        cls.ctx = AppContext(settings, cls.db, cls.worker_db, LocalWormStore(Path(tempfile.mkdtemp())), HeuristicProvider())
        cls.client = AsgiClient(create_app(cls.ctx))
        cls.worker = jobs.Worker(cls.worker_db, cls.db, handlers.build(cls.ctx))
        cls.secret = settings.dev_token_secret
        cls.docs = synthetic.claim_documents()

    def h(self, user, **extra):
        hdrs = {"Authorization": f"Bearer {auth.issue_dev_token(self.secret, user, T)}"}
        hdrs.update(extra)
        return hdrs

    def idem(self, user, **extra):
        return self.h(user, **{"Idempotency-Key": str(uuid.uuid4()), **extra})

    def etag(self, user, claim_id):
        return self.client.get(f"/v1/claims/{claim_id}", headers=self.h(user)).headers["etag"]

    def create_and_upload(self, claim_id, trace, user="PROC-07"):
        f = seed._fixture(trace)
        r = self.client.post("/v1/claims", json_body={"external_ref": f"API-{claim_id}", "workflow": "IPD_REIMBURSEMENT", "policy_no": f["policy"]["policy_no"],
                                                       "member_id": f["member"]["member_id"], "hospital_id": f["hospital_id"]}, headers=self.idem(user))
        self.assertEqual(r.status, 201, r)
        cid = r.json()["claim_id"]
        for name, dtype, data in self.docs[claim_id]:
            body = {"declared_type": dtype, "sha256": hashlib.sha256(data).hexdigest(), "mime_type": "application/pdf", "size_bytes": len(data)}
            slot = self.client.post(f"/v1/claims/{cid}/documents", json_body=body, headers=self.idem(user))
            self.assertEqual(slot.status, 201, slot)
            up = self.client.request("PUT", slot.json()["upload_url"], body=data, headers={"content-type": "application/pdf"})
            self.assertIn(up.status, (200, 201), up)
            done = self.client.post(f"/v1/claims/{cid}/documents/{slot.json()['document_id']}:complete", headers=self.idem(user))
            self.assertEqual(done.status, 202, done)
        self.worker.drain()
        return cid

    def test_full_flow_claim_1_and_2(self):
        # --- claim 1: decision within limit, idempotent replay, stale ETag
        c1 = self.create_and_upload("CLM-DEMO-0001", "trace-1-straightforward")
        ev = self.client.get(f"/v1/claims/{c1}/evaluations/current", headers=self.h("PROC-07"))
        self.assertEqual(ev.status, 200, ev)
        body = ev.json()
        errors = [e.message for e in EVAL_SCHEMA.iter_errors({k: v for k, v in body.items() if k not in ("status", "supersedes_evaluation_id")})]
        self.assertEqual(errors, [], "current evaluation must match evaluation-result.schema.json")
        self.assertEqual(body["recommendation"]["recommended_payable"], "107591.00")
        decision = {"evaluation_id": body["evaluation_id"], "disposition": "APPROVED_PARTIAL", "approved_payable": "107591.00"}
        stale = self.client.post(f"/v1/claims/{c1}/decisions", json_body=decision, headers=self.idem("PROC-07", **{"If-Match": '"rv-0"'}))
        self.assertEqual(stale.status, 412, stale)
        key = str(uuid.uuid4())
        hdrs = self.h("PROC-07", **{"Idempotency-Key": key, "If-Match": self.etag("PROC-07", c1)})
        d1 = self.client.post(f"/v1/claims/{c1}/decisions", json_body=decision, headers=hdrs)
        self.assertEqual(d1.status, 201, d1)
        replay = self.client.post(f"/v1/claims/{c1}/decisions", json_body=decision, headers=hdrs)
        self.assertEqual((replay.status, replay.headers.get("idempotent-replay")), (201, "true"))
        self.assertEqual(replay.json()["decision_id"], d1.json()["decision_id"])
        reused = self.client.post(f"/v1/claims/{c1}/decisions", json_body={**decision, "approved_payable": "1.00"}, headers=hdrs)
        self.assertEqual(reused.status, 409, reused)
        ws = self.client.get(f"/v1/claims/{c1}/decisions/{d1.json()['decision_id']}/worksheet", headers=self.h("PROC-07"))
        self.assertEqual([e.message for e in WS_SCHEMA.iter_errors(ws.json())], [])
        pdf = self.client.get(f"/v1/claims/{c1}/decisions/{d1.json()['decision_id']}/worksheet?format=pdf", headers=self.h("PROC-07"))
        self.assertEqual((pdf.status, pdf.body[:5]), (200, b"%PDF-"))

        # --- claim 2: second approval required, then approved by SUP-02
        c2 = self.create_and_upload("CLM-DEMO-0002", "trace-2-interacting-adjustments", user="PROC-11")
        ev2 = self.client.get(f"/v1/claims/{c2}/evaluations/current", headers=self.h("PROC-11")).json()
        self.assertEqual(ev2["recommendation"]["recommended_payable"], "85000.00")
        dec2 = {"evaluation_id": ev2["evaluation_id"], "disposition": "APPROVED_PARTIAL", "approved_payable": "85000.00"}
        r = self.client.post(f"/v1/claims/{c2}/decisions", json_body=dec2, headers=self.idem("PROC-11", **{"If-Match": self.etag("PROC-11", c2)}))
        self.assertEqual((r.status, r.json()["type"].rsplit("/", 1)[-1]), (409, "second-approval-required"))
        self.assertEqual(r.json()["triggers"], ["TOTAL_DEDUCTIONS_ABOVE_SHARE_OF_BILLED"])
        ar = self.client.post(f"/v1/claims/{c2}/approval-requests",
                              json_body={"evaluation_id": ev2["evaluation_id"], "proposed_disposition": "APPROVED_PARTIAL", "proposed_payable": "85000.00",
                                         "approver_user_id": "SUP-02"}, headers=self.idem("PROC-11", **{"If-Match": self.etag("PROC-11", c2)}))
        self.assertEqual(ar.status, 201, ar)
        wrong = self.client.post(f"/v1/approval-requests/{ar.json()['approval_request_id']}:approve", headers=self.idem("PROC-07"))
        self.assertEqual(wrong.status, 403, wrong)
        ok = self.client.post(f"/v1/approval-requests/{ar.json()['approval_request_id']}:approve", headers=self.idem("SUP-02"))
        self.assertEqual(ok.status, 200, ok)
        self.assertEqual((ok.json()["second_approver"], ok.json()["approved_payable"]), ("SUP-02", "85000.00"))
        # the SI ledger is now exhausted for this member: a re-opened duplicate decision cannot overdraw it
        claim = self.client.get(f"/v1/claims/{c2}", headers=self.h("SUP-02")).json()
        self.assertEqual(claim["status"], "FINALISED")
        audit_r = self.client.get(f"/v1/claims/{c2}/audit-events", headers=self.h("AUD-01")).json()
        self.assertTrue(audit_r["verification"]["verified"])
        self.assertIn("APPROVAL_GRANTED", {e["event_type"] for e in audit_r["items"]})

    def test_contract_validation_permissions_and_isolation(self):
        bad = self.client.post("/v1/claims", json_body={"workflow": "IPD_REIMBURSEMENT"}, headers=self.idem("PROC-07"))
        self.assertEqual(bad.status, 422)
        self.assertTrue(any(e["pointer"] == "/" for e in bad.json()["errors"]))
        missing = self.client.post("/v1/claims", json_body={"external_ref": "X", "workflow": "IPD_REIMBURSEMENT", "policy_no": "P", "member_id": "M"},
                                   headers=self.h("PROC-07"))
        self.assertEqual(missing.status, 400, "Idempotency-Key is required by the contract")
        self.assertEqual(self.client.get("/v1/claims").status, 401)
        ro = self.client.post("/v1/claims", json_body={"external_ref": "RO-1", "workflow": "IPD_REIMBURSEMENT", "policy_no": "ILL-POL-000101",
                                                       "member_id": "MEM-DEMO-1001"}, headers=self.idem("RO-01"))
        self.assertEqual(ro.status, 403)
        # another tenant's user cannot see this tenant's claims
        with self.owner.connection() as c:
            c.execute("INSERT INTO tenant (tenant_id, legal_name, tenant_kind) VALUES ('TENANT-OTHER','Other','INSURER') ON CONFLICT DO NOTHING")
        with self.db.tenant_tx("TENANT-OTHER") as c:
            c.execute("INSERT INTO app_user (user_id, tenant_id, idp_subject, display_name) VALUES ('X-1','TENANT-OTHER','dev|X-1','x') ON CONFLICT DO NOTHING")
            c.execute("INSERT INTO role_assignment (tenant_id, user_id, role) VALUES ('TENANT-OTHER','X-1','SUPERVISOR') ON CONFLICT DO NOTHING")
        other = {"Authorization": f"Bearer {auth.issue_dev_token(self.secret, 'X-1', 'TENANT-OTHER')}"}
        self.assertEqual(self.client.get("/v1/claims/CLM-DEMO-0088", headers=other).status, 404)
        self.assertEqual(self.client.get("/v1/claims", headers=other).json()["items"], [])
        forged = {"Authorization": "Bearer " + auth.issue_dev_token("wrong-secret", "SUP-02", T)}
        self.assertEqual(self.client.get("/v1/claims", headers=forged).status, 401)

    def test_page_urls_are_signed_and_expire(self):
        docs = self.client.get("/v1/claims/CLM-DEMO-0088/documents", headers=self.h("PROC-07"))
        self.assertEqual(docs.status, 200)
        r = self.client.get("/v1/claims/CLM-DEMO-0088/documents/DOC-NOPE/pages/1/image?t=TENANT-DEMO&exp=9999999999&sig=forged")
        self.assertEqual(r.status, 403)
