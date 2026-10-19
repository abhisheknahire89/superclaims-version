"""Summarize recorded evidence without modifying any benchmark report."""
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json

PACK = Path(__file__).resolve().parents[2]
EVIDENCE = PACK / "workbench/evidence/2026-10-12"


def ratio(correct, total):
    return f"{correct}/{total} ({correct / total * 100:.2f}%)" if total else "not applicable (0 labels)"


def totals(report):
    if "totals" in report:
        return report["totals"]
    result = Counter()
    for group in report["groups"]:
        result.update({k:v for k,v in group.items() if isinstance(v, (int, float)) and not isinstance(v, bool)})
    return result


def main():
    text = ["# Independent extraction benchmark summary", "",
            "Synthetic documents only. This report summarizes recorded runs; it does not tune or rerun the extractor. Original blind reports remain unchanged. Revealed regression scores are explicitly not blind generalization performance.", "",
            "## Corpus inventory and coverage", "",
            "| Source | Distinct claim IDs | Declared layouts | Document artifacts |",
            "|---|---:|---:|---:|"]
    all_claims, all_layouts, files = set(), set(), []
    bundles = defaultdict(set)
    manifests = []
    for relative in ("workbench/corpus/out", "workbench/heldout/out", "workbench/heldout/challenge/out", "workbench/heldout/final_reserved/out"):
        directory = PACK / relative
        manifest = json.loads((directory / "manifest.json").read_text())
        rows = manifest["documents"]
        claims = {row["claim_id"] for row in rows}
        layouts = {row.get("layout_id", row.get("layout")) for row in rows}
        all_claims.update(claims)
        all_layouts.update(layouts)
        manifests.append(manifest)
        for row in rows:
            file = directory / row.get("path", row.get("file"))
            assert file.is_file(), str(file)
            files.append(file)
            bundles[row["claim_id"]].add(row["document_type"])
        text.append(f"| `{relative}` | {len(claims)} | {len(layouts)} | {len(rows)} |")
    duplicate_groups = sum(count > 1 for count in Counter(hashlib.sha256(file.read_bytes()).hexdigest() for file in files).values())
    text += [f"| **Total unique** | **{len(all_claims)}** | **{len(all_layouts)}** | **{len(files)}** |", "",
             "A PDF and its raster variants repeat underlying clinical content; they are not independent claims. The five training layout IDs change placement, font size and spacing around the same template. The six independently generated reserved layouts are structurally distinct hospital templates: two initial hospital documents, two subsequent challenge designs, and the final narrow receipt/account and sectioned service-card designs. This provides **seven structural templates**, not eleven equally diverse templates. The final two were scored before content was revealed to the extractor implementer.", "",
             "| Required variant | Manifest/artifact evidence | Limitation |", "|---|---|---|",
             "| Clearly synthetic | All generators print a synthetic notice; reserved scoring recognized it on 124/124 and 100/100 artifacts | Training generator marking verified in code; no separate full raster-label recognition metric |",
             "| Native PDF, scanned PDF, PNG, JPG | Training 60 native PDF/60 PNG; first reserved 30 native/30 scanned PDF/32 PNG/32 JPG; challenge 24 native/24 scanned PDF/26 PNG/26 JPG; final reserved 18 native PDF including duplicates/16 scanned PDF/18 PNG/18 JPG | Variant counts repeat claims |",
             "| Skew, noise, stamp | Present in manifests; challenge combines noise/stamp; final contradiction cases combine skew/noise and multipage | Quality labels are generation settings, not a measured clinical scan-quality scale |",
             "| Multipage tables | All training bills have two pages; reserved case 05, challenge case 04 and final case 03 split bill lines over two pages | Standalone first/second page images cannot each reconcile to whole-bill totals |",
             "| Contradictory values | Training case 03 prints 9999.00 against 1500.00 line sum; reserved case 05 changes summary identity; challenge case 04 changes summary admission date; final case 03 prints 100.00 more than line sum | Full corpus conflict-detection accuracy is not measured |",
             "| Injected instructions | Training case 04; reserved case 05 bill; challenge case 04 bill; final case 03 bill | Correct-abstention denominators differ between scorers, see below |",
             f"| Deliberately missing documents | {sum(len(types) < 3 for types in bundles.values())}/{len(all_claims)} manifest bundles omit form/summary/bill | Both final case 02 bundles deliberately omit the discharge summary; actual product probe below |",
             f"| Exact duplicates | {duplicate_groups} duplicate SHA256 groups among {len(files)} artifacts | Both final case 01 bills have byte-identical second artifacts and labelled duplicate_of; actual ingest deduplication observed below |", "",
             "## Metric definitions and limits", "",
             "Fields use exact equality against normalized ground truth; missing fields count wrong. Lines require exact description and amount; missing lines count wrong. Line scores do not measure quantity/rate correctness separately. Bill reconciliation means nonempty extracted lines sum to the extracted printed total, not semantic correctness of each row.", "",
             "The training scorer and the reserved scorer apply a document-only abstention heuristic: any extracted confidence below .95, unreconciled classified itemised bills, an injection warning, or no fields. Training `must_abstain` labels propagate a claim-case label to every document, so a form in a contradictory-bill case can be labelled must-abstain although its own fields are correct. This is not a calibrated claim-level safety metric. Initial reserved/challenge correct-abstention counts cover injected bill artifacts only (8 per set, including repeated format variants). Final reserved labels cover 12 contradictory/injected bill artifacts, including partial-page images; missing-bundle labels are claim-level and are not included in document-scoring abstention. Identity/date conflict abstention accuracy was NOT RUN over the complete corpora.", "",
             "Reserved reports also count a stricter **scoring-only** conservative gate for missing critical fields, OTHER/UNREADABLE classification and unreconciled expected itemised bills. Its count is not evidence that product gating occurred. A separate actual product probe is reported below.", "",
             "No extraction accuracy is measured for admission records, pharmacy bills, investigation reports, prescriptions, receipts, ID proof, bank details, preauth requests or implant invoices in these four corpora. Their metrics are NOT MEASURED, not zero or passed.", "",
             "## Recorded runs: training, blind and revealed remain separate", "",
             "| Role / evidence file | Docs | Exact fields | Exact lines | Reconciled bills | Labelled correct abstention |",
             "|---|---:|---|---|---|---|"]
    runs = [
        ("Training snapshot", "training-metrics.json"),
        ("Blind first reserved", "heldout-metrics.json"),
        ("Blind second challenge", "challenge-metrics.json"),
        ("Blind final structural layouts", "final-reserved-blind-metrics.json"),
        ("Earlier revealed first", "revealed-regression-first.json"),
        ("Earlier revealed challenge", "revealed-regression-challenge.json"),
        ("Latest revealed first", "revealed-regression-first-latest.json"),
        ("Latest revealed challenge", "revealed-regression-challenge-latest.json"),
    ]
    reports = []
    for role, filename in runs:
        report = json.loads((EVIDENCE / filename).read_text())
        counts = totals(report)
        reports.append((role, filename, report))
        text.append(f"| {role}: [{filename}]({filename}) | {counts['documents']} | {ratio(counts['fields_correct'], counts['fields_total'])} | {ratio(counts['lines_correct'], counts['lines_total'])} | {ratio(counts['total_reconciled'], counts['bills'])} | {counts['correct_abstention']}/{counts['must_abstain']} |")
    for role, filename, report in reports:
        text += ["", f"### {role}: per type and generation-quality", "",
                 "| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |",
                 "|---|---|---:|---|---|---|---|"]
        for group in report["groups"]:
            text.append(f"| {group['document_type']} | {group['quality']} | {group['documents']} | {ratio(group['fields_correct'], group['fields_total'])} | {ratio(group['lines_correct'], group['lines_total'])} | {ratio(group['total_reconciled'], group['bills'])} | {group['correct_abstention']}/{group['must_abstain']} |")
    text += ["", "## Interpretation of revealed regressions", "",
             "The latest first-set regression records 610/1132 exact fields and 379/400 exact lines. Full native bills score 100/100 lines and 10/10 reconciliations; scanned PDFs score 81/100 lines and 6/10 reconciliations. Its stacked label/value layout still omits half the identity/date fields. Native and scan errors are distinct; overall 30/44 reconciliations include standalone images from multipage bills.", "",
             "The latest challenge regression records 175/876 fields and 65/256 lines. Eighteen of 36 bills remain misclassified as summary bills. Native challenge bills score 0/64 exact lines despite 4/8 total reconciliations. Inspection of actual extractor output found `General ward bed` became `1 bed`, and `Nursing care` became `2`, with null quantity and copied amounts. Grounded quotes and reconciled money therefore do not establish correct bill semantics. Member ID, policy number, admission date and discharge date each score 0/96; bill number 0/36, bill date 0/32. No acceptable blind performance or readiness for arbitrary real documents is claimed.", "",
             "The final untouched structural layouts scored 158/610 fields (25.90%), 0/156 exact lines and 0/30 bill reconciliations. Classification matched 0/70 expected types. Shared document-only abstention caught 10/12 labelled contradictory/injected bill artifacts; the stricter scoring-only gate caught 70/70. These failures were retained without tuning. They demonstrate that the no-model extractor still requires manual handling for unfamiliar formats.", "",
             "## Bounded actual product safety probe", ""]
    probe = json.loads((EVIDENCE / "product-abstention-probe.json").read_text())
    text += ["The independent probe used a throwaway native PostgreSQL 16 cluster/database, isolated temporary object storage, actual ingestion, extraction, grounding, reconciliation, worker and evaluation code. Three revealed challenge native-PDF bundles (nine originals) were uploaded without declared type. The seeded member name/gender was aligned to the printed synthetic identity so an unrelated demo-person mismatch did not manufacture the block. Seed policy/hospital configuration remained illustrative. This is a three-case safety observation, not an accuracy estimate or proof of every material conflict path.", "",
             "```bash", "AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=workbench/src:workbench/tests \\", "  workbench/.venv/bin/python workbench/heldout/product_safety_probe.py", "```", "",
             "| Challenge case | Original docs | Jobs drained | Evaluation | Payable | Attempted approval | Persisted decisions |", "|---|---:|---:|---|---|---|---:|"]
    for claim in probe["claims"]:
        text.append(f"| {claim['claim_id']} | {claim['documents']} | {claim['jobs_drained']} | {claim['evaluation_status']} | {claim['recommendation']['recommended_payable']} | {claim['attempted_approval_result']} | {claim['persisted_decisions']} |")
    text += ["", "Actual result: **3/3 evaluations BLOCKED, 3/3 attempted approvals refused (`evaluation-blocked`), zero persisted decisions, 21 jobs completed and no non-success jobs**. Findings included DOCUMENT_READING_UNCONFIRMED, DOCUMENT_INCOMPLETE, BILL_TOTAL_MISMATCH and LINE_CATEGORY_UNCONFIRMED. The injected/date-conflicting case abstained, but the parser did not extract the dates; this does not demonstrate correct date-conflict recognition.", "",
             "Evidence: [product-abstention-probe.json](product-abstention-probe.json), [product-abstention-probe.log](product-abstention-probe.log). The isolated cluster and object directory were cleaned up. No existing app/database state or source was mutated.", "",
             "### Final reserved missing/duplicate/contradiction probe", ""]
    final_probe = json.loads((EVIDENCE / "final-reserved-product-probe.json").read_text())
    text += ["After blind scoring completed, all six final reserved bundles were processed through a separate throwaway PostgreSQL database. This included two deliberately missing discharge summaries, two duplicate uploads, and two contradictory/injected multipage bills. No financial decision was accepted. These are bounded product safety results, not extraction accuracy or calibrated conflict-recognition sensitivity.", "",
             "```bash", "AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=workbench/src:workbench/tests \\", "  workbench/.venv/bin/python workbench/heldout/product_safety_probe.py \\", "  --directory workbench/heldout/final_reserved/out \\", "  --claims CLM-FINAL-05-01 CLM-FINAL-06-01 CLM-FINAL-05-02 \\", "           CLM-FINAL-06-02 CLM-FINAL-05-03 CLM-FINAL-06-03 \\", "  --evidence-file final-reserved-product-probe.json", "```", "",
             "| Case | Upload artifacts | Duplicate responses | Stored docs | Jobs | Evaluation | Attempted approval |", "|---|---:|---:|---:|---:|---|---|"]
    for claim in final_probe["claims"]:
        text.append(f"| {claim['claim_id']} | {claim['documents']} | {claim['duplicate_uploads']} | {claim['stored_documents']} | {claim['jobs_drained']} | {claim['evaluation_status']} | {claim['attempted_approval_result']} |")
    jobs_count = sum(c["jobs_drained"] for c in final_probe["claims"])
    text += ["", f"Actual result: **6/6 blocked with null payable; 6/6 attempted approvals refused; zero decisions; 2/2 exact duplicate uploads identified without new document rows; 18 uploaded artifacts became 16 stored documents; {jobs_count} jobs drained with no non-success jobs**. Both deliberately missing bundles and both contradictory/injected bundles were blocked. Because unfamiliar document classification/reading also blocks these bundles, this does not isolate each individual rule's sensitivity. Cluster and objects were cleaned up.", "",
             "Evidence: [final-reserved-product-probe.json](final-reserved-product-probe.json), [final-reserved-product-probe.log](final-reserved-product-probe.log).", "",
             "## Reproducibility and provenance", "",
             "Reserved generation: `workbench/.venv/bin/python workbench/heldout/generate.py`, `workbench/.venv/bin/python workbench/heldout/challenge/generate.py`, and `workbench/.venv/bin/python workbench/heldout/final_reserved/generate.py`. Extraction scoring: `PYTHONPATH=workbench/src workbench/.venv/bin/python workbench/heldout/evaluate.py --directory <corpus-dir> --evidence-file <new-report.json> --metrics-file <new-details.json>`. Use new filenames to preserve existing snapshots. Training evidence comes from `PYTHONPATH=src .venv/bin/python -m aw.corpus.measure corpus/out` run from workbench.", "",
             "Code fingerprints are recorded in each reserved/regression report. Original failure report hashes are preserved in `workbench/heldout/original-benchmark-hashes.json`; all four original blind detail/compact reports were rechecked SHA256-identical during this summary. The product probe ran against current code; earlier extraction scores are recorded snapshots, not assumed current-code accuracy. None of these runs contacts hosted OCR, cloud models or external hospital services.", ""]
    hashes = json.loads((PACK / "workbench/heldout/original-benchmark-hashes.json").read_text())
    for path, digest in hashes.items():
        assert hashlib.sha256((PACK / path).read_bytes()).hexdigest() == digest
    final_hashes = json.loads((PACK / "workbench/heldout/final-reserved-blind-hashes.json").read_text())
    for path, digest in final_hashes.items():
        assert hashlib.sha256((PACK / path).read_bytes()).hexdigest() == digest
    output = EVIDENCE / "extraction-benchmark-summary.md"
    output.write_text("\n".join(text), encoding="utf-8")
    print(f"Wrote {output}; {len(all_claims)} claims, {len(all_layouts)} declared layouts, {len(files)} artifacts; originals unchanged")


if __name__ == "__main__":
    main()
