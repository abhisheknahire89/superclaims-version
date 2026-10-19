"""Reviewer actions (CAP-15, CAP-05, CAP-07). Every action is an append-only reviewer_action row plus an audit
event. Actions that change rule inputs mark the current evaluation STALE and queue a new evaluation; the reviewer
sees a 'What changed' diff when it completes.

Permissions follow 03 §4 (aw.auth.PERMISSIONS). Comments are mandatory where the DB says so (overrides, dismissals)
and when a conflict is resolved against the majority of sources.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .errors import AppError
from . import audit, jobs
from .auth import Forbidden, Principal
from .db import Conn, Json
from .extraction import normalise as N
from .facts import latest_facts
from .ids import new_id
from .ingest import mark_stale
from .money import from_paise, to_paise

LINE_CATEGORIES = {"ROOM", "ICU_ROOM", "NURSING", "PROFESSIONAL_FEES", "OT_CHARGES", "PROCEDURE_CHARGES", "PHARMACY", "CONSUMABLES",
                   "IMPLANTS", "DIAGNOSTICS", "OTHER_HOSPITAL_SERVICES"}
DATE_FIELDS = {"admission.date", "discharge.date"}
AMOUNT_FIELDS = {"bill.total"}
CORRECTABLE = {"admission.date", "discharge.date", "bill.number", "bill.total", "diagnosis.primary_text", "procedure.text",
               "history.past_illness_text"}


class ReviewError(AppError):
    pass


def _record(conn: Conn, p: Principal, claim_id: str, action: str, target: dict, before, after, reason_code: str, comment: str | None,
            evaluation_id: str | None) -> str:
    ra = new_id("RA")
    conn.execute("INSERT INTO reviewer_action (tenant_id, reviewer_action_id, claim_id, evaluation_id, actor_user_id, action, target_ref, before_value,"
                 " after_value, reason_code, comment) VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb,$10,$11)",
                 p.tenant_id, ra, claim_id, evaluation_id, p.user_id, action, Json(target), Json(before), Json(after), reason_code, comment)
    audit.append(conn, p.tenant_id, claim_id, p.actor, "REVIEWER_ACTION_RECORDED",
                 {"reviewer_action_id": ra, "action": action, "target": target, "reason_code": reason_code})
    return ra


def _requeue(conn: Conn, p: Principal, claim_id: str, ra: str, reason: str, reconcile: bool = False):
    mark_stale(conn, p.tenant_id, claim_id, p.actor, reason)
    if reconcile:
        jobs.enqueue(conn, p.tenant_id, "RECONCILE", claim_id, f"reconcile:{claim_id}:{ra}", {})
    else:
        jobs.enqueue(conn, p.tenant_id, "EVALUATE", claim_id, f"evaluate:{claim_id}:{ra}", {"trigger": "REVIEWER_CORRECTION"})


def _check_value(field: str, value):
    if field in DATE_FIELDS:
        v = N.to_date(str(value))
        if not v:
            raise ReviewError(422, "bad-value", f"{field} must be a date (YYYY-MM-DD)")
        return v
    if field in AMOUNT_FIELDS:
        v = N.amount(str(value))
        if not v:
            raise ReviewError(422, "bad-value", f"{field} must be an amount like 1234.50")
        return v
    if not str(value).strip():
        raise ReviewError(422, "bad-value", "value required")
    return str(value).strip()


def record(conn: Conn, p: Principal, claim_id: str, body: dict) -> dict:
    claim = conn.fetch_one("SELECT * FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE", p.tenant_id, claim_id)
    if not claim:
        raise ReviewError(404, "claim-not-found", "claim not found")
    if claim["status"] in ("FINALISED","EXPORTED","WITHDRAWN"):
        raise ReviewError(409,"claim-closed","reopen the claim before changing its review")
    if body.get("evaluation_id") and body["evaluation_id"]!=claim["current_evaluation_id"]:
        raise ReviewError(409,"stale-evaluation","review the current evaluation")
    action, target = body["action"], body["target"]
    after, reason, comment = body.get("after_value") or {}, body["reason_code"], body.get("comment")
    eval_id = body.get("evaluation_id") or claim["current_evaluation_id"]
    handler = HANDLERS.get(action)
    if handler is None:
        raise ReviewError(422, "unsupported-action", f"{action} is not supported in this release")
    return handler(conn, p, claim, target, after, reason, comment, eval_id)


# ---------------------------------------------------------------- facts and conflicts
def _resolve(conn, p, claim, target, after, reason, comment, eval_id, basis: str):
    p.require("fact.correct")
    field = target["id"]
    if field not in CORRECTABLE:
        raise ReviewError(422, "not-correctable", f"{field} cannot be corrected here")
    value = _check_value(field, after.get("value"))
    obs = latest_facts(conn, p.tenant_id, claim["claim_id"], field)
    if basis == "REVIEWER_SELECTED":
        counts = Counter(str(f["normalised_value"]) for f in obs)
        if obs and counts.get(value, 0) * 2 < len(obs) and not comment:
            raise ReviewError(422, "comment-required", "a comment is required when the chosen value contradicts most sources")
        sources = [f["fact_id"] for f in obs if str(f["normalised_value"]) == value]
        if after.get("evidence_fact_id"):
            sources = sorted(set(sources) | {after["evidence_fact_id"]})
    else:
        sources = [f["fact_id"] for f in obs if str(f["normalised_value"]) == value]
    valid_sources = {f["fact_id"] for f in obs if str(f["normalised_value"]) == value}
    if not sources or not set(sources) <= valid_sources:
        raise ReviewError(422, "ungrounded-correction", "choose a grounded source value or enter a reading with a source page quote")
    current = conn.fetch_one("SELECT * FROM resolved_fact WHERE tenant_id=$1 AND claim_id=$2 AND field_path=$3 AND is_active",
                             p.tenant_id, claim["claim_id"], field)
    ra = _record(conn, p, claim["claim_id"], "RESOLVE_CONFLICT" if basis == "REVIEWER_SELECTED" else "CORRECT_FACT", target,
                 {"value": current["value"] if current else None, "basis": current["basis"] if current else None}, {"value": value}, reason, comment, eval_id)
    if current:
        conn.execute("UPDATE resolved_fact SET is_active=false WHERE tenant_id=$1 AND resolved_fact_id=$2", p.tenant_id, current["resolved_fact_id"])
    conn.execute("INSERT INTO resolved_fact (tenant_id, resolved_fact_id, claim_id, field_path, value, basis, source_fact_ids, reviewer_action_id)"
                 " VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7::text[],$8)", p.tenant_id, new_id("RSF"), claim["claim_id"], field, Json(value), basis, sources, ra)
    if field in DATE_FIELDS:
        col = "admission_date" if field == "admission.date" else "discharge_date"
        conn.execute(f"UPDATE claim SET {col}=$3::date WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim["claim_id"], value)
    _requeue(conn, p, claim["claim_id"], ra, "REVIEWER_CORRECTION")
    return {"reviewer_action_id": ra, "field": field, "value": value, "basis": basis}


def correct_fact(conn, p, claim, target, after, reason, comment, eval_id):
    return _resolve(conn, p, claim, target, after, reason, comment, eval_id, "REVIEWER_ENTERED")


def resolve_conflict(conn, p, claim, target, after, reason, comment, eval_id):
    return _resolve(conn, p, claim, target, after, reason, comment, eval_id, "REVIEWER_SELECTED")


# ---------------------------------------------------------------- documents and lines
def reclassify_document(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("fact.correct")
    doc = conn.fetch_one("SELECT document_id, classified_type FROM document WHERE tenant_id=$1 AND document_id=$2 AND claim_id=$3",
                         p.tenant_id, target["id"], claim["claim_id"])
    if not doc:
        raise ReviewError(404, "document-not-found", "document not found")
    ra = _record(conn, p, claim["claim_id"], "RECLASSIFY_DOCUMENT", target, {"document_type": doc["classified_type"]},
                 {"document_type": after["document_type"]}, reason, comment, eval_id)
    mark_stale(conn, p.tenant_id, claim["claim_id"], p.actor, "REVIEWER_CORRECTION")
    jobs.enqueue(conn, p.tenant_id, "EXTRACT", doc["document_id"], f"extract:{doc['document_id']}:{ra}", {"claim_id": claim["claim_id"]})
    return {"reviewer_action_id": ra}


def mark_page_unreadable(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("fact.correct")
    ra = _record(conn, p, claim["claim_id"], "MARK_PAGE_UNREADABLE", target, None, after, reason, comment, eval_id)
    doc_id, page_no = target["id"].rsplit(":", 1)
    conn.execute("UPDATE document_page SET quality_score=0 WHERE tenant_id=$1 AND document_id=$2 AND page_no=$3", p.tenant_id, doc_id, int(page_no))
    conn.execute("UPDATE document SET status='NEEDS_REVIEW' WHERE tenant_id=$1 AND document_id=$2", p.tenant_id, doc_id)
    return {"reviewer_action_id": ra}


def reclassify_line(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("line.reclassify")
    cat = after.get("category")
    if cat not in LINE_CATEGORIES:
        raise ReviewError(422, "bad-category", f"category must be one of {sorted(LINE_CATEGORIES)}")
    line = conn.fetch_one("SELECT * FROM bill_line WHERE tenant_id=$1 AND bill_line_id=$2 AND claim_id=$3 AND is_active",
                          p.tenant_id, target["id"], claim["claim_id"])
    if not line:
        raise ReviewError(404, "line-not-found", "active bill line not found")
    ra = _record(conn, p, claim["claim_id"], "RECLASSIFY_LINE", target, {"category": line["category"]}, {"category": cat}, reason, comment, eval_id)
    # new bill version: history keeps the old categorisation that earlier evaluations used
    lines = conn.fetch_all("SELECT * FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active", p.tenant_id, claim["claim_id"])
    version = (conn.fetch_val("SELECT max(bill_version) FROM bill_line WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim["claim_id"]) or 0) + 1
    conn.execute("UPDATE bill_line SET is_active=false WHERE tenant_id=$1 AND claim_id=$2 AND is_active", p.tenant_id, claim["claim_id"])
    for l in lines:
        changed = l["bill_line_id"] == line["bill_line_id"]
        conn.execute(
            "INSERT INTO bill_line (tenant_id, bill_line_id, claim_id, bill_version, line_no, description, category, category_source, category_confidence,"
            " ward_context, room_category, service_date, invoice_no, quantity, unit_rate_paise, billed_paise, evidence)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17::jsonb)",
            p.tenant_id, new_id("BLN"), claim["claim_id"], version, l["line_no"], l["description"], cat if changed else l["category"],
            "REVIEWER" if changed else l["category_source"], 1.0 if changed else l["category_confidence"], l["ward_context"], l["room_category"],
            l["service_date"], l["invoice_no"], l["quantity"], l["unit_rate_paise"], l["billed_paise"], Json(l["evidence"]))
    _requeue(conn, p, claim["claim_id"], ra, "REVIEWER_CORRECTION")
    return {"reviewer_action_id": ra, "bill_version": version}


# ---------------------------------------------------------------- adjustments
def override_adjustment(conn, p, claim, target, after, reason, comment, eval_id, remove: bool = False):
    p.require("adjustment.override")
    if not comment:
        raise ReviewError(422, "comment-required", "overrides need a comment")
    adj = conn.fetch_one("SELECT a.*, r.rule_id, e.result, e.claim_id, e.status AS eval_status, b.line_no FROM adjustment a"
                         " JOIN rule_execution r ON r.tenant_id=a.tenant_id AND r.rule_execution_id=a.rule_execution_id"
                         " JOIN evaluation e ON e.tenant_id=a.tenant_id AND e.evaluation_id=a.evaluation_id"
                         " LEFT JOIN bill_line b ON b.tenant_id=a.tenant_id AND b.bill_line_id=a.bill_line_id"
                         " WHERE a.tenant_id=$1 AND a.adjustment_id=$2", p.tenant_id, target["id"])
    if not adj or adj["claim_id"] != claim["claim_id"]:
        raise ReviewError(404, "adjustment-not-found", "adjustment not found on this claim")
    if adj["evaluation_id"] != claim["current_evaluation_id"] or adj["eval_status"] in ("STALE", "SUPERSEDED"):
        raise ReviewError(409, "evaluation-stale", "override an adjustment of the current evaluation")
    if adj["level"] != "LINE" or adj["reason_code"] == "ROUNDING":
        raise ReviewError(422, "not-overridable", "only line-level adjustments can be overridden in this release")
    amount = Decimal("0") if remove else Decimal(str(after.get("amount")))
    if amount < 0 or to_paise(amount) > adj["base_before_paise"]:
        raise ReviewError(422, "bad-amount", f"override must be between 0 and {from_paise(adj['base_before_paise'])}")
    fp = next(l["fingerprint"] for l in adj["result"]["lines"] if l["line_id"] == adj["line_no"])
    ra = _record(conn, p, claim["claim_id"], "REMOVE_ADJUSTMENT" if remove else "OVERRIDE_ADJUSTMENT", target,
                 {"amount": f"{from_paise(adj['amount_paise']):.2f}"}, {"amount": f"{amount:.2f}"}, reason, comment, eval_id)
    bill_version = conn.fetch_val("SELECT bill_version FROM bill_line WHERE tenant_id=$1 AND bill_line_id=$2", p.tenant_id, adj["bill_line_id"])
    conn.execute("UPDATE adjustment_override SET is_active=false WHERE tenant_id=$1 AND claim_id=$2 AND line_no=$3 AND rule_id=$4 AND is_active",
                 p.tenant_id, claim["claim_id"], adj["line_no"], adj["rule_id"])
    oid = new_id("OVR")
    conn.execute("INSERT INTO adjustment_override (tenant_id, override_id, claim_id, line_no, bill_version, rule_id, amount_paise, line_fingerprint, reviewer_action_id)"
                 " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)", p.tenant_id, oid, claim["claim_id"], adj["line_no"], bill_version, adj["rule_id"],
                 to_paise(amount), fp, ra)
    _requeue(conn, p, claim["claim_id"], ra, "REVIEWER_CORRECTION")
    return {"reviewer_action_id": ra, "override_id": oid}


def remove_adjustment(conn, p, claim, target, after, reason, comment, eval_id):
    return override_adjustment(conn, p, claim, target, after, reason, comment, eval_id, remove=True)


# ---------------------------------------------------------------- findings
def _finding(conn, p, claim, target):
    f = conn.fetch_one("SELECT * FROM finding WHERE tenant_id=$1 AND finding_id=$2 AND claim_id=$3", p.tenant_id, target["id"], claim["claim_id"])
    if not f:
        raise ReviewError(404, "finding-not-found", "finding not found")
    return f


def _finding_status(conn, p, claim, target, after, reason, comment, eval_id, action: str, status: str):
    f = _finding(conn, p, claim, target)
    if f["blocking"] and status in ("RESOLVED", "DISMISSED"):
        raise ReviewError(409, "blocking-finding", "a blocking finding clears when its cause is fixed (resolve the conflict, correct the fact or add the document)")
    if f["category"] == "CLINICAL" and status in ("RESOLVED", "DISMISSED"):
        if "MEDICAL_OFFICER" not in p.roles:
            raise Forbidden("clinical findings are resolved by a medical officer")
    elif status == "DISMISSED" and f["category"] == "ANOMALY" and f["severity"] in ("HIGH", "CRITICAL"):
        p.require("finding.dismiss_high_anomaly")
    else:
        p.require("finding.resolve")
    if status == "DISMISSED" and not comment:
        raise ReviewError(422, "comment-required", "dismissing a finding needs a comment")
    ra = _record(conn, p, claim["claim_id"], action, target, {"status": f["status"]}, {"status": status, **after}, reason, comment, eval_id)
    conn.execute("UPDATE finding SET status=$3::finding_status, resolution=$4::jsonb WHERE tenant_id=$1 AND finding_id=$2", p.tenant_id, f["finding_id"],
                 status, Json({"by": p.user_id, "reason_code": reason, "comment": comment, "reviewer_action_id": ra, **after}))
    if f["category"] == "CLINICAL" and status == "RESOLVED":
        audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "MEDICAL_REVIEW_COMPLETED", {"finding_id": f["finding_id"], "outcome": after.get("outcome")})
        open_mo = conn.fetch_val("SELECT count(*) FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND route_to='MEDICAL_OFFICER' AND status='OPEN'",
                                 p.tenant_id, claim["claim_id"])
        if not open_mo and claim["status"] == "MEDICAL_REVIEW":
            conn.execute("UPDATE claim SET status='IN_REVIEW', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim["claim_id"])
    if f["category"] == "ANOMALY":
        audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "ANOMALY_TRIAGED", {"finding_id": f["finding_id"], "disposition": status})
    return {"reviewer_action_id": ra, "status": status}


def acknowledge_finding(conn, p, claim, target, after, reason, comment, eval_id):
    return _finding_status(conn, p, claim, target, after, reason, comment, eval_id, "ACKNOWLEDGE_FINDING", "ACKNOWLEDGED")


def resolve_finding(conn, p, claim, target, after, reason, comment, eval_id):
    return _finding_status(conn, p, claim, target, after, reason, comment, eval_id, "RESOLVE_FINDING", "RESOLVED")


def dismiss_finding(conn, p, claim, target, after, reason, comment, eval_id):
    return _finding_status(conn, p, claim, target, after, reason, comment, eval_id, "DISMISS_FINDING", "DISMISSED")


# ---------------------------------------------------------------- routing and holds
def _status(conn, p, claim_id, status):
    conn.execute("UPDATE claim SET status=$3::claim_status, updated_at=now(), row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2",
                 p.tenant_id, claim_id, status)


def escalate_medical(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("finding.resolve")
    ra = _record(conn, p, claim["claim_id"], "ESCALATE_MEDICAL", target, None, after, reason, comment, eval_id)
    _status(conn, p, claim["claim_id"], "MEDICAL_REVIEW")
    audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "MEDICAL_REVIEW_OPENED", {"finding_id": target.get("id")})
    return {"reviewer_action_id": ra, "claim_status": "MEDICAL_REVIEW"}


def escalate_crc(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("finding.resolve")
    if not comment:
        raise ReviewError(422, "comment-required", "explain why repudiation is proposed")
    ra = _record(conn, p, claim["claim_id"], "ESCALATE_CRC", target, None, after, reason, comment, eval_id)
    _status(conn, p, claim["claim_id"], "ESCALATED_CRC")
    return {"reviewer_action_id": ra, "claim_status": "ESCALATED_CRC"}


def record_crc_declined(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("decision.repudiate")
    if claim["status"] != "ESCALATED_CRC":
        raise ReviewError(409, "not-escalated", "claim is not with the CRC")
    if not after.get("crc_reference"):
        raise ReviewError(422, "crc-reference-required", "record the CRC reference")
    ra = _record(conn, p, claim["claim_id"], "RECORD_CRC_DECLINED", target, None, after, reason, comment, eval_id)
    _status(conn, p, claim["claim_id"], "IN_REVIEW")
    audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "CRC_OUTCOME_RECORDED", {"outcome": "DECLINED", "crc_reference": after["crc_reference"]})
    return {"reviewer_action_id": ra, "claim_status": "IN_REVIEW"}


def escalate_fwa(conn, p, claim, target, after, reason, comment, eval_id):
    p.require("finding.resolve")
    ra = _record(conn, p, claim["claim_id"], "ESCALATE_FWA", target, None, after, reason, comment, eval_id)
    audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "ANOMALY_TRIAGED", {"finding_id": target.get("id"), "disposition": "FORWARDED_TO_FWA"})
    return {"reviewer_action_id": ra}


def _hold(conn, p, claim, target, after, reason, comment, eval_id, place: bool):
    p.require("claim.hold")
    ra = _record(conn, p, claim["claim_id"], "PLACE_INVESTIGATION_HOLD" if place else "RELEASE_INVESTIGATION_HOLD", target,
                 {"hold": claim["investigation_hold"]}, {"hold": place}, reason, comment, eval_id)
    conn.execute("UPDATE claim SET investigation_hold=$3, row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim["claim_id"], place)
    audit.append(conn, p.tenant_id, claim["claim_id"], p.actor, "INVESTIGATION_HOLD_PLACED" if place else "INVESTIGATION_HOLD_RELEASED", {"reason_code": reason})
    return {"reviewer_action_id": ra, "investigation_hold": place}


def place_hold(conn, p, claim, target, after, reason, comment, eval_id):
    return _hold(conn, p, claim, target, after, reason, comment, eval_id, True)


def release_hold(conn, p, claim, target, after, reason, comment, eval_id):
    return _hold(conn, p, claim, target, after, reason, comment, eval_id, False)


HANDLERS = {
    "CORRECT_FACT": correct_fact, "RESOLVE_CONFLICT": resolve_conflict, "RECLASSIFY_DOCUMENT": reclassify_document,
    "MARK_PAGE_UNREADABLE": mark_page_unreadable, "RECLASSIFY_LINE": reclassify_line, "OVERRIDE_ADJUSTMENT": override_adjustment,
    "REMOVE_ADJUSTMENT": remove_adjustment, "ACKNOWLEDGE_FINDING": acknowledge_finding, "RESOLVE_FINDING": resolve_finding,
    "DISMISS_FINDING": dismiss_finding, "ESCALATE_MEDICAL": escalate_medical, "ESCALATE_CRC": escalate_crc, "ESCALATE_FWA": escalate_fwa,
    "PLACE_INVESTIGATION_HOLD": place_hold, "RELEASE_INVESTIGATION_HOLD": release_hold, "RECORD_CRC_DECLINED": record_crc_declined,
}
# Not in this release: ADD_ADJUSTMENT (use corrections or overrides), RETURN_FOR_REWORK (see aw.decisions.return_request).
