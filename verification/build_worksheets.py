"""Generate settlement worksheets for decided traces (1 and 2) from engine output + decision.
Writes fixtures/worksheets/WS-*.json; validated by validate_contracts.py against settlement-worksheet.schema.json."""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = {
    "trace-1-straightforward": {"decision_id": "DEC-0001", "disposition": "APPROVED_PARTIAL", "decided_by": "PROC-07", "second_approver": None, "approved": "107591.00"},
    "trace-2-interacting-adjustments": {"decision_id": "DEC-0002", "disposition": "APPROVED_PARTIAL", "decided_by": "PROC-11", "second_approver": "SUP-02", "approved": "85000.00"},
}
GRIEVANCE = {  # content is customer-supplied per tenant; placeholders mark what the TPA letter must contain (E-REG-04)
    "insurer_grievance_procedure": "<customer-supplied: insurer's grievance redressal procedure; complaints may also be registered on IRDAI's Bima Bharosa portal (E-REG-03)>",
    "grievance_officer_contact": "<customer-supplied: grievance redressal office and officer contact>",
    "ombudsman_procedure": "<customer-supplied: procedure to approach the Insurance Ombudsman if not satisfied>",
    "ombudsman_contact": "<customer-supplied: office of the Insurance Ombudsman for the policyholder's jurisdiction>",
}
(ROOT / "fixtures/worksheets").mkdir(parents=True, exist_ok=True)
for name, dec in DECISIONS.items():
    out = json.loads((ROOT / f"fixtures/claims/{name}.output.json").read_text())
    inp = json.loads((ROOT / f"fixtures/claims/{name}.input.json").read_text())
    billed = Decimal(out["recommendation"]["billed_total"])
    approved = Decimal(dec["approved"])
    ws = {
        "worksheet_id": f"WS-{dec['decision_id']}",
        "claim_id": out["claim_id"],
        "status": "SYNTHETIC",
        "decision": {**{k: dec[k] for k in ("decision_id", "disposition", "decided_by", "second_approver")}, "evaluation_id": out["evaluation_id"]},
        "amounts": {"claimed": inp.get("bill_stated_total"), "billed": f"{billed:.2f}", "approved": dec["approved"], "disallowed_total": f"{billed - approved:.2f}"},
        "disallowances": [{"line_id": a["line_id"] or "CLAIM", "amount": a["amount"], "reason": a["explanation"], "clause": f"{a['authority']['doc_id']} {a['authority']['clause']}",
                           "rule_id": a["rule_id"]} for a in out["adjustments"] if Decimal(a["amount"]) != 0],
        "line_table": [{"line_id": l["line_id"], "description": l["description"], "billed": l["billed"], "payable": l["payable"]} for l in out["lines"]],
        "grievance_route": GRIEVANCE,
        "provenance": {"engine_version": out["engine_version"], "config_versions": out["config_versions"], "output_hash": out["output_hash"]},
    }
    assert Decimal(ws["amounts"]["disallowed_total"]) == sum(Decimal(d["amount"]) for d in ws["disallowances"]), f"{name}: disallowances do not sum"
    (ROOT / f"fixtures/worksheets/{ws['worksheet_id']}.json").write_text(json.dumps(ws, indent=2, ensure_ascii=False) + "\n")
print("worksheets written; disallowances reconcile")
