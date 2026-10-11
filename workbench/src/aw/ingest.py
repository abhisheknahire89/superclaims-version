"""Claim registration and document ingestion (CAP-01, CAP-02).

Originals are stored write-once under tenant/claim/document/sha256; an exact duplicate on the same claim returns
the existing record. Files whose bytes are not an allowed type are QUARANTINED and never displayed. Each new
document marks the current evaluation STALE and queues extraction.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import audit, jobs
from .db import Conn, Json
from .extraction.pages import read_pdf, render_png, sniff_mime
from .ids import new_id, sha256_hex
from .storage import ObjectStore

ALLOWED_MIME = {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
MAX_BYTES = 50 * 1024 * 1024
OPEN_STATES = ("INTAKE", "DOCS_INCOMPLETE", "PROCESSING", "READY_FOR_REVIEW", "IN_REVIEW", "MEDICAL_REVIEW", "QUERY_RAISED",
               "AWAITING_RESPONSE", "PENDING_APPROVAL", "REOPENED")


class IngestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def create_claim(conn: Conn, tenant_id: str, body: dict, actor: str) -> dict:
    if body.get("external_ref"):
        existing = conn.fetch_one("SELECT claim_id FROM claim WHERE tenant_id=$1 AND external_ref=$2", tenant_id, body["external_ref"])
        if existing:
            raise IngestError(409, "duplicate-external-ref", f"claim with external_ref {body['external_ref']} already exists ({existing['claim_id']})")
    pm = conn.fetch_one("SELECT 1 FROM policy_member WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3",
                        tenant_id, body["policy_no"], body["member_id"])
    if not pm:
        raise IngestError(422, "unknown-policy-member", "policy and member are not known; import them first (/imports/policies)")
    if body.get("hospital_id") and not conn.fetch_one("SELECT 1 FROM hospital WHERE tenant_id=$1 AND hospital_id=$2", tenant_id, body["hospital_id"]):
        raise IngestError(422, "unknown-hospital", "hospital is not known")
    claim_id = body.get("claim_id") or new_id("CLM")
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO claim (tenant_id, claim_id, external_ref, workflow, status, policy_no, member_id, hospital_id, intimated_at, submitted_at)"
        " VALUES ($1,$2,$3,$4::workflow_type,'INTAKE',$5,$6,$7,$8::timestamptz,$9::timestamptz)",
        tenant_id, claim_id, body.get("external_ref"), body["workflow"], body["policy_no"], body["member_id"], body.get("hospital_id"),
        body.get("intimated_at") or now, body.get("submitted_at") or now)
    audit.append(conn, tenant_id, claim_id, actor, "CLAIM_CREATED", {"workflow": body["workflow"], "external_ref": body.get("external_ref")})
    return get_claim(conn, tenant_id, claim_id)


def get_claim(conn: Conn, tenant_id: str, claim_id: str) -> dict | None:
    return conn.fetch_one("SELECT * FROM claim WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id)


def mark_stale(conn: Conn, tenant_id: str, claim_id: str, actor: str, reason: str) -> str | None:
    claim = conn.fetch_one("SELECT current_evaluation_id FROM claim WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id)
    eid = claim and claim["current_evaluation_id"]
    if not eid:
        return None
    n = conn.execute("UPDATE evaluation SET status='STALE' WHERE tenant_id=$1 AND evaluation_id=$2 AND status IN ('COMPUTED','BLOCKED')",
                     tenant_id, eid)
    if n:
        audit.append(conn, tenant_id, claim_id, actor, "RECOMMENDATION_MARKED_STALE", {"evaluation_id": eid, "reason": reason})
    return eid


def add_document(conn: Conn, store: ObjectStore, tenant_id: str, claim_id: str, data: bytes, *, declared_type: str | None,
                 source_channel: str, actor: str, supersedes_document_id: str | None = None, filename: str | None = None) -> dict:
    claim = get_claim(conn, tenant_id, claim_id)
    if not claim:
        raise IngestError(404, "claim-not-found", "claim not found")
    if claim["status"] not in OPEN_STATES:
        raise IngestError(409, "claim-closed", f"claim is {claim['status']}; reopen it before adding documents")
    if len(data) == 0 or len(data) > MAX_BYTES:
        raise IngestError(422, "bad-size", "file must be between 1 byte and 50 MB")
    digest = sha256_hex(data)
    dup = conn.fetch_one("SELECT * FROM document WHERE tenant_id=$1 AND claim_id=$2 AND sha256=$3", tenant_id, claim_id, digest)
    if dup:
        return {**dup, "duplicate": True}
    document_id = new_id("DOC")
    mime = sniff_mime(data)
    key = f"{tenant_id}/{claim_id}/{document_id}/{digest}"
    if mime not in ALLOWED_MIME:
        store.put_once(f"quarantine/{key}", data)
        conn.execute("INSERT INTO document (tenant_id, document_id, claim_id, declared_type, status, source_channel, object_key, sha256, mime_type)"
                     " VALUES ($1,$2,$3,$4,'QUARANTINED',$5,$6,$7,'application/octet-stream')",
                     tenant_id, document_id, claim_id, declared_type, source_channel, f"quarantine/{key}", digest)
        audit.append(conn, tenant_id, claim_id, actor, "DOCUMENT_QUARANTINED", {"document_id": document_id, "sha256": digest, "reason": "TYPE_NOT_ALLOWED"})
        return get_document(conn, tenant_id, document_id)
    store.put_once(key, data)
    pages = read_pdf(data) if mime == "application/pdf" else []
    conn.execute(
        "INSERT INTO document (tenant_id, document_id, claim_id, declared_type, status, source_channel, object_key, sha256, mime_type, page_count, supersedes_document_id)"
        " VALUES ($1,$2,$3,$4,'STORED',$5,$6,$7,$8,$9,$10)",
        tenant_id, document_id, claim_id, declared_type, source_channel, key, digest, mime, len(pages) or 1, supersedes_document_id)
    for p in pages:
        text_key = f"{key}.p{p.page_no}.json"
        image_key = f"{key}.p{p.page_no}.png"
        store.put_once(text_key, json.dumps(p.to_json()).encode())
        store.put_once(image_key, render_png(data, p.page_no))
        conn.execute("INSERT INTO document_page (tenant_id, document_id, page_no, text_layer, image_key, text_key, width_pt, height_pt)"
                     " VALUES ($1,$2,$3,$4,$5,$6,$7,$8)", tenant_id, document_id, p.page_no, p.text_layer, image_key, text_key, p.width, p.height)
    if mime != "application/pdf":
        image_key = key
        conn.execute("INSERT INTO document_page (tenant_id, document_id, page_no, text_layer, image_key) VALUES ($1,$2,1,'NONE',$3)",
                     tenant_id, document_id, image_key)
    audit.append(conn, tenant_id, claim_id, actor, "DOCUMENT_RECEIVED",
                 {"document_id": document_id, "sha256": digest, "pages": len(pages) or 1, "declared_type": declared_type})
    if supersedes_document_id:
        n = conn.execute("UPDATE document SET status='SUPERSEDED' WHERE tenant_id=$1 AND document_id=$2 AND claim_id=$3",
                         tenant_id, supersedes_document_id, claim_id)
        if n:
            audit.append(conn, tenant_id, claim_id, actor, "DOCUMENT_SUPERSEDED", {"document_id": supersedes_document_id, "superseded_by": document_id})
    mark_stale(conn, tenant_id, claim_id, actor, "NEW_EVIDENCE")
    new_status = "PROCESSING" if claim["status"] in ("INTAKE", "DOCS_INCOMPLETE", "AWAITING_RESPONSE", "REOPENED", "READY_FOR_REVIEW") else claim["status"]
    conn.execute("UPDATE claim SET status=$3::claim_status, updated_at=now(), row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2",
                 tenant_id, claim_id, new_status)
    jobs.enqueue(conn, tenant_id, "EXTRACT", document_id, f"extract:{document_id}", {"claim_id": claim_id})
    return get_document(conn, tenant_id, document_id)


def get_document(conn: Conn, tenant_id: str, document_id: str) -> dict | None:
    return conn.fetch_one("SELECT * FROM document WHERE tenant_id=$1 AND document_id=$2", tenant_id, document_id)
