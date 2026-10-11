"""Queries (CAP-16): drafts come from the evaluation's query items, grouped by addressee; a person edits and approves
them; only approved letters are released. Claims never auto-close on non-response (workflow config: auto_close false)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import audit
from .auth import Principal
from .db import Conn
from .ids import new_id


class QueryError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def draft_from_evaluation(conn: Conn, p: Principal, claim_id: str, evaluation_id: str, edits: dict | None = None) -> list[dict]:
    p.require("query.draft")
    ev = conn.fetch_one("SELECT result FROM evaluation WHERE tenant_id=$1 AND evaluation_id=$2 AND claim_id=$3", p.tenant_id, evaluation_id, claim_id)
    if not ev:
        raise QueryError(404, "evaluation-not-found", "evaluation not found")
    items = ev["result"]["query_items"]
    if not items:
        raise QueryError(422, "nothing-to-ask", "the evaluation has no query items")
    findings = {f["finding_id"]: f for f in ev["result"]["findings"]}
    db_findings = {r["subject_key"]: r["finding_id"] for r in conn.fetch_all("SELECT subject_key, finding_id FROM finding WHERE tenant_id=$1 AND claim_id=$2",
                                                                          p.tenant_id, claim_id)}
    from .evaluations import _subject_key
    letters: dict[str, str] = {}
    out = []
    for it in items:
        addr = it["addressed_to"]
        if addr not in letters:
            qid = new_id("QRY")
            letters[addr] = qid
            conn.execute("INSERT INTO query_letter (tenant_id, query_id, claim_id, addressed_to, status, due_at) VALUES ($1,$2,$3,$4,'DRAFT',$5)",
                         p.tenant_id, qid, claim_id, addr, datetime.now(timezone.utc) + timedelta(days=7))
            out.append({"query_id": qid, "addressed_to": addr, "items": []})
        linked = [db_findings.get(_subject_key(findings[f])) for f in it["linked_findings"] if f in findings]
        text = (edits or {}).get(it["query_item_id"], it["text"])
        qi = new_id("QIT")
        conn.execute("INSERT INTO query_item (tenant_id, query_item_id, query_id, requested_document_type, text, linked_finding_ids, addressed_to)"
                     " VALUES ($1,$2,$3,$4,$5,$6::text[],$7)", p.tenant_id, qi, letters[addr], it.get("requested_document_type"), text,
                     [x for x in linked if x], addr)
        next(o for o in out if o["query_id"] == letters[addr])["items"].append({"query_item_id": qi, "text": text})
    audit.append(conn, p.tenant_id, claim_id, p.actor, "QUERY_DRAFTED", {"letters": [o["query_id"] for o in out], "items": len(items)})
    return out


def approve(conn: Conn, p: Principal, query_id: str) -> dict:
    p.require("query.approve")
    q = conn.fetch_one("SELECT * FROM query_letter WHERE tenant_id=$1 AND query_id=$2 FOR UPDATE", p.tenant_id, query_id)
    if not q:
        raise QueryError(404, "query-not-found", "query not found")
    if q["status"] != "DRAFT":
        raise QueryError(409, "query-not-draft", f"query is {q['status']}")
    conn.execute("UPDATE query_letter SET status='APPROVED', approved_by=$3 WHERE tenant_id=$1 AND query_id=$2", p.tenant_id, query_id, p.user_id)
    audit.append(conn, p.tenant_id, q["claim_id"], p.actor, "QUERY_APPROVED", {"query_id": query_id, "addressed_to": q["addressed_to"]})
    # release: Phase 1 has no TMS adapter (BL-20); the letter is marked SENT for the portal channel
    conn.execute("UPDATE query_letter SET status='SENT', sent_at=now() WHERE tenant_id=$1 AND query_id=$2", p.tenant_id, query_id)
    audit.append(conn, p.tenant_id, q["claim_id"], "SYSTEM", "QUERY_SENT", {"query_id": query_id, "channel": "PORTAL"})
    conn.execute("UPDATE claim SET status='AWAITING_RESPONSE', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2 AND status IN"
                 " ('READY_FOR_REVIEW','IN_REVIEW','MEDICAL_REVIEW','QUERY_RAISED')", p.tenant_id, q["claim_id"])
    return {"query_id": query_id, "status": "SENT"}
