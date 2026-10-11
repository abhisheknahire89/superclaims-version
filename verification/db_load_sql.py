"""Emit SQL that loads the trace fixtures/outputs into db/schema.sql, plus negative tests.

Usage: python3 verification/db_load_sql.py > /tmp/load.sql ; psql -v ON_ERROR_STOP=1 -f /tmp/load.sql
Proves the proposed schema can hold the engine's outputs without loss, and that key constraints
(append-only audit, CRC reference + insurer communication for repudiation, authority on every
adjustment, four-eyes config, RLS) bite. Trace 2b is a what-if branch and is not loaded.
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def js(v):
    return lit(json.dumps(v, ensure_ascii=False)) + "::jsonb"


def paise(x):
    return None if x is None else int(Decimal(str(x)) * 100)


def arr(items):
    return "ARRAY[" + ",".join(lit(i) for i in items) + "]::text[]" if items else "'{}'::text[]"


T = "TENANT-DEMO"
out = ["BEGIN;", f"SET app.tenant_id = {lit(T)};",
       f"INSERT INTO tenant VALUES ({lit(T)}, 'Demo TPA (synthetic)', 'TPA', 'ap-south-1', now());"]
for uid in ["U-AUTHOR", "U-APPROVER", "PROC-04", "PROC-07", "PROC-11", "SUP-02", "MO-01", "FWA-01"]:
    out.append(f"INSERT INTO app_user VALUES ({lit(uid)}, {lit(T)}, {lit('sub-' + uid.lower())}, {lit(uid)}, true);")

policy = json.loads((ROOT / "config/policy-ILL-INDEMNITY-A.v2026.1.0.json").read_text())
out.append(f"INSERT INTO config_artifact VALUES ('POLCFG-ILL-INDEMNITY-A', '2026.1.0', {lit(T)}, 'POLICY_CONFIG', 'PUBLISHED', '2026-04-01', NULL, "
           f"{js(policy)}, 'sha256:demo', '[]', 'U-AUTHOR', 'U-APPROVER', now());")
for kind, f, aid, ver in [("CHECKLIST", "checklist-IPD-REIMB.v2026.1.0.json", "CHECKLIST-IPD-REIMB", "2026.1.0"),
                          ("WORKFLOW_CONFIG", "workflow-TENANT-DEMO.v2026.1.0.json", "WFCFG-TENANT-DEMO", "2026.1.0"),
                          ("TARIFF", "tariff-ILL-HOSP-NW-01.v2026.07.json", "TARIFF-ILL-HOSP-NW-01", "2026.07"),
                          ("NME_LIST", "nme-list-ILL-A.v2026.1.0.json", "NMELIST-ILL-A", "2026.1.0")]:
    body = json.loads((ROOT / "config" / f).read_text())
    out.append(f"INSERT INTO config_artifact VALUES ({lit(aid)}, {lit(ver)}, {lit(T)}, {lit(kind)}, 'PUBLISHED', '2026-04-01', NULL, {js(body)}, 'sha256:demo', '[]', 'U-AUTHOR', 'U-APPROVER', now());")

for name in ["trace-1-straightforward", "trace-2-interacting-adjustments", "trace-3a-insufficient-conflicting", "trace-3b-after-new-evidence"]:
    inp = json.loads((ROOT / f"fixtures/claims/{name}.input.json").read_text())
    res = json.loads((ROOT / f"fixtures/claims/{name}.output.json").read_text())
    cid, m, p = inp["claim_id"], inp["member"], inp["policy"]
    first_for_claim = name != "trace-3b-after-new-evidence"
    if first_for_claim:
        out.append(f"INSERT INTO member VALUES ({lit(T)}, {lit(m['member_id'])}, {lit(m['name_normalised'].title())}, {lit(m['name_normalised'])}, {lit(m['gender'])}, {lit(m['dob'])}, NULL);")
        out.append(f"INSERT INTO policy VALUES ({lit(T)}, {lit(p['policy_no'])}, 'Illustrative Indemnity Plan A', NULL, {lit(p['period_start'])}, {lit(p['period_end'])}, 'POLCFG-ILL-INDEMNITY-A', '2026.1.0');")
        out.append(f"INSERT INTO policy_member VALUES ({lit(T)}, {lit(p['policy_no'])}, {lit(m['member_id'])}, {lit(p['continuous_cover_since'])}, {paise(p['base_sum_insured'])}, {paise(p['cumulative_bonus'])}, '[]');")
        out.append(f"INSERT INTO hospital VALUES ({lit(T)}, {lit(inp['hospital_id'])}, 'Synthetic hospital', NULL, NULL, {lit(inp['hospital_is_network'])}) ON CONFLICT DO NOTHING;")
        out.append(f"INSERT INTO claim (tenant_id, claim_id, workflow, status, policy_no, member_id, hospital_id, admission_date, discharge_date) VALUES "
                   f"({lit(T)}, {lit(cid)}, 'IPD_REIMBURSEMENT', 'READY_FOR_REVIEW', {lit(p['policy_no'])}, {lit(m['member_id'])}, {lit(inp['hospital_id'])}, {lit(inp.get('admission_date'))}, {lit(inp.get('discharge_date'))});")
    bill_version = 2 if name.endswith("3b-after-new-evidence") else 1
    for l in inp["bill_lines"]:
        blid = f"{cid}-v{bill_version}-{l['line_id']}"
        out.append(f"INSERT INTO bill_line (tenant_id, bill_line_id, claim_id, bill_version, line_no, description, category, category_source, ward_context, room_category, service_date, invoice_no, quantity, unit_rate_paise, billed_paise, evidence) VALUES "
                   f"({lit(T)}, {lit(blid)}, {lit(cid)}, {bill_version}, {lit(l['line_id'])}, {lit(l['description'])}, {lit(l['category'])}, 'REVIEWER', {lit(l.get('ward_context', 'WARD'))}, {lit(l.get('room_category'))}, "
                   f"{lit(l.get('service_date'))}, {lit(l.get('invoice_no'))}, {lit(l.get('quantity', '1'))}, {lit(paise(l.get('unit_rate')))}, {paise(l['billed'])}, {js(l.get('evidence', []))});")
    rec = res["recommendation"]
    eid = res["evaluation_id"]
    evno = 2 if name.endswith("3b-after-new-evidence") else 1
    status = "COMPUTED" if rec["computed"] else "BLOCKED"
    out.append(f"INSERT INTO evaluation (tenant_id, evaluation_id, claim_id, evaluation_no, supersedes_evaluation_id, trigger, status, engine_version, config_versions, input_hash, output_hash, recommendation, recommended_payable_paise, billed_total_paise, blocked_scopes) VALUES "
               f"({lit(T)}, {lit(eid)}, {lit(cid)}, {evno}, {lit(inp.get('supersedes_evaluation_id'))}, {lit('NEW_EVIDENCE' if evno == 2 else 'INITIAL')}, {lit(status)}, {lit(res['engine_version'])}, {js(res['config_versions'])}, "
               f"{lit(res['input_hash'])}, {lit(res['output_hash'])}, {lit(rec['type'])}, {lit(paise(rec['recommended_payable']))}, {lit(paise(rec['billed_total']) if rec['itemised_lines_available'] else None)}, {arr(rec['blocked_scopes'])});")
    if evno == 2:
        out.append(f"UPDATE evaluation SET status = 'SUPERSEDED' WHERE tenant_id = {lit(T)} AND evaluation_id = {lit(inp['supersedes_evaluation_id'])};")
    exec_ids = {}
    for i, ex in enumerate(res["rule_executions"], 1):
        exid = f"{eid}-{ex['execution_id']}"
        exec_ids[ex["rule_id"]] = exid
        out.append(f"INSERT INTO rule_execution VALUES ({lit(T)}, {lit(exid)}, {lit(eid)}, {i}, {lit(ex['rule_id'])}, {lit(ex['rule_version'])}, {lit(ex['status'])}, {js(ex['detail'])});")
    for a in res["adjustments"]:
        blid = f"{cid}-v{bill_version}-{a['line_id']}" if a["line_id"] else None
        out.append("INSERT INTO adjustment (tenant_id, adjustment_id, evaluation_id, rule_execution_id, level, bill_line_id, reason_code, amount_paise, engine_amount_paise, "
                   "base_before_paise, remaining_after_paise, formula, explanation, authority, evidence, origin, override_ref) VALUES "
                   f"({lit(T)}, {lit(eid + '-' + a['adjustment_id'])}, {lit(eid)}, {lit(exec_ids[a['rule_id']])}, {lit(a['level'])}, {lit(blid)}, {lit(a['reason_code'])}, "
                   f"{paise(a['amount'])}, {paise(a['engine_amount'])}, {paise(a['base_before'])}, {paise(a['remaining_after'])}, {lit(a['formula'])}, {lit(a['explanation'])}, "
                   f"{js(a['authority'])}, {js(a['evidence_refs'])}, {lit(a['origin'])}, {lit(a['override_ref'])});")
    for f in res["findings"]:
        out.append(f"INSERT INTO finding VALUES ({lit(T)}, {lit(eid + '-' + f['finding_id'])}, {lit(cid)}, {lit(eid)}, {lit(eid)}, {lit(f['rule_id'])}, {lit(f['category'])}, {lit(f['kind'])}, {lit(f['severity'])}, "
                   f"{lit(f['blocking'])}, {arr(f['blocked_scopes'])}, {lit(f['route_to'])}, {lit(f['summary'])}, {lit(f['uncertainty_note'])}, {js(f['evidence_refs'])}, 'OPEN', NULL);")
    out.append(f"UPDATE claim SET current_evaluation_id = {lit(eid)} WHERE tenant_id = {lit(T)} AND claim_id = {lit(cid)};")
    events = json.loads((ROOT / f"fixtures/claims/{name}.audit.json").read_text())
    for e in events:
        kind = "USER" if e["actor"].startswith("USER:") else ("INTEGRATION" if e["actor"].startswith("INTEGRATION:") else "SYSTEM")
        out.append(f"INSERT INTO audit_event (tenant_id, claim_id, seq, occurred_at, actor_kind, actor_id, event_type, payload, prev_hash, event_hash) VALUES "
                   f"({lit(T)}, {lit(cid)}, {e['seq']}, {lit(e['occurred_at'])}, {lit(kind)}, {lit(e['actor'])}, {lit(e['event_type'])}, {js(e['payload'])}, {lit(e['prev_hash'])}, {lit(e['event_hash'])});")

# trace 2: second approval then decision (decided by PROC-11, approved by SUP-02)
out.append(f"INSERT INTO approval_request VALUES ({lit(T)}, 'AR-0002', 'CLM-DEMO-0002', 'EVAL-0002-v1', 'APPROVED_PARTIAL', 8500000, 'PROC-11', 'SUP-02', "
           "ARRAY['TOTAL_DEDUCTIONS_ABOVE_SHARE_OF_BILLED']::text[], 'APPROVED', now(), NULL);")
out.append("INSERT INTO decision (tenant_id, decision_id, claim_id, evaluation_id, disposition, approved_payable_paise, decided_by, second_approver, deviation_from_recommendation_paise, communicated_by) "
           f"VALUES ({lit(T)}, 'DEC-0002', 'CLM-DEMO-0002', 'EVAL-0002-v1', 'APPROVED_PARTIAL', 8500000, 'PROC-11', 'SUP-02', 0, 'TPA');")
out.append("INSERT INTO decision (tenant_id, decision_id, claim_id, evaluation_id, disposition, approved_payable_paise, decided_by, deviation_from_recommendation_paise, communicated_by) "
           f"VALUES ({lit(T)}, 'DEC-0001', 'CLM-DEMO-0001', 'EVAL-0001-v1', 'APPROVED_PARTIAL', 10759100, 'PROC-07', 0, 'TPA');")
out.append("COMMIT;")

out.append("""
SELECT e.evaluation_id, e.billed_total_paise, e.recommended_payable_paise, COALESCE(SUM(a.amount_paise),0) AS adj,
       e.billed_total_paise = e.recommended_payable_paise + COALESCE(SUM(a.amount_paise),0) AS reconciles,
       bool_and(a.authority ? 'clause') AS all_have_authority
FROM evaluation e LEFT JOIN adjustment a USING (tenant_id, evaluation_id)
WHERE e.status = 'COMPUTED' GROUP BY 1,2,3 ORDER BY 1;""")

ADJ_COLS = "(tenant_id, adjustment_id, evaluation_id, rule_execution_id, level, bill_line_id, reason_code, amount_paise, engine_amount_paise, base_before_paise, remaining_after_paise, formula, explanation, authority, evidence, origin, override_ref)"
GOOD_AUTH = """'{"artifact":"x@1","doc_id":"d","clause":"c"}'"""
GOOD_EV = """'[{"record_type":"CONFIG","record_id":"x","field":"y"}]'"""
neg = [
    ("append-only audit", "UPDATE audit_event SET event_type = 'X' WHERE claim_id = 'CLM-DEMO-0001' AND seq = 1;"),
    ("repudiation needs CRC reference", f"INSERT INTO decision (tenant_id, decision_id, claim_id, evaluation_id, disposition, decided_by, communicated_by) VALUES ({lit(T)}, 'DEC-BAD', 'CLM-DEMO-0003', 'EVAL-0003-v2', 'REPUDIATED_WITH_CRC_APPROVAL', 'SUP-02', 'INSURER');"),
    ("repudiation must be communicated by insurer", f"INSERT INTO decision (tenant_id, decision_id, claim_id, evaluation_id, disposition, decided_by, crc_reference, communicated_by) VALUES ({lit(T)}, 'DEC-BAD2', 'CLM-DEMO-0003', 'EVAL-0003-v2', 'REPUDIATED_WITH_CRC_APPROVAL', 'SUP-02', 'CRC-1', 'TPA');"),
    ("negative non-rounding adjustment", f"INSERT INTO adjustment {ADJ_COLS} VALUES ({lit(T)}, 'ADJ-BAD', 'EVAL-0001-v1', 'EVAL-0001-v1-EXE-0001', 'CLAIM', NULL, 'CO_PAYMENT', -100, -100, 0, 100, 'x', 'x', {GOOD_AUTH}, {GOOD_EV}, 'ENGINE', NULL);"),
    ("deduction above base", f"INSERT INTO adjustment {ADJ_COLS} VALUES ({lit(T)}, 'ADJ-BAD2', 'EVAL-0001-v1', 'EVAL-0001-v1-EXE-0001', 'CLAIM', NULL, 'CO_PAYMENT', 500, 500, 100, 0, 'x', 'x', {GOOD_AUTH}, {GOOD_EV}, 'ENGINE', NULL);"),
    ("adjustment without clause authority", f"INSERT INTO adjustment {ADJ_COLS} VALUES ({lit(T)}, 'ADJ-BAD3', 'EVAL-0001-v1', 'EVAL-0001-v1-EXE-0001', 'CLAIM', NULL, 'CO_PAYMENT', 10, 10, 100, 90, 'x', 'x', '{{\"artifact\":\"x@1\"}}', {GOOD_EV}, 'ENGINE', NULL);"),
    ("adjustment without evidence", f"INSERT INTO adjustment {ADJ_COLS} VALUES ({lit(T)}, 'ADJ-BAD4', 'EVAL-0001-v1', 'EVAL-0001-v1-EXE-0001', 'CLAIM', NULL, 'CO_PAYMENT', 10, 10, 100, 90, 'x', 'x', {GOOD_AUTH}, '[]', 'ENGINE', NULL);"),
    ("self-approval of config", f"INSERT INTO config_artifact VALUES ('X', '1', {lit(T)}, 'TARIFF', 'PUBLISHED', '2026-01-01', NULL, '{{}}', 'h', '[]', 'U-AUTHOR', 'U-AUTHOR', now());"),
    ("blocked evaluation with payable", f"INSERT INTO evaluation (tenant_id, evaluation_id, claim_id, evaluation_no, trigger, status, engine_version, config_versions, input_hash, recommended_payable_paise) VALUES ({lit(T)}, 'E-BAD', 'CLM-DEMO-0001', 9, 'MANUAL_RERUN', 'BLOCKED', 'x', '{{}}', 'h', 100);"),
    ("clinical finding without uncertainty note", f"INSERT INTO finding VALUES ({lit(T)}, 'F-BAD', 'CLM-DEMO-0001', 'EVAL-0001-v1', 'EVAL-0001-v1', 'R', 'CLINICAL', 'K', 'LOW', false, '{{}}', NULL, 's', NULL, '[]', 'OPEN', NULL);"),
    ("self second-approval", f"INSERT INTO approval_request VALUES ({lit(T)}, 'AR-BAD', 'CLM-DEMO-0002', 'EVAL-0002-v1', 'APPROVED_PARTIAL', 1, 'SUP-02', 'SUP-02', ARRAY['X']::text[], 'PENDING', NULL, NULL);"),
]
for label, stmt in neg:
    out.append(f"""DO $neg$ BEGIN
  BEGIN {stmt}
    RAISE EXCEPTION 'NEGATIVE TEST DID NOT FAIL: {label}';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM LIKE 'NEGATIVE TEST DID NOT FAIL%' THEN RAISE; END IF;
    RAISE NOTICE 'ok (rejected as expected): {label} -> %', SQLERRM;
  WHEN others THEN
    RAISE NOTICE 'ok (rejected as expected): {label} -> %', SQLERRM;
  END;
END $neg$;""")
print("\n".join(out))
