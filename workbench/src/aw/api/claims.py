"""Claims, documents, evaluations, review, queries, decisions, audit and exports (api/openapi.yaml)."""
from __future__ import annotations

import base64
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from .. import audit, configs, decisions, evaluations, ingest, jobs, queries, review
from ..exports import render_worksheet_pdf
from ..ids import new_id, sha256_hex
from ..money import fmt
from .core import Api, Problem, mask_name, problem_response


def claim_view(conn, p, claim_id: str, full: bool = True) -> dict:
    c = conn.fetch_one(
        "SELECT c.*, m.full_name, m.gender, m.dob, h.name AS hospital_name, h.is_network, pm.base_sum_insured_paise, pm.cumulative_bonus_paise,"
        " e.recommendation, e.recommended_payable_paise, e.status AS evaluation_status, e.billed_total_paise"
        " FROM claim c JOIN member m ON m.tenant_id=c.tenant_id AND m.member_id=c.member_id"
        " JOIN policy_member pm ON pm.tenant_id=c.tenant_id AND pm.policy_no=c.policy_no AND pm.member_id=c.member_id"
        " LEFT JOIN hospital h ON h.tenant_id=c.tenant_id AND h.hospital_id=c.hospital_id"
        " LEFT JOIN evaluation e ON e.tenant_id=c.tenant_id AND e.evaluation_id=c.current_evaluation_id"
        " WHERE c.tenant_id=$1 AND c.claim_id=$2", p.tenant_id, claim_id)
    if not c:
        raise Problem(404, "claim-not-found", "claim not found")
    blocking = conn.fetch_val("SELECT count(*) FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND blocking AND status IN ('OPEN','ACKNOWLEDGED')",
                              p.tenant_id, claim_id)
    wf = configs.effective(conn, p.tenant_id, "WORKFLOW_CONFIG", date.today()) or {}
    tat = (wf.get("tat") or {}).get(c["workflow"], {})
    from ..tat import deadline
    due = deadline(c,wf)
    show_name = "READ_ONLY" not in p.roles or len(p.roles) > 1
    out = {
        "claim_id": c["claim_id"], "external_ref": c["external_ref"], "workflow": c["workflow"], "status": c["status"],
        "parent_claim_id":c.get("parent_claim_id"),"cashless_root_id":c.get("cashless_root_id"),
        "recommendation": c["recommendation"], "recommended_payable": fmt(c["recommended_payable_paise"]),
        "open_blocking_findings": blocking, "sla_due_at": due, "assigned_to": c["assigned_to"],
        "patient_display": mask_name(c["full_name"]), "hospital_name": c["hospital_name"],
    }
    if full:
        pending = conn.fetch_all("SELECT approval_request_id, evaluation_id, proposed_disposition, proposed_payable_paise, requested_by, approver, triggers, state"
                                 " FROM approval_request WHERE tenant_id=$1 AND claim_id=$2 ORDER BY decided_at NULLS FIRST", p.tenant_id, claim_id)
        decs = conn.fetch_all("SELECT decision_id, disposition, approved_payable_paise, decided_by, second_approver, decided_at, evaluation_id FROM decision"
                              " WHERE tenant_id=$1 AND claim_id=$2 ORDER BY decided_at", p.tenant_id, claim_id)
        out.update({
            "policy_no": c["policy_no"], "member_id": c["member_id"], "hospital_id": c["hospital_id"], "hospital_is_network": c["is_network"],
            "admission_date": c["admission_date"], "discharge_date": c["discharge_date"], "current_evaluation_id": c["current_evaluation_id"],
            "evaluation_status": c["evaluation_status"], "billed_total": fmt(c["billed_total_paise"]),
            "patient": {"name": c["full_name"] if show_name else mask_name(c["full_name"]), "gender": c["gender"], "dob": c["dob"] if show_name else None},
            "sum_insured": {"base": fmt(c["base_sum_insured_paise"]), "cumulative_bonus": fmt(c["cumulative_bonus_paise"])},
            "tat": {"clock_start": tat.get("clock_start"), "submitted_at": c["submitted_at"], "intimated_at": c["intimated_at"], "due_at": due,
                    "interest_from": tat.get("interest_from")},
            "investigation_hold": c["investigation_hold"], "row_version": c["row_version"],
            "approval_requests": [{**a, "proposed_payable": fmt(a.pop("proposed_payable_paise"))} for a in pending],
            "decisions": [{**d, "approved_payable": fmt(d.pop("approved_payable_paise"))} for d in decs],
        })
    return out


def doc_view(d: dict) -> dict:
    return {k: d.get(k) for k in ("document_id", "declared_type", "classified_type", "status", "page_count", "sha256", "supersedes_document_id", "received_at")}


def register(api: Api):
    ctx = api.ctx

    # ------------------------------------------------------------------ me and claims
    @api.op("getMe", "/v1/me", "GET")
    def h_me(conn, p, req, body):
        u = conn.fetch_one("SELECT display_name FROM app_user WHERE tenant_id=$1 AND user_id=$2", p.tenant_id, p.user_id)
        return 200, {"user_id": p.user_id, "tenant_id": p.tenant_id, "display_name": u["display_name"], "roles": sorted(p.roles),
                     "approval_limit": fmt(p.approval_limit_paise)}, None

    @api.op("createClaim", "/v1/claims", "POST")
    def h_create_claim(conn, p, req, body):
        p.require("claim.create")
        c = ingest.create_claim(conn, p.tenant_id, body, p.actor)
        return 201, claim_view(conn, p, c["claim_id"]), api.etag(conn, p, c["claim_id"])

    @api.op("listClaims", "/v1/claims", "GET")
    def h_list_claims(conn, p, req, body):
        p.require("claim.view")
        q = req.query_params
        sql, args = "SELECT claim_id FROM claim WHERE tenant_id=$1", [p.tenant_id]
        for col in ("status", "workflow", "assigned_to"):
            if col=="assigned_to" and q.get(col)=="UNASSIGNED":
                sql+=" AND assigned_to IS NULL";continue
            if q.get(col):
                args.append(q[col])
                sql += f" AND {col}{'::text' if col != 'assigned_to' else ''} = ${len(args)}"
        if q.get("search"):
            args.append("%"+q["search"][:128]+"%")
            sql+=f" AND (claim_id ILIKE ${len(args)} OR external_ref ILIKE ${len(args)})"
        if not q.get("status"):
            sql += " AND status NOT IN ('EXPORTED','WITHDRAWN','FINALISED')"
        ids = [r["claim_id"] for r in conn.fetch_all(sql, *args)]
        items = [claim_view(conn, p, cid, full=False) for cid in ids]
        if q.get("sla_breach_within_minutes"):
            limit_t = datetime.now(timezone.utc) + timedelta(minutes=int(q["sla_breach_within_minutes"]))
            items = [i for i in items if i["sla_due_at"] and i["sla_due_at"] <= limit_t]
        items.sort(key=lambda i: (i["sla_due_at"] is None, i["sla_due_at"] or datetime.max.replace(tzinfo=timezone.utc), i["claim_id"]))
        try:
            limit = max(1,min(int(q.get("limit", 50)), 200))
            start = max(0,int(base64.urlsafe_b64decode(q["cursor"]).decode())) if q.get("cursor") else 0
        except (ValueError,TypeError):raise Problem(422,"invalid-pagination","valid limit and cursor required")
        page = items[start:start + limit]
        nxt = base64.urlsafe_b64encode(str(start + limit).encode()).decode() if start + limit < len(items) else None
        return 200, {"items": page, "next_cursor": nxt}, None

    @api.op("getClaim", "/v1/claims/{claim_id}", "GET")
    def h_get_claim(conn, p, req, body):
        p.require("claim.view")
        cid = req.path_params["claim_id"]
        if req.query_params.get("record_view") == "1":
            audit.append(conn, p.tenant_id, cid, p.actor, "REVIEWER_VIEWED_RECOMMENDATION", {})
        return 200, claim_view(conn, p, cid), api.etag(conn, p, cid)

    def _claim_cmd(action):
        def h(conn, p, req, body):
            cid = req.path_params["claim_id"]
            c = ingest.get_claim(conn, p.tenant_id, cid)
            if not c:
                raise Problem(404, "claim-not-found", "claim not found")
            if action == "assign":
                p.require("claim.assign")
                from ..auth import load_principal
                assignee=load_principal(conn,p.tenant_id,body["assignee_user_id"])
                if not assignee.roles & {"PROCESSOR","MEDICAL_OFFICER","SUPERVISOR"}:
                    raise Problem(422,"invalid-assignee","active reviewer role required")
                if c["status"] in ("FINALISED","EXPORTED","WITHDRAWN"):
                    raise Problem(409,"claim-closed","closed claims cannot be assigned")
                conn.execute("UPDATE claim SET assigned_to=$3, status=CASE WHEN status='READY_FOR_REVIEW' THEN 'IN_REVIEW'::claim_status ELSE status END,"
                             " row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, cid, body["assignee_user_id"])
                audit.append(conn, p.tenant_id, cid, p.actor, "CLAIM_ASSIGNED", {"assignee": body["assignee_user_id"]})
            elif action == "withdraw":
                p.require("claim.withdraw")
                if c["status"] in ("FINALISED", "EXPORTED", "WITHDRAWN"):
                    raise Problem(409, "claim-closed", f"claim is {c['status']}")
                conn.execute("UPDATE claim SET status='WITHDRAWN', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, cid)
                audit.append(conn, p.tenant_id, cid, p.actor, "CLAIM_WITHDRAWN", {"reason": body["reason"]})
            elif action == "reopen":
                p.require("claim.reopen")
                if c["status"] not in ("FINALISED", "EXPORTED"):
                    raise Problem(409, "not-final", "only finalised or exported claims can be reopened")
                if conn.fetch_one("SELECT 1 FROM claim WHERE tenant_id=$1 AND parent_claim_id=$2 AND status<>'WITHDRAWN'",p.tenant_id,cid):raise Problem(409,'cashless-stage-continued','reopen the latest cashless stage instead')
                conn.execute("UPDATE claim SET status='REOPENED', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, cid)
                conn.execute("INSERT INTO si_ledger_entry (tenant_id,policy_no,member_id,policy_year_start,claim_id,entry_kind,amount_paise) SELECT tenant_id,policy_no,member_id,policy_year_start,claim_id,'RELEASED',sum(CASE WHEN entry_kind='RESERVED' THEN amount_paise WHEN entry_kind='RELEASED' THEN -amount_paise ELSE 0 END) FROM si_ledger_entry WHERE tenant_id=$1 AND claim_id=$2 GROUP BY tenant_id,policy_no,member_id,policy_year_start,claim_id HAVING sum(CASE WHEN entry_kind='RESERVED' THEN amount_paise WHEN entry_kind='RELEASED' THEN -amount_paise ELSE 0 END)>0",p.tenant_id,cid)
                audit.append(conn, p.tenant_id, cid, p.actor, "CLAIM_REOPENED", {"reason": body["reason"]})
                jobs.enqueue(conn, p.tenant_id, "EVALUATE", cid, f"evaluate:{cid}:reopen:{new_id('R')}", {"trigger": "MANUAL_RERUN"})
            return 200, claim_view(conn, p, cid), api.etag(conn, p, cid)
        return h

    api.op("assignClaim", "/v1/claims/{claim_id}:assign", "POST", claim_scoped=True)(_claim_cmd("assign"))
    api.op("withdrawClaim", "/v1/claims/{claim_id}:withdraw", "POST", claim_scoped=True)(_claim_cmd("withdraw"))
    api.op("reopenClaim", "/v1/claims/{claim_id}:reopen", "POST", claim_scoped=True)(_claim_cmd("reopen"))

    # ------------------------------------------------------------------ documents
    @api.op("createDocumentUpload", "/v1/claims/{claim_id}/documents", "POST")
    def h_create_upload(conn, p, req, body):
        p.require("document.upload")
        cid = req.path_params["claim_id"]
        if not ingest.get_claim(conn, p.tenant_id, cid):
            raise Problem(404, "claim-not-found", "claim not found")
        dup = conn.fetch_one("SELECT * FROM document WHERE tenant_id=$1 AND claim_id=$2 AND sha256=$3", p.tenant_id, cid, body["sha256"])
        if dup:
            return 200, doc_view(dup), None
        upload_id = new_id("UPL")
        slot = {"claim_id": cid, "tenant_id": p.tenant_id, **body, "upload_id": upload_id, "actor": p.actor,
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}
        ctx.store.put_once(f"staging/{p.tenant_id}/{upload_id}.json", json.dumps(slot).encode())
        return 201, {"document_id": upload_id, "upload_url": api.sign(f"/v1/uploads/{upload_id}", p.tenant_id, 1800), "expires_at": slot["expires_at"]}, None

    @api.raw("/v1/uploads/{upload_id}", "PUT", "putUpload")
    async def put_upload(request: Request):
        try:
            tenant = api.verify_signed(request)
        except Problem as e:
            return problem_response(e, request.url.path)
        upload_id = request.path_params["upload_id"]
        try:
            slot = json.loads(await run_in_threadpool(ctx.store.get, f"staging/{tenant}/{upload_id}.json"))
        except FileNotFoundError:
            return Response(status_code=404)
        limit = min(ingest.MAX_BYTES, slot["size_bytes"])
        received = bytearray()
        async for chunk in request.stream():
            if len(received) + len(chunk) > limit:
                return problem_response(Problem(413,"upload-too-large","upload exceeds declared or permitted size"),request.url.path)
            received.extend(chunk)
        data = bytes(received)
        if len(data) != slot['size_bytes'] or sha256_hex(data) != slot['sha256']:
            return problem_response(Problem(422,'hash-mismatch','uploaded bytes do not match declared size and SHA-256'),request.url.path)

        def _store():
            key = f"staging/{tenant}/bytes/{upload_id}"
            if ctx.store.exists(key):
                return Response(status_code=200)
            ctx.store.put_once(key, data)
            return Response(status_code=201)
        return await run_in_threadpool(_store)

    @api.op("completeDocumentUpload", "/v1/claims/{claim_id}/documents/{document_id}:complete", "POST")
    def h_complete_upload(conn, p, req, body):
        p.require("document.upload")
        cid, upload_id = req.path_params["claim_id"], req.path_params["document_id"]
        try:
            slot = json.loads(ctx.store.get(f"staging/{p.tenant_id}/{upload_id}.json"))
            data = ctx.store.get(f"staging/{p.tenant_id}/bytes/{upload_id}")
        except FileNotFoundError:
            raise Problem(422, "upload-missing", "upload the file to upload_url first")
        if slot["claim_id"] != cid:
            raise Problem(404, "upload-not-found", "upload slot does not belong to this claim")
        if sha256_hex(data) != slot["sha256"] or len(data) != slot["size_bytes"]:
            raise Problem(422, "hash-mismatch", "uploaded bytes do not match the declared SHA-256 and size")
        if data[:4] == b"PK\x03\x04":
            from ..bundles import unpack
            try:
                members = unpack(data)
            except (ValueError, OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError):
                raise Problem(422, "unsafe-bundle", "archive is corrupt, unsafe or unsupported")
            if slot.get("supersedes_document_id"):
                raise Problem(422, "bundle-supersede", "upload replacement documents individually")
            documents = [ingest.add_document(conn, ctx.store, p.tenant_id, cid, payload,
                         declared_type=slot["declared_type"], source_channel="API", actor=p.actor, filename=name)
                         for name, payload in members]
            return 202, {"items": [doc_view(d) for d in documents]}, None
        d = ingest.add_document(conn, ctx.store, p.tenant_id, cid, data, declared_type=slot["declared_type"], source_channel="API",
                                actor=p.actor, supersedes_document_id=slot.get("supersedes_document_id"))
        return 202, doc_view(d), None

    @api.op("listDocuments", "/v1/claims/{claim_id}/documents", "GET")
    def h_list_documents(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT * FROM document WHERE tenant_id=$1 AND claim_id=$2 AND status <> 'QUARANTINED' ORDER BY received_at",
                              p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": [doc_view(r) for r in rows], "next_cursor": None}, None

    @api.op("getPage", "/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}", "GET")
    def h_get_page(conn, p, req, body):
        p.require("claim.view")
        cid, did, n = req.path_params["claim_id"], req.path_params["document_id"], int(req.path_params["page_no"])
        pg = conn.fetch_one("SELECT dp.* FROM document_page dp JOIN document d ON d.tenant_id=dp.tenant_id AND d.document_id=dp.document_id"
                            " WHERE dp.tenant_id=$1 AND dp.document_id=$2 AND dp.page_no=$3 AND d.claim_id=$4 AND d.status <> 'QUARANTINED'",
                            p.tenant_id, did, n, cid)
        if not pg:
            raise Problem(404, "page-not-found", "page not found")
        base = f"/v1/claims/{cid}/documents/{did}/pages/{n}"
        return 200, {"image_url": api.sign(base + "/image", p.tenant_id), "image_sha256": sha256_hex(ctx.store.get(pg["image_key"])), "words_url": api.sign(base + "/words", p.tenant_id) if pg["text_key"] else None,
                     "text_layer": pg["text_layer"], "quality_score": float(pg["quality_score"]) if pg["quality_score"] is not None else None,
                     "width_pt": float(pg["width_pt"]) if pg["width_pt"] else None, "height_pt": float(pg["height_pt"]) if pg["height_pt"] else None}, None

    def page_asset(kind: str):
        async def endpoint(request: Request):
            try:
                tenant = api.verify_signed(request)
            except Problem as e:
                return problem_response(e, request.url.path)
            did, n = request.path_params["document_id"], int(request.path_params["page_no"])

            def _get():
                with ctx.db.tenant_tx(tenant) as c:
                    r = c.fetch_one("SELECT image_key, text_key FROM document_page WHERE tenant_id=$1 AND document_id=$2 AND page_no=$3", tenant, did, n)
                key = r and (r["image_key"] if kind == "image" else r["text_key"])
                return ctx.store.get(key) if key else None
            data = await run_in_threadpool(_get)
            if data is None:
                return Response(status_code=404)
            return Response(data, media_type="image/png" if kind == "image" else "application/json",
                            headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})
        return endpoint

    api.raw("/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}/image", "GET", "getPageImage")(page_asset("image"))
    api.raw("/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}/words", "GET", "getPageWords")(page_asset("words"))

    @api.op("confirmDocumentReading", "/v1/claims/{claim_id}/documents/{document_id}/reading-confirmations", "POST", claim_scoped=True)
    def h_confirm_reading(conn, p, req, body):
        from ..extraction.manual import confirm
        return 201, confirm(conn, ctx, p, req.path_params["claim_id"], req.path_params["document_id"], body), api.etag(conn,p,req.path_params["claim_id"])

    # ------------------------------------------------------------------ evaluations
    @api.op("requestEvaluation", "/v1/claims/{claim_id}/evaluations", "POST", claim_scoped=True)
    def h_request_evaluation(conn, p, req, body):
        p.require("fact.correct")
        cid = req.path_params["claim_id"]
        ingest.mark_stale(conn, p.tenant_id, cid, p.actor, (body or {}).get("trigger", "MANUAL_RERUN"))
        job = jobs.enqueue(conn, p.tenant_id, "EVALUATE", cid, f"evaluate:{cid}:manual:{new_id('R')}", {"trigger": (body or {}).get("trigger", "MANUAL_RERUN")})
        return 202, {"job_id": job, "status": "QUEUED"}, None

    @api.op("getCurrentEvaluation", "/v1/claims/{claim_id}/evaluations/current", "GET")
    def h_current_evaluation(conn, p, req, body):
        p.require("claim.view")
        ev = evaluations.current(conn, p.tenant_id, req.path_params["claim_id"])
        if not ev or not ev["result"]:
            raise Problem(404, "no-evaluation", "no evaluation yet")
        view = evaluations.api_view(conn, p.tenant_id, ev)
        view["status"] = ev["status"]
        view["supersedes_evaluation_id"] = ev["supersedes_evaluation_id"]
        return 200, view, None

    @api.op("getEvaluation", "/v1/claims/{claim_id}/evaluations/{evaluation_id}", "GET")
    def h_get_evaluation(conn, p, req, body):
        p.require("claim.view")
        ev = conn.fetch_one("SELECT * FROM evaluation WHERE tenant_id=$1 AND claim_id=$2 AND evaluation_id=$3", p.tenant_id,
                            req.path_params["claim_id"], req.path_params["evaluation_id"])
        if not ev:
            raise Problem(404, "evaluation-not-found", "evaluation not found")
        if ev["status"] == "FAILED":
            return 200, {"evaluation_id": ev["evaluation_id"], "status": "FAILED", "error_code": ev["error_code"], "error_detail": ev["error_detail"]}, None
        view = evaluations.api_view(conn, p.tenant_id, ev)
        view["status"] = ev["status"]
        return 200, view, None

    @api.op("diffEvaluations", "/v1/claims/{claim_id}/evaluations/{evaluation_id}/diff", "GET")
    def h_diff(conn, p, req, body):
        p.require("claim.view")
        cid, eid = req.path_params["claim_id"], req.path_params["evaluation_id"]
        ev = conn.fetch_one("SELECT supersedes_evaluation_id FROM evaluation WHERE tenant_id=$1 AND claim_id=$2 AND evaluation_id=$3", p.tenant_id, cid, eid)
        if not ev:
            raise Problem(404, "evaluation-not-found", "evaluation not found")
        against = req.query_params.get("against") or ev["supersedes_evaluation_id"]
        if not against:
            return 200, {"facts": [], "adjustments": [], "findings": [], "payable_before": None, "payable_after": None, "note": "first evaluation"}, None
        d = evaluations.diff(conn, p.tenant_id, cid, against, eid)
        return 200, {"facts": [], "adjustments": [{"key": k, "change": c} for c, ks in (("added", d["adjustments_added"]), ("removed", d["adjustments_removed"]),
                                                                                   ("changed", d["adjustments_changed"])) for k in ks],
                     "findings": [{"kind": k, "change": "added"} for k in d["findings_added"]] + [{"kind": k, "change": "removed"} for k in d["findings_removed"]],
                     "payable_before": d["recommended_payable"]["from"], "payable_after": d["recommended_payable"]["to"], "detail": d}, None

    # ------------------------------------------------------------------ review
    @api.op("listFacts", "/v1/claims/{claim_id}/facts", "GET")
    def h_facts(conn, p, req, body):
        p.require("claim.view")
        cid = req.path_params["claim_id"]
        resolved = conn.fetch_all("SELECT field_path, value, basis, source_fact_ids, reviewer_action_id, created_at FROM resolved_fact"
                                  " WHERE tenant_id=$1 AND claim_id=$2 AND is_active ORDER BY field_path", p.tenant_id, cid)
        obs = conn.fetch_all("SELECT f.fact_id, f.field_path, f.raw_value, f.normalised_value, f.confidence, f.evidence, f.grounding_check, d.classified_type, d.status AS document_status"
                             " FROM extracted_fact f JOIN extraction_run r ON r.tenant_id=f.tenant_id AND r.extraction_run_id=f.extraction_run_id"
                             " JOIN document d ON d.tenant_id=r.tenant_id AND d.document_id=r.document_id"
                             " WHERE f.tenant_id=$1 AND f.claim_id=$2 AND f.field_path <> 'bill.line_item' ORDER BY f.field_path, d.received_at", p.tenant_id, cid)
        by = {}
        for o in obs:
            by.setdefault(o["field_path"], []).append({**o, "confidence": float(o["confidence"]) if o["confidence"] is not None else None})
        return 200, {"items": [{**r, "observations": by.get(r["field_path"], [])} for r in resolved],
                     "other_observations": {k: v for k, v in by.items() if k not in {r["field_path"] for r in resolved}}}, None

    @api.op("listBillLines", "/v1/claims/{claim_id}/bill-lines", "GET")
    def h_bill_lines(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT * FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active ORDER BY line_no", p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": [{**{k: r[k] for k in ("bill_line_id", "bill_version", "line_no", "description", "category", "category_source", "ward_context",
                                                       "room_category", "service_date", "invoice_no", "evidence")},
                                 "category_confidence": float(r["category_confidence"]) if r["category_confidence"] is not None else None,
                                 "quantity": str(r["quantity"].normalize()), "unit_rate": fmt(r["unit_rate_paise"]), "billed": fmt(r["billed_paise"])} for r in rows]}, None

    @api.op("listFindings", "/v1/claims/{claim_id}/findings", "GET")
    def h_findings(conn, p, req, body):
        p.require("claim.view")
        sql, args = "SELECT * FROM finding WHERE tenant_id=$1 AND claim_id=$2", [p.tenant_id, req.path_params["claim_id"]]
        for col in ("status", "category"):
            if req.query_params.get(col):
                args.append(req.query_params[col])
                sql += f" AND {col}::text = ${len(args)}"
        rows = conn.fetch_all(sql + " ORDER BY blocking DESC, severity DESC, finding_id", *args)
        return 200, {"items": [{k: v for k, v in r.items() if k not in ("tenant_id", "subject_key")} for r in rows]}, None

    @api.op("recordReviewerAction", "/v1/claims/{claim_id}/reviewer-actions", "POST", claim_scoped=True)
    def h_reviewer_action(conn, p, req, body):
        cid = req.path_params["claim_id"]
        out = review.record(conn, p, cid, body)
        return 201, out, api.etag(conn, p, cid)

    # ------------------------------------------------------------------ queries
    @api.op("draftQuery", "/v1/claims/{claim_id}/queries", "POST")
    def h_draft_query(conn, p, req, body):
        p.require("query.draft")
        cid = req.path_params["claim_id"]
        claim=conn.fetch_one("SELECT status FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE",p.tenant_id,cid)
        if not claim:raise Problem(404,"claim-not-found","claim not found")
        if claim["status"] in ("FINALISED","EXPORTED","WITHDRAWN"):raise Problem(409,"claim-closed","reopen before drafting a query")
        qid = new_id("QRY")
        conn.execute("INSERT INTO query_letter (tenant_id, query_id, claim_id, addressed_to, status, due_at) VALUES ($1,$2,$3,$4,'DRAFT', now() + interval '7 days')",
                     p.tenant_id, qid, cid, body["addressed_to"])
        items = []
        for it in body["items"]:
            qi = new_id("QIT")
            conn.execute("INSERT INTO query_item (tenant_id, query_item_id, query_id, requested_document_type, text, linked_finding_ids, addressed_to)"
                         " VALUES ($1,$2,$3,$4,$5,$6::text[],$7)", p.tenant_id, qi, qid, it.get("requested_document_type"), it["text"],
                         it.get("linked_finding_ids", []), body["addressed_to"])
            items.append({"query_item_id": qi, "text": it["text"]})
        audit.append(conn, p.tenant_id, cid, p.actor, "QUERY_DRAFTED", {"letters": [qid], "items": len(items)})
        return 201, {"query_id": qid, "addressed_to": body["addressed_to"], "status": "DRAFT", "items": items}, None

    @api.op("approveQuery", "/v1/queries/{query_id}:approve", "POST")
    def h_approve_query(conn, p, req, body):
        return 200, queries.approve(conn, p, req.path_params["query_id"]), None

    # ------------------------------------------------------------------ decisions
    @api.op("recordDecision", "/v1/claims/{claim_id}/decisions", "POST", claim_scoped=True)
    def h_decision(conn, p, req, body):
        cid = req.path_params["claim_id"]
        out = decisions.decide(conn, p, ctx.schema_dir, cid, body)
        return 201, out, api.etag(conn, p, cid)

    @api.op("requestApproval", "/v1/claims/{claim_id}/approval-requests", "POST", claim_scoped=True)
    def h_request_approval(conn, p, req, body):
        cid = req.path_params["claim_id"]
        return 201, decisions.request_approval(conn, p, cid, body), api.etag(conn, p, cid)

    @api.op("approveRequest", "/v1/approval-requests/{approval_request_id}:approve", "POST")
    def h_approve_request(conn, p, req, body):
        return 200, decisions.approve_request(conn, p, ctx.schema_dir, req.path_params["approval_request_id"], (body or {}).get("comment")), None

    @api.op("returnRequest", "/v1/approval-requests/{approval_request_id}:return", "POST")
    def h_return_request(conn, p, req, body):
        return 200, decisions.return_request(conn, p, req.path_params["approval_request_id"], body["comment"]), None

    @api.op("getWorksheet", "/v1/claims/{claim_id}/decisions/{decision_id}/worksheet", "GET")
    def h_worksheet(conn, p, req, body):
        p.require("claim.view")
        d = conn.fetch_one("SELECT worksheet FROM decision WHERE tenant_id=$1 AND claim_id=$2 AND decision_id=$3", p.tenant_id,
                           req.path_params["claim_id"], req.path_params["decision_id"])
        if not d or not d["worksheet"]:
            raise Problem(404, "worksheet-not-found", "no worksheet for this decision")
        if "application/pdf" in req.headers.get("accept", "") or req.query_params.get("format") == "pdf":
            return 200, Response(render_worksheet_pdf(d["worksheet"]), media_type="application/pdf",
                                 headers={"Content-Disposition": f'inline; filename="{d["worksheet"]["worksheet_id"]}.pdf"'}), None
        return 200, d["worksheet"], None

    @api.op("listExports", "/v1/claims/{claim_id}/exports", "GET")
    def h_exports(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT export_id, decision_id, target, state, target_reference FROM export_record WHERE tenant_id=$1 AND claim_id=$2",
                              p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": rows}, None

    @api.op("listAuditEvents", "/v1/claims/{claim_id}/audit-events", "GET")
    def h_audit(conn, p, req, body):
        p.require("claim.view")
        cid = req.path_params["claim_id"]
        rows = conn.fetch_all("SELECT seq, occurred_at, actor_kind, actor_id, event_type, payload, prev_hash, event_hash FROM audit_event"
                              " WHERE tenant_id=$1 AND claim_id=$2 ORDER BY seq", p.tenant_id, cid)
        items = [{"seq": r["seq"], "occurred_at": r["occurred_at"], "actor": "SYSTEM" if r["actor_kind"] == "SYSTEM" else f"{r['actor_kind']}:{r['actor_id']}",
                  "event_type": r["event_type"], "payload": r["payload"], "prev_hash": r["prev_hash"], "event_hash": r["event_hash"]} for r in rows]
        return 200, {"items": items, "next_cursor": None, "verification": audit.verify_chain(conn, p.tenant_id, cid)}, None

    @api.op('getClaimJobs','/v1/claims/{claim_id}/jobs','GET')
    def h_jobs(conn,p,req,body):
        p.require('claim.view');claim_view(conn,p,req.path_params['claim_id'])
        return 200,{'items':conn.fetch_all('SELECT job_id,job_kind,state,attempts,max_attempts,last_error_code,run_after,finished_at FROM processing_job WHERE tenant_id=$1 AND (subject_id=$2 OR subject_id IN (SELECT document_id FROM document WHERE tenant_id=$1 AND claim_id=$2)) ORDER BY created_at',p.tenant_id,req.path_params['claim_id'])},None
