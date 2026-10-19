# Independent extraction benchmark summary

Synthetic documents only. This report summarizes recorded runs; it does not tune or rerun the extractor. Original blind reports remain unchanged. Revealed regression scores are explicitly not blind generalization performance.

## Corpus inventory and coverage

| Source | Distinct claim IDs | Declared layouts | Document artifacts |
|---|---:|---:|---:|
| `workbench/corpus/out` | 20 | 5 | 120 |
| `workbench/heldout/out` | 10 | 2 | 124 |
| `workbench/heldout/challenge/out` | 8 | 2 | 100 |
| `workbench/heldout/final_reserved/out` | 6 | 2 | 70 |
| **Total unique** | **44** | **11** | **414** |

A PDF and its raster variants repeat underlying clinical content; they are not independent claims. The five training layout IDs change placement, font size and spacing around the same template. The six independently generated reserved layouts are structurally distinct hospital templates: two initial hospital documents, two subsequent challenge designs, and the final narrow receipt/account and sectioned service-card designs. This provides **seven structural templates**, not eleven equally diverse templates. The final two were scored before content was revealed to the extractor implementer.

| Required variant | Manifest/artifact evidence | Limitation |
|---|---|---|
| Clearly synthetic | All generators print a synthetic notice; reserved scoring recognized it on 124/124 and 100/100 artifacts | Training generator marking verified in code; no separate full raster-label recognition metric |
| Native PDF, scanned PDF, PNG, JPG | Training 60 native PDF/60 PNG; first reserved 30 native/30 scanned PDF/32 PNG/32 JPG; challenge 24 native/24 scanned PDF/26 PNG/26 JPG; final reserved 18 native PDF including duplicates/16 scanned PDF/18 PNG/18 JPG | Variant counts repeat claims |
| Skew, noise, stamp | Present in manifests; challenge combines noise/stamp; final contradiction cases combine skew/noise and multipage | Quality labels are generation settings, not a measured clinical scan-quality scale |
| Multipage tables | All training bills have two pages; reserved case 05, challenge case 04 and final case 03 split bill lines over two pages | Standalone first/second page images cannot each reconcile to whole-bill totals |
| Contradictory values | Training case 03 prints 9999.00 against 1500.00 line sum; reserved case 05 changes summary identity; challenge case 04 changes summary admission date; final case 03 prints 100.00 more than line sum | Full corpus conflict-detection accuracy is not measured |
| Injected instructions | Training case 04; reserved case 05 bill; challenge case 04 bill; final case 03 bill | Correct-abstention denominators differ between scorers, see below |
| Deliberately missing documents | 2/44 manifest bundles omit form/summary/bill | Both final case 02 bundles deliberately omit the discharge summary; actual product probe below |
| Exact duplicates | 2 duplicate SHA256 groups among 414 artifacts | Both final case 01 bills have byte-identical second artifacts and labelled duplicate_of; actual ingest deduplication observed below |

## Metric definitions and limits

Fields use exact equality against normalized ground truth; missing fields count wrong. Lines require exact description and amount; missing lines count wrong. Line scores do not measure quantity/rate correctness separately. Bill reconciliation means nonempty extracted lines sum to the extracted printed total, not semantic correctness of each row.

The training scorer and the reserved scorer apply a document-only abstention heuristic: any extracted confidence below .95, unreconciled classified itemised bills, an injection warning, or no fields. Training `must_abstain` labels propagate a claim-case label to every document, so a form in a contradictory-bill case can be labelled must-abstain although its own fields are correct. This is not a calibrated claim-level safety metric. Initial reserved/challenge correct-abstention counts cover injected bill artifacts only (8 per set, including repeated format variants). Final reserved labels cover 12 contradictory/injected bill artifacts, including partial-page images; missing-bundle labels are claim-level and are not included in document-scoring abstention. Identity/date conflict abstention accuracy was NOT RUN over the complete corpora.

Reserved reports also count a stricter **scoring-only** conservative gate for missing critical fields, OTHER/UNREADABLE classification and unreconciled expected itemised bills. Its count is not evidence that product gating occurred. A separate actual product probe is reported below.

No extraction accuracy is measured for admission records, pharmacy bills, investigation reports, prescriptions, receipts, ID proof, bank details, preauth requests or implant invoices in these four corpora. Their metrics are NOT MEASURED, not zero or passed.

## Recorded runs: training, blind and revealed remain separate

| Role / evidence file | Docs | Exact fields | Exact lines | Reconciled bills | Labelled correct abstention |
|---|---:|---|---|---|---|
| Training snapshot: [training-metrics.json](training-metrics.json) | 120 | 396/400 (99.00%) | 43/60 (71.67%) | 15/40 (37.50%) | 45/60 |
| Blind first reserved: [heldout-metrics.json](heldout-metrics.json) | 124 | 100/1132 (8.83%) | 0/400 (0.00%) | 0/44 (0.00%) | 8/8 |
| Blind second challenge: [challenge-metrics.json](challenge-metrics.json) | 100 | 157/876 (17.92%) | 0/256 (0.00%) | 0/36 (0.00%) | 8/8 |
| Blind final structural layouts: [final-reserved-blind-metrics.json](final-reserved-blind-metrics.json) | 70 | 158/610 (25.90%) | 0/156 (0.00%) | 0/30 (0.00%) | 10/12 |
| Earlier revealed first: [revealed-regression-first.json](revealed-regression-first.json) | 124 | 610/1132 (53.89%) | 379/400 (94.75%) | 30/44 (68.18%) | 8/8 |
| Earlier revealed challenge: [revealed-regression-challenge.json](revealed-regression-challenge.json) | 100 | 157/876 (17.92%) | 0/256 (0.00%) | 0/36 (0.00%) | 8/8 |
| Latest revealed first: [revealed-regression-first-latest.json](revealed-regression-first-latest.json) | 124 | 610/1132 (53.89%) | 379/400 (94.75%) | 30/44 (68.18%) | 8/8 |
| Latest revealed challenge: [revealed-regression-challenge-latest.json](revealed-regression-challenge-latest.json) | 100 | 175/876 (19.98%) | 65/256 (25.39%) | 8/36 (22.22%) | 8/8 |

### Training snapshot: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| CLAIM_FORM | native | 20 | 60/60 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 5/10 |
| CLAIM_FORM | scan | 5 | 15/15 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 20 | 80/80 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 5/10 |
| DISCHARGE_SUMMARY | scan | 5 | 20/20 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | native | 20 | 60/60 (100.00%) | 40/40 (100.00%) | 15/20 (75.00%) | 10/10 |
| FINAL_BILL_ITEMISED | scan | 5 | 15/15 (100.00%) | 0/5 (0.00%) | 0/5 (0.00%) | 0/0 |
| CLAIM_FORM | skew | 5 | 15/15 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | skew | 5 | 20/20 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 5 | 14/15 (93.33%) | 1/5 (20.00%) | 0/5 (0.00%) | 0/0 |
| CLAIM_FORM | noise | 5 | 15/15 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 5/5 |
| DISCHARGE_SUMMARY | noise | 5 | 20/20 (100.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/5 |
| FINAL_BILL_ITEMISED | noise | 5 | 15/15 (100.00%) | 0/5 (0.00%) | 0/5 (0.00%) | 5/5 |
| CLAIM_FORM | stamp | 5 | 14/15 (93.33%) | not applicable (0 labels) | not applicable (0 labels) | 5/5 |
| DISCHARGE_SUMMARY | stamp | 5 | 19/20 (95.00%) | not applicable (0 labels) | not applicable (0 labels) | 5/5 |
| FINAL_BILL_ITEMISED | stamp | 5 | 14/15 (93.33%) | 2/5 (40.00%) | 0/5 (0.00%) | 5/5 |

### Blind first reserved: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 3/66 (4.55%) | 0/60 (0.00%) | 0/6 (0.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 10 | 5/110 (4.55%) | 0/100 (0.00%) | 0/10 (0.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 9/60 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 10 | 15/100 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 3/42 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 10 | 5/70 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 3/66 (4.55%) | 0/60 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 9/60 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 3/42 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise | 6 | 3/66 (4.55%) | 0/60 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | noise | 6 | 9/60 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise | 6 | 3/42 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | stamp | 6 | 3/66 (4.55%) | 0/60 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | stamp | 6 | 9/60 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | stamp | 6 | 3/42 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 3/78 (3.85%) | 0/60 (0.00%) | 0/10 (0.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 9/60 (15.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 3/42 (7.14%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Blind second challenge: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 12/66 (18.18%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 8 | 16/88 (18.18%) | 0/64 (0.00%) | 0/8 (0.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 8 | 16/72 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 8 | 8/56 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 12/66 (18.18%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise_stamp | 6 | 9/66 (13.64%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | noise_stamp | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise_stamp | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 12/78 (15.38%) | 0/48 (0.00%) | 0/10 (0.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Blind final structural layouts: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 12/66 (18.18%) | 0/36 (0.00%) | 0/6 (0.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 8 | 16/88 (18.18%) | 0/48 (0.00%) | 0/8 (0.00%) | 2/2 |
| CLAIM_FORM | clean | 6 | 12/42 (28.57%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 6 | 12/42 (28.57%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | clean | 6 | 24/54 (44.44%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 4 | 16/36 (44.44%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise | 6 | 12/66 (18.18%) | 0/36 (0.00%) | 0/6 (0.00%) | 0/0 |
| CLAIM_FORM | noise | 6 | 12/42 (28.57%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew_noise_multipage | 10 | 10/78 (12.82%) | 0/36 (0.00%) | 0/10 (0.00%) | 8/10 |
| CLAIM_FORM | skew_noise_multipage | 6 | 10/42 (23.81%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | skew_noise_multipage | 6 | 22/54 (40.74%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Earlier revealed first: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 36/66 (54.55%) | 60/60 (100.00%) | 6/6 (100.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 10 | 61/110 (55.45%) | 100/100 (100.00%) | 10/10 (100.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 10 | 60/100 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 10 | 30/70 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 36/66 (54.55%) | 45/60 (75.00%) | 2/6 (33.33%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise | 6 | 36/66 (54.55%) | 56/60 (93.33%) | 5/6 (83.33%) | 0/0 |
| DISCHARGE_SUMMARY | noise | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | stamp | 6 | 36/66 (54.55%) | 60/60 (100.00%) | 6/6 (100.00%) | 0/0 |
| DISCHARGE_SUMMARY | stamp | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | stamp | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 45/78 (57.69%) | 58/60 (96.67%) | 1/10 (10.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Earlier revealed challenge: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 12/66 (18.18%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 8 | 16/88 (18.18%) | 0/64 (0.00%) | 0/8 (0.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 8 | 16/72 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 8 | 8/56 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 12/66 (18.18%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise_stamp | 6 | 9/66 (13.64%) | 0/48 (0.00%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | noise_stamp | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise_stamp | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 12/78 (15.38%) | 0/48 (0.00%) | 0/10 (0.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Latest revealed first: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 36/66 (54.55%) | 60/60 (100.00%) | 6/6 (100.00%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 10 | 61/110 (55.45%) | 100/100 (100.00%) | 10/10 (100.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 10 | 60/100 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 10 | 30/70 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 36/66 (54.55%) | 45/60 (75.00%) | 2/6 (33.33%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise | 6 | 36/66 (54.55%) | 56/60 (93.33%) | 5/6 (83.33%) | 0/0 |
| DISCHARGE_SUMMARY | noise | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | stamp | 6 | 36/66 (54.55%) | 60/60 (100.00%) | 6/6 (100.00%) | 0/0 |
| DISCHARGE_SUMMARY | stamp | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | stamp | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 45/78 (57.69%) | 58/60 (96.67%) | 1/10 (10.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 36/60 (60.00%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 18/42 (42.86%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

### Latest revealed challenge: per type and generation-quality

| Document type | Quality | Docs | Exact fields | Exact lines | Reconciled bills | Correct abstention / labelled need |
|---|---|---:|---|---|---|---|
| FINAL_BILL_ITEMISED | clean | 6 | 15/66 (22.73%) | 14/48 (29.17%) | 1/6 (16.67%) | 0/0 |
| FINAL_BILL_ITEMISED | native | 8 | 20/88 (22.73%) | 0/64 (0.00%) | 4/8 (50.00%) | 2/2 |
| DISCHARGE_SUMMARY | clean | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| DISCHARGE_SUMMARY | native | 8 | 16/72 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | clean | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | native | 8 | 8/56 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | skew | 6 | 15/66 (22.73%) | 23/48 (47.92%) | 2/6 (33.33%) | 0/0 |
| DISCHARGE_SUMMARY | skew | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | skew | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | noise_stamp | 6 | 12/66 (18.18%) | 15/48 (31.25%) | 0/6 (0.00%) | 0/0 |
| DISCHARGE_SUMMARY | noise_stamp | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | noise_stamp | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| FINAL_BILL_ITEMISED | multipage | 10 | 17/78 (21.79%) | 13/48 (27.08%) | 1/10 (10.00%) | 6/6 |
| DISCHARGE_SUMMARY | multipage | 6 | 12/54 (22.22%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |
| CLAIM_FORM | multipage | 6 | 6/42 (14.29%) | not applicable (0 labels) | not applicable (0 labels) | 0/0 |

## Interpretation of revealed regressions

The latest first-set regression records 610/1132 exact fields and 379/400 exact lines. Full native bills score 100/100 lines and 10/10 reconciliations; scanned PDFs score 81/100 lines and 6/10 reconciliations. Its stacked label/value layout still omits half the identity/date fields. Native and scan errors are distinct; overall 30/44 reconciliations include standalone images from multipage bills.

The latest challenge regression records 175/876 fields and 65/256 lines. Eighteen of 36 bills remain misclassified as summary bills. Native challenge bills score 0/64 exact lines despite 4/8 total reconciliations. Inspection of actual extractor output found `General ward bed` became `1 bed`, and `Nursing care` became `2`, with null quantity and copied amounts. Grounded quotes and reconciled money therefore do not establish correct bill semantics. Member ID, policy number, admission date and discharge date each score 0/96; bill number 0/36, bill date 0/32. No acceptable blind performance or readiness for arbitrary real documents is claimed.

The final untouched structural layouts scored 158/610 fields (25.90%), 0/156 exact lines and 0/30 bill reconciliations. Classification matched 0/70 expected types. Shared document-only abstention caught 10/12 labelled contradictory/injected bill artifacts; the stricter scoring-only gate caught 70/70. These failures were retained without tuning. They demonstrate that the no-model extractor still requires manual handling for unfamiliar formats.

## Bounded actual product safety probe

The independent probe used a throwaway native PostgreSQL 16 cluster/database, isolated temporary object storage, actual ingestion, extraction, grounding, reconciliation, worker and evaluation code. Three revealed challenge native-PDF bundles (nine originals) were uploaded without declared type. The seeded member name/gender was aligned to the printed synthetic identity so an unrelated demo-person mismatch did not manufacture the block. Seed policy/hospital configuration remained illustrative. This is a three-case safety observation, not an accuracy estimate or proof of every material conflict path.

```bash
AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=workbench/src:workbench/tests \
  workbench/.venv/bin/python workbench/heldout/product_safety_probe.py
```

| Challenge case | Original docs | Jobs drained | Evaluation | Payable | Attempted approval | Persisted decisions |
|---|---:|---:|---|---|---|---:|
| CLM-CHALLENGE-03-01 | 3 | 7 | BLOCKED | None | evaluation-blocked | 0 |
| CLM-CHALLENGE-04-01 | 3 | 7 | BLOCKED | None | evaluation-blocked | 0 |
| CLM-CHALLENGE-03-04 | 3 | 7 | BLOCKED | None | evaluation-blocked | 0 |

Actual result: **3/3 evaluations BLOCKED, 3/3 attempted approvals refused (`evaluation-blocked`), zero persisted decisions, 21 jobs completed and no non-success jobs**. Findings included DOCUMENT_READING_UNCONFIRMED, DOCUMENT_INCOMPLETE, BILL_TOTAL_MISMATCH and LINE_CATEGORY_UNCONFIRMED. The injected/date-conflicting case abstained, but the parser did not extract the dates; this does not demonstrate correct date-conflict recognition.

Evidence: [product-abstention-probe.json](product-abstention-probe.json), [product-abstention-probe.log](product-abstention-probe.log). The isolated cluster and object directory were cleaned up. No existing app/database state or source was mutated.

### Final reserved missing/duplicate/contradiction probe

After blind scoring completed, all six final reserved bundles were processed through a separate throwaway PostgreSQL database. This included two deliberately missing discharge summaries, two duplicate uploads, and two contradictory/injected multipage bills. No financial decision was accepted. These are bounded product safety results, not extraction accuracy or calibrated conflict-recognition sensitivity.

```bash
AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=workbench/src:workbench/tests \
  workbench/.venv/bin/python workbench/heldout/product_safety_probe.py \
  --directory workbench/heldout/final_reserved/out \
  --claims CLM-FINAL-05-01 CLM-FINAL-06-01 CLM-FINAL-05-02 \
           CLM-FINAL-06-02 CLM-FINAL-05-03 CLM-FINAL-06-03 \
  --evidence-file final-reserved-product-probe.json
```

| Case | Upload artifacts | Duplicate responses | Stored docs | Jobs | Evaluation | Attempted approval |
|---|---:|---:|---:|---:|---|---|
| CLM-FINAL-05-01 | 4 | 1 | 3 | 7 | BLOCKED | evaluation-blocked |
| CLM-FINAL-06-01 | 4 | 1 | 3 | 7 | BLOCKED | evaluation-blocked |
| CLM-FINAL-05-02 | 2 | 0 | 2 | 5 | BLOCKED | evaluation-blocked |
| CLM-FINAL-06-02 | 2 | 0 | 2 | 5 | BLOCKED | evaluation-blocked |
| CLM-FINAL-05-03 | 3 | 0 | 3 | 7 | BLOCKED | evaluation-blocked |
| CLM-FINAL-06-03 | 3 | 0 | 3 | 7 | BLOCKED | evaluation-blocked |

Actual result: **6/6 blocked with null payable; 6/6 attempted approvals refused; zero decisions; 2/2 exact duplicate uploads identified without new document rows; 18 uploaded artifacts became 16 stored documents; 38 jobs drained with no non-success jobs**. Both deliberately missing bundles and both contradictory/injected bundles were blocked. Because unfamiliar document classification/reading also blocks these bundles, this does not isolate each individual rule's sensitivity. Cluster and objects were cleaned up.

Evidence: [final-reserved-product-probe.json](final-reserved-product-probe.json), [final-reserved-product-probe.log](final-reserved-product-probe.log).

## Reproducibility and provenance

Reserved generation: `workbench/.venv/bin/python workbench/heldout/generate.py`, `workbench/.venv/bin/python workbench/heldout/challenge/generate.py`, and `workbench/.venv/bin/python workbench/heldout/final_reserved/generate.py`. Extraction scoring: `PYTHONPATH=workbench/src workbench/.venv/bin/python workbench/heldout/evaluate.py --directory <corpus-dir> --evidence-file <new-report.json> --metrics-file <new-details.json>`. Use new filenames to preserve existing snapshots. Training evidence comes from `PYTHONPATH=src .venv/bin/python -m aw.corpus.measure corpus/out` run from workbench.

Code fingerprints are recorded in each reserved/regression report. Original failure report hashes are preserved in `workbench/heldout/original-benchmark-hashes.json`; all four original blind detail/compact reports were rechecked SHA256-identical during this summary. The product probe ran against current code; earlier extraction scores are recorded snapshots, not assumed current-code accuracy. None of these runs contacts hosted OCR, cloud models or external hospital services.
