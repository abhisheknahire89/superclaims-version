"""RECONCILE job (CAP-05, CAP-07): pick one value per claim-level fact or surface a conflict, and build the
versioned bill from the current itemised bill. Only grounded (VERIFIED) facts from active documents count.

Resolution rules:
  * all observations agree          -> AUTO_AGREEMENT (2+ sources) or AUTO_SINGLE_SOURCE (1 source)
  * observations disagree           -> UNRESOLVED (value NULL); the engine's gates then block the dependent scopes
  * a reviewer's selection/entry    -> kept until a NEW observation (extracted after the resolution) disagrees with it,
                                       which re-opens the conflict
Bill lines: categorised dictionary-first (classifier map); a reviewer's category for the same line carries forward
to later bill versions; anything the dictionary cannot place becomes UNCLASSIFIED and blocks line rules
(R-GATE-LINE-CATEGORY) until a reviewer reclassifies it.
"""
from __future__ import annotations

from datetime import date

from . import configs, jobs
from .db import Conn, Json
from .ids import new_id
from .money import to_paise

ACTIVE_DOC = "d.status NOT IN ('SUPERSEDED','QUARANTINED')"
CLAIM_FIELDS = ["admission.date", "discharge.date", "bill.number", "bill.total", "bill.is_itemised",
                "diagnosis.primary_text", "procedure.text", "history.past_illness_text"]
BILL_FIELDS = {"bill.number", "bill.total", "bill.is_itemised"}
BILL_TYPES = ("FINAL_BILL_ITEMISED", "FINAL_BILL_SUMMARY")


def latest_facts(conn: Conn, tenant_id: str, claim_id: str, field_path: str | None = None, include_inactive: bool = False) -> list[dict]:
    """VERIFIED facts from the latest extraction run of each (active) document."""
    sql = ("SELECT f.*, d.classified_type, d.document_id, d.received_at FROM extracted_fact f"
           " JOIN extraction_run r ON r.tenant_id=f.tenant_id AND r.extraction_run_id=f.extraction_run_id"
           " JOIN document d ON d.tenant_id=r.tenant_id AND d.document_id=r.document_id"
           " WHERE f.tenant_id=$1 AND f.claim_id=$2 AND f.grounding_check='VERIFIED'"
           " AND r.started_at = (SELECT max(r2.started_at) FROM extraction_run r2 WHERE r2.tenant_id=r.tenant_id AND r2.document_id=r.document_id)")
    if not include_inactive:
        sql += f" AND {ACTIVE_DOC}"
    args: list = [tenant_id, claim_id]
    if field_path:
        sql += " AND f.field_path = $3"
        args.append(field_path)
    sql += " ORDER BY d.received_at, f.created_at"
    return conn.fetch_all(sql, *args)


def _bill_scope(facts: list[dict]) -> list[dict]:
    """Bill fields come from bill documents only; an itemised bill outranks a summary bill."""
    bills = [f for f in facts if f["classified_type"] in BILL_TYPES]
    itemised = [f for f in bills if f["classified_type"] == "FINAL_BILL_ITEMISED"]
    return itemised or bills


def resolve_claim(conn: Conn, tenant_id: str, claim_id: str) -> dict:
    all_facts = latest_facts(conn, tenant_id, claim_id)
    summary = {}
    for path in CLAIM_FIELDS:
        obs = [f for f in all_facts if f["field_path"] == path]
        if path in BILL_FIELDS:
            obs = _bill_scope(obs)
        current = conn.fetch_one("SELECT * FROM resolved_fact WHERE tenant_id=$1 AND claim_id=$2 AND field_path=$3 AND is_active",
                                 tenant_id, claim_id, path)
        if current and current["basis"] in ("REVIEWER_SELECTED", "REVIEWER_ENTERED"):
            newer_disagree = [f for f in obs if f["created_at"] > current["created_at"] and f["normalised_value"] != current["value"]]
            if not newer_disagree:
                summary[path] = ("KEPT_REVIEWER", current["value"])
                continue
        values = []
        for f in obs:
            if f["normalised_value"] not in values:
                values.append(f["normalised_value"])
        if not obs:
            basis, value = None, None
        elif len(values) == 1:
            basis, value = ("AUTO_AGREEMENT" if len(obs) > 1 else "AUTO_SINGLE_SOURCE"), values[0]
        else:
            basis, value = "UNRESOLVED", None
        sources = sorted(f["fact_id"] for f in obs)
        if current and current["basis"] == basis and current["value"] == value and sorted(current["source_fact_ids"]) == sources:
            summary[path] = (basis, value)
            continue
        if current:
            conn.execute("UPDATE resolved_fact SET is_active=false WHERE tenant_id=$1 AND resolved_fact_id=$2", tenant_id, current["resolved_fact_id"])
        if basis:
            conn.execute("INSERT INTO resolved_fact (tenant_id, resolved_fact_id, claim_id, field_path, value, basis, source_fact_ids)"
                         " VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7::text[])",
                         tenant_id, new_id("RSF"), claim_id, path, Json(value), basis, sources)
        summary[path] = (basis, value)
    adm = _active_value(conn, tenant_id, claim_id, "admission.date")
    dis = _active_value(conn, tenant_id, claim_id, "discharge.date")
    if adm and dis and dis < adm:
        dis = None
    conn.execute("UPDATE claim SET admission_date=$3::date, discharge_date=$4::date, updated_at=now() WHERE tenant_id=$1 AND claim_id=$2",
                 tenant_id, claim_id, adm, dis)
    return summary


def _active_value(conn: Conn, tenant_id: str, claim_id: str, path: str):
    r = conn.fetch_one("SELECT value FROM resolved_fact WHERE tenant_id=$1 AND claim_id=$2 AND field_path=$3 AND is_active",
                       tenant_id, claim_id, path)
    return r["value"] if r else None


def categorise(description: str, cmap: dict) -> str | None:
    d = description.lower()
    for rule in cmap["line_categories"]:
        if any(k in d for k in rule["keywords_any"]):
            return rule["category"]
    return None


def room_category(description: str, category: str, cmap: dict) -> str | None:
    if category not in ("ROOM", "ICU_ROOM"):
        return None
    d = description.lower()
    for rule in cmap["room_categories"]:
        if any(k in d for k in rule["keywords_any"]):
            return rule["room_category"]
    return "ICU" if category == "ICU_ROOM" else None


def sync_bill_lines(conn: Conn, tenant_id: str, claim_id: str) -> dict:
    bill = conn.fetch_one(f"SELECT d.document_id FROM document d WHERE d.tenant_id=$1 AND d.claim_id=$2 AND d.classified_type='FINAL_BILL_ITEMISED'"
                          f" AND {ACTIVE_DOC} ORDER BY d.received_at DESC LIMIT 1", tenant_id, claim_id)
    active = conn.fetch_all("SELECT * FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active ORDER BY line_no", tenant_id, claim_id)
    if not bill:
        if active:
            conn.execute("UPDATE bill_line SET is_active=false WHERE tenant_id=$1 AND claim_id=$2 AND is_active", tenant_id, claim_id)
        return {"bill_version": None, "lines": 0}
    items = [f for f in latest_facts(conn, tenant_id, claim_id, "bill.line_item") if f["document_id"] == bill["document_id"]]
    wanted = [(i["normalised_value"]["line_no"], i["normalised_value"]["description"], to_paise(i["normalised_value"]["amount"]),
               i["evidence"]["document_id"]) for i in items]
    have = [(l["line_no"], l["description"], l["billed_paise"], (l["evidence"] or [{}])[0].get("document_id")) for l in active]
    if sorted(wanted) == sorted(have):
        return {"bill_version": active[0]["bill_version"] if active else None, "lines": len(active), "changed": False}
    cmap = configs.effective(conn, tenant_id, "CLASSIFIER_MAP", date.today())
    if cmap is None:
        raise RuntimeError("CLASSIFIER_MAP_NOT_CONFIGURED")
    version = (conn.fetch_val("SELECT max(bill_version) FROM bill_line WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id) or 0) + 1
    reviewer_cats = {(r["line_no"], r["description"]): r["category"] for r in conn.fetch_all(
        "SELECT DISTINCT ON (line_no, description) line_no, description, category FROM bill_line WHERE tenant_id=$1 AND claim_id=$2"
        " AND category_source='REVIEWER' ORDER BY line_no, description, bill_version DESC", tenant_id, claim_id)}
    conn.execute("UPDATE bill_line SET is_active=false WHERE tenant_id=$1 AND claim_id=$2 AND is_active", tenant_id, claim_id)
    for f in items:
        it = f["normalised_value"]
        desc = it["description"]
        if (it["line_no"], desc) in reviewer_cats:
            cat, src, conf = reviewer_cats[(it["line_no"], desc)], "REVIEWER", 1.0
        else:
            cat = categorise(desc, cmap)
            src, conf = "DICTIONARY", 1.0
            if cat is None:
                sug = it.get("suggested_category")
                if sug and sug != "UNKNOWN" and it.get("confidence", 0) >= 0.9:
                    cat, src, conf = sug, "MODEL", float(it["confidence"])
                else:
                    cat, src, conf = "UNCLASSIFIED", "MODEL", 0.0
        ward = it.get("ward_context") or "UNKNOWN"
        if ward == "UNKNOWN":
            ward = "ICU" if "icu" in desc.lower() or cat == "ICU_ROOM" else "WARD"
        qty = it.get("quantity") or "1"
        conn.execute(
            "INSERT INTO bill_line (tenant_id, bill_line_id, claim_id, bill_version, line_no, description, category, category_source, category_confidence,"
            " ward_context, room_category, service_date, invoice_no, quantity, unit_rate_paise, billed_paise, evidence)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::date,$13,$14::numeric,$15,$16,$17::jsonb)",
            tenant_id, new_id("BLN"), claim_id, version, it["line_no"], desc, cat, src, round(conf, 3), ward,
            room_category(desc, cat, cmap), it.get("service_date"), it.get("invoice_no"), qty,
            to_paise(it["unit_rate"]) if it.get("unit_rate") else None, to_paise(it["amount"]),
            Json([{**f["evidence"]}]))
    return {"bill_version": version, "lines": len(items), "changed": True}


def run_reconcile(conn: Conn, tenant_id: str, claim_id: str) -> dict:
    facts = resolve_claim(conn, tenant_id, claim_id)
    bill = sync_bill_lines(conn, tenant_id, claim_id)
    pending = conn.fetch_val("SELECT count(*) FROM document WHERE tenant_id=$1 AND claim_id=$2 AND status IN ('RECEIVED','STORED','CLASSIFYING','CLASSIFIED','EXTRACTING')",
                             tenant_id, claim_id)
    queued = None
    if not pending:
        token = conn.fetch_val("SELECT count(*)::text || ':' || coalesce(max(created_at)::text,'') FROM extracted_fact WHERE tenant_id=$1 AND claim_id=$2",
                               tenant_id, claim_id)
        rev = conn.fetch_val("SELECT count(*) FROM reviewer_action WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id)
        queued = jobs.enqueue(conn, tenant_id, "EVALUATE", claim_id, f"evaluate:{claim_id}:{token}:{rev}", {"trigger": "NEW_EVIDENCE"})
    return {"facts": {k: v[0] for k, v in facts.items()}, "bill": bill, "documents_pending": pending, "evaluation_job": queued}
