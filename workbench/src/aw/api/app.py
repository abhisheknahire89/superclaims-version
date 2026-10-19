"""HTTP API (FastAPI), implementing pack/api/openapi.yaml.

The contract is spec-first: api/openapi.yaml is the single source of truth. FastAPI serves it unchanged at
/v1/openapi.json, and every route is registered under the operationId the contract declares (ADR-13). Request
validation, idempotency and concurrency checks are driven by the contract in aw.api.core; route modules hold the
handlers. tests/test_hardening.py checks that the routes and the contract match both ways.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from .. import auth
from . import claims, config_routes, integrations, sessions, operations, policy_intelligence
from .contract import Contract
from .core import Api, jresp

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
MODULES = (claims, config_routes, integrations, sessions, operations, policy_intelligence)


def create_app(ctx) -> FastAPI:
    contract = Contract(ctx.settings.pack_dir)
    api = Api(ctx, contract)
    for m in MODULES:
        m.register(api)

    # ------------------------------------------------------------------ dev login (never in prod)
    @api.raw("/dev/login", "POST", "devLogin")
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
        if ctx.settings.environment!="test":return Response(status_code=404)
        return jresp({"token": auth.issue_dev_token(api.secret, data["user_id"], data.get("tenant_id", "TENANT-DEMO")), "environment": ctx.settings.environment})

    @api.raw("/", "GET", "index")
    async def index(request: Request):
        return FileResponse(WEB_DIR / "index.html")

    @api.raw("/healthz", "GET", "health")
    async def health(request: Request):
        from ..engine import ENGINE_VERSION
        return jresp({"status": "ok", "engine": ENGINE_VERSION})

    @api.raw('/readyz','GET','readiness')
    async def readiness(request:Request):
        def check():
            import os,shutil
            try:
                with ctx.db.connection() as c:c.fetch_val('SELECT 1')
                ready=os.access(ctx.store.root,os.W_OK) and ctx.worker_db is not None
                return jresp({'ready':ready,'database':True,'storage':os.access(ctx.store.root,os.W_OK),'local_ocr':bool(shutil.which('tesseract')),'manual_entry':True,'worker_configured':ctx.worker_db is not None},200 if ready else 503)
            except Exception:return jresp({'ready':False,'database':False},503)
        return await run_in_threadpool(check)

    app = FastAPI(title=contract.doc["info"]["title"], version=contract.doc["info"]["version"],
                  openapi_url=None, docs_url=None, redoc_url=None)
    for path, endpoint, methods, name in api.routes:
        app.add_api_route(path, endpoint, methods=methods, name=name, operation_id=name, include_in_schema=False)

    async def openapi_doc(request: Request):
        return jresp(contract.doc)
    app.add_api_route("/v1/openapi.json", openapi_doc, methods=["GET"], include_in_schema=False)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    app.state.ctx = ctx
    app.state.contract = contract
    app.state.api = api
    return app
