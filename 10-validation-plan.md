# 10 — Validation plan, metrics and readiness gates

Status: **PROPOSED** plan. Proof status is tracked per item in §7 as one of four values:

- **planned** — not yet done.
- **simulated** — run on synthetic data.
- **executed** — actually run (in this task), with reproducible scripts.
- **independently reviewed** — checked by someone who did not build it.

Nothing in this pack has reached independently reviewed. The synthetic traces and property tests show that the *logic behaves as specified*. They say nothing about real-world accuracy.

## 1. Evaluation dataset

- **Source and permission.** Closed IPD reimbursement files from the pilot customer, shared under a data-processing agreement. The customer's legal basis for the purpose must be confirmed (OQ-31). Data stays in the customer's tenant account; annotators work there.
- **De-identification for annotation.**
  - Replace names, phone numbers, addresses, policy, member and bank numbers with consistent pseudonyms. Shift dates per claim by a random offset of whole days, preserving intervals.
  - Mask doctor and hospital names only if the customer requires it, because tariffs need hospital identity.
  - Re-identification keys stay with the customer.
- **Sampling.**
  - Stratify by: hospital network status (network vs non-network); claim size (< ₹50k, ₹50k–2L, > ₹2L); document quality (native PDF vs scan vs phone photo); historical outcome (paid in full / partial / repudiated / query); presence of ICU; product.
  - Oversample rare but costly strata (repudiations, ICU, > ₹2L) and record the weights, so metrics can be reported both stratified and re-weighted to production mix.
  - Sizes:
    - technical prototype: 50 claims, plus 200 pages for the OCR/LLM bake-off;
    - pilot entry: 300 claims;
    - production gate: 1,000 claims with a 200-claim hold-out never used for tuning.
- **Ground truth.**
  - Two experienced processors independently re-adjudicate each claim, **blind to the historical decision and to AW's output**. They produce field values, line categories, deductions with reasons, and recommendation type.
  - A medical officer answers the clinical questions.
  - Disagreements go to a third senior adjudicator.
  - Inter-annotator agreement is reported: Cohen's κ on categorical fields; percentage of claims with payable within ±₹1.
  - Historical decisions are recorded but are **not** ground truth (09 §2).
- **Leakage-control truth.** For M-FIN-04, a deduction counts as "correct additional" only if the ground-truth panel agrees with it *and* the historical decision missed it. Wrong deductions count against.

## 2. Metrics

Each metric has a denominator, ground truth and exclusions. Thresholds are **proposed** and must be confirmed with the customer before the pilot. "Prototype / Pilot / Production" refers to the gates in §6.

| ID | What it measures | Unit and denominator | Ground truth | Exclusions | Severity | Proposed threshold (Proto / Pilot / Prod) |
|---|---|---|---|---|---|---|
| M-EXT-01 | Field extraction exact-match (after normalisation) | C1 fields present in documents | Panel values | Fields absent from all documents | C1 critical | ≥ 95% / ≥ 97% / ≥ 98% |
| M-EXT-02 | Auto-accepted C1 error rate | C1 fields auto-accepted without a human | Panel | — | Critical | ≤ 1% / ≤ 0.5% / ≤ 0.3% |
| M-EXT-03 | Coverage: C1 fields auto-accepted | C1 fields present | — | — | Efficiency | ≥ 50% / ≥ 70% / ≥ 80% |
| M-EXT-04 | Grounding pass rate | Model-extracted facts | Deterministic check | — | Integrity | ≥ 98% at all gates |
| M-BIL-01 | Bill-line recall (lines captured) | Lines on itemised bills | Panel line list | Illegible lines marked by panel | High | ≥ 97% / ≥ 99% / ≥ 99.5% |
| M-BIL-02 | Line category accuracy | Captured lines | Panel category | — | High | ≥ 90% / ≥ 95% / ≥ 97% |
| M-RUL-01 | Rule applicability accuracy (right rule fires or does not) | (claim, rule) pairs | Panel's reasoning per rule | Rules blocked by gates | High | ≥ 95% / ≥ 98% / ≥ 99% |
| M-RUL-02 | Rule computation correctness given correct inputs | Rule executions with panel-confirmed inputs | Recompute | — | Critical | 100% at all gates (any miss is a bug) |
| M-FIN-01 | Payable exact match | Computed claims | Panel payable | Claims with open MO questions at panel time | Critical | ≥ 85% / ≥ 92% / ≥ 95% within ±₹1 |
| M-FIN-02 | Absolute payable error | Computed claims | Panel | — | Critical | Median ₹0; p95 ≤ ₹2,000 (pilot) |
| M-FIN-03 | Deduction precision and recall (by rupee) | Deducted rupees (precision); panel-deducted rupees (recall) | Panel | — | High | Precision ≥ 95%, recall ≥ 90% (pilot) |
| M-FIN-04 | Net leakage control | Σ correct additional deductions − Σ incorrect deductions, ÷ Σ paid | Panel + historical | — | Business | Reported, not gated, until a baseline exists |
| M-FIN-05 | Reconciliation invariants FI-01..FI-11 | All evaluations | Code | — | Critical | 0 violations ever |
| M-EVD-01 | Evidence traceability | Adjustments and findings | Every item has a resolvable page+region+quote and a rule/clause | — | Critical | 100% |
| M-EVD-02 | Explanation quality (rubric 1–4: correct, specific clause, understandable to the claimant, no unsupported claims) | Sampled deduction explanations (n ≥ 100) | Two raters | — | High | Mean ≥ 3.0 / 3.3 / 3.5; zero "unsupported claim" |
| M-ABS-01 | Missing-information detection recall | Claims with a panel-identified gap (missing or illegible document, identity or date conflict) | Panel | — | Critical | ≥ 90% / ≥ 95% / ≥ 97% |
| M-ABS-02 | Over-abstention rate | Claims the panel could complete without a query but AW blocked | Panel | — | Efficiency | ≤ 20% / ≤ 10% / ≤ 7% |
| M-ABS-03 | Unsafe computation rate | Claims where AW computed a payable although the panel found a blocking gap | Panel | — | Critical | ≤ 1% / ≤ 0.5% / ≤ 0.2% |
| M-ANO-01 | Anomaly flag precision | Flags raised | FWA analyst triage outcome "warranted review" | — | Medium | ≥ 30% (pilot), tuned upward |
| M-ANO-02 | Anomaly flag rate | Claims | — | — | Workload | ≤ 5% of claims flagged |
| M-CLN-01 | Clinical escalation recall | Claims where the MO panel says MO review was needed | MO panel | — | High | ≥ 90% (pilot) |
| M-CLN-02 | Clinical summary citation completeness | Summary sentences | Lint + spot check | — | Critical | 100% cited; 0 banned phrases |
| M-CLN-03 | Clinical summary factual accuracy | Sampled sentences (n ≥ 200) | MO rater | — | High | ≥ 98% |
| M-OPS-01 | Reviewer correction rate | Fields shown to reviewers | Reviewer actions | — | Efficiency | Reported per field; target trend ↓ |
| M-OPS-02 | Override rate by rule | Engine adjustments | Reviewer actions | — | Quality signal | Any rule > 10% overrides → review |
| M-OPS-03 | Handling time (active human minutes) | Closed claims | UI telemetry (focus time), validated by time-and-motion on 30 claims | Waiting time | Business | ≥ 40% reduction vs measured baseline (pilot) |
| M-OPS-04 | Recommendation-to-decision agreement | Decided claims | Decision vs recommendation (type and payable ±₹1) | Claims with new evidence after recommendation | Signal, not accuracy | Reported. Not a quality metric on its own: agreement can be high because reviewers rubber-stamp |
| M-OPS-05 | Latency | Claims | Timestamps | — | SLO | NFR-01/02 |
| M-OPS-06 | Reliability | Jobs | Job states | — | SLO | ≥ 99% jobs succeed without manual intervention |
| M-OPS-07 | Cost per claim | Claims | Gateway + billing | — | Business | Within ±25% of 09 model |

**Terms are not interchangeable.**

- **Accuracy** (exact match against the panel) is a different measure from **precision** (correct share of what AW asserted, e.g. deductions).
- **Automation/coverage rate** (share accepted without a human) is different again.
- **Reviewer agreement** (M-OPS-04) is a weak proxy, because it rises with over-trust.

The competitor's ">97% precision" and "99% accuracy" (01 §4) cannot be compared with any of these until their definitions are known.

## 3. Test catalogue

Type: U = unit, P = property, I = integration, W = workflow/UI, S = security, R = reliability, E = evaluation on data.

| Test | Type | What | Expected | Status |
|---|---|---|---|---|
| TC-INT-01 | I | Create claim twice with the same Idempotency-Key | Same response; one row | partially executed (synthetic): replay and key reuse with a different body are tested on `POST /claims/{id}/decisions`; the same mechanism serves `POST /claims` (workbench `tests/test_api.py`) |
| TC-INT-02 | I | Same `external_ref`, different key | 409 | planned |
| TC-DOC-01 | I | Upload an exact duplicate file | Existing document returned (200) | **executed** (synthetic, service level: workbench `tests/test_workflow.py` test_quarantine_and_duplicates) |
| TC-DOC-02 | E | Unreadable page | `FAILED_UNREADABLE` + query item | planned |
| TC-DOC-03 | W | Supersede a document | Evaluation → STALE; decision buttons disabled | **executed** for STALE and the server-side 409 (workbench `tests/test_workflow.py`); the disabled button is in the UI code but not asserted by a test |
| TC-DOC-04 | U | Checklist per workflow; missing itemised bill blocks line rules | Block + hospital query | **executed** (trace 3a) |
| TC-DOC-05 | U | Implant billed without invoice | Line blocked + query | planned |
| TC-DOC-06 | U | Checklist item missing (incl. conditional items) | Non-blocking `DOCUMENT_INCOMPLETE` + query to the configured addressee; gate-covered items skipped | **executed** (`test_rules.py`) |
| TC-EXT-01 | E | C1/C2 accuracy on golden set | M-EXT-01..03 thresholds | planned |
| TC-EXT-02 | U | Quote not on page | `NOT_FOUND`; fact unusable | **executed** (synthetic: workbench `tests/test_workflow.py` test_ungrounded_values_are_never_used) |
| TC-EXT-03 | E | Multi-page table continuation | Lines captured once | planned |
| TC-EXT-04 | E | Handwritten C1 field | `NEEDS_REVIEW` | planned |
| TC-RCN-01 | U | Conflicting admission dates | `DATE_CONFLICT` blocks ROOM_DAYS etc. | **executed** (trace 3a) |
| TC-MAT-01 | U | Name and gender mismatch on bill | `IDENTITY_CONFLICT` blocks ALL_FINANCIAL; eligibility uses identity-matched documents only | **executed** (trace 3a; `test_rules.py`) |
| TC-MAT-02 | E | Transliteration variants (LAKSHMI/LAXMI, initials) | Pass or review, never block | **executed** in the workbench engine (R-GATE-IDENTITY 1.1.0, workbench `tests/test_engine_equivalence.py`); the harness still uses exact matching. Thresholds need real member data |
| TC-BIL-01 | U/P | Σ lines ≠ stated total | Blocks line rules | **executed** (engine gate; randomised claims use matching totals) |
| TC-BIL-02 | E | Category accuracy | M-BIL-02 | planned |
| TC-ELG-01 | U | Admission outside policy period | `REFER_CRC` | planned (code path exists) |
| TC-ELG-02 | U | PED signal within waiting period | REVIEW finding; no deduction | **executed** (traces 3a/3b) |
| TC-ELG-03 | U | Specific waiting period not met | REVIEW finding | planned (trace 2 shows the passing case) |
| TC-ELG-04 | U | Date conflict between identity-matched documents, same eligibility outcome | Rule runs; invariance recorded | **executed** (`test_rules.py`) |
| TC-ELG-07 | U | Date conflict where candidate dates give different eligibility outcomes | Rule blocked (WAITING_PERIOD); no finding guessed | **executed** (`test_rules.py`) |
| TC-ELG-05 | U | Exclusion text match | REVIEW finding | planned |
| TC-ELG-06 | U | Pre/post-hospitalisation window | Line flag | planned |
| TC-TAR-01 | U | Tariff cap | Excess deducted with tariff version | **executed** (trace 2) |
| TC-TAR-02 | U | Item missing from tariff | Flag, no deduction | planned |
| TC-TAR-03 | U | Package replacement consumes components | No double deduction | planned |
| TC-NME-01 | U | NME matches | Full deduction with list version | **executed** (trace 1) |
| TC-NME-02 | U | NME billed under an associated category | No proportionate deduction after full disallowance | **executed** (trace 2 L19; FI-04) |
| TC-CAL-01 | U | Room and ICU caps | Correct excess | **executed** (trace 2) |
| TC-CAL-02 | U | Proportionate deduction with exemptions and ICU context | Correct lines only | **executed** (trace 2) |
| TC-CAL-03 | U | Co-pay then SI cap; order sensitivity | ₹85,000 vs ₹76,500 if reversed | **executed** (trace 2 + independent recomputation) |
| TC-CAL-04 | U | Rounding adjustment recorded | −₹0.50 in trace 1 | **executed** |
| TC-CAL-05 | U | Duplicate pharmacy invoice | Deducted once | **executed** (trace 2) |
| TC-CAL-06 | U | Sub-limit (cataract) | Capped | simulated (randomised claims include CATARACT; not asserted separately) |
| TC-CAL-07 | U | Deductible | Applied before co-pay | planned |
| TC-CAL-08 | U | Multi-room stay, lines in any order | Same payable; day-weighted actual room rate | **executed** (`test_rules.py`; FI-10 with multi-room claims) |
| TC-CAL-09 | U | Room days billed beyond the stay (MIDNIGHTS) | `ROOM_DAYS_EXCEED_STAY` review finding; no deduction | **executed** (`test_rules.py`) |
| TC-EVD-01 | U | Every adjustment carries authority and evidence | artifact@version, doc, clause; non-empty evidence with quote or record reference | **executed** (`test_rules.py`; FI-06; DB checks) |
| TC-FIN-01..11 | P | Invariants FI-01..FI-11 | 0 violations | **executed** (3,000 random claims, seed 20261009) |
| TC-CLN-01 | E | Every summary sentence cited | M-CLN-02 | planned |
| TC-CLN-02 | U | Banned verdict phrases | Lint rejects | planned |
| TC-CLN-03 | U | LOS outlier question | MO question raised | planned |
| TC-ANO-01 | U | Bill-number reuse | MEDIUM flag; "pattern for review" wording | **executed** (trace 3a) |
| TC-ANO-02 | E | Flag precision and rate | M-ANO-01..02 | planned |
| TC-ANO-03 | U | Near-duplicate claims | Flag | planned |
| TC-RCM-01 | P | Blocked ⇒ no payable | FI-07 | **executed** |
| TC-RCM-02 | E | Explanation rubric | M-EVD-02 | planned |
| TC-REV-01 | I | Override without comment | 422 | planned (API schema rule exists; DB check exists) |
| TC-REV-02 | W | Correction → new evaluation | Supersedes; diff shown | simulated (trace 3a → 3b) |
| TC-REV-03 | U | Override survives re-evaluation only if the line is unchanged | Re-applied with `engine_amount` kept; otherwise `OVERRIDE_NEEDS_RECONFIRMATION` | **executed** (`test_rules.py`; trace 2b) |
| TC-QRY-01 | W | Query must be approved before release | Unapproved never exported | planned (DB check exists) |
| TC-QRY-02 | W | Non-response | No auto-closure; supervisor queue | planned |
| TC-DEC-01 | I | Repudiation without CRC reference | Rejected | **executed** (DB negative test; API example validator) |
| TC-DEC-02 | I | Decision on STALE evaluation | 409 | **executed** (synthetic: workbench `tests/test_workflow.py` test_stale_evaluation_cannot_be_decided) |
| TC-DEC-03 | I | Decision when a second-approval rule fires (limit, deviation > ₹5,000, deductions > 30% of billed) | 403 without approval; approver ≠ requester | partly executed (DB negative test for self-approval; DEC-0002 loaded with SUP-02); API test planned |
| TC-RPR-01 | W | Late document after decision | REOPENED; delta decision | simulated (3a → 3b before decision) |
| TC-EXP-01 | I | Re-export same decision | One export per target | planned (DB unique exists) |
| TC-EXP-02 | I | Webhook receiver down 2 h | Retries, then delivered; de-duplicated by `event_id` | planned |
| TC-AUD-01 | U/I | Hash chain verifies; events in causal order; UPDATE forbidden | Pass | **executed** (`render_traces.py` self-consistency, `validate_db.sh` append-only) |
| TC-CFG-01 | I | Publish by the author | Rejected (four-eyes) | **executed** (DB negative test) |
| TC-CFG-02 | W | New config version, non-retroactive | Open claims unchanged | planned |
| TC-CFG-03 | U | Rule would deduct but no clause reference is configured | Evaluation fails (`ConfigurationError`); no deduction | **executed** (`test_rules.py`) |
| TC-CFG-04 | U | New tariff or NME list version | Different `input_hash`, so a new evaluation | **executed** (`test_rules.py`) |
| TC-SEC-01 | S | Cross-tenant read | 0 rows | **executed** (RLS test) |
| TC-SEC-02 | S | Role matrix (03 §4) | Forbidden actions → 403 | partially executed: read-only user cannot create a claim; a non-named user cannot approve (workbench `tests/test_api.py`). Full matrix planned |
| TC-SEC-03 | S | Injected instruction in bill | No behavioural effect; warning raised | **executed** (synthetic: workbench `tests/test_workflow.py` test_injected_instructions_have_no_effect) |
| TC-SEC-04 | S | PHI in logs | CI fails | planned |
| TC-SEC-05 | S | Malware / type-mismatch upload | QUARANTINED | **executed** for type mismatch (workbench `tests/test_workflow.py`); no malware scanner yet |
| TC-SEC-06 | S | Bulk access anomaly | Alert | planned |
| TC-REL-01 | R | OCR outage | Backoff; no partial evaluation | planned |
| TC-REL-02 | R | LLM outage | Manual path; claim visible | planned |
| TC-REL-03 | R | Repeated callback | Idempotent | planned |
| TC-REL-04 | R | Worker crash mid-evaluation | No duplicate adjustments | planned (DB uniques executed) |
| TC-TAT-01 | U | Clock computation and alerts | Reimbursement due 15 days from first submission; interest exposure from intimation; per workflow config | planned |
| TC-UX-01 | W | Keyboard-only review of trace 2 | Completed without mouse | planned |
| TC-UX-02 | W | Any finding or deduction → highlighted evidence in one click ≤ 300 ms | Pass | partially executed: one click shows the highlighted page in the workbench UI (workbench `tests/ui_smoke.py`); the 300 ms budget has not been measured |
| TC-UX-03 | W | WCAG 2.2 AA automated + manual audit | No serious issues | planned |
| TC-UX-04 | W | Next claim ≤ 1 click; due-time default sort | Pass | planned |
| TC-OPS-01 | I | Metrics reconcile with DB | Equal | planned |

## 4. Golden and edge cases (to build into the golden set)

| ID | Case | Expected behaviour |
|---|---|---|
| EC-01 | Unreadable or missing final bill | Block line rules; hospital query |
| EC-02 | Identity mismatch (name or gender) between bill and policy | Block ALL_FINANCIAL; eligibility on identity-matched documents only; query |
| EC-03 | Admission date differs by 1 day (midnight admission) | Block date-dependent rules; invariance for eligibility |
| EC-04 | Duplicate pharmacy invoice (photocopy) | One deduction |
| EC-05 | The same bill submitted on two claims | Anomaly flag across claims |
| EC-06 | Tariff exists but item missing | Flag, no deduction |
| EC-07 | Room above eligibility plus ICU stay | Room/ICU caps; proportionate only on ward-context associated lines |
| EC-08 | Sub-limit and SI cap both binding | Sub-limit first, then co-pay, then SI cap per configuration |
| EC-09 | Policy config changed mid-year | Version by admission date; no retroactive change by default |
| EC-10 | Unsupported product (no config) | `CONFIGURATION_MISSING` block |
| EC-11 | Clinical history ambiguous ("h/o DM?") | MO question; no deduction |
| EC-12 | Late itemised bill after a query | STALE → new evaluation; findings carried over |
| EC-13 | Repeated TMS callback | Idempotent |
| EC-14 | OCR or LLM outage during discharge | Manual path within the 3-hour clock |
| EC-15 | Bill in Hindi or mixed script | Detected; routed to a human |
| EC-16 | Instruction text addressed to AI in a bill footer | Ignored; warning; anomaly signal |
| EC-17 | Concurrent claims exhausting SI | Ledger reservation prevents double spend |
| EC-18 | Negative line (discount) on bill | Handled as stated discount; reconciliation |
| EC-19 | GST shown separately on items | Configuration decides payable treatment (OQ-28) |
| EC-20 | Patient died during treatment | Priority routing (E-REG-01 ¶16c; UNVERIFIED paraphrase, verbatim re-capture pending) |

## 5. Change gates for models, prompts and configuration

Any change to the OCR provider, model, prompt, extraction pipeline or rule engine must:

1. run the full golden set;
2. show no regression beyond the tolerance on any critical metric (M-EXT-02, M-RUL-02, M-FIN-01, M-ABS-03, M-EVD-01);
3. pass property tests FI-01..FI-11;
4. be canaried on 5% of new claims for 48 h, with the override rate monitored.

Configuration changes must replay the product's golden claims and get four-eyes approval (CAP-21).

## 6. Readiness gates

| Gate | Purpose | Evidence required to pass | Not claimed at this gate |
|---|---|---|---|
| **G1 Technical prototype** | Show the end-to-end slice works on real documents | - End-to-end run on 50 permissioned claims for one product configuration and one tariff<br>- OCR/LLM bake-off report (BL-07)<br>- M-EXT, M-BIL, M-FIN-01, M-ABS-03 at prototype thresholds<br>- FI-01..11 green<br>- DDL and API contract tests green<br>- Security baseline: SSO, RLS, PHI-free logs<br>- A medical advisor has reviewed the clinical boundaries | Accuracy at scale; production security; any regulatory approval |
| **G2 Supervised pilot** | Use with real reviewers, human decision on every claim | G1, plus:<br>- 300-claim evaluation at pilot thresholds, inter-annotator agreement reported<br>- Customer sign-off of configuration by clause<br>- Penetration test with critical and high findings fixed<br>- DPA signed; legal positions on OQ-24/27/45 documented<br>- Incident runbooks<br>- Restore drill passed<br>- Reviewer training<br>- Rollback plan (TMS remains the system of record) | Autonomous processing; production SLA; certification |
| **G3 Production** | Routine use at volume | G2, plus:<br>- 3 months of pilot metrics stable within thresholds on the hold-out and in live monitoring<br>- Measured handling-time reduction (M-OPS-03) and net leakage (M-FIN-04) reported with method<br>- Grievance and ombudsman reversals tracked<br>- Annual cyber audit evidence for the customer<br>- ISMS operating<br>- DR tested cross-region<br>- On-call established<br>- Customer's compliance sign-off | Clinical validation of medical judgement (none is made); fraud determination (none is made) |

Nothing in this research task meets any gate. It provides the specification and the executable checks the gates will use. The Phase 1 workbench (`workbench/`) runs the G1 slice end to end, but only on synthetic documents, so it does not meet G1 either.

## 7. Proof status register

| Proof | Status | Where |
|---|---|---|
| Rule arithmetic for traces 1, 2, 2b, 3a, 3b | executed (synthetic) | `verification/run_traces.py`, `trace-report.md` |
| Targeted rule tests (10) | executed (synthetic) | `verification/test_rules.py` |
| Independent recomputation of trace 2 | executed (by a separate formula in the same script; not by a separate person) | same |
| Financial invariants FI-01..FI-11 on 3,000 random claims | executed (synthetic) | `verification/test_invariants.py` |
| DDL validity (31 tables), trace and decision load, SQL reconciliation, authority on every adjustment, 11 constraint negative tests, RLS isolation | executed | `verification/validate_db.sh` |
| JSON Schemas, fixtures, configs, OpenAPI refs, examples, enum parity (53 checks) | executed | `verification/validate_contracts.py` |
| Validator mutation test (8 broken inputs must be rejected) | executed: 8/8 caught | `verification/mutation_test_contracts.py` |
| Settlement worksheets reconcile to decisions | executed (synthetic) | `verification/build_worksheets.py` |
| Audit hash chains for all traces | executed (self-consistency only: the same script writes and checks them) | `verification/render_traces.py` |
| Cost-per-claim model | executed (assumption-driven) | `verification/cost_model.py` |
| Workbench (Phase 1 build): synthetic PDFs → ingest → extraction → grounding → resolution → engine → review → decision → worksheet → export; reproduces traces 1, 2, 2b, 3a, 3b | executed (synthetic; 27 automated tests) | `workbench/tests/`, `workbench/docs/traceability.md` |
| Workbench engine equivalence with the harness | executed (all pack traces, ignoring IDs and the two WB gates) | `workbench/tests/test_engine_equivalence.py` |
| Reviewer UI walk-through in a headless browser | executed (synthetic; no console or HTTP errors) | `workbench/tests/ui_smoke.py` |
| Extraction accuracy, OCR quality, latency | planned | BL-07, §1 |
| Reviewer time saving | planned | BL-03, M-OPS-03 |
| Review of the pack by a separate agent that had not written it | executed: 25 defects found and repaired (11 §5) | — |
| Independent human review (claims expert, actuary, counsel) | planned | BL-38 |
