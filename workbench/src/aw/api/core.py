"""Request plumbing shared by every API module (05 §2).

  * auth: session or bearer token -> principal; roles and limits come from the database on every request
  * errors: RFC 9457 problem details (application/problem+json) with a JSON-pointer error list
  * Idempotency-Key and If-Match are required exactly where api/openapi.yaml requires them
  * idempotency: same key + same body -> original response; same key + different body -> 409
  * concurrency: claim-scoped writes compare If-Match with the claim's row_version (ETag "rv-<n>") -> 412 when stale
  * request bodies are validated against the OpenAPI schemas before any handler runs

Handlers are plain functions `(conn, principal, request, body) -> (status, payload, headers)`, registered with
`Api.op(operation_id, path, method)`. They run in a worker thread inside one tenant-scoped transaction.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from .. import auth, configs
from ..db import Json, PgError
from ..errors import AppError
from ..ids import sha256_hex

log = logging.getLogger("aw.api")
PROBLEM_BASE = "https://aw.example.invalid/problems/"


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str, errors: list | None = None, extra: dict | None = None):
        super().__init__(detail)
        self.status, self.code, self.detail, self.errors, self.extra = status, code, detail, errors or [], extra or {}


def json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(type(o))


def jresp(payload, status: int = 200, headers: dict | None = None) -> Response:
    return Response(json.dumps(payload, default=json_default, ensure_ascii=False), status_code=status, headers=headers or {},
                    media_type="application/json")


def problem_response(p: Problem, instance: str) -> Response:
    body = {"type": PROBLEM_BASE + p.code, "title": p.code.replace("-", " "), "status": p.status, "detail": p.detail, "instance": instance}
    if p.errors:
        body["errors"] = p.errors
    body.update(p.extra)
    return Response(json.dumps(body, default=json_default), status_code=p.status, media_type="application/problem+json")


def to_problem(e: Exception) -> Problem | None:
    """Map a domain exception to a problem; None for unexpected errors."""
    if isinstance(e, Problem):
        return e
    if isinstance(e, AppError):
        return Problem(e.status, e.code, str(e), extra=e.extra)
    if isinstance(e, configs.ConfigError):
        return Problem(422, "configuration-invalid", str(e), [{"pointer": x.split(":")[0], "message": x} for x in e.errors])
    if isinstance(e, auth.Forbidden):
        return Problem(403, "forbidden", str(e))
    if isinstance(e, auth.AuthError):
        return Problem(401, "unauthenticated", str(e))
    if isinstance(e, PgError):
        if e.sqlstate == "23505":
            return Problem(409, "conflict", "a record with the same key already exists")
        if e.sqlstate in ("23514", "23502", "22P02", "23503"):
            return Problem(422, "constraint-violated", f"rejected by a data rule ({e.constraint or e.sqlstate})")
    return None


def mask_name(name: str) -> str:
    parts = name.split()
    if not parts:
        return ""
    first = parts[0][0] + "."
    last = parts[-1]
    return f"{first} {last[0]}{'*' * max(1, len(last) - 2)}{last[-1]}" if len(last) > 2 else f"{first} {last}"


class _NullCtx:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class Api:
    """Holds the application context and the route table; modules register handlers on it."""

    def __init__(self, ctx, contract):
        self.ctx, self.contract = ctx, contract
        self.secret = ctx.settings.dev_token_secret or ""
        self.routes: list[tuple[str, Callable, list[str], str | None]] = []

    # ------------------------------------------------------------------ authentication
    def principal_of(self, request: Request) -> auth.Principal:
        return auth.authenticate(self.ctx, request)

    # ------------------------------------------------------------------ signed URLs (stand-in for S3 pre-signed URLs)
    def _mac(self, path: str, tenant: str, exp: int) -> str:
        return base64.urlsafe_b64encode(hmac.new(self.secret.encode(), f"{path}|{tenant}|{exp}".encode(), hashlib.sha256).digest()).decode().rstrip("=")

    def sign(self, path: str, tenant: str, ttl: int = 300) -> str:
        exp = int(time.time()) + ttl
        return f"{path}?t={tenant}&exp={exp}&sig={self._mac(path, tenant, exp)}"

    def verify_signed(self, request: Request) -> str:
        """Returns the tenant the URL was issued for. Authorisation happened when the URL was issued."""
        tenant, exp, sig = request.query_params.get("t", ""), request.query_params.get("exp", "0"), request.query_params.get("sig", "")
        if not exp.isdigit() or not hmac.compare_digest(self._mac(request.url.path, tenant, int(exp)), sig) or int(exp) < time.time():
            raise Problem(403, "bad-signature", "link expired or invalid")
        return tenant

    # ------------------------------------------------------------------ registration
    def op(self, operation_id: str, path: str, method: str, *, claim_scoped: bool = False, auth_required: bool = True):
        def deco(fn):
            self.routes.append((path, self.wrap(operation_id, fn, claim_scoped=claim_scoped, auth_required=auth_required),
                                [method.upper()], operation_id))
            return fn
        return deco

    def raw(self, path: str, method: str, name: str | None = None):
        """Register an async endpoint that does its own plumbing (signed downloads, uploads, sign-in)."""
        def deco(fn):
            self.routes.append((path, fn, [method.upper()], name))
            return fn
        return deco

    def wrap(self, operation_id: str | None, fn, *, claim_scoped: bool = False, auth_required: bool = True):
        api = self

        async def endpoint(request: Request):
            raw = bytearray()
            async for chunk in request.stream():
                if len(raw)+len(chunk)>2*1024*1024:
                    return problem_response(Problem(413,"request-too-large","JSON body exceeds 2 MB"),request.url.path)
                raw.extend(chunk)
            raw = bytes(raw)
            return await run_in_threadpool(api._handle, operation_id, fn, claim_scoped, auth_required, request, raw)
        endpoint.__name__ = operation_id or fn.__name__
        return endpoint

    def _handle(self, operation_id, fn, claim_scoped, auth_required, request: Request, raw: bytes):
        try:
            body = None
            if raw and request.headers.get("content-type", "").startswith("application/json"):
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise Problem(400, "bad-json", f"request body is not valid JSON: {e.msg}")
            if operation_id and operation_id in self.contract.ops:
                for h in self.contract.required_headers(operation_id):
                    if not request.headers.get(h):
                        raise Problem(428 if h == "If-Match" else 400, "missing-header", f"{h} header is required")
                if self.contract.ops[operation_id]["validator"] is not None:
                    errs = self.contract.validate(operation_id, body if body is not None else {})
                    if errs:
                        raise Problem(422, "validation-failed", "request does not match the API contract", errs)
            p = self.principal_of(request) if auth_required else None
            # Preserve the inherited receiver's route/handler, but enforce platform
            # RBAC before it can mutate a claim. No adapter or external calls added.
            if operation_id == "receiveTmsEvent":
                p.require("claim.withdraw")
            if p is not None:
                request.state.principal = p
            idem = request.headers.get("idempotency-key")
            with (self.ctx.db.tenant_tx(p.tenant_id) if p else _NullCtx()) as conn:
                if idem and p and request.method == "POST":
                    replay = self._idempotency(conn, p, request, raw, idem)
                    if replay is not None:
                        return replay
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
                                 p.tenant_id, idem, status, Json(json.loads(json.dumps(payload, default=json_default))))
            if isinstance(payload, Response):
                return payload
            return jresp(payload, status, headers)
        except Exception as e:  # noqa: BLE001
            prob = to_problem(e)
            if prob is None:
                log.error("unhandled operation=%s error_code=%s",operation_id or fn.__name__,type(e).__name__)
                prob = Problem(500, "internal", "unexpected error")
            return problem_response(prob, request.url.path)

    def _idempotency(self, conn, p, request: Request, raw: bytes, idem: str) -> Response | None:
        # A cache key is never an authorization credential. Bind it to the actor's
        # current DB-backed roles and limit, so cross-user reuse and revoked authority
        # cannot return a previous privileged response.
        authority = json.dumps([p.user_id, sorted(p.roles), p.approval_limit_paise], separators=(",", ":")).encode()
        req_hash = sha256_hex(authority + b"|" + request.method.encode() + request.url.path.encode() + raw)
        conn.execute("SAVEPOINT idem")
        try:
            conn.execute("INSERT INTO idempotency_key (tenant_id, key, request_sha256, expires_at) VALUES ($1,$2,$3, now() + interval '24 hours')",
                         p.tenant_id, idem, req_hash)
            conn.execute("RELEASE SAVEPOINT idem")
            return None
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

    # ------------------------------------------------------------------ helpers for handlers
    def etag(self, conn, p, claim_id: str) -> dict:
        return {"ETag": f'"rv-{conn.fetch_val("SELECT row_version FROM claim WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim_id)}"'}
