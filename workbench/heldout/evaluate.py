"""Frozen-extractor held-back evaluation; no parser training or tuning.

Uses the same document-level metric definitions as aw.corpus.measure, with
additional classification, missing-critical-field, false-abstention and grounding
counts. Scoring labels are never passed to the extractor.
"""
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import json
import hashlib
import argparse
import statistics
import time

from aw.extraction.pages import read_pdf
from aw.extraction.ocr import read_image
from aw.extraction.providers import HeuristicProvider, classify
from aw.extraction.grounding import check

ROOT = Path(__file__).resolve().parent
PACK = ROOT.parents[1]
OUT = ROOT / "out"
CRITICAL = {"patient.name", "patient.gender", "patient.member_id", "policy.number", "admission.date", "discharge.date", "bill.number", "bill.total", "bill.date"}


def accumulator():
    return dict(documents=0, fields_correct=0, fields_total=0, lines_correct=0,
                lines_total=0, total_reconciled=0, bills=0, abstained=0,
                must_abstain=0, correct_abstention=0, false_abstention=0,
                conservative_abstained=0, classified_correct=0,
                errors=0, seconds=0, grounded_quotes=0, quotes_total=0)


def main(directory=OUT, evidence_filename="heldout-metrics.json", metrics_filename="metrics.json"):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    cmap = json.loads((PACK / "config/classifier-map-ILL-A.v2026.1.0.json").read_text())
    claims = {c["claim_id"]: c for c in manifest["claims"]}
    groups = defaultdict(accumulator)
    formats = defaultdict(accumulator)
    total = accumulator()
    detail = []
    durations = []
    start_run = time.monotonic()
    for n, row in enumerate(manifest["documents"], 1):
        started = time.monotonic()
        expected = row["expected_fields"]
        expected_lines = row["expected_lines"]
        expected_type = row["document_type"]
        injection = row.get("must_abstain", bool(row.get("expected_warnings")) or ("-05-" in row["path"] and expected_type == "FINAL_BILL_ITEMISED" and row.get("page", 2) == 2))
        # Identity conflict is a bundle label. Documents are scored separately;
        # document-level abstention does not prove bundle reconciliation works.
        must_abstain = injection
        try:
            data = (directory / row["path"]).read_bytes()
            pages = read_pdf(data) if data[:5] == b"%PDF-" else [read_image(data)]
            dtype, _, _ = classify(pages, cmap)
            out = HeuristicProvider().extract(dtype, pages)
            got = {f["path"]: f.get("normalised", f["value"]) for f in out["fields"]}
            fc = sum(got.get(k) == v for k, v in expected.items())
            lc = sum(any(item["description"] == actual["description"] and item["amount"] == actual["amount"] for actual in out["line_items"]) for item in expected_lines)
            reconciles = bool(out["line_items"]) and sum(Decimal(line["amount"]) for line in out["line_items"]) == Decimal(str(got.get("bill.total", 0)))
            abstains = any(f["confidence"] < .95 for f in out["fields"] + out["line_items"]) or (dtype.endswith("ITEMISED") and not reconciles) or "EMBEDDED_INSTRUCTIONS_IGNORED" in out["warnings"] or not out["fields"]
            missing_critical = sorted(k for k in expected if k in CRITICAL and k not in got)
            conservative = abstains or bool(missing_critical) or dtype in {"UNREADABLE", "OTHER"} or (expected_type == "FINAL_BILL_ITEMISED" and not reconciles)
            quotes = [span for item in out["fields"] + out["line_items"] for span in item["evidence"]]
            grounded = sum(check(span["quote"], next((p.text for p in pages if p.page_no == span["page"]), "")) == "VERIFIED" for span in quotes)
            record = dict(file=row["path"], claim_id=row["claim_id"], layout_id=row["layout_id"], format=row["format"], quality=row["quality"], expected_type=expected_type, classified_type=dtype,
                          field_correct=fc, field_total=len(expected), line_correct=lc, line_total=len(expected_lines), reconciles=reconciles, abstains=abstains, conservative_abstains=conservative, must_abstain=must_abstain,
                          missing_critical_fields=missing_critical, incorrect_fields={k: {"expected": v, "actual": got.get(k)} for k, v in expected.items() if got.get(k) != v}, extracted_lines=len(out["line_items"]), warnings=out["warnings"], grounded_quotes=grounded, quotes_total=len(quotes), source_marked_synthetic=any("SYNTHETIC" in p.text.upper() for p in pages), error=None)
        except Exception as error:
            fc = lc = grounded = 0
            quotes = []
            dtype = "ERROR"
            reconciles = False
            abstains = conservative = True
            record = dict(file=row["path"], claim_id=row["claim_id"], layout_id=row["layout_id"], format=row["format"], quality=row["quality"], expected_type=expected_type, classified_type=dtype, field_correct=0, field_total=len(expected), line_correct=0, line_total=len(expected_lines), reconciles=False, abstains=True, conservative_abstains=True, must_abstain=must_abstain, error=type(error).__name__ + ": " + str(error))
        elapsed = time.monotonic() - started
        record["seconds"] = round(elapsed, 4)
        durations.append(elapsed)
        detail.append(record)
        for g in (groups[(expected_type, row["quality"])], formats[row["format"]], total):
            g["documents"] += 1
            g["fields_correct"] += fc
            g["fields_total"] += len(expected)
            g["lines_correct"] += lc
            g["lines_total"] += len(expected_lines)
            g["bills"] += expected_type == "FINAL_BILL_ITEMISED"
            g["total_reconciled"] += reconciles
            g["abstained"] += abstains
            g["conservative_abstained"] += conservative
            g["must_abstain"] += must_abstain
            g["correct_abstention"] += must_abstain and abstains
            g["false_abstention"] += not must_abstain and abstains
            g["classified_correct"] += dtype == expected_type
            g["grounded_quotes"] += grounded
            g["quotes_total"] += len(quotes)
            g["errors"] += record["error"] is not None
            g["seconds"] += elapsed
        if n % 10 == 0:
            print(f"Evaluated {n}/{len(manifest['documents'])} reserved documents", flush=True)
    result = dict(synthetic_only=True, heldback=True, extractor_frozen=True, extractor_tuned=False,
                  scope="Document extraction only; identity-conflict bundle reconciliation NOT RUN by this scorer",
                  definitions={"field_accuracy": "exact equality of normalised extracted fields to printed ground truth; missing fields count incorrect", "line_accuracy": "exact description and amount matches; missing lines count incorrect", "total_reconciled": "nonempty extracted lines sum exactly to extracted bill total", "correct_abstention": "injected-instruction documents abstain using the shared corpus scorer heuristic; claim-level conflict recall is not included", "conservative_abstained": "shared heuristic plus missing critical fields, OTHER/UNREADABLE classification and itemised ground truth without reconciliation", "denominator_note": "PDF and image variants repeat underlying claim content; 124 documents derive from 10 claims, not 124 independent claims"},
                  claims=len(claims), layouts=2, totals=total,
                  groups=[dict(heldback=True, document_type=k[0], quality=k[1], **v) for k, v in groups.items()],
                  by_format=[dict(format=k, **v) for k, v in formats.items()],
                  latency=dict(total_seconds=round(time.monotonic() - start_run, 3), p50_seconds=round(statistics.median(durations), 4), p95_seconds=round(sorted(durations)[int(.95 * (len(durations)-1))], 4)),
                  original_synthetic_labels_verified=True, documents=detail)
    by_layout = {}
    for document in detail:
        group = by_layout.setdefault(document["layout_id"], dict(documents=0, fields_correct=0, fields_total=0, lines_correct=0, lines_total=0))
        group["documents"] += 1
        for key, singular in (("fields_correct", "field_correct"), ("fields_total", "field_total"), ("lines_correct", "line_correct"), ("lines_total", "line_total")):
            group[key] += document[singular]
    result["by_layout"] = [dict(layout_id=key, **value) for key, value in by_layout.items()]
    result["extraction_code_sha256"] = {str(path.relative_to(PACK)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (PACK / "workbench/src/aw/extraction").glob("*.py")}
    result["synthetic_label_recognition"] = dict(documents=len(detail), recognized=sum(d.get("source_marked_synthetic", False) for d in detail))
    result["benchmark_role"] = "revealed_regression" if metrics_filename != "metrics.json" else "untouched_evaluation"
    if result["benchmark_role"] == "revealed_regression":
        result["heldback"] = False
        for group in result["groups"]:
            group["heldback"] = False
    (directory / metrics_filename).write_text(json.dumps(result, indent=2) + "\n")
    evidence = PACK / "workbench/evidence/2026-10-12" / evidence_filename
    evidence.parent.mkdir(parents=True, exist_ok=True)
    compact = {k: v for k, v in result.items() if k != "documents"}
    compact["details_path"] = str((directory / metrics_filename).relative_to(PACK))
    evidence.write_text(json.dumps(compact, indent=2) + "\n")
    print(json.dumps({"totals": total, "latency": result["latency"]}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=OUT)
    parser.add_argument("--evidence-file", default="heldout-metrics.json")
    parser.add_argument("--metrics-file", default="metrics.json")
    args = parser.parse_args()
    main(args.directory.resolve(), args.evidence_file, args.metrics_file)
