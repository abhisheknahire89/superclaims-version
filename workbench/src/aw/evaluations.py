"""EVALUATE job (CAP-11, CAP-14, CAP-18): assemble the engine input from resolved facts, confirmed bill lines,
the policy/member record, the SI ledger and the configuration effective on the admission date; run the engine;
persist the evaluation, rule executions, adjustments and findings; supersede the previous evaluation.

The engine input follows schemas/engine-input.schema.json (05 §1.6). Facts that failed the grounding check never
reach it. When a reviewer has resolved the admission-date conflict, only observations that agree with the
resolution (plus the reviewer's cited evidence) are passed on, exactly as in pack trace 3b.
"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from . import audit, configs
from .db import Conn, Json
from .engine import ENGINE_VERSION, ConfigurationError, evaluate
from .facts import latest_facts
from .ids import canonical_json, new_id
from .matching import normalise_name
from .money import from_paise, to_paise

IDENTITY_SOURCE_TYPES = None  # every active document with a patient name contributes an identity observation


class EvaluationError(Exception):
    pass


def _ev(f: dict) -> dict:
    e = f["evidence"]
    return {"document_id": e["document_id"], "page": e["page"], "bbox": e.get("bbox") or [0, 0, 0, 0], "quote": e["quote"]}


def available_si_inputs(conn: Conn, tenant_id: str, claim: dict, pm: dict, policy_row: dict) -> Decimal:
    rows = conn.fetch_all("SELECT entry_kind, sum(amount_paise) AS s FROM si_ledger_entry WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3"
                          " AND policy_year_start=$4 AND (claim_id IS NULL OR claim_id <> $5) GROUP BY entry_kind",
                          tenant_id, claim["policy_no"], claim["member_id"], policy_row["period_start"], claim["claim_id"])
    s = {r["entry_kind"]: int(r["s"]) for r in rows}
    used = s.get("OPENING_PAID_EXTERNAL", 0) + s.get("PAID", 0) + s.get("RESERVED", 0) - s.get("RELEASED", 0)
    return from_paise(max(used, 0))


def build_engine_input(conn: Conn, tenant_id: str, claim_id: str, evaluation_id: str) -> tuple[dict, dict]:
    claim = conn.fetch_one("SELECT * FROM claim WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id)
    member = conn.fetch_one("SELECT * FROM member WHERE tenant_id=$1 AND member_id=$2", tenant_id, claim["member_id"])
    policy_row = conn.fetch_one("SELECT * FROM policy WHERE tenant_id=$1 AND policy_no=$2", tenant_id, claim["policy_no"])
    pm = conn.fetch_one("SELECT * FROM policy_member WHERE tenant_id=$1 AND policy_no=$2 AND member_id=$3",
                        tenant_id, claim["policy_no"], claim["member_id"])
    hospital = conn.fetch_one("SELECT * FROM hospital WHERE tenant_id=$1 AND hospital_id=$2", tenant_id, claim["hospital_id"]) if claim["hospital_id"] else None
    facts = latest_facts(conn, tenant_id, claim_id)
    resolved = {r["field_path"]: r for r in conn.fetch_all(
        "SELECT * FROM resolved_fact WHERE tenant_id=$1 AND claim_id=$2 AND is_active", tenant_id, claim_id)}

    def rv(path):
        r = resolved.get(path)
        return r["value"] if r and r["basis"] != "UNRESOLVED" else None

    # identity observations: one per document that names the patient
    by_doc: dict[str, dict] = {}
    for f in facts:
        if f["field_path"] in ("patient.name", "patient.gender"):
            by_doc.setdefault(f["document_id"], {})[f["field_path"]] = f
    identity_obs = []
    for doc_id, fs in by_doc.items():
        if "patient.name" not in fs:
            continue
        name_f = fs["patient.name"]
        identity_obs.append({"source": doc_id, "name_normalised": normalise_name(str(name_f["normalised_value"])),
                             "gender": fs["patient.gender"]["normalised_value"] if "patient.gender" in fs else None,
                             "evidence": _ev(name_f)})
    # admission-date observations, filtered by a reviewer resolution if one exists
    adm_facts = [f for f in facts if f["field_path"] == "admission.date"]
    adm_res = resolved.get("admission.date")
    if adm_res and adm_res["basis"] in ("REVIEWER_SELECTED", "REVIEWER_ENTERED"):
        adm_facts = [f for f in adm_facts if f["normalised_value"] == adm_res["value"]]
    adm_obs = [{"source": f["document_id"], "value": f["normalised_value"], "evidence": _ev(f)} for f in adm_facts]

    bill_lines = conn.fetch_all("SELECT * FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active ORDER BY line_no", tenant_id, claim_id)
    docs = conn.fetch_all("SELECT document_id, classified_type, status FROM document WHERE tenant_id=$1 AND claim_id=$2 AND status <> 'QUARANTINED'"
                          " ORDER BY received_at", tenant_id, claim_id)
    itemised = any(d["classified_type"] == "FINAL_BILL_ITEMISED" and d["status"] != "SUPERSEDED" for d in docs)
    bill_total_facts = [f for f in facts if f["field_path"] == "bill.total" and f["classified_type"] in ("FINAL_BILL_ITEMISED", "FINAL_BILL_SUMMARY")]
    bill_no_facts = [f for f in facts if f["field_path"] == "bill.number" and f["classified_type"] in ("FINAL_BILL_ITEMISED", "FINAL_BILL_SUMMARY")]
    summary_docs = [f for f in facts if f["classified_type"] == "FINAL_BILL_SUMMARY" and f["field_path"] == "bill.is_itemised"]

    eff_date = date.fromisoformat(rv("admission.date")) if rv("admission.date") else (
        date.fromisoformat(adm_obs[0]["value"]) if adm_obs else claim["created_at"].date())
    policy_cfg = configs.get(conn, tenant_id, policy_row["config_artifact_id"], policy_row["config_version"])
    nme = configs.get(conn, tenant_id, policy_cfg["non_payable"]["list_ref"], policy_cfg["non_payable"]["list_version"])
    tariff = configs.effective(conn, tenant_id, "TARIFF", eff_date, hospital_id=claim["hospital_id"]) if hospital and hospital["is_network"] else None
    checklist = configs.effective(conn, tenant_id, "CHECKLIST", eff_date, workflow=claim["workflow"])
    cmap = configs.effective(conn, tenant_id, "CLASSIFIER_MAP", eff_date)

    proc_text = (rv("procedure.text") or "") + " " + (rv("diagnosis.primary_text") or "")
    procedure_codes = sorted({p["code"] for p in (cmap or {}).get("procedures", []) if any(k in proc_text.lower() for k in p["keywords_any"])})
    history = rv("history.past_illness_text")
    ped_signals = []
    if history:
        h = str(history)
        if any(k in h.lower() for k in ("known case of", "k/c/o", "history of", "since ", " years", "on treatment for")) and "no significant" not in h.lower():
            hist_f = next(f for f in facts if f["field_path"] == "history.past_illness_text")
            ped_signals.append({"text": h, "evidence": _ev(hist_f)})

    bill_no = rv("bill.number")
    portfolio = []
    if bill_no and claim["hospital_id"]:
        portfolio = conn.fetch_all(
            "SELECT c.claim_id, rf.value #>> '{}' AS bill_no, c.hospital_id, c.member_id FROM resolved_fact rf JOIN claim c"
            " ON c.tenant_id=rf.tenant_id AND c.claim_id=rf.claim_id WHERE rf.tenant_id=$1 AND rf.field_path='bill.number' AND rf.is_active"
            " AND rf.value #>> '{}' = $2 AND c.hospital_id=$3 AND c.claim_id<>$4", tenant_id, bill_no, claim["hospital_id"], claim_id)
    overrides = conn.fetch_all(
        "SELECT o.override_id, o.line_no, o.rule_id, o.amount_paise, o.line_fingerprint, a.reason_code, a.comment, a.actor_user_id"
        " FROM adjustment_override o JOIN reviewer_action a ON a.tenant_id=o.tenant_id AND a.reviewer_action_id=o.reviewer_action_id"
        " WHERE o.tenant_id=$1 AND o.claim_id=$2 AND o.is_active", tenant_id, claim_id)

    engine_input = {
        "claim_id": claim_id,
        "evaluation_id": evaluation_id,
        "workflow": claim["workflow"],
        "member": {"member_id": member["member_id"], "name_normalised": member["name_normalised"], "gender": member["gender"],
                   "dob": member["dob"].isoformat()},
        "policy": {"policy_no": policy_row["policy_no"], "config_ref": f"{policy_row['config_artifact_id']}@{policy_row['config_version']}",
                   "period_start": policy_row["period_start"].isoformat(), "period_end": policy_row["period_end"].isoformat(),
                   "continuous_cover_since": pm["continuous_cover_since"].isoformat(),
                   "base_sum_insured": f"{from_paise(pm['base_sum_insured_paise']):.2f}",
                   "cumulative_bonus": f"{from_paise(pm['cumulative_bonus_paise']):.2f}",
                   "paid_in_current_year": f"{available_si_inputs(conn, tenant_id, claim, pm, policy_row):.2f}"},
        "hospital_id": claim["hospital_id"],
        "hospital_is_network": bool(hospital and hospital["is_network"]),
        "bill_no": bill_no,
        "bill_no_evidence": _ev(bill_no_facts[-1]) if bill_no_facts else None,
        "bill_stated_total": rv("bill.total"),
        "admission_date": rv("admission.date"),
        "discharge_date": rv("discharge.date"),
        "procedure_codes": procedure_codes,
        "identity_observations": identity_obs,
        "admission_date_observations": adm_obs,
        "itemised_bill_available": itemised,
        "summary_bill_evidence": [_ev(f) for f in summary_docs] if not itemised else [],
        "bill_lines": [{
            "line_id": l["line_no"], "description": l["description"], "category": l["category"],
            "ward_context": l["ward_context"], "room_category": l["room_category"],
            "quantity": format(l["quantity"].normalize(), "f") if isinstance(l["quantity"], Decimal) else str(l["quantity"]),
            "unit_rate": f"{from_paise(l['unit_rate_paise']):.2f}" if l["unit_rate_paise"] is not None else None,
            "billed": f"{from_paise(l['billed_paise']):.2f}",
            "invoice_no": l["invoice_no"], "service_date": l["service_date"].isoformat() if l["service_date"] else None,
            "evidence": l["evidence"]} for l in bill_lines] if itemised else [],
        "ped_signals": ped_signals,
        "portfolio_bill_number_index": [{"claim_id": p["claim_id"], "bill_no": p["bill_no"], "hospital_id": p["hospital_id"], "member_id": p["member_id"]} for p in portfolio],
        "documents_present": [{"document_id": d["document_id"], "type": d["classified_type"]} for d in docs if d["classified_type"]],
        "reviewer_overrides": [{"override_id": o["override_id"], "line_id": o["line_no"], "rule_id": o["rule_id"],
                                "amount": f"{from_paise(o['amount_paise']):.2f}", "reason_code": o["reason_code"], "comment": o["comment"],
                                "actor": f"USER:{o['actor_user_id']}", "line_fingerprint": o["line_fingerprint"]} for o in overrides],
    }
    if engine_input["bill_no_evidence"] is None:
        engine_input.pop("bill_no_evidence")
    if engine_input["bill_stated_total"] is None:
        engine_input.pop("bill_stated_total")
    cfgs = {"policy": policy_cfg, "nme": nme, "tariff": tariff, "checklist": checklist}
    return engine_input, cfgs


def _stable_input_hash(engine_input: dict, cfgs: dict) -> str:
    """Hash of the engine input without the per-run evaluation_id, plus the exact configuration bodies."""
    material = {"input": {k: v for k, v in engine_input.items() if k != "evaluation_id"},
                "configs": {k: (hashlib.sha256(canonical_json(v)).hexdigest() if v else None) for k, v in cfgs.items()},
                "engine": ENGINE_VERSION}
    return "sha256:" + hashlib.sha256(canonical_json(material)).hexdigest()


def evaluate_claim(conn: Conn, tenant_id: str, claim_id: str, trigger: str = "MANUAL_RERUN", actor: str = "SYSTEM") -> dict:
    claim = conn.fetch_one("SELECT * FROM claim WHERE tenant_id=$1 AND claim_id=$2 FOR UPDATE", tenant_id, claim_id)
    if claim is None:
        raise EvaluationError("claim not found")
    evaluation_id = new_id("EVL")
    engine_input, cfgs = build_engine_input(conn, tenant_id, claim_id, evaluation_id)
    input_hash = _stable_input_hash(engine_input, cfgs)
    existing = conn.fetch_one("SELECT evaluation_id, status, result FROM evaluation WHERE tenant_id=$1 AND claim_id=$2 AND input_hash=$3 AND engine_version=$4",
                              tenant_id, claim_id, input_hash, ENGINE_VERSION)
    if existing:
        # identical inputs and configuration: the earlier evaluation is the answer (idempotent re-run)
        if existing["evaluation_id"] != claim["current_evaluation_id"] or existing["status"] in ("STALE", "SUPERSEDED"):
            restored = "COMPUTED" if existing["result"]["recommendation"]["computed"] else "BLOCKED"
            _supersede_current(conn, tenant_id, claim, existing["evaluation_id"])
            conn.execute("UPDATE evaluation SET status=$3::evaluation_status WHERE tenant_id=$1 AND evaluation_id=$2", tenant_id, existing["evaluation_id"], restored)
            _set_current(conn, tenant_id, claim, existing["evaluation_id"])
        return {"evaluation_id": existing["evaluation_id"], "reused": True}
    evaluation_no = (conn.fetch_val("SELECT max(evaluation_no) FROM evaluation WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim_id) or 0) + 1
    audit.append(conn, tenant_id, claim_id, actor, "RULE_RUN_STARTED", {"evaluation_id": evaluation_id, "trigger": trigger, "input_hash": input_hash})
    try:
        out = evaluate(engine_input, cfgs["policy"], cfgs["nme"], cfgs["tariff"], cfgs["checklist"])
    except ConfigurationError as e:
        conn.execute("INSERT INTO evaluation (tenant_id, evaluation_id, claim_id, evaluation_no, supersedes_evaluation_id, trigger, status, engine_version,"
                     " config_versions, input_hash, error_code, error_detail) VALUES ($1,$2,$3,$4,$5,$6,'FAILED',$7,$8::jsonb,$9,'CONFIGURATION_ERROR',$10)",
                     tenant_id, evaluation_id, claim_id, evaluation_no, claim["current_evaluation_id"], trigger, ENGINE_VERSION,
                     Json({"policy_config": engine_input["policy"]["config_ref"]}), input_hash, str(e)[:500])
        audit.append(conn, tenant_id, claim_id, actor, "EVALUATION_FAILED", {"evaluation_id": evaluation_id, "code": "CONFIGURATION_ERROR"})
        return {"evaluation_id": evaluation_id, "status": "FAILED", "error": str(e)}
    rec = out["recommendation"]
    status = "COMPUTED" if rec["computed"] else "BLOCKED"
    conn.execute(
        "INSERT INTO evaluation (tenant_id, evaluation_id, claim_id, evaluation_no, supersedes_evaluation_id, trigger, status, engine_version, config_versions,"
        " input_hash, output_hash, recommendation, recommended_payable_paise, billed_total_paise, blocked_scopes, result)"
        " VALUES ($1,$2,$3,$4,$5,$6,$7::evaluation_status,$8,$9::jsonb,$10,$11,$12::recommendation_type,$13,$14,$15::text[],$16::jsonb)",
        tenant_id, evaluation_id, claim_id, evaluation_no, claim["current_evaluation_id"], trigger, status, ENGINE_VERSION,
        Json(out["config_versions"]), input_hash, out["output_hash"], rec["type"],
        to_paise(rec["recommended_payable"]) if rec["recommended_payable"] is not None else None,
        to_paise(rec["billed_total"]), rec["blocked_scopes"], Json(out))
    line_ids = {r["line_no"]: r["bill_line_id"] for r in conn.fetch_all(
        "SELECT line_no, bill_line_id FROM bill_line WHERE tenant_id=$1 AND claim_id=$2 AND is_active", tenant_id, claim_id)}
    exec_ids: dict[str, str] = {}
    id_map: dict[str, str] = {}
    for step, ex in enumerate(out["rule_executions"], start=1):
        rid = new_id("REX")
        exec_ids[ex["rule_id"]] = rid
        conn.execute("INSERT INTO rule_execution (tenant_id, rule_execution_id, evaluation_id, step_no, rule_id, rule_version, status, detail)"
                     " VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb)", tenant_id, rid, evaluation_id, step, ex["rule_id"], ex["rule_version"], ex["status"], Json(ex["detail"]))
        audit.append(conn, tenant_id, claim_id, "SYSTEM", "RULE_EXECUTED", {"evaluation_id": evaluation_id, "rule_id": ex["rule_id"],
                                                                           "rule_version": ex["rule_version"], "status": ex["status"]})
    for a in out["adjustments"]:
        adj_id = new_id("ADJ")
        id_map[a["adjustment_id"]] = adj_id
        conn.execute(
            "INSERT INTO adjustment (tenant_id, adjustment_id, evaluation_id, rule_execution_id, level, bill_line_id, reason_code, amount_paise, engine_amount_paise,"
            " base_before_paise, remaining_after_paise, formula, explanation, authority, evidence, origin, override_ref)"
            " VALUES ($1,$2,$3,$4,$5::adjustment_level,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb,$15::jsonb,$16,$17)",
            tenant_id, adj_id, evaluation_id, exec_ids[a["rule_id"]], a["level"], line_ids.get(a["line_id"]) if a["line_id"] else None,
            a["reason_code"], to_paise(a["amount"]), to_paise(a["engine_amount"]), to_paise(a["base_before"]), to_paise(a["remaining_after"]),
            a["formula"], a["explanation"], Json(a["authority"]), Json(a["evidence_refs"]), a["origin"], a["override_ref"])
    id_map.update(_persist_findings(conn, tenant_id, claim_id, evaluation_id, out["findings"]))
    for ex in out["rule_executions"]:
        id_map[ex["execution_id"]] = exec_ids[ex["rule_id"]]
    # engine IDs (ADJ-0007, FND-0012, …) -> stored IDs; kept beside the engine output so output_hash stays verifiable
    conn.execute("UPDATE evaluation SET result = result || jsonb_build_object('_ids', $3::jsonb) WHERE tenant_id=$1 AND evaluation_id=$2",
                 tenant_id, evaluation_id, Json(id_map))
    _supersede_current(conn, tenant_id, claim, evaluation_id)
    _set_current(conn, tenant_id, claim, evaluation_id)
    audit.append(conn, tenant_id, claim_id, "SYSTEM", "RECOMMENDATION_CREATED",
                 {"evaluation_id": evaluation_id, "type": rec["type"], "recommended_payable": rec["recommended_payable"],
                  "blocked_scopes": rec["blocked_scopes"], "output_hash": out["output_hash"]})
    return {"evaluation_id": evaluation_id, "status": status, "recommendation": rec}


def _subject_key(f: dict) -> str:
    return hashlib.sha256(canonical_json([f["rule_id"], f["kind"], f["summary"]])).hexdigest()[:32]


def _persist_findings(conn: Conn, tenant_id: str, claim_id: str, evaluation_id: str, findings: list[dict]) -> dict:
    keys, mapping = [], {}
    for f in findings:
        key = _subject_key(f)
        keys.append(key)
        existing = conn.fetch_one("SELECT finding_id, status FROM finding WHERE tenant_id=$1 AND claim_id=$2 AND subject_key=$3",
                                  tenant_id, claim_id, key)
        if existing:
            new_status = "OPEN" if existing["status"] == "SUPERSEDED" else existing["status"]
            conn.execute("UPDATE finding SET last_evaluation_id=$3, status=$4::finding_status WHERE tenant_id=$1 AND finding_id=$2",
                         tenant_id, existing["finding_id"], evaluation_id, new_status)
            mapping[f["finding_id"]] = existing["finding_id"]
            continue
        fid = new_id("FND")
        mapping[f["finding_id"]] = fid
        conn.execute(
            "INSERT INTO finding (tenant_id, finding_id, claim_id, first_evaluation_id, last_evaluation_id, rule_id, category, kind, severity, blocking,"
            " blocked_scopes, route_to, summary, uncertainty_note, evidence, status, subject_key)"
            " VALUES ($1,$2,$3,$4,$4,$5,$6,$7,$8::severity,$9,$10::text[],$11,$12,$13,$14::jsonb,'OPEN',$15)",
            tenant_id, fid, claim_id, evaluation_id, f["rule_id"], f["category"], f["kind"], f["severity"], f["blocking"],
            f["blocked_scopes"], f["route_to"], f["summary"], f["uncertainty_note"], Json(f["evidence_refs"]), key)
    # findings that no longer fire are superseded (kept for history)
    conn.execute("UPDATE finding SET status='SUPERSEDED' WHERE tenant_id=$1 AND claim_id=$2 AND status IN ('OPEN','ACKNOWLEDGED')"
                 " AND NOT (subject_key = ANY($3::text[]))", tenant_id, claim_id, keys)
    return mapping


def api_view(conn: Conn, tenant_id: str, ev: dict) -> dict:
    """The stored engine output with stored IDs and live finding statuses (schemas/evaluation-result.schema.json)."""
    import copy
    out = copy.deepcopy(ev["result"])
    ids = out.pop("_ids", {})
    status = {r["finding_id"]: r["status"] for r in conn.fetch_all(
        "SELECT finding_id, status FROM finding WHERE tenant_id=$1 AND claim_id=$2", tenant_id, ev["claim_id"])}
    for a in out["adjustments"]:
        a["adjustment_id"] = ids.get(a["adjustment_id"], a["adjustment_id"])
    for f in out["findings"]:
        f["finding_id"] = ids.get(f["finding_id"], f["finding_id"])
        f["status"] = status.get(f["finding_id"], f["status"])
    for q in out["query_items"]:
        q["linked_findings"] = [ids.get(x, x) for x in q["linked_findings"]]
    for e in out["rule_executions"]:
        e["execution_id"] = ids.get(e["execution_id"], e["execution_id"])
    return out


def _supersede_current(conn: Conn, tenant_id: str, claim: dict, new_id_: str):
    cur = claim["current_evaluation_id"]
    if cur and cur != new_id_:
        conn.execute("UPDATE evaluation SET status='SUPERSEDED' WHERE tenant_id=$1 AND evaluation_id=$2", tenant_id, cur)


def _set_current(conn: Conn, tenant_id: str, claim: dict, evaluation_id: str):
    status = claim["status"]
    if status in ("INTAKE", "DOCS_INCOMPLETE", "PROCESSING", "REOPENED", "AWAITING_RESPONSE"):
        status = "READY_FOR_REVIEW"
    conn.execute("UPDATE claim SET current_evaluation_id=$3, status=$4::claim_status, updated_at=now(), row_version=row_version+1"
                 " WHERE tenant_id=$1 AND claim_id=$2", tenant_id, claim["claim_id"], evaluation_id, status)
    claim["current_evaluation_id"] = evaluation_id


def current(conn: Conn, tenant_id: str, claim_id: str) -> dict | None:
    return conn.fetch_one("SELECT e.* FROM evaluation e JOIN claim c ON c.tenant_id=e.tenant_id AND c.current_evaluation_id=e.evaluation_id"
                          " WHERE c.tenant_id=$1 AND c.claim_id=$2", tenant_id, claim_id)


def diff(conn: Conn, tenant_id: str, claim_id: str, old_id: str, new_id_: str) -> dict:
    """'What changed' between two evaluations: payable, recommendation, adjustments by (line, rule), findings."""
    rows = {r["evaluation_id"]: r for r in conn.fetch_all("SELECT evaluation_id, result FROM evaluation WHERE tenant_id=$1 AND claim_id=$2 AND evaluation_id = ANY($3::text[])",
                                                          tenant_id, claim_id, [old_id, new_id_])}
    if old_id not in rows or new_id_ not in rows:
        raise EvaluationError("evaluation not found")
    a, b = rows[old_id]["result"], rows[new_id_]["result"]

    def adj(r):
        return {f"{x['line_id'] or 'CLAIM'}|{x['rule_id']}": x["amount"] for x in r["adjustments"]}

    aa, bb = adj(a), adj(b)
    return {
        "from": old_id, "to": new_id_,
        "recommendation": {"from": a["recommendation"]["type"], "to": b["recommendation"]["type"]},
        "recommended_payable": {"from": a["recommendation"]["recommended_payable"], "to": b["recommendation"]["recommended_payable"]},
        "blocked_scopes": {"from": a["recommendation"]["blocked_scopes"], "to": b["recommendation"]["blocked_scopes"]},
        "adjustments_added": sorted(set(bb) - set(aa)),
        "adjustments_removed": sorted(set(aa) - set(bb)),
        "adjustments_changed": sorted(k for k in set(aa) & set(bb) if aa[k] != bb[k]),
        "findings_added": sorted({f["kind"] for f in b["findings"]} - {f["kind"] for f in a["findings"]}),
        "findings_removed": sorted({f["kind"] for f in a["findings"]} - {f["kind"] for f in b["findings"]}),
    }
