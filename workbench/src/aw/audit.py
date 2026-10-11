"""Append-only, hash-chained audit events per claim (05 §1.2; schemas/audit-event.schema.json).

event_hash = sha256(prev_hash | seq | occurred_at | actor | event_type | canonical payload)
The first event of a claim chains from "GENESIS". The claim row is locked (FOR UPDATE) while appending,
so concurrent writers cannot fork the chain. Payloads carry identifiers and hashes, never document text.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .db import Conn, Json
from .ids import canonical_json, new_id

GENESIS = "GENESIS"

EVENT_TYPES = {
    "CLAIM_CREATED", "CLAIM_ASSIGNED", "CLAIM_WITHDRAWN", "CLAIM_REOPENED", "DOCUMENT_RECEIVED", "DOCUMENT_QUARANTINED",
    "DOCUMENT_CLASSIFIED", "DOCUMENT_SUPERSEDED", "EXTRACTION_COMPLETED", "EXTRACTION_FAILED", "RULE_RUN_STARTED",
    "RULE_EXECUTED", "RECOMMENDATION_CREATED", "RECOMMENDATION_MARKED_STALE", "EVALUATION_FAILED",
    "REVIEWER_VIEWED_RECOMMENDATION", "REVIEWER_ACTION_RECORDED", "REVIEWER_CONFIRMED_FINDING", "MEDICAL_REVIEW_OPENED",
    "MEDICAL_REVIEW_PENDING", "MEDICAL_REVIEW_COMPLETED", "ANOMALY_TRIAGED", "INVESTIGATION_HOLD_PLACED",
    "INVESTIGATION_HOLD_RELEASED", "QUERY_DRAFTED", "QUERY_APPROVED", "QUERY_SENT", "QUERY_ANSWERED", "APPROVAL_REQUESTED",
    "APPROVAL_GRANTED", "APPROVAL_RETURNED", "DECISION_RECORDED", "CRC_OUTCOME_RECORDED", "SETTLEMENT_WORKSHEET_EXPORTED",
    "EXPORT_ACKNOWLEDGED", "EXPORT_FAILED", "CONFIG_PUBLISHED", "BREAK_GLASS_ACCESS",
}


def _hash(prev: str, seq: int, occurred_at: str, actor_kind: str, actor_id: str, event_type: str, payload: dict) -> str:
    h = hashlib.sha256()
    for part in (prev, str(seq), occurred_at, actor_kind, actor_id, event_type):
        h.update(part.encode())
        h.update(b"|")
    h.update(canonical_json(payload))
    return "sha256:" + h.hexdigest()


def actor_parts(actor: str) -> tuple[str, str]:
    """'SYSTEM' | 'USER:<id>' | 'INTEGRATION:<name>' -> (actor_kind, actor_id)."""
    if actor == "SYSTEM":
        return "SYSTEM", "SYSTEM"
    kind, _, ident = actor.partition(":")
    if kind not in ("USER", "INTEGRATION") or not ident:
        raise ValueError(f"bad actor {actor!r}")
    return kind, ident


def append(conn: Conn, tenant_id: str, claim_id: str, actor: str, event_type: str, payload: dict | None = None) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown audit event type {event_type}")
    payload = payload or {}
    conn.execute("SELECT 1 FROM claim WHERE tenant_id = $1 AND claim_id = $2 FOR UPDATE", tenant_id, claim_id)
    last = conn.fetch_one(
        "SELECT seq, event_hash FROM audit_event WHERE tenant_id = $1 AND claim_id = $2 ORDER BY seq DESC LIMIT 1",
        tenant_id, claim_id)
    seq = 1 if last is None else last["seq"] + 1
    prev = GENESIS if last is None else last["event_hash"]
    occurred = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    kind, ident = actor_parts(actor)
    h = _hash(prev, seq, occurred, kind, ident, event_type, payload)
    event_id = new_id("AEV")
    conn.execute(
        "INSERT INTO audit_event (tenant_id, event_id, claim_id, seq, occurred_at, actor_kind, actor_id, event_type, payload, prev_hash, event_hash)"
        " VALUES ($1,$2,$3,$4,$5::timestamptz,$6::actor_kind,$7,$8,$9::jsonb,$10,$11)",
        tenant_id, event_id, claim_id, seq, occurred, kind, ident, event_type, Json(payload), prev, h)
    return {"event_id": event_id, "seq": seq, "event_hash": h}


def verify_chain(conn: Conn, tenant_id: str, claim_id: str) -> dict:
    rows = conn.fetch_all(
        "SELECT seq, occurred_at, actor_kind, actor_id, event_type, payload, prev_hash, event_hash FROM audit_event"
        " WHERE tenant_id = $1 AND claim_id = $2 ORDER BY seq", tenant_id, claim_id)
    prev = GENESIS
    for i, r in enumerate(rows, start=1):
        occurred = r["occurred_at"].astimezone(timezone.utc).isoformat(timespec="microseconds")
        expect = _hash(prev, r["seq"], occurred, r["actor_kind"], r["actor_id"], r["event_type"], r["payload"])
        if r["seq"] != i or r["prev_hash"] != prev or r["event_hash"] != expect:
            return {"verified": False, "events": len(rows), "broken_at_seq": r["seq"]}
        prev = r["event_hash"]
    return {"verified": True, "events": len(rows), "head": prev}
