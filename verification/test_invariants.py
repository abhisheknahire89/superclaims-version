"""Property-style invariant tests for the reference harness (no third-party deps).

Usage: python3 verification/test_invariants.py [n_cases]
Generates random synthetic claims and asserts the financial invariants listed in
10-validation-plan.md section 'Financial invariants' (FI-01..FI-08).
"""
import copy
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "verification"))
from engine import evaluate, D, line_fingerprint  # noqa: E402

policy = json.loads((ROOT / "config/policy-ILL-INDEMNITY-A.v2026.1.0.json").read_text())
nme = json.loads((ROOT / "config/nme-list-ILL-A.v2026.1.0.json").read_text())
tariff = json.loads((ROOT / "config/tariff-ILL-HOSP-NW-01.v2026.07.json").read_text())
checklist = json.loads((ROOT / "config/checklist-IPD-REIMB.v2026.1.0.json").read_text())
ALL_DOCS = [{"document_id": f"D-{t}", "type": t} for t in ["CLAIM_FORM", "DISCHARGE_SUMMARY", "FINAL_BILL_ITEMISED", "PHARMACY_BILL", "INVESTIGATION_REPORT", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS", "IMPLANT_INVOICE"]]

CATS = ["NURSING", "PROFESSIONAL_FEES", "OT_CHARGES", "PHARMACY", "CONSUMABLES", "DIAGNOSTICS", "OTHER_HOSPITAL_SERVICES"]
DESCS = {"NURSING": ["Nursing charges", "Nursing - bed pan"], "PROFESSIONAL_FEES": ["Surgeon fee - laparoscopic cholecystectomy", "Consultant visits", "Anaesthetist fee"],
         "OT_CHARGES": ["Operation theatre charges"], "PHARMACY": ["Pharmacy invoice"], "CONSUMABLES": ["Surgical consumables", "Urine bag"],
         "DIAGNOSTICS": ["CT scan abdomen (contrast)", "Laboratory investigations"],
         "OTHER_HOSPITAL_SERVICES": ["Television charges", "Mineral water", "Admission / registration charges", "Infusion pump charges", "Dietician review"]}


def rand_money(rng, lo, hi):
    return f"{Decimal(rng.randint(lo * 100, hi * 100)) / 100:.2f}"


def gen_claim(rng, i):
    base_si = rng.choice([200000, 300000, 500000, 1000000])
    room_rate = rng.choice([1800, 3000, 4500, 6000, 9000])
    days = rng.randint(1, 8)
    lines = [{"line_id": "L01", "description": "Room charges", "category": "ROOM", "room_category": "X", "ward_context": "WARD",
              "quantity": str(days), "unit_rate": f"{room_rate}.00", "billed": f"{room_rate * days}.00"}]
    if rng.random() < 0.4:  # room change during the stay: a second normal-room line at another rate
        r2, d2 = rng.choice([1800, 3000, 4500, 6000, 9000]), rng.randint(1, 4)
        lines.append({"line_id": "L01B", "description": "Room charges (after transfer)", "category": "ROOM", "room_category": "Y", "ward_context": "WARD",
                      "quantity": str(d2), "unit_rate": f"{r2}.00", "billed": f"{r2 * d2}.00"})
    if rng.random() < 0.5:
        lines.append({"line_id": "L02", "description": "ICU charges", "category": "ICU_ROOM", "ward_context": "ICU", "quantity": "1",
                      "unit_rate": f"{rng.choice([6000, 9000, 15000])}.00", "billed": "0"})
        lines[-1]["billed"] = lines[-1]["unit_rate"]
    for k in range(rng.randint(3, 25)):
        cat = rng.choice(CATS)
        line = {"line_id": f"L{k + 10:02d}", "description": rng.choice(DESCS[cat]), "category": cat,
                "ward_context": rng.choice(["WARD", "WARD", "ICU"]), "billed": rand_money(rng, 50, 60000)}
        if cat == "PHARMACY":
            line["invoice_no"] = f"PH-{rng.randint(1, 6)}"
            line["service_date"] = "2026-07-02"
            line["description"] = f"Pharmacy invoice {line['invoice_no']}"
            if rng.random() < 0.3:
                lines.append(dict(line, line_id=line["line_id"] + "D"))
        lines.append(line)
    stated = f"{sum(D(l['billed']) for l in lines):.2f}"
    identity = [{"source": "FINAL_BILL", "name_normalised": "TEST PERSON", "gender": "F", "evidence": {}}]
    if rng.random() < 0.1:  # inject an identity conflict to exercise FI-07
        identity.append({"source": "PHARMACY_BILL", "name_normalised": "OTHER PERSON", "gender": "M", "evidence": {}})
    dob_year = rng.randint(1945, 2005)
    return {
        "claim_id": f"CLM-RAND-{i:05d}", "evaluation_id": f"EV-{i}",
        "member": {"member_id": f"M{i}", "name_normalised": "TEST PERSON", "gender": "F", "dob": f"{dob_year}-06-15"},
        "policy": {"policy_no": f"P{i}", "period_start": "2026-04-01", "period_end": "2027-03-31", "continuous_cover_since": rng.choice(["2019-04-01", "2025-04-01", "2026-04-01"]),
                   "base_sum_insured": f"{base_si}.00", "cumulative_bonus": rng.choice(["0.00", "50000.00"]),
                   "paid_in_current_year": rand_money(rng, 0, base_si)},
        "hospital_id": "H", "hospital_is_network": rng.random() < 0.5, "bill_no": "B", "bill_stated_total": stated,
        "admission_date": "2026-07-01", "procedure_codes": rng.choice([[], ["LAP_CHOLECYSTECTOMY"], ["CATARACT"]]),
        "identity_observations": identity,
        "admission_date_observations": [{"source": "FINAL_BILL", "value": "2026-07-01", "evidence": {}}],
        "itemised_bill_available": True, "bill_lines": lines, "ped_signals": [], "portfolio_bill_number_index": [],
        "documents_present": ALL_DOCS,
        "reviewer_overrides": [{"override_id": f"OV-{i}", "line_id": l["line_id"], "rule_id": "R-LINE-PROPORTIONATE",
                                "amount": rand_money(rng, 0, int(D(l["billed"])) + 1), "reason_code": "TEST", "comment": "random override",
                                "actor": "T", "line_fingerprint": line_fingerprint(l)}
                               for l in lines if l["category"] in ("NURSING", "PROFESSIONAL_FEES") and rng.random() < 0.1],
    }


def assert_invariants(claim, out):
    rec = out["recommendation"]
    adj = out["adjustments"]
    total_adj = sum((D(a["amount"]) for a in adj), Decimal("0"))
    # FI-01 reconciliation
    if rec["computed"]:
        assert D(rec["billed_total"]) == D(rec["recommended_payable"]) + total_adj, "FI-01 reconciliation"
        # FI-03 non-negative and within available SI
        p = claim["policy"]
        avail = D(p["base_sum_insured"]) + D(p["cumulative_bonus"]) - D(p["paid_in_current_year"])
        assert D(rec["recommended_payable"]) >= 0, "FI-03 negative payable"
        assert D(rec["recommended_payable"]) <= max(avail, Decimal("0")) + Decimal("0.50"), "FI-03 exceeds available SI (beyond rounding)"
    # FI-02 per-line bound
    per = {}
    for a in adj:
        if a["level"] == "LINE":
            per.setdefault(a["line_id"], []).append(a)
    billed = {l["line_id"]: D(l["billed"]) for l in out["lines"]}
    for lid, items in per.items():
        assert sum(D(a["amount"]) for a in items) <= billed[lid], "FI-02 over-deduction"
        assert all(D(a["amount"]) >= 0 for a in items), "FI-02 negative line deduction"
        # FI-04 a fully disallowed line receives no later deduction
        full = [k for k, a in enumerate(items) if D(a["remaining_after"]) == 0]
        if full:
            assert all(D(a["amount"]) == 0 for a in items[full[0] + 1:]), "FI-04 deduction after full disallowance"
        # FI-05 at most one adjustment per (line, rule)
        rules = [a["rule_id"] for a in items]
        assert len(rules) == len(set(rules)), "FI-05 duplicate rule application on a line"
    # FI-06 every adjustment carries rule id + version
    for a in adj:
        assert a["rule_id"] and a["rule_version"] and a["authority"]["clause"], "FI-06 missing provenance or authority"
    # FI-07 blocked => not computed
    if rec["blocked_scopes"]:
        assert not rec["computed"] and rec["recommended_payable"] is None, "FI-07 computed despite block"
    # FI-08 never a final rejection
    assert rec["type"] in {"PAY_FULL", "PAY_PARTIAL", "QUERY", "QUERY_AND_REFER_MEDICAL", "REFER_MEDICAL", "REFER_CRC"}, "FI-08 unexpected type"
    assert rec["human_decision_required"] is True


def main(n=2000, seed=20261009):
    rng = random.Random(seed)
    stats = {"cases": 0, "computed": 0, "blocked": 0, "order_invariance_checked": 0, "nme_monotonic_checked": 0}
    for i in range(n):
        claim = gen_claim(rng, i)
        trf = tariff if claim["hospital_is_network"] else None
        out = evaluate(copy.deepcopy(claim), policy, nme, trf, checklist)
        assert_invariants(claim, out)
        stats["cases"] += 1
        stats["computed"] += out["recommendation"]["computed"]
        stats["blocked"] += bool(out["recommendation"]["blocked_scopes"])
        # FI-09 determinism
        assert evaluate(copy.deepcopy(claim), policy, nme, trf, checklist)["output_hash"] == out["output_hash"], "FI-09 non-deterministic"
        # FI-10 line-order invariance of the payable
        shuffled = copy.deepcopy(claim)
        rng.shuffle(shuffled["bill_lines"])
        out_s = evaluate(shuffled, policy, nme, trf, checklist)
        assert out_s["recommendation"]["recommended_payable"] == out["recommendation"]["recommended_payable"], "FI-10 order dependence"
        stats["order_invariance_checked"] += 1
        # FI-11 inflating a non-payable line never changes the payable
        nme_lines = [l for l in claim["bill_lines"] if l["description"] in ("Television charges", "Mineral water")]
        if nme_lines:
            bumped = copy.deepcopy(claim)
            for l in bumped["bill_lines"]:
                if l["line_id"] == nme_lines[0]["line_id"]:
                    l["billed"] = f"{D(l['billed']) + 1000:.2f}"
            bumped["bill_stated_total"] = f"{sum(D(l['billed']) for l in bumped['bill_lines']):.2f}"
            out_b = evaluate(bumped, policy, nme, trf, checklist)
            assert out_b["recommendation"]["recommended_payable"] == out["recommendation"]["recommended_payable"], "FI-11 NME leak"
            stats["nme_monotonic_checked"] += 1
    return stats


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    s = main(n)
    print(json.dumps({"result": "PASS", **s}))
