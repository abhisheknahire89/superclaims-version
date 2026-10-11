"""Mutation test for validate_contracts.py: seed known defects into a temporary copy of the pack and
assert the validator reports each one. Usage: python3 verification/mutation_test_contracts.py"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_with(mutate, expect_substring):
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(ROOT, tmp / "p", ignore=shutil.ignore_patterns("raw", "wireframes", "*.png", "*.jpg"))
    mutate(tmp / "p")
    r = subprocess.run([sys.executable, str(tmp / "p/verification/validate_contracts.py")], capture_output=True, text=True)
    shutil.rmtree(tmp)
    report = json.loads(r.stdout)
    hit = any(expect_substring in f for f in report["failures"])
    return r.returncode != 0 and hit, report["failures"][:2]


def edit_json(path, fn):
    d = json.loads(path.read_text())
    fn(d)
    path.write_text(json.dumps(d))


MUTANTS = [
    ("float money in an evaluation output", lambda p: edit_json(p / "fixtures/claims/trace-1-straightforward.output.json",
        lambda d: d["recommendation"].__setitem__("recommended_payable", 107591.0)), "C3 trace-1"),
    ("adjustment without authority", lambda p: edit_json(p / "fixtures/claims/trace-2-interacting-adjustments.output.json",
        lambda d: d["adjustments"][0].pop("authority")), "C3 trace-2-interacting"),
    ("document evidence without quote", lambda p: edit_json(p / "fixtures/claims/trace-1-straightforward.input.json",
        lambda d: d["bill_lines"][0]["evidence"][0].pop("quote")), "C2b trace-1"),
    ("clinical finding without uncertainty note", lambda p: edit_json(p / "fixtures/claims/trace-3b-after-new-evidence.output.json",
        lambda d: [f.__setitem__("uncertainty_note", None) for f in d["findings"] if f["category"] == "CLINICAL"]), "C3 trace-3b"),
    ("repudiation example without CRC reference", lambda p: (p / "api/openapi.yaml").write_text((p / "api/openapi.yaml").read_text().replace(
        "disposition: APPROVED_PARTIAL\n                  approved_payable: '107591.00'", "disposition: REPUDIATED_WITH_CRC_APPROVAL\n                  approved_payable: '107591.00'")), "C6 example recordDecision"),
    ("disposition enum drift (QUERY_ISSUED re-added to API only)", lambda p: (p / "api/openapi.yaml").write_text((p / "api/openapi.yaml").read_text().replace(
        "disposition: {enum: [APPROVED_FULL, APPROVED_PARTIAL, REPUDIATED_WITH_CRC_APPROVAL", "disposition: {enum: [APPROVED_FULL, APPROVED_PARTIAL, QUERY_ISSUED, REPUDIATED_WITH_CRC_APPROVAL")), "C7 disposition"),
    ("policy config missing a clause reference", lambda p: edit_json(p / "config/policy-ILL-INDEMNITY-A.v2026.1.0.json",
        lambda d: d["clause_refs"].pop("R-CLAIM-COPAY")), "C2 policy-"),
    ("workflow config letting a TPA issue repudiations", lambda p: edit_json(p / "config/workflow-TENANT-DEMO.v2026.1.0.json",
        lambda d: d["repudiation"].__setitem__("behaviour", "ISSUE_WITH_CRC_REFERENCE")), "C2 workflow-"),
]
results = []
for label, mut, expect in MUTANTS:
    caught, sample = run_with(mut, expect)
    results.append((label, caught, sample))
    print(f"{'caught' if caught else 'MISSED':<7} {label}")
sys.exit(0 if all(c for _, c, _ in results) else 1)
