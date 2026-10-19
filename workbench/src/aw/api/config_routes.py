"""Configuration artifacts: list, draft, validate, replay and publish (S-09, CAP-21)."""
from __future__ import annotations

from datetime import date

from .. import configs, evaluations, config_admin, jobs, audit
from ..money import fmt
from .core import Api, Problem


def register(api: Api):
    ctx = api.ctx

    @api.op("listConfigArtifacts", "/v1/config-artifacts", "GET")
    def h_list_configs(conn, p, req, body):
        rows = conn.fetch_all("SELECT artifact_id, version, artifact_kind, status, effective_from, effective_to, authored_by, approved_by, published_at, body_sha256"
                              " FROM config_artifact WHERE tenant_id=$1 ORDER BY artifact_kind, artifact_id, effective_from", p.tenant_id)
        return 200, {"items": rows, "next_cursor": None}, None

    @api.op("createConfigDraft", "/v1/config-artifacts", "POST")
    def h_create_config(conn, p, req, body):
        p.require("config.author")
        ident = configs.identity(body["kind"], body["body"]) if body["kind"] in configs.KINDS else (None, None)
        if ident != (body["artifact_id"], body["version"]):
            raise Problem(422, "identity-mismatch", "artifact_id and version must match the identifiers inside body")
        out = configs.create_draft(conn, ctx.schema_dir, p.tenant_id, body["kind"], body["body"], p.user_id, date.fromisoformat(body["effective_from"]),
                                   date.fromisoformat(body["effective_to"]) if body.get("effective_to") else None, body.get("source_documents"))
        return 201, out, None

    @api.op("validateConfig", "/v1/config-artifacts/{artifact_id}/versions/{version}:validate", "POST")
    def h_validate_config(conn, p, req, body):
        row = conn.fetch_one("SELECT artifact_kind, body FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3", p.tenant_id,
                             req.path_params["artifact_id"], req.path_params["version"])
        if not row:
            raise Problem(404, "config-not-found", "configuration not found")
        errs = configs.validate(ctx.schema_dir, row["artifact_kind"], row["body"])
        return 200, {"valid": not errs, "errors": errs}, None

    @api.op("replayConfig", "/v1/config-artifacts/{artifact_id}/versions/{version}:replay", "POST")
    def h_replay_config(conn, p, req, body):
        p.require('config.author')
        row=conn.fetch_one('SELECT * FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3',p.tenant_id,req.path_params['artifact_id'],req.path_params['version'])
        if not row:raise Problem(404,'config-not-found','configuration not found')
        return 202,config_admin.replay(conn,p.tenant_id,row,(body or {}).get('claim_ids'),ctx.store),None

    @api.op("publishConfig", "/v1/config-artifacts/{artifact_id}/versions/{version}:publish", "POST")
    def h_publish_config(conn, p, req, body):
        p.require("config.publish")
        from ..local_auth import matches
        credential=conn.fetch_val('SELECT password_hash FROM local_credential WHERE tenant_id=$1 AND user_id=$2',p.tenant_id,p.user_id)
        if not credential or not matches((body or {}).get('current_password',''),credential):raise Problem(401,'reauthentication-required','confirm your password to publish configuration')
        out = configs.publish(conn, p.tenant_id, req.path_params["artifact_id"], req.path_params["version"], p.user_id)
        published=conn.fetch_one('SELECT artifact_kind,body FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3',p.tenant_id,out['artifact_id'],out['version'])
        if published['artifact_kind']=='WORKFLOW_CONFIG' and out['changed']:
            from ..money import to_paise
            for uid,amount in published['body']['approval'].get('illustrative_limits',{}).items():
                conn.execute('UPDATE role_assignment SET approval_limit_paise=$3 WHERE tenant_id=$1 AND user_id=$2 AND valid_to IS NULL',p.tenant_id,uid,to_paise(amount))
        if (body or {}).get('retroactive_to_open_claims') and out['changed']:
            from ..ingest import mark_stale
            row=conn.fetch_one('SELECT * FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3',p.tenant_id,out['artifact_id'],out['version'])
            count=0
            for c in conn.fetch_all("SELECT claim_id,policy_no FROM claim WHERE tenant_id=$1 AND status NOT IN ('FINALISED','EXPORTED','WITHDRAWN')",p.tenant_id):
                ei,cfg=evaluations.build_engine_input(conn,p.tenant_id,c['claim_id'],'CONFIG_CHANGE')
                from datetime import date as dt
                on=dt.fromisoformat(ei['admission_date']) if ei['admission_date'] else None
                if not on or on<row['effective_from'] or (row['effective_to'] and on>row['effective_to']):continue
                if row['artifact_kind']=='POLICY_CONFIG':
                    if cfg['policy']['config_id']!=out['artifact_id']:continue
                    conn.execute('UPDATE policy SET config_version=$3 WHERE tenant_id=$1 AND policy_no=$2',p.tenant_id,c['policy_no'],out['version'])
                mark_stale(conn,p.tenant_id,c['claim_id'],p.actor,'CONFIG_PUBLISHED')
                if row['artifact_kind']=='CLASSIFIER_MAP':
                    for doc in conn.fetch_all("SELECT document_id FROM document WHERE tenant_id=$1 AND claim_id=$2 AND status NOT IN ('SUPERSEDED','QUARANTINED')",p.tenant_id,c['claim_id']):
                        jobs.enqueue(conn,p.tenant_id,'EXTRACT',doc['document_id'],f"config:{doc['document_id']}:{out['artifact_id']}:{out['version']}",{})
                else:
                    jobs.enqueue(conn,p.tenant_id,'EVALUATE',c['claim_id'],f"config:{c['claim_id']}:{out['artifact_id']}:{out['version']}",{'trigger':'CONFIG_CHANGE'})
                count+=1
            out['reevaluations_queued']=count
        return 200, out, None

    @api.op('getConfigVersion','/v1/config-artifacts/{artifact_id}/versions/{version}','GET')
    def h_get(conn,p,req,body):
        if not (p.can('config.author') or p.can('config.publish')):p.require('config.author')
        row=conn.fetch_one('SELECT * FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3',p.tenant_id,req.path_params['artifact_id'],req.path_params['version'])
        if not row:raise Problem(404,'config-not-found','configuration not found')
        prior=conn.fetch_one('SELECT body FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version<>$3 ORDER BY effective_from DESC LIMIT 1',p.tenant_id,row['artifact_id'],row['version'])
        row['diff']=config_admin.diff(prior['body'] if prior else {},row['body'])
        return 200,row,None

    @api.op('importConfigPatch','/v1/config-artifacts:import','POST')
    def h_import(conn,p,req,body):
        p.require('config.author')
        try:candidate=config_admin.import_patch(body['body'],body['filename'],body['file_base64'])
        except Exception:raise Problem(422,'invalid-config-import','use bounded CSV/XLSX with path,value_json; values must be JSON and formulas are forbidden')
        errors=configs.validate(ctx.schema_dir,body['kind'],candidate)
        return 200,{'valid':not errors,'errors':errors,'body':candidate,'diff':config_admin.diff(body['body'],candidate)},None
