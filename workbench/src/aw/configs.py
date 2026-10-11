"""Configuration artifacts (CAP-21): validate against the pack's JSON Schemas, store immutably by version,
publish only with a second person (four-eyes, DB-enforced), and select by effective date.

Artifact kinds and how their identity is read from the body:
  POLICY_CONFIG   config_id / config_version          schemas/policy-config.schema.json
  NME_LIST        list_id / list_version              schemas/nme-list.schema.json
  TARIFF          tariff_id / tariff_version          schemas/tariff.schema.json (per hospital)
  CHECKLIST       checklist_id / checklist_version    schemas/checklist.schema.json (per workflow)
  WORKFLOW_CONFIG workflow_config_id / version        schemas/workflow-config.schema.json
  CLASSIFIER_MAP  map_id / map_version                schemas/classifier-map.schema.json
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .db import Conn, Json
from .ids import canonical_json

KINDS = {
    "POLICY_CONFIG": ("config_id", "config_version", "policy-config.schema.json"),
    "NME_LIST": ("list_id", "list_version", "nme-list.schema.json"),
    "TARIFF": ("tariff_id", "tariff_version", "tariff.schema.json"),
    "CHECKLIST": ("checklist_id", "checklist_version", "checklist.schema.json"),
    "WORKFLOW_CONFIG": ("workflow_config_id", "version", "workflow-config.schema.json"),
    "CLASSIFIER_MAP": ("map_id", "map_version", "classifier-map.schema.json"),
}


class ConfigError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


@lru_cache(maxsize=None)
def _validator(schema_dir: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((Path(schema_dir) / schema_name).read_text(encoding="utf-8")))


def validate(schema_dir: Path, kind: str, body: dict) -> list[str]:
    if kind not in KINDS:
        return [f"unknown artifact kind {kind}"]
    v = _validator(str(schema_dir), KINDS[kind][2])
    return [f"/{'/'.join(map(str, e.path))}: {e.message}" for e in v.iter_errors(body)]


def identity(kind: str, body: dict) -> tuple[str, str]:
    id_key, ver_key, _ = KINDS[kind]
    return body[id_key], body[ver_key]


def create_draft(conn: Conn, schema_dir: Path, tenant_id: str, kind: str, body: dict, authored_by: str | None,
                 effective_from: date, effective_to: date | None = None, source_documents: list | None = None) -> dict:
    errs = validate(schema_dir, kind, body)
    if errs:
        raise ConfigError("configuration failed schema validation", errs)
    artifact_id, version = identity(kind, body)
    digest = hashlib.sha256(canonical_json(body)).hexdigest()
    existing = conn.fetch_one("SELECT body_sha256, status FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3",
                              tenant_id, artifact_id, version)
    if existing:
        if existing["body_sha256"] != digest:
            raise ConfigError(f"{artifact_id}@{version} already exists with different content; bump the version")
        return {"artifact_id": artifact_id, "version": version, "status": existing["status"], "created": False}
    conn.execute(
        "INSERT INTO config_artifact (artifact_id, version, tenant_id, artifact_kind, status, effective_from, effective_to, body, body_sha256,"
        " source_documents, authored_by) VALUES ($1,$2,$3,$4,'DRAFT',$5,$6,$7::jsonb,$8,$9::jsonb,$10)",
        artifact_id, version, tenant_id, kind, effective_from, effective_to, Json(body), digest,
        Json(source_documents or body.get("authoritative_documents") or []), authored_by)
    return {"artifact_id": artifact_id, "version": version, "status": "DRAFT", "created": True}


def publish(conn: Conn, tenant_id: str, artifact_id: str, version: str, approver: str) -> dict:
    row = conn.fetch_one("SELECT status, authored_by, artifact_kind, effective_from, effective_to, body FROM config_artifact"
                         " WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3 FOR UPDATE", tenant_id, artifact_id, version)
    if not row:
        raise ConfigError(f"{artifact_id}@{version} not found")
    if row["status"] == "PUBLISHED":
        return {"artifact_id": artifact_id, "version": version, "status": "PUBLISHED", "changed": False}
    if row["authored_by"] and row["authored_by"] == approver:
        raise ConfigError("the author cannot publish their own configuration (four-eyes)")
    # overlapping published versions of the same artifact are not allowed: close the previous one
    conn.execute("UPDATE config_artifact SET effective_to = ($4::date - 1) WHERE tenant_id=$1 AND artifact_id=$2 AND version<>$3"
                 " AND status='PUBLISHED' AND (effective_to IS NULL OR effective_to >= $4::date) AND effective_from < $4::date",
                 tenant_id, artifact_id, version, row["effective_from"])
    conn.execute("UPDATE config_artifact SET status='PUBLISHED', approved_by=$4, published_at=now() WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3",
                 tenant_id, artifact_id, version, approver)
    return {"artifact_id": artifact_id, "version": version, "status": "PUBLISHED", "changed": True}


def get(conn: Conn, tenant_id: str, artifact_id: str, version: str) -> dict:
    row = conn.fetch_one("SELECT body, status FROM config_artifact WHERE tenant_id=$1 AND artifact_id=$2 AND version=$3",
                         tenant_id, artifact_id, version)
    if not row:
        raise ConfigError(f"configuration {artifact_id}@{version} not found")
    if row["status"] != "PUBLISHED":
        raise ConfigError(f"configuration {artifact_id}@{version} is {row['status']}, not PUBLISHED")
    return row["body"]


def effective(conn: Conn, tenant_id: str, kind: str, on: date, *, hospital_id: str | None = None, workflow: str | None = None) -> dict | None:
    """The PUBLISHED artifact of `kind` effective on `on` (selection by date, never 'latest')."""
    sql = ("SELECT artifact_id, version, body FROM config_artifact WHERE tenant_id=$1 AND artifact_kind=$2 AND status='PUBLISHED'"
           " AND effective_from <= $3 AND (effective_to IS NULL OR effective_to >= $3)")
    args: list = [tenant_id, kind, on]
    if hospital_id is not None:
        sql += f" AND body->>'hospital_id' = ${len(args) + 1}"
        args.append(hospital_id)
    if workflow is not None:
        sql += f" AND body->>'workflow' = ${len(args) + 1}"
        args.append(workflow)
    sql += " ORDER BY effective_from DESC, published_at DESC LIMIT 1"
    row = conn.fetch_one(sql, *args)
    return row["body"] if row else None


def load_directory(conn: Conn, schema_dir: Path, tenant_id: str, config_dir: Path, author: str, approver: str,
                   default_effective_from: date = date(2026, 1, 1)) -> list[dict]:
    """Seed helper: load every JSON config in a directory, create drafts and publish them (author ≠ approver)."""
    prefix_kind = {"policy-": "POLICY_CONFIG", "nme-list-": "NME_LIST", "tariff-": "TARIFF", "checklist-": "CHECKLIST",
                   "workflow-": "WORKFLOW_CONFIG", "classifier-map-": "CLASSIFIER_MAP"}
    out = []
    for p in sorted(config_dir.glob("*.json")):
        kind = next((k for pre, k in prefix_kind.items() if p.name.startswith(pre)), None)
        if not kind:
            continue
        body = json.loads(p.read_text(encoding="utf-8"))
        eff_from = date.fromisoformat(body["effective_from"]) if body.get("effective_from") else default_effective_from
        eff_to = date.fromisoformat(body["effective_to"]) if body.get("effective_to") else None
        d = create_draft(conn, schema_dir, tenant_id, kind, body, author, eff_from, eff_to)
        publish(conn, tenant_id, d["artifact_id"], d["version"], approver)
        out.append({"file": p.name, "kind": kind, **d})
    return out
