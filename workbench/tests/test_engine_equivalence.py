"""BL-13 acceptance: the production engine reproduces the research pack's harness on all five traces,
and the pack's targeted rule tests (TC-*) and invariants hold for the production engine too."""
from __future__ import annotations

import copy
import importlib.util
import unittest

from support import PACK, load_json

from aw.engine import evaluate as aw_evaluate, ENGINE_VERSION

CFG = PACK / "config"
TRACES = ["trace-1-straightforward", "trace-2-interacting-adjustments", "trace-2b-reviewer-override",
          "trace-3a-insufficient-conflicting", "trace-3b-after-new-evidence"]


def _harness():
    spec = importlib.util.spec_from_file_location("harness_engine", PACK / "verification" / "engine.py")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def configs():
    return (load_json(CFG / "policy-ILL-INDEMNITY-A.v2026.1.0.json"), load_json(CFG / "nme-list-ILL-A.v2026.1.0.json"),
            load_json(CFG / "tariff-ILL-HOSP-NW-01.v2026.07.json"), load_json(CFG / "checklist-IPD-REIMB.v2026.1.0.json"))


def strip_identity_gate(out: dict) -> dict:
    o = copy.deepcopy(out)
    for k in ("engine_version", "config_versions", "input_hash", "output_hash"):
        o.pop(k, None)
    o["rule_executions"] = [e for e in o["rule_executions"] if e["rule_id"] not in ("R-GATE-IDENTITY", "R-GATE-LINE-CATEGORY")]
    # execution IDs are sequence-numbered; the extra gate shifts them, so compare everything but the counter
    for coll in ("rule_executions", "adjustments", "findings", "query_items"):
        for item in o[coll]:
            for k in ("execution_id", "adjustment_id", "finding_id", "query_item_id"):
                item.pop(k, None)
            if "linked_findings" in item:
                item["linked_findings"] = len(item["linked_findings"])
    return o


class EngineEquivalence(unittest.TestCase):
    def test_unclassified_line_blocks_line_rules(self):
        policy, nme, tariff, checklist = configs()
        claim = load_json(PACK / "fixtures" / "claims" / "trace-1-straightforward.input.json")
        claim["bill_lines"][3]["category"] = "UNCLASSIFIED"
        out = aw_evaluate(claim, policy, nme, None, checklist)
        self.assertIsNone(out["recommendation"]["recommended_payable"])
        self.assertIn("LINE_RULES", out["recommendation"]["blocked_scopes"])
        self.assertIn("LINE_CATEGORY_UNCONFIRMED", {f["kind"] for f in out["findings"]})

    def test_reproduces_all_pack_traces(self):
        harness = _harness()
        policy, nme, tariff, checklist = configs()
        for t in TRACES:
            claim = load_json(PACK / "fixtures" / "claims" / f"{t}.input.json")
            trf = tariff if claim["hospital_is_network"] else None
            ours = aw_evaluate(copy.deepcopy(claim), policy, nme, trf, checklist)
            ref = harness.evaluate(copy.deepcopy(claim), policy, nme, trf, checklist)
            stored = load_json(PACK / "fixtures" / "claims" / f"{t}.output.json")
            with self.subTest(trace=t):
                self.assertEqual(ours["engine_version"], ENGINE_VERSION)
                self.assertEqual(strip_identity_gate(ours), strip_identity_gate(ref))
                self.assertEqual(ours["recommendation"], stored["recommendation"])
                self.assertEqual([a["amount"] for a in ours["adjustments"]], [a["amount"] for a in stored["adjustments"]])

    def test_key_payables(self):
        policy, nme, tariff, checklist = configs()
        expect = {"trace-1-straightforward": "107591.00", "trace-2-interacting-adjustments": "85000.00",
                  "trace-2b-reviewer-override": "85000.00", "trace-3a-insufficient-conflicting": None,
                  "trace-3b-after-new-evidence": "85570.00"}
        for t, payable in expect.items():
            claim = load_json(PACK / "fixtures" / "claims" / f"{t}.input.json")
            out = aw_evaluate(claim, policy, nme, tariff if claim["hospital_is_network"] else None, checklist)
            self.assertEqual(out["recommendation"]["recommended_payable"], payable, t)

    def test_transliteration_variant_does_not_block(self):
        """TC-MAT-02: LAKSHMI vs LAXMI passes; the harness (exact match) would have blocked ALL_FINANCIAL."""
        policy, nme, tariff, checklist = configs()
        claim = load_json(PACK / "fixtures" / "claims" / "trace-2-interacting-adjustments.input.json")
        for o in claim["identity_observations"]:
            if o["source"] == "FINAL_BILL":
                o["name_normalised"] = "LAXMI IYER"
        out = aw_evaluate(claim, policy, nme, tariff, checklist)
        self.assertEqual(out["recommendation"]["recommended_payable"], "85000.00")
        self.assertNotIn("ALL_FINANCIAL", out["recommendation"]["blocked_scopes"])

    def test_similar_name_goes_to_review_not_pass(self):
        policy, nme, tariff, checklist = configs()
        claim = load_json(PACK / "fixtures" / "claims" / "trace-1-straightforward.input.json")
        claim["identity_observations"][-1]["name_normalised"] = "ARJUN MEHRA"
        claim["identity_observations"][-1]["gender"] = None
        out = aw_evaluate(claim, policy, nme, None, checklist)
        kinds = {f["kind"] for f in out["findings"]}
        self.assertTrue({"IDENTITY_NEEDS_REVIEW", "IDENTITY_CONFLICT"} & kinds)


if __name__ == "__main__":
    unittest.main()
