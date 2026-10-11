"""Targeted rule tests (no third-party deps). Usage: python3 verification/test_rules.py
Each test names the test-catalogue ID it executes (10-validation-plan.md §3)."""
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verification"))
from engine import evaluate, ConfigurationError, line_fingerprint, D  # noqa: E402

policy = json.loads((ROOT / "config/policy-ILL-INDEMNITY-A.v2026.1.0.json").read_text())
nme = json.loads((ROOT / "config/nme-list-ILL-A.v2026.1.0.json").read_text())
tariff = json.loads((ROOT / "config/tariff-ILL-HOSP-NW-01.v2026.07.json").read_text())
checklist = json.loads((ROOT / "config/checklist-IPD-REIMB.v2026.1.0.json").read_text())
t2 = json.loads((ROOT / "fixtures/claims/trace-2-interacting-adjustments.input.json").read_text())
t3a = json.loads((ROOT / "fixtures/claims/trace-3a-insufficient-conflicting.input.json").read_text())
results = []


def test(tc, name):
    def deco(fn):
        try:
            fn()
            results.append((tc, name, "PASS", ""))
        except AssertionError as e:
            results.append((tc, name, "FAIL", str(e)))
        return fn
    return deco


@test("TC-ELG-04", "Decision invariance: date conflict between identity-matched documents, same PED outcome")
def _():
    c = copy.deepcopy(t3a)
    c["identity_observations"][2].update({"name_normalised": "SUNITA SHARMA", "gender": "F"})  # bill identity now matches
    out = evaluate(c, policy, nme, None, checklist)
    ex = {e["rule_id"]: e for e in out["rule_executions"]}
    assert ex["R-ELIG-WAITING"]["status"] == "REVIEW", ex["R-ELIG-WAITING"]
    assert ex["R-ELIG-WAITING"]["detail"]["invariant_under_date_conflict"] is True
    assert ex["R-ELIG-WAITING"]["detail"]["evaluated_dates"] == ["2026-09-02", "2026-09-03"]
    assert out["recommendation"]["computed"] is False


@test("TC-ELG-07", "Eligibility blocked when candidate dates give different outcomes")
def _():
    c = copy.deepcopy(t3a)
    c["identity_observations"][2].update({"name_normalised": "SUNITA SHARMA", "gender": "F"})
    c["policy"]["continuous_cover_since"] = "2023-09-03"  # 36 months reached on 09-03 but not on 09-02
    out = evaluate(c, policy, nme, None, checklist)
    ex = {e["rule_id"]: e for e in out["rule_executions"]}
    assert ex["R-ELIG-WAITING"]["status"] == "SKIPPED_BLOCKED", ex["R-ELIG-WAITING"]


@test("TC-CAL-08", "Multi-room stay: payable independent of line order (DAY_WEIGHTED actual rate)")
def _():
    c = copy.deepcopy(t2)
    room = c["bill_lines"][0]
    a = dict(room, line_id="L01A", quantity="1", unit_rate="3000.00", billed="3000.00", room_category="TWIN_SHARING")
    b = dict(room, line_id="L01B", quantity="2", unit_rate="6000.00", billed="12000.00")
    c["bill_lines"] = [a, b] + c["bill_lines"][1:]
    c["bill_stated_total"] = f"{sum(D(l['billed']) for l in c['bill_lines']):.2f}"
    o1 = evaluate(copy.deepcopy(c), policy, nme, tariff, checklist)
    c2 = copy.deepcopy(c)
    c2["bill_lines"] = [b, a] + c["bill_lines"][2:]
    o2 = evaluate(c2, policy, nme, tariff, checklist)
    assert o1["recommendation"]["admissible_after_line_rules"] == o2["recommendation"]["admissible_after_line_rules"]
    ex = {e["rule_id"]: e for e in o1["rule_executions"]}
    assert ex["R-LINE-ROOM-CAP"]["detail"]["actual_normal_per_day"] == "5000.00"  # (3000x1 + 6000x2)/3


@test("TC-CAL-09", "Room days billed beyond the stay raise a review finding, no deduction")
def _():
    c = copy.deepcopy(t2)
    c["discharge_date"] = "2026-07-04"  # 3 midnights, 4 room/ICU days billed
    out = evaluate(c, policy, nme, tariff, checklist)
    kinds = [f["kind"] for f in out["findings"]]
    assert "ROOM_DAYS_EXCEED_STAY" in kinds
    assert out["recommendation"]["recommended_payable"] == "85000.00"


@test("TC-REV-03", "Override is re-applied only when the line is unchanged; otherwise a reconfirmation finding")
def _():
    c = json.loads((ROOT / "fixtures/claims/trace-2b-reviewer-override.input.json").read_text())
    c2 = copy.deepcopy(c)
    for l in c2["bill_lines"]:
        if l["line_id"] == "L14":
            l["billed"] = "5600.00"
    c2["bill_stated_total"] = f"{sum(D(l['billed']) for l in c2['bill_lines']):.2f}"
    out = evaluate(c2, policy, nme, tariff, checklist)
    assert any(f["kind"] == "OVERRIDE_NEEDS_RECONFIRMATION" for f in out["findings"])
    l14 = [a for a in out["adjustments"] if a["line_id"] == "L14"]
    assert l14 and l14[0]["origin"] == "ENGINE" and l14[0]["amount"] == "1600.00"


@test("TC-EVD-01", "Every adjustment carries authority (artifact@version, doc, clause) and evidence")
def _():
    for name in ["trace-1-straightforward", "trace-2-interacting-adjustments", "trace-2b-reviewer-override", "trace-3b-after-new-evidence"]:
        out = json.loads((ROOT / f"fixtures/claims/{name}.output.json").read_text())
        for a in out["adjustments"]:
            assert a["authority"]["artifact"] and a["authority"]["clause"], (name, a["adjustment_id"])
            assert a["evidence_refs"], (name, a["adjustment_id"], "no evidence")


@test("TC-CFG-03", "Missing clause reference fails the evaluation instead of deducting")
def _():
    p = copy.deepcopy(policy)
    del p["clause_refs"]["R-CLAIM-COPAY"]
    try:
        evaluate(copy.deepcopy(t2), p, nme, tariff, checklist)
    except ConfigurationError:
        return
    raise AssertionError("expected ConfigurationError")


@test("TC-CFG-04", "Input hash changes when any config version changes (tariff, NME list)")
def _():
    base = evaluate(copy.deepcopy(t2), policy, nme, tariff, checklist)["input_hash"]
    t_new = dict(tariff, tariff_version="2026.10")
    n_new = dict(nme, list_version="2026.2.0")
    assert evaluate(copy.deepcopy(t2), policy, nme, t_new, checklist)["input_hash"] != base
    assert evaluate(copy.deepcopy(t2), policy, n_new, tariff, checklist)["input_hash"] != base


@test("TC-DOC-06", "Missing checklist document raises a non-blocking finding and a query to the configured addressee")
def _():
    c = copy.deepcopy(t2)
    c["documents_present"] = [d for d in c["documents_present"] if d["type"] != "BANK_DETAILS"]
    out = evaluate(c, policy, nme, tariff, checklist)
    f = [x for x in out["findings"] if x["kind"] == "DOCUMENT_INCOMPLETE"]
    assert f and not f[0]["blocking"]
    assert any(q["requested_document_type"] == "BANK_DETAILS" and q["addressed_to"] == "CLAIMANT" for q in out["query_items"])
    assert out["recommendation"]["recommended_payable"] == "85000.00"


@test("TC-MAT-01", "Identity conflict blocks all financial computation but eligibility uses identity-matched documents only")
def _():
    out = evaluate(copy.deepcopy(t3a), policy, nme, None, checklist)
    assert "ALL_FINANCIAL" in out["recommendation"]["blocked_scopes"] and out["recommendation"]["recommended_payable"] is None
    ex = {e["rule_id"]: e for e in out["rule_executions"]}
    assert ex["R-ELIG-WAITING"]["detail"]["evaluated_dates"] == ["2026-09-03"]  # summary bill (identity-mismatched) excluded


fails = [r for r in results if r[2] != "PASS"]
for r in results:
    print(f"{r[0]:<11} {r[2]}  {r[1]}" + (f"  -> {r[3]}" if r[3] else ""))
sys.exit(1 if fails else 0)
