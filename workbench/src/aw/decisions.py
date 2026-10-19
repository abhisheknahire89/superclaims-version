"""Decisions, second approval, sum-insured reservation and the settlement worksheet (CAP-17, CAP-19).

A decision is recorded only by a person, against the current non-stale evaluation. Second approval is required when
any rule in the tenant's workflow config fires (config/workflow-*.json -> approval.second_approval_required_when):
  PAYABLE_ABOVE_APPROVER_LIMIT, DEVIATION_FROM_RECOMMENDATION_ABOVE (amount), TOTAL_DEDUCTIONS_ABOVE_SHARE_OF_BILLED (percent).
Repudiation needs an insurer CRC reference and communicated_by = INSURER; for a TPA tenant the workflow config fixes
repudiation to RECORD_INSURER_OUTCOME_ONLY, so AW records the insurer's outcome and produces no repudiation letter (E-REG-04).
Approvals reserve the approved amount in the SI ledger in the same transaction (05 §1.4); if it would overdraw the
available sum insured the decision fails with 409.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import AppError
from . import audit, configs, jobs
from .auth import Forbidden, Principal
from .db import Conn, Json
from .ids import new_id
from .money import from_paise, to_paise

APPROVALS = ("APPROVED_FULL", "APPROVED_PARTIAL")
DECIDABLE_STATES = ("READY_FOR_REVIEW", "IN_REVIEW", "MEDICAL_REVIEW", "ESCALATED_CRC")
GRIEVANCE_PLACEHOLDER = {  # customer-supplied per tenant before go-live; placeholders mark what the letter must contain (E-REG-04)
    "insurer_grievance_procedure": "<customer-supplied: insurer's grievance redressal procedure; complaints may also be registered on IRDAI's Bima Bharosa portal>",
    "grievance_officer_contact": "<customer-supplied: grievance redressal office and officer contact>",
    "ombudsman_procedure": "<customer-supplied: procedure to approach the Insurance Ombudsman if not satisfied>",
    "ombudsman_contact": "<customer-supplied: office of the Insurance Ombudsman for the policyholder's jurisdiction>",
}


class DecisionError(AppError):
    pass


@lru_cache(maxsize=2)
def _ws_validator(schema_dir: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((Path(schema_dir) / "settlement-worksheet.schema.json").read_text(encoding="utf-8")))


def _workflow_cfg(conn: Conn, tenant_id: str) -> dict:
    cfg = configs.effective(conn, tenant_id, "WORKFLOW_CONFIG", date.today())
    if not cfg:
        raise DecisionError(500, "workflow-config-missing", "no published workflow configuration")
    return cfg


def _load(conn: Conn, tenant_id: str, claim_id: str, evaluation_id: str, lock: bool = True):
    claim = conn.fetch_one("SELECT c.*, t.tenant_kind FROM claim c JOIN tenant t ON t.tenant_id=c.tenant_id WHERE c.tenant_id=$1 AND c.claim_id=$2"
                           + (" FOR UPDATE OF c" if lock else ""), tenant_id, claim_id)
    if not claim:
        raise DecisionError(404, "claim-not-found", "claim not found")
    ev = conn.fetch_one("SELECT * FROM evaluation WHERE tenant_id=$1 AND evaluation_id=$2 AND claim_id=$3", tenant_id, evaluation_id, claim_id)
    if not ev:
        raise DecisionError(404, "evaluation-not-found", "evaluation not found")
    if ev["evaluation_id"] != claim["current_evaluation_id"] or ev["status"] in ("STALE", "SUPERSEDED", "FAILED", "RUNNING"):
        raise DecisionError(409, "evaluation-stale", "the evaluation is not current; open the latest evaluation",
                            {"current_evaluation_id": claim["current_evaluation_id"]})
    return claim, ev


def second_approval_triggers(cfg: dict, principal: Principal, ev: dict, approved_paise: int | None) -> list[str]:
    fired = []
    billed = ev["billed_total_paise"] or 0
    recommended = ev["recommended_payable_paise"]
    for rule in cfg["approval"]["second_approval_required_when"]:
        r = rule["rule"]
        if r == "PAYABLE_ABOVE_APPROVER_LIMIT" and approved_paise is not None:
            if principal.approval_limit_paise is None or approved_paise > principal.approval_limit_paise:
                fired.append(r)
        elif r == "DEVIATION_FROM_RECOMMENDATION_ABOVE" and approved_paise is not None and recommended is not None:
            if abs(approved_paise - recommended) > to_paise(rule["amount"]):
                fired.append(r)
        elif r == "TOTAL_DEDUCTIONS_ABOVE_SHARE_OF_BILLED" and approved_paise is not None and billed:
            if (billed - approved_paise) * 100 > Decimal(rule["percent"]) * billed:
                fired.append(r)
    return fired


def _preconditions(conn: Conn, p: Principal, claim: dict, ev: dict, body: dict) -> int | None:
    disp = body["disposition"]
    if claim['workflow']=='ENHANCEMENT' and disp in APPROVALS:
        prior=conn.fetch_val('SELECT approved_payable_paise FROM decision WHERE tenant_id=$1 AND claim_id=$2 ORDER BY decided_at DESC LIMIT 1',p.tenant_id,claim['parent_claim_id'])
        if to_paise(body['approved_payable'])<prior:raise DecisionError(422,'enhancement-below-authorisation','enhancement amount is cumulative and cannot be below previous authorisation')
    if claim["status"] not in DECIDABLE_STATES + ("PENDING_APPROVAL",):
        raise DecisionError(409, "claim-not-decidable", f"claim is {claim['status']}")
    if claim["investigation_hold"]:
        raise DecisionError(409, "investigation-hold", "an investigation hold is in place")
    approved = None
    if disp in APPROVALS:
        p.require("decision.approve")
        if ev["status"] != "COMPUTED":
            raise DecisionError(409, "evaluation-blocked", "no payable was computed; resolve the blocking findings first")
        open_blocking = conn.fetch_val("SELECT count(*) FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND blocking AND status IN ('OPEN','ACKNOWLEDGED')",
                                       p.tenant_id, claim["claim_id"])
        open_mo = conn.fetch_val("SELECT count(*) FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND route_to='MEDICAL_OFFICER' AND status IN ('OPEN','ACKNOWLEDGED')",
                                 p.tenant_id, claim["claim_id"])
        if open_blocking or open_mo:
            raise DecisionError(409, "open-findings", "blocking or medical-officer findings are still open",
                                {"blocking": open_blocking, "medical_officer": open_mo})
        approved = to_paise(body["approved_payable"])
        if approved < 0 or approved > (ev["billed_total_paise"] or 0):
            raise DecisionError(422, "bad-amount", "approved amount must be between 0 and the billed total")
        if disp == "APPROVED_FULL" and approved != ev["billed_total_paise"]:
            raise DecisionError(422, "not-full", "APPROVED_FULL must equal the billed total")
        if approved != ev["recommended_payable_paise"] and not body.get("deviation_reason"):
            raise DecisionError(422, "deviation-reason-required", "explain why the approved amount differs from the recommendation")
    elif disp == "REPUDIATED_WITH_CRC_APPROVAL":
        p.require("decision.repudiate")
        if not body.get("crc_reference") or body.get("communicated_by") != "INSURER":
            raise DecisionError(422, "crc-required", "repudiation needs the insurer's CRC reference and communicated_by = INSURER")
        if claim["status"] != "ESCALATED_CRC":
            raise DecisionError(409, "not-escalated", "escalate to the CRC first")
    elif disp == "CLOSED_DUPLICATE":
        p.require("decision.close_duplicate")
        if not body.get("duplicate_of_claim_id"):
            raise DecisionError(422, "duplicate-ref-required", "name the claim this duplicates")
    elif disp == "WITHDRAWN":
        p.require("claim.withdraw")
    return approved


def decide(conn: Conn, p: Principal, schema_dir: Path, claim_id: str, body: dict) -> dict:
    """Record a decision within the user's authority, or answer 409 'second-approval-required' with the triggers."""
    claim, ev = _load(conn, p.tenant_id, claim_id, body["evaluation_id"])
    approved = _preconditions(conn, p, claim, ev, body)
    if body["disposition"] in APPROVALS:
        triggers = second_approval_triggers(_workflow_cfg(conn, p.tenant_id), p, ev, approved)
        if triggers:
            raise DecisionError(409, "second-approval-required", "a second approver is required", {"triggers": triggers})
    return _write_decision(conn, p.tenant_id, schema_dir, claim, ev, body, decided_by=p.user_id, second_approver=None, approved=approved)


def request_approval(conn: Conn, p: Principal, claim_id: str, body: dict) -> dict:
    claim, ev = _load(conn, p.tenant_id, claim_id, body["evaluation_id"])
    approved = _preconditions(conn, p, claim, ev, {**body, "disposition": body["proposed_disposition"], "approved_payable": body["proposed_payable"]})
    triggers = second_approval_triggers(_workflow_cfg(conn, p.tenant_id), p, ev, approved)
    if body["approver_user_id"] == p.user_id:
        raise DecisionError(422, "self-approval", "the second approver must be someone else")
    approver = conn.fetch_one("SELECT 1 FROM role_assignment WHERE tenant_id=$1 AND user_id=$2 AND role='SUPERVISOR' AND (valid_to IS NULL OR valid_to > now())",
                              p.tenant_id, body["approver_user_id"])
    if not approver:
        raise DecisionError(422, "bad-approver", "the second approver must be an active supervisor")
    arid = new_id("APR")
    conn.execute("INSERT INTO approval_request (tenant_id, approval_request_id, claim_id, evaluation_id, proposed_disposition, proposed_payable_paise,"
                 " requested_by, approver, triggers, comment) VALUES ($1,$2,$3,$4,$5::disposition_type,$6,$7,$8,$9::text[],$10)",
                 p.tenant_id, arid, claim_id, ev["evaluation_id"], body["proposed_disposition"], approved, p.user_id, body["approver_user_id"],
                 triggers or ["REQUESTED_BY_REVIEWER"], body.get("deviation_reason"))
    conn.execute("UPDATE claim SET status='PENDING_APPROVAL', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, claim_id)
    audit.append(conn, p.tenant_id, claim_id, p.actor, "APPROVAL_REQUESTED", {"approval_request_id": arid, "approver": body["approver_user_id"],
                                                                               "triggers": triggers, "proposed_payable": f"{from_paise(approved):.2f}"})
    return {"approval_request_id": arid, "triggers": triggers, "state": "PENDING"}


def _pending(conn: Conn, p: Principal, arid: str) -> dict:
    ar = conn.fetch_one("SELECT * FROM approval_request WHERE tenant_id=$1 AND approval_request_id=$2 FOR UPDATE", p.tenant_id, arid)
    if not ar:
        raise DecisionError(404, "approval-not-found", "approval request not found")
    if ar["state"] != "PENDING":
        raise DecisionError(409, "approval-closed", f"request is {ar['state']}")
    if ar["approver"] != p.user_id:
        raise Forbidden("only the named approver can act on this request")
    p.require("decision.second_approve")
    return ar


def approve_request(conn: Conn, p: Principal, schema_dir: Path, arid: str, comment: str | None = None) -> dict:
    ar = _pending(conn, p, arid)
    claim, ev = _load(conn, p.tenant_id, ar["claim_id"], ar["evaluation_id"])
    if ar["proposed_payable_paise"] is not None and (p.approval_limit_paise is None or ar["proposed_payable_paise"] > p.approval_limit_paise):
        raise Forbidden("the approved amount is above the approver's own limit")
    conn.execute("UPDATE approval_request SET state='APPROVED', decided_at=now(), comment=coalesce($3, comment) WHERE tenant_id=$1 AND approval_request_id=$2",
                 p.tenant_id, arid, comment)
    audit.append(conn, p.tenant_id, ar["claim_id"], p.actor, "APPROVAL_GRANTED", {"approval_request_id": arid})
    body = {"disposition": ar["proposed_disposition"], "evaluation_id": ar["evaluation_id"], "deviation_reason": ar["comment"]}
    return _write_decision(conn, p.tenant_id, schema_dir, claim, ev, body, decided_by=ar["requested_by"], second_approver=p.user_id,
                           approved=ar["proposed_payable_paise"])


def return_request(conn: Conn, p: Principal, arid: str, comment: str) -> dict:
    if not comment:
        raise DecisionError(422, "comment-required", "say why the decision is returned")
    ar = _pending(conn, p, arid)
    conn.execute("UPDATE approval_request SET state='RETURNED', decided_at=now(), comment=$3 WHERE tenant_id=$1 AND approval_request_id=$2",
                 p.tenant_id, arid, comment)
    conn.execute("UPDATE claim SET status='IN_REVIEW', row_version=row_version+1 WHERE tenant_id=$1 AND claim_id=$2", p.tenant_id, ar["claim_id"])
    audit.append(conn, p.tenant_id, ar["claim_id"], p.actor, "APPROVAL_RETURNED", {"approval_request_id": arid})
    return {"approval_request_id": arid, "state": "RETURNED"}


def _reserve_si(conn: Conn, tenant_id: str, claim: dict, ev: dict, approved: int):
    pm = conn.fetch_one("SELECT * FROM policy_member WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3 FOR UPDATE",
                        tenant_id, claim["policy_no"], claim["member_id"])
    pol = conn.fetch_one("SELECT period_start, config_artifact_id, config_version FROM policy WHERE tenant_id=$1 AND policy_no=$2", tenant_id, claim["policy_no"])
    cfg = configs.get(conn, tenant_id, pol["config_artifact_id"], pol["config_version"])
    from .workflows import group_claims
    group=group_claims(conn,tenant_id,claim)
    for cid in group:
        rows0=conn.fetch_all("SELECT entry_kind,sum(amount_paise) AS amount FROM si_ledger_entry WHERE tenant_id=$1 AND claim_id=$2 AND policy_year_start=$3 GROUP BY entry_kind",tenant_id,cid,pol['period_start'])
        amounts={r['entry_kind']:int(r['amount']) for r in rows0};release=amounts.get('RESERVED',0)-amounts.get('RELEASED',0)
        if release>0:conn.execute("INSERT INTO si_ledger_entry (tenant_id,policy_no,member_id,policy_year_start,claim_id,entry_kind,amount_paise) VALUES ($1,$2,$3,$4,$5,'RELEASED',$6)",tenant_id,claim['policy_no'],claim['member_id'],pol['period_start'],cid,release)
    if claim['workflow'].startswith('OPD'):
        benefit=cfg.get('opd_benefit')
        rows1=conn.fetch_all("SELECT l.entry_kind,sum(l.amount_paise) AS amount FROM si_ledger_entry l JOIN claim c ON c.tenant_id=l.tenant_id AND c.claim_id=l.claim_id WHERE l.tenant_id=$1 AND l.policy_no=$2 AND l.member_id=$3 AND l.policy_year_start=$4 AND c.workflow IN ('OPD_REIMBURSEMENT','OPD_CASHLESS') GROUP BY l.entry_kind",tenant_id,claim['policy_no'],claim['member_id'],pol['period_start'])
        values={r['entry_kind']:int(r['amount']) for r in rows1};used_opd=values.get('RESERVED',0)+values.get('PAID',0)-values.get('RELEASED',0)
        if not benefit or approved>min(to_paise(benefit['per_claim_limit']),to_paise(benefit['annual_limit'])-used_opd):raise DecisionError(409,'opd-benefit-exhausted','re-evaluate OPD benefit balance')
    rows = conn.fetch_all("SELECT entry_kind, sum(amount_paise) AS s FROM si_ledger_entry WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3"
                          " AND policy_year_start=$4 GROUP BY entry_kind", tenant_id, claim["policy_no"], claim["member_id"], pol["period_start"])
    s = {r["entry_kind"]: int(r["s"]) for r in rows}
    used = s.get("OPENING_PAID_EXTERNAL", 0) + s.get("PAID", 0) + s.get("RESERVED", 0) - s.get("RELEASED", 0)
    cb = pm["cumulative_bonus_paise"] if cfg["sum_insured"]["cumulative_bonus_counts_toward_available_si"] else 0
    available = pm["base_sum_insured_paise"] + cb - used
    if approved > available:
        raise DecisionError(409, "si-exhausted", "the approved amount exceeds the available sum insured (another claim may have used it); re-evaluate",
                            {"available": f"{from_paise(available):.2f}"})
    conn.execute("INSERT INTO si_ledger_entry (tenant_id, policy_no, member_id, policy_year_start, claim_id, entry_kind, amount_paise)"
                 " VALUES ($1,$2,$3,$4,$5,'RESERVED',$6)", tenant_id, claim["policy_no"], claim["member_id"], pol["period_start"], claim["claim_id"], approved)


def worksheet(claim: dict, ev: dict, decision: dict, approved: int | None) -> dict:
    out = ev["result"]
    billed = from_paise(ev["billed_total_paise"])
    appr = from_paise(approved) if approved is not None else Decimal("0.00")
    dis = [{"line_id": a["line_id"] or "CLAIM", "amount": a["amount"], "reason": a["explanation"],
            "clause": f"{a['authority']['doc_id']} {a['authority']['clause']}", "rule_id": a["rule_id"]}
           for a in out["adjustments"] if Decimal(a["amount"]) != 0]
    if decision["disposition"] in APPROVALS and approved is not None and approved != ev["recommended_payable_paise"]:
        dev = from_paise(ev["recommended_payable_paise"]) - appr
        dis.append({"line_id": "CLAIM", "amount": f"{dev:.2f}", "reason": f"Reviewer decision differs from the recommendation: {decision.get('deviation_reason')}",
                    "clause": "Reviewer decision (see reason)", "rule_id": "REVIEWER_DECISION"})
    return {
        "worksheet_id": f"WS-{decision['decision_id']}",
        "claim_id": claim["claim_id"],
        "decision": {"decision_id": decision["decision_id"], "disposition": decision["disposition"], "decided_by": decision["decided_by"],
                     "second_approver": decision.get("second_approver"), "evaluation_id": ev["evaluation_id"]},
        "amounts": {"claimed": f"{billed:.2f}", "billed": f"{billed:.2f}", "approved": f"{appr:.2f}", "disallowed_total": f"{billed - appr:.2f}"},
        "disallowances": dis,
        "line_table": [{"line_id": l["line_id"], "description": l["description"], "billed": l["billed"], "payable": l["payable"]} for l in out["lines"]],
        "grievance_route": GRIEVANCE_PLACEHOLDER,
        "provenance": {"engine_version": out["engine_version"], "config_versions": out["config_versions"], "output_hash": out["output_hash"]},
    }


def _write_decision(conn: Conn, tenant_id: str, schema_dir: Path, claim: dict, ev: dict, body: dict, *, decided_by: str,
                    second_approver: str | None, approved: int | None) -> dict:
    disp = body["disposition"]
    did = new_id("DEC")
    cfg = _workflow_cfg(conn, tenant_id)
    communicated_by = body.get("communicated_by") or ("INSURER" if disp == "REPUDIATED_WITH_CRC_APPROVAL" else "TPA" if claim["tenant_kind"] == "TPA" else "INSURER")
    if disp in APPROVALS:
        _reserve_si(conn, tenant_id, claim, ev, approved)
    dev = None if approved is None or ev["recommended_payable_paise"] is None else approved - ev["recommended_payable_paise"]
    decision = {"decision_id": did, "disposition": disp, "decided_by": decided_by, "second_approver": second_approver,
                "deviation_reason": body.get("deviation_reason")}
    ws = None
    # TPA tenants: repudiation is the insurer's decision and communication; no letter or worksheet is produced here
    produce_ws = disp in APPROVALS or disp in ("WITHDRAWN", "CLOSED_DUPLICATE")
    if produce_ws and ev["result"]:
        ws = worksheet(claim, ev, decision, approved if disp in APPROVALS else None)
        if disp not in APPROVALS:
            ws["amounts"]["approved"] = "0.00"
            ws["amounts"]["disallowed_total"] = ws["amounts"]["billed"]
            ws["disallowances"] = []
        errs = [e.message for e in _ws_validator(str(schema_dir)).iter_errors(ws)]
        if errs:
            raise DecisionError(500, "worksheet-invalid", "worksheet failed schema validation", {"errors": errs[:3]})
        if disp in APPROVALS:
            total = sum(Decimal(d["amount"]) for d in ws["disallowances"])
            if total != Decimal(ws["amounts"]["disallowed_total"]):
                raise DecisionError(500, "worksheet-unreconciled", "disallowances do not add up to billed minus approved")
    conn.execute("INSERT INTO decision (tenant_id, decision_id, claim_id, evaluation_id, disposition, approved_payable_paise, decided_by, second_approver,"
                 " crc_reference, communicated_by, duplicate_of_claim_id, deviation_from_recommendation_paise, worksheet)"
                 " VALUES ($1,$2,$3,$4,$5::disposition_type,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)",
                 tenant_id, did, claim["claim_id"], ev["evaluation_id"], disp, approved, decided_by, second_approver, body.get("crc_reference"),
                 communicated_by, body.get("duplicate_of_claim_id"), dev, Json(ws))
    from .workflows import assert_transition
    assert_transition(claim["workflow"],claim["status"],"WITHDRAWN" if disp=="WITHDRAWN" else "FINALISED")
    new_status = "WITHDRAWN" if disp == "WITHDRAWN" else "FINALISED"
    conn.execute("UPDATE claim SET status=$3::claim_status, row_version=row_version+1, updated_at=now() WHERE tenant_id=$1 AND claim_id=$2",
                 tenant_id, claim["claim_id"], new_status)
    audit.append(conn, tenant_id, claim["claim_id"], f"USER:{second_approver or decided_by}", "DECISION_RECORDED",
                 {"decision_id": did, "disposition": disp, "approved_payable": None if approved is None else f"{from_paise(approved):.2f}",
                  "decided_by": decided_by, "second_approver": second_approver,
                  "repudiation_behaviour": cfg["repudiation"]["behaviour"] if disp == "REPUDIATED_WITH_CRC_APPROVAL" else None})
    if disp == "REPUDIATED_WITH_CRC_APPROVAL":
        audit.append(conn, tenant_id, claim["claim_id"], f"USER:{decided_by}", "CRC_OUTCOME_RECORDED", {"outcome": "APPROVED", "crc_reference": body.get("crc_reference")})
    if ws:
        audit.append(conn, tenant_id, claim["claim_id"], "SYSTEM", "SETTLEMENT_WORKSHEET_EXPORTED", {"decision_id": did, "worksheet_id": ws["worksheet_id"]})
        conn.execute("INSERT INTO export_record (tenant_id, export_id, claim_id, decision_id, target, payload_sha256, state) VALUES ($1,$2,$3,$4,'TMS',$5,'PENDING')",
                     tenant_id, new_id("EXP"), claim["claim_id"], did, __import__("hashlib").sha256(json.dumps(ws, sort_keys=True).encode()).hexdigest())
        jobs.enqueue(conn, tenant_id, "EXPORT", did, f"export:{did}:TMS", {"claim_id": claim["claim_id"]})
    return {"decision_id": did, "disposition": disp, "approved_payable": None if approved is None else f"{from_paise(approved):.2f}",
            "second_approver": second_approver, "worksheet_id": ws["worksheet_id"] if ws else None, "claim_status": new_status}
