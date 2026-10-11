"""HTTP API (Starlette), implementing pack/api/openapi.yaml.

Cross-cutting behaviour (05 §2):
  * auth: Bearer token -> principal; roles and limits come from the database on every request
  * errors: RFC 9457 problem details (application/problem+json) with a JSON-pointer error list
  * Idempotency-Key and If-Match are required exactly where the OpenAPI document requires them
  * idempotency: same key + same body -> original response; same key + different body -> 409
  * concurrency: claim-scoped writes compare If-Match with the claim's row_version (ETag "rv-<n>") -> 412 when stale
  * request bodies are validated against the OpenAPI schemas before any handler runs
Page images are served through short-lived signed URLs (the development stand-in for S3 pre-signed URLs).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .. import audit, auth, configs, decisions, evaluations, ingest, jobs, queries, review
from ..db import Json, PgError
from ..exports import render_worksheet_pdf
from ..ids import new_id, sha256_hex
from ..money import fmt, from_paise, to_paise
from .contract import Contract

log = logging.getLogger("aw.api")
PROBLEM_BASE = "https://aw.example.invalid/problems/"
WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str, errors: list | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.status, self.code, self.detail, self.errors, self.extra = status, code, detail, errors or [], extra or {}


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(type(o))


def jresp(payload, status: int = 200, headers: dict | None = None) -> Response:
    return Response(json.dumps(payload, default=_json_default, ensure_ascii=False), status_code=status, headers=headers or {},
                    media_type="application/json")


def problem_response(p: Problem, instance: str) -> Response:
    body = {"type": PROBLEM_BASE + p.code, "title": p.code.replace("-", " "), "status": p.status, "detail": p.detail, "instance": instance}
    if p.errors:
        body["errors"] = p.errors
    body.update(p.extra)
    return Response(json.dumps(body, default=_json_default), status_code=p.status, media_type="application/problem+json")


def _mask(name: str) -> str:
    parts = name.split()
    if not parts:
        return ""
    first = parts[0][0] + "."
    last = parts[-1]
    return f"{first} {last[0]}{'*' * max(1, len(last) - 2)}{last[-1]}" if len(last) > 2 else f"{first} {last}"


def create_app(ctx) -> Starlette:
    contract = Contract(ctx.settings.pack_dir)
    secret = ctx.settings.dev_token_secret or ""

    # ------------------------------------------------------------------ plumbing
    def principal_of(request: Request) -> auth.Principal:
        authz = request.headers.get("authorization", "")
        if not authz.lower().startswith("bearer "):
            raise Problem(401, "unauthenticated", "Bearer token required")
        try:
            user_id, tenant_id = auth.verify_dev_token(secret, authz[7:].strip())
            with ctx.db.tenant_tx(tenant_id) as c:
                return auth.load_principal(c, tenant_id, user_id)
        except auth.AuthError as e:
            raise Problem(401, "unauthenticated", str(e))

    def _mac(path: str, tenant: str, exp: int) -> str:
        return base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{path}|{tenant}|{exp}".encode(), hashlib.sha256).digest()).decode().rstrip("=")

    def sign(path: str, tenant: str, ttl: int = 300) -> str:
        exp = int(time.time()) + ttl
        return f"{path}?t={tenant}&exp={exp}&sig={_mac(path, tenant, exp)}"

    def verify_signed(request: Request) -> str:
        """Returns the tenant the URL was issued for. Authorisation happened when the URL was issued (like an S3 pre-signed URL)."""
        tenant, exp, sig = request.query_params.get("t", ""), request.query_params.get("exp", "0"), request.query_params.get("sig", "")
        if not exp.isdigit() or not hmac.compare_digest(_mac(request.url.path, tenant, int(exp)), sig) or int(exp) < time.time():
            raise Problem(403, "bad-signature", "link expired or invalid")
        return tenant

    def operation(operation_id: str | None, fn, *, claim_scoped: bool = False, auth_required: bool = True):
        async def endpoint(request: Request):
            raw = await request.body()
            return await run_in_threadpool(_handle, request, raw)

        def _handle(request: Request, raw: bytes):
            try:
                body = None
                if raw and request.headers.get("content-type", "").startswith("application/json"):
                    try:
                        body = json.loads(raw)
                    except json.JSONDecodeError as e:
                        raise Problem(400, "bad-json", f"request body is not valid JSON: {e.msg}")
                if operation_id:
                    for h in contract.required_headers(operation_id):
                        if not request.headers.get(h):
                            raise Problem(428 if h == "If-Match" else 400, "missing-header", f"{h} header is required")
                    if contract.ops[operation_id]["validator"] is not None:
                        errs = contract.validate(operation_id, body if body is not None else {})
                        if errs:
                            raise Problem(422, "validation-failed", "request does not match the API contract", errs)
                p = principal_of(request) if auth_required else None
                idem = request.headers.get("idempotency-key")
                with (ctx.db.tenant_tx(p.tenant_id) if p else _nullctx()) as conn:
                    if idem and p and request.method == "POST":
                        req_hash = sha256_hex(request.method.encode() + request.url.path.encode() + raw)
                        conn.execute("SAVEPOINT idem")
                        try:
                            conn.execute("INSERT INTO idempotency_key (tenant_id, key, request_sha256, expires_at) VALUES ($1,$2,$3, now() + interval '24 hours')",
                                         p.tenant_id, idem, req_hash)
                            conn.execute("RELEASE SAVEPOINT idem")
                        except PgError as e:
                            conn.execute("ROLLBACK TO SAVEPOINT idem")
                            if e.sqlstate != "23505":
                                raise
                            prev = conn.fetch_one("SELECT request_sha256, response_status, response_body FROM idempotency_key WHERE tenant_id=$1 AND key=$2",
                                                  p.tenant_id, idem)
                            if prev["request_sha256"] != req_hash:
                                raise Problem(409, "idempotency-key-reused", "this Idempotency-Key was used with a different request")
                            if prev["response_status"] is None:
                                raise Problem(409, "request-in-progress", "a request with this Idempotency-Key is still being processed")
                            return jresp(prev["response_body"], prev["response_status"], {"Idempotent-Replay": "true"})
                    if claim_scoped and request.headers.get("if-match"):
                        rv = conn.fetch_val("SELECT row_version FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE",
                                            p.tenant_id, request.path_params["claim_id"])
                        if rv is None:
                            raise Problem(404, "claim-not-found", "claim not found")
                        if request.headers["if-match"].strip('W/"') != f"rv-{rv}":
                            raise Problem(412, "precondition-failed", "claim changed since you loaded it; reload", extra={"current_etag": f'"rv-{rv}"'})
                    status, payload, headers = fn(conn, p, request, body)
                    if idem and p and request.method == "POST" and isinstance(payload, (dict, list)):
                        conn.execute("UPDATE idempotency_key SET response_status=$3, response_body=$4::jsonb WHERE tenant_id=$1 AND key=$2",
                                     p.tenant_id, idem, status, Json(json.loads(json.dumps(payload, default=_json_default))))
                if isinstance(payload, Response):
                    return payload
                return jresp(payload, status, headers)
            except Problem as e:
                return problem_response(e, request.url.path)
            except (ingest.IngestError, review.ReviewError, queries.QueryError) as e:
                return problem_response(Problem(e.status, e.code, str(e)), request.url.path)
            except decisions.DecisionError as e:
                return problem_response(Problem(e.status, e.code, str(e), extra=e.extra), request.url.path)
            except configs.ConfigError as e:
                return problem_response(Problem(422, "configuration-invalid", str(e), [{"pointer": x.split(":")[0], "message": x} for x in e.errors]), request.url.path)
            except auth.Forbidden as e:
                return problem_response(Problem(403, "forbidden", str(e)), request.url.path)
            except PgError as e:
                if e.sqlstate == "23505":
                    return problem_response(Problem(409, "conflict", "a record with the same key already exists"), request.url.path)
                if e.sqlstate in ("23514", "23502", "22P02", "23503"):
                    return problem_response(Problem(422, "constraint-violated", f"rejected by a data rule ({e.constraint or e.sqlstate})"), request.url.path)
                log.exception("database error")
                return problem_response(Problem(500, "internal", "unexpected database error"), request.url.path)
            except Exception:  # noqa: BLE001
                log.exception("unhandled error")
                return problem_response(Problem(500, "internal", "unexpected error"), request.url.path)
        return endpoint

    # ------------------------------------------------------------------ views
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
        due = None
        if c["submitted_at"] and tat.get("due_days"):
            due = c["submitted_at"] + timedelta(days=tat["due_days"])
        show_name = "READ_ONLY" not in p.roles or len(p.roles) > 1
        out = {
            "claim_id": c["claim_id"], "external_ref": c["external_ref"], "workflow": c["workflow"], "status": c["status"],
            "recommendation": c["recommendation"], "recommended_payable": fmt(c["recommended_payable_paise"]),
            "open_blocking_findings": blocking, "sla_due_at": due, "assigned_to": c["assigned_to"],
            "patient_display": _mask(c["full_name"]), "hospital_name": c["hospital_name"],
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
                "patient": {"name": c["full_name"] if show_name else _mask(c["full_name"]), "gender": c["gender"], "dob": c["dob"] if show_name else None},
                "sum_insured": {"base": fmt(c["base_sum_insured_paise"]), "cumulative_bonus": fmt(c["cumulative_bonus_paise"])},
                "tat": {"clock_start": tat.get("clock_start"), "submitted_at": c["submitted_at"], "intimated_at": c["intimated_at"], "due_at": due,
                        "interest_from": tat.get("interest_from")},
                "investigation_hold": c["investigation_hold"], "row_version": c["row_version"],
                "approval_requests": [{**a, "proposed_payable": fmt(a.pop("proposed_payable_paise"))} for a in pending],
                "decisions": [{**d, "approved_payable": fmt(d.pop("approved_payable_paise"))} for d in decs],
            })
        return out

    def etag(conn, p, claim_id):
        return {"ETag": f'"rv-{conn.fetch_val("SELECT row_version FROM claim WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim_id)}"'}

    # ------------------------------------------------------------------ handlers
    def h_me(conn, p, req, body):
        u = conn.fetch_one("SELECT display_name FROM app_user WHERE tenant_id=$1 AND user_id=$2", p.tenant_id, p.user_id)
        return 200, {"user_id": p.user_id, "tenant_id": p.tenant_id, "display_name": u["display_name"], "roles": sorted(p.roles),
                     "approval_limit": fmt(p.approval_limit_paise)}, None

    def h_create_claim(conn, p, req, body):
        p.require("claim.create")
        c = ingest.create_claim(conn, p.tenant_id, body, p.actor)
        return 201, claim_view(conn, p, c["claim_id"]), etag(conn, p, c["claim_id"])

    def h_list_claims(conn, p, req, body):
        p.require("claim.view")
        q = req.query_params
        sql, args = "SELECT claim_id FROM claim WHERE tenant_id=$1", [p.tenant_id]
        for col in ("status", "workflow", "assigned_to"):
            if q.get(col):
                args.append(q[col])
                sql += f" AND {col}{'::text' if col != 'assigned_to' else ''} = ${len(args)}"
        if not q.get("status"):
            sql += " AND status NOT IN ('EXPORTED','WITHDRAWN','FINALISED')"
        ids = [r["claim_id"] for r in conn.fetch_all(sql, *args)]
        items = [claim_view(conn, p, cid, full=False) for cid in ids]
        if q.get("sla_breach_within_minutes"):
            limit_t = datetime.now(timezone.utc) + timedelta(minutes=int(q["sla_breach_within_minutes"]))
            items = [i for i in items if i["sla_due_at"] and i["sla_due_at"] <= limit_t]
        items.sort(key=lambda i: (i["sla_due_at"] is None, i["sla_due_at"] or datetime.max.replace(tzinfo=timezone.utc), i["claim_id"]))
        limit = min(int(q.get("limit", 50)), 200)
        start = int(base64.urlsafe_b64decode(q["cursor"]).decode()) if q.get("cursor") else 0
        page = items[start:start + limit]
        nxt = base64.urlsafe_b64encode(str(start + limit).encode()).decode() if start + limit < len(items) else None
        return 200, {"items": page, "next_cursor": nxt}, None

    def h_get_claim(conn, p, req, body):
        p.require("claim.view")
        cid = req.path_params["claim_id"]
        audit.append(conn, p.tenant_id, cid, p.actor, "REVIEWER_VIEWED_RECOMMENDATION", {}) if req.query_params.get("record_view") == "1" else None
        return 200, claim_view(conn, p, cid), etag(conn, p, cid)

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
        return 201, {"document_id": upload_id, "upload_url": sign(f"/v1/uploads/{upload_id}", p.tenant_id, 1800), "expires_at": slot["expires_at"]}, None

    async def put_upload(request: Request):
        try:
            tenant = verify_signed(request)
        except Problem as e:
            return problem_response(e, request.url.path)
        upload_id = request.path_params["upload_id"]
        data = await request.body()

        def _store():
            key = f"staging/{tenant}/bytes/{upload_id}"
            if ctx.store.exists(key):
                return Response(status_code=200)
            ctx.store.put_once(key, data)
            return Response(status_code=201)
        return await run_in_threadpool(_store)

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
        d = ingest.add_document(conn, ctx.store, p.tenant_id, cid, data, declared_type=slot["declared_type"], source_channel="API",
                                actor=p.actor, supersedes_document_id=slot.get("supersedes_document_id"))
        return 202, doc_view(d), None

    def doc_view(d: dict) -> dict:
        return {k: d.get(k) for k in ("document_id", "declared_type", "classified_type", "status", "page_count", "sha256", "supersedes_document_id", "received_at")}

    def h_list_documents(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT * FROM document WHERE tenant_id=$1 AND claim_id=$2 AND status <> 'QUARANTINED' ORDER BY received_at",
                              p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": [doc_view(r) for r in rows], "next_cursor": None}, None

    def h_get_page(conn, p, req, body):
        p.require("claim.view")
        cid, did, n = req.path_params["claim_id"], req.path_params["document_id"], int(req.path_params["page_no"])
        pg = conn.fetch_one("SELECT dp.* FROM document_page dp JOIN document d ON d.tenant_id=dp.tenant_id AND d.document_id=dp.document_id"
                            " WHERE dp.tenant_id=$1 AND dp.document_id=$2 AND dp.page_no=$3 AND d.claim_id=$4 AND d.status <> 'QUARANTINED'",
                            p.tenant_id, did, n, cid)
        if not pg:
            raise Problem(404, "page-not-found", "page not found")
        base = f"/v1/claims/{cid}/documents/{did}/pages/{n}"
        return 200, {"image_url": sign(base + "/image", p.tenant_id), "words_url": sign(base + "/words", p.tenant_id) if pg["text_key"] else None,
                     "text_layer": pg["text_layer"], "quality_score": float(pg["quality_score"]) if pg["quality_score"] is not None else None,
                     "width_pt": float(pg["width_pt"]) if pg["width_pt"] else None, "height_pt": float(pg["height_pt"]) if pg["height_pt"] else None}, None

    def page_asset(kind: str):
        async def endpoint(request: Request):
            try:
                tenant = verify_signed(request)
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

    def h_request_evaluation(conn, p, req, body):
        p.require("fact.correct")
        cid = req.path_params["claim_id"]
        ingest.mark_stale(conn, p.tenant_id, cid, p.actor, (body or {}).get("trigger", "MANUAL_RERUN"))
        job = jobs.enqueue(conn, p.tenant_id, "EVALUATE", cid, f"evaluate:{cid}:manual:{new_id('R')}", {"trigger": (body or {}).get("trigger", "MANUAL_RERUN")})
        return 202, {"job_id": job, "status": "QUEUED"}, None

    def h_current_evaluation(conn, p, req, body):
        p.require("claim.view")
        ev = evaluations.current(conn, p.tenant_id, req.path_params["claim_id"])
        if not ev or not ev["result"]:
            raise Problem(404, "no-evaluation", "no evaluation yet")
        view = evaluations.api_view(conn, p.tenant_id, ev)
        view["status"] = ev["status"]
        view["supersedes_evaluation_id"] = ev["supersedes_evaluation_id"]
        return 200, view, None

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

    def h_bill_lines(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT * FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active ORDER BY line_no", p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": [{**{k: r[k] for k in ("bill_line_id", "bill_version", "line_no", "description", "category", "category_source", "ward_context",
                                                       "room_category", "service_date", "invoice_no", "evidence")},
                                 "category_confidence": float(r["category_confidence"]) if r["category_confidence"] is not None else None,
                                 "quantity": str(r["quantity"].normalize()), "unit_rate": fmt(r["unit_rate_paise"]), "billed": fmt(r["billed_paise"])} for r in rows]}, None

    def h_findings(conn, p, req, body):
        p.require("claim.view")
        sql, args = "SELECT * FROM finding WHERE tenant_id=$1 AND claim_id=$2", [p.tenant_id, req.path_params["claim_id"]]
        for col in ("status", "category"):
            if req.query_params.get(col):
                args.append(req.query_params[col])
                sql += f" AND {col}::text = ${len(args)}"
        rows = conn.fetch_all(sql + " ORDER BY blocking DESC, severity DESC, finding_id", *args)
        return 200, {"items": [{k: v for k, v in r.items() if k not in ("tenant_id", "subject_key")} for r in rows]}, None

    def h_reviewer_action(conn, p, req, body):
        cid = req.path_params["claim_id"]
        out = review.record(conn, p, cid, body)
        return 201, out, etag(conn, p, cid)

    def h_draft_query(conn, p, req, body):
        p.require("query.draft")
        cid = req.path_params["claim_id"]
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

    def h_approve_query(conn, p, req, body):
        return 200, queries.approve(conn, p, req.path_params["query_id"]), None

    def h_decision(conn, p, req, body):
        cid = req.path_params["claim_id"]
        out = decisions.decide(conn, p, ctx.schema_dir, cid, body)
        return 201, out, etag(conn, p, cid)

    def h_request_approval(conn, p, req, body):
        cid = req.path_params["claim_id"]
        return 201, decisions.request_approval(conn, p, cid, body), etag(conn, p, cid)

    def h_approve_request(conn, p, req, body):
        return 200, decisions.approve_request(conn, p, ctx.schema_dir, req.path_params["approval_request_id"], (body or {}).get("comment")), None

    def h_return_request(conn, p, req, body):
        return 200, decisions.return_request(conn, p, req.path_params["approval_request_id"], body["comment"]), None

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

    def h_exports(conn, p, req, body):
        p.require("claim.view")
        rows = conn.fetch_all("SELECT export_id, decision_id, target, state, target_reference FROM export_record WHERE tenant_id=$1 AND claim_id=$2",
                              p.tenant_id, req.path_params["claim_id"])
        return 200, {"items": rows}, None

    def h_audit(conn, p, req, body):
        p.require("claim.view")
        cid = req.path_params["claim_id"]
        rows = conn.fetch_all("SELECT seq, occurred_at, actor_kind, actor_id, event_type, payload, prev_hash, event_hash FROM audit_event"
                              " WHERE tenant_id=$1 AND claim_id=$2 ORDER BY seq", p.tenant_id, cid)
        items = [{"seq": r["seq"], "occurred_at": r["occurred_at"], "actor": "SYSTEM" if r["actor_kind"] == "SYSTEM" else f"{r['actor_kind']}:{r['actor_id']}",
                  "event_type": r["event_type"], "payload": r["payload"], "prev_hash": r["prev_hash"], "event_hash": r["event_hash"]} for r in rows]
        return 200, {"items": items, "next_cursor": None, "verification": audit.verify_chain(conn, p.tenant_id, cid)}, None

    def _claim_cmd(action):
        def h(conn, p, req, body):
            cid = req.path_params["claim_id"]
            c = ingest.get_claim(conn, p.tenant_id, cid)
            if not c:
                raise Problem(404, "claim-not-found", "claim not found")
            if action == "assign":
                p.require("claim.assign")
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
                conn.execute("UPDATE claim SET status='REOPENED', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, cid)
                conn.execute("INSERT INTO si_ledger_entry (tenant_id, policy_no, member_id, policy_year_start, claim_id, entry_kind, amount_paise)"
                             " SELECT tenant_id, policy_no, member_id, policy_year_start, claim_id, 'RELEASED', amount_paise FROM si_ledger_entry"
                             " WHERE tenant_id=$1 AND claim_id=$2 AND entry_kind='RESERVED'", p.tenant_id, cid)
                audit.append(conn, p.tenant_id, cid, p.actor, "CLAIM_REOPENED", {"reason": body["reason"]})
                jobs.enqueue(conn, p.tenant_id, "EVALUATE", cid, f"evaluate:{cid}:reopen:{new_id('R')}", {"trigger": "MANUAL_RERUN"})
            return 200, claim_view(conn, p, cid), etag(conn, p, cid)
        return h

    def h_list_configs(conn, p, req, body):
        rows = conn.fetch_all("SELECT artifact_id, version, artifact_kind, status, effective_from, effective_to, authored_by, approved_by, published_at, body_sha256"
                              " FROM config_artifact WHERE tenant_id=$1 ORDER BY artifact_kind, artifact_id, effective_from", p.tenant_id)
        return 200, {"items": rows, "next_cursor": None}, None

    def h_create_config(conn, p, req, body):
        p.require("config.author")
        ident = configs.identity(body["kind"], body["body"]) if body["kind"] in configs.KINDS else (None, None)
        if ident != (body["artifact_id"], body["version"]):
            raise Problem(422, "identity-mismatch", "artifact_id and version must match the identifiers inside body")
        out = configs.create_draft(conn, ctx.schema_dir, p.tenant_id, body["kind"], body["body"], p.user_id, date.fromisoformat(body["effective_from"]),
                                   date.fromisoformat(body["effective_to"]) if body.get("effective_to") else None, body.get("source_documents"))
        return 201, out, None

    def h_validate_config(conn, p, req, body):
        row = conn.fetch_one("SELECT artifact_kind, body FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3", p.tenant_id,
                             req.path_params["artifact_id"], req.path_params["version"])
        if not row:
            raise Problem(404, "config-not-found", "configuration not found")
        errs = configs.validate(ctx.schema_dir, row["artifact_kind"], row["body"])
        return 200, {"valid": not errs, "errors": errs}, None

    def h_replay_config(conn, p, req, body):
        """Re-evaluate the given (or all open) claims with the draft policy configuration; nothing is persisted."""
        from ..engine import evaluate as run_engine
        row = conn.fetch_one("SELECT artifact_kind, body FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3", p.tenant_id,
                             req.path_params["artifact_id"], req.path_params["version"])
        if not row or row["artifact_kind"] != "POLICY_CONFIG":
            raise Problem(422, "replay-unsupported", "replay supports policy configurations in this release")
        claim_ids = (body or {}).get("claim_ids") or [r["claim_id"] for r in conn.fetch_all(
            "SELECT claim_id FROM claim WHERE tenant_id=$1 AND current_evaluation_id IS NOT NULL", p.tenant_id)]
        results = []
        for cid in claim_ids:
            ev = evaluations.current(conn, p.tenant_id, cid)
            if not ev:
                continue
            ei, cfgs = evaluations.build_engine_input(conn, p.tenant_id, cid, "REPLAY")
            if cfgs["policy"]["config_id"] != row["body"]["config_id"]:
                continue
            try:
                out = run_engine(ei, row["body"], cfgs["nme"], cfgs["tariff"], cfgs["checklist"])
                after = out["recommendation"]["recommended_payable"]
            except Exception as e:  # noqa: BLE001
                after = f"ERROR: {type(e).__name__}"
            before = fmt(ev["recommended_payable_paise"])
            results.append({"claim_id": cid, "payable_before": before, "payable_after": after, "changed": before != after})
        return 202, {"claims": len(results), "changed": sum(r["changed"] for r in results), "results": results}, None

    def h_publish_config(conn, p, req, body):
        p.require("config.publish")
        out = configs.publish(conn, p.tenant_id, req.path_params["artifact_id"], req.path_params["version"], p.user_id)
        return 200, out, None

    def h_import_policies(conn, p, req, body):
        p.require("admin.users")
        n = 0
        for r in body["records"]:
            conn.execute("INSERT INTO member (tenant_id, member_id, full_name, name_normalised, gender, dob) VALUES ($1,$2,$3,$4,$5,$6::date)"
                         " ON CONFLICT (tenant_id, member_id) DO UPDATE SET full_name=EXCLUDED.full_name, name_normalised=EXCLUDED.name_normalised",
                         p.tenant_id, r["member_id"], r["full_name"], __import__("aw.matching", fromlist=["x"]).normalise_name(r["full_name"]), r.get("gender"), r.get("dob"))
            conn.execute("INSERT INTO policy (tenant_id, policy_no, product_name, period_start, period_end, config_artifact_id, config_version)"
                         " VALUES ($1,$2,$3,$4::date,$5::date,$6,$7) ON CONFLICT DO NOTHING", p.tenant_id, r["policy_no"], r.get("product_name", ""),
                         r["period_start"], r["period_end"], r["config_artifact_id"], r["config_version"])
            conn.execute("INSERT INTO policy_member (tenant_id, policy_no, member_id, continuous_cover_since, base_sum_insured_paise, cumulative_bonus_paise)"
                         " VALUES ($1,$2,$3,$4::date,$5,$6) ON CONFLICT DO NOTHING", p.tenant_id, r["policy_no"], r["member_id"], r["continuous_cover_since"],
                         to_paise(r["base_sum_insured"]), to_paise(r.get("cumulative_bonus", "0.00")))
            n += 1
        return 202, {"accepted": n}, None

    def h_import_si(conn, p, req, body):
        p.require("admin.users")
        for e in body["entries"]:
            conn.execute("INSERT INTO si_ledger_entry (tenant_id, policy_no, member_id, policy_year_start, entry_kind, amount_paise) VALUES ($1,$2,$3,$4::date,'OPENING_PAID_EXTERNAL',$5)",
                         p.tenant_id, e["policy_no"], e["member_id"], e["policy_year_start"], to_paise(e["amount"]))
        return 202, {"accepted": len(body["entries"])}, None

    def h_tms_event(conn, p, req, body):
        claim = conn.fetch_one("SELECT claim_id FROM claim WHERE tenant_id=$1 AND external_ref=$2", p.tenant_id, body["external_ref"])
        if not claim:
            raise Problem(404, "claim-not-found", "no claim with that external_ref")
        if body["event_type"] == "CLAIM_WITHDRAWN":
            conn.execute("UPDATE claim SET status='WITHDRAWN', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2 AND status NOT IN ('FINALISED','EXPORTED')",
                         p.tenant_id, claim["claim_id"])
            audit.append(conn, p.tenant_id, claim["claim_id"], "INTEGRATION:TMS", "CLAIM_WITHDRAWN", {"event_id": body["event_id"]})
        return 202, {"accepted": True, "claim_id": claim["claim_id"]}, None

    # ------------------------------------------------------------------ dev login (never in prod)
    async def dev_login(request: Request):
        if ctx.settings.environment not in ("dev", "test"):
            return Response(status_code=404)
        data = json.loads(await request.body() or b"{}")

        def _users():
            with ctx.db.tenant_tx(data.get("tenant_id", "TENANT-DEMO")) as c:
                return c.fetch_all("SELECT u.user_id, u.display_name, array_agg(r.role) AS roles FROM app_user u JOIN role_assignment r"
                                   " ON r.tenant_id=u.tenant_id AND r.user_id=u.user_id GROUP BY 1,2 ORDER BY 1")
        if not data.get("user_id"):
            return jresp({"users": await run_in_threadpool(_users)})
        return jresp({"token": auth.issue_dev_token(secret, data["user_id"], data.get("tenant_id", "TENANT-DEMO")), "environment": ctx.settings.environment})

    async def index(request: Request):
        return FileResponse(WEB_DIR / "index.html")

    async def health(request: Request):
        return jresp({"status": "ok", "engine": __import__("aw.engine", fromlist=["x"]).ENGINE_VERSION})

    R = Route
    routes = [
        R("/healthz", health),
        R("/", index),
        R("/dev/login", dev_login, methods=["POST"]),
        R("/v1/me", operation("getMe", h_me)),
        R("/v1/claims", operation("createClaim", h_create_claim), methods=["POST"]),
        R("/v1/claims", operation("listClaims", h_list_claims), methods=["GET"]),
        R("/v1/claims/{claim_id}", operation("getClaim", h_get_claim), methods=["GET"]),
        R("/v1/claims/{claim_id}:assign", operation("assignClaim", _claim_cmd("assign"), claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}:withdraw", operation("withdrawClaim", _claim_cmd("withdraw"), claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}:reopen", operation("reopenClaim", _claim_cmd("reopen"), claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}/documents", operation("createDocumentUpload", h_create_upload), methods=["POST"]),
        R("/v1/claims/{claim_id}/documents", operation("listDocuments", h_list_documents), methods=["GET"]),
        R("/v1/uploads/{upload_id}", put_upload, methods=["PUT"]),
        R("/v1/claims/{claim_id}/documents/{document_id}:complete", operation("completeDocumentUpload", h_complete_upload), methods=["POST"]),
        R("/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}", operation("getPage", h_get_page), methods=["GET"]),
        R("/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}/image", page_asset("image"), methods=["GET"]),
        R("/v1/claims/{claim_id}/documents/{document_id}/pages/{page_no:int}/words", page_asset("words"), methods=["GET"]),
        R("/v1/claims/{claim_id}/evaluations", operation("requestEvaluation", h_request_evaluation, claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}/evaluations/current", operation("getCurrentEvaluation", h_current_evaluation), methods=["GET"]),
        R("/v1/claims/{claim_id}/evaluations/{evaluation_id}", operation("getEvaluation", h_get_evaluation), methods=["GET"]),
        R("/v1/claims/{claim_id}/evaluations/{evaluation_id}/diff", operation("diffEvaluations", h_diff), methods=["GET"]),
        R("/v1/claims/{claim_id}/facts", operation("listFacts", h_facts), methods=["GET"]),
        R("/v1/claims/{claim_id}/bill-lines", operation("listBillLines", h_bill_lines), methods=["GET"]),
        R("/v1/claims/{claim_id}/findings", operation("listFindings", h_findings), methods=["GET"]),
        R("/v1/claims/{claim_id}/reviewer-actions", operation("recordReviewerAction", h_reviewer_action, claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}/queries", operation("draftQuery", h_draft_query), methods=["POST"]),
        R("/v1/queries/{query_id}:approve", operation("approveQuery", h_approve_query), methods=["POST"]),
        R("/v1/claims/{claim_id}/decisions", operation("recordDecision", h_decision, claim_scoped=True), methods=["POST"]),
        R("/v1/claims/{claim_id}/approval-requests", operation("requestApproval", h_request_approval, claim_scoped=True), methods=["POST"]),
        R("/v1/approval-requests/{approval_request_id}:approve", operation("approveRequest", h_approve_request), methods=["POST"]),
        R("/v1/approval-requests/{approval_request_id}:return", operation("returnRequest", h_return_request), methods=["POST"]),
        R("/v1/claims/{claim_id}/decisions/{decision_id}/worksheet", operation("getWorksheet", h_worksheet), methods=["GET"]),
        R("/v1/claims/{claim_id}/exports", operation("listExports", h_exports), methods=["GET"]),
        R("/v1/claims/{claim_id}/audit-events", operation("listAuditEvents", h_audit), methods=["GET"]),
        R("/v1/config-artifacts", operation("listConfigArtifacts", h_list_configs), methods=["GET"]),
        R("/v1/config-artifacts", operation("createConfigDraft", h_create_config), methods=["POST"]),
        R("/v1/config-artifacts/{artifact_id}/versions/{version}:validate", operation("validateConfig", h_validate_config), methods=["POST"]),
        R("/v1/config-artifacts/{artifact_id}/versions/{version}:replay", operation("replayConfig", h_replay_config), methods=["POST"]),
        R("/v1/config-artifacts/{artifact_id}/versions/{version}:publish", operation("publishConfig", h_publish_config), methods=["POST"]),
        R("/v1/imports/policies", operation("importPolicies", h_import_policies), methods=["POST"]),
        R("/v1/imports/si-ledger", operation("importSiLedger", h_import_si), methods=["POST"]),
        R("/v1/integrations/tms/events", operation("receiveTmsEvent", h_tms_event), methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=str(WEB_DIR)), name="static"),
    ]
    app = Starlette(routes=routes)
    app.state.ctx = ctx
    app.state.contract = contract
    return app


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False
