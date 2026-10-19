"""Enrich revealed-regression reports; original blind benchmarks never change."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import argparse

PACK = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--suffix", default="")
args = parser.parse_args()
suffix = "-" + args.suffix if args.suffix else ""
metrics_file = "revealed-regression" + suffix + ".json"
originals = json.loads((HERE / "original-benchmark-hashes.json").read_text())
for path, digest in originals.items():
    assert hashlib.sha256((PACK / path).read_bytes()).hexdigest() == digest, f"Original benchmark modified: {path}"

comparisons = []
for directory, evidence_name in ((HERE / "out", "revealed-regression-first" + suffix + ".json"), (HERE / "challenge/out", "revealed-regression-challenge" + suffix + ".json")):
    original = json.loads((directory / "metrics.json").read_text())
    result = json.loads((directory / metrics_file).read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = {row["path"]: row for row in manifest["documents"]}
    per_field = {}
    for document in result["documents"]:
        for field in expected[document["file"]]["expected_fields"]:
            metric = per_field.setdefault(field, dict(expected=0, correct=0, missing_or_null=0, wrong=0))
            metric["expected"] += 1
            error = document.get("incorrect_fields", {}).get(field)
            if error is None and document.get("error") is None:
                metric["correct"] += 1
            elif error is None or error.get("actual") is None:
                metric["missing_or_null"] += 1
            else:
                metric["wrong"] += 1
    result["per_field"] = per_field
    result["classification_confusions"] = [dict(expected=k[0], actual=k[1], documents=v) for k,v in Counter((d["expected_type"], d["classified_type"]) for d in result["documents"]).items()]
    result["original_benchmark_retained_unchanged"] = True
    result["blind_performance_claim"] = False
    result["benchmark_role"] = "revealed_regression"
    result["comparison"] = {key: dict(original=original["totals"][key], regression=result["totals"][key]) for key in ("documents", "fields_correct", "fields_total", "lines_correct", "lines_total", "total_reconciled", "bills", "classified_correct", "abstained", "conservative_abstained", "errors")}
    (directory / metrics_file).write_text(json.dumps(result, indent=2) + "\n")
    compact = {k:v for k,v in result.items() if k != "documents"}
    compact["details_path"] = str((directory / metrics_file).relative_to(PACK))
    (PACK / "workbench/evidence/2026-10-12" / evidence_name).write_text(json.dumps(compact, indent=2) + "\n")
    comparisons.append(dict(evidence=evidence_name, comparison=result["comparison"], critical_fields={k:v for k,v in per_field.items() if k in {"patient.name", "patient.gender", "patient.member_id", "policy.number", "admission.date", "discharge.date", "bill.number", "bill.date", "bill.total"}}, latency=result["latency"], confusions=result["classification_confusions"]))
print(json.dumps(comparisons, indent=2))
