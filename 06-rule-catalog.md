# 06 — Rule catalog, calculations and worked traces

Status: **PROPOSED** rule design. Policies, tariffs and lists used in examples are **ILLUSTRATIVE** (invented, labelled in every file). Regulatory statements cite E-REG evidence and are flagged where an interpretation needs qualified legal or actuarial review. The arithmetic in §7 was produced and cross-checked by code that actually ran: `verification/run_traces.py` (engine plus an independent hand-coded recomputation of trace 2), `verification/test_rules.py` (10 targeted rule tests) and `verification/test_invariants.py` (3,000 randomised claims). Validation status: **simulated and executed. It is not independently reviewed, and it is not evidence of real-world accuracy.**

## 1. What kind of rule is what

Three sources of rules must never be blurred:

| Source | Examples | Who owns it | How it enters AW |
|---|---|---|---|
| **Documented regulatory obligation** | 1-hour/3-hour cashless clocks; 15-day reimbursement settlement; repudiation only via PMC/CRC; partial disallowance communicated with clause references; insurer/TPA collects documents from hospitals; TPA cannot itself repudiate (E-REG-01, E-REG-03, E-REG-04) | Regulator → customer's compliance team | Hard-coded product behaviour (no configuration can switch it off): e.g. no `REJECT` type, CRC reference required, TAT clocks |
| **Customer contract/wording** | Room-rent limits, proportionate deduction, co-pay, deductible, sub-limits, waiting periods, NME list, exclusions, calculation order, rounding, tariffs and packages | Insurer (product wording, claims manual); TPA (insurer's claims guidelines, E-REG-04 Reg 3) | Versioned configuration artifacts with effective dates and four-eyes publication |
| **Our proposed control** | Gates (identity/date/itemisation), decision-invariance, one-deduction-per-rule-per-line, anomaly heuristics, second-approver thresholds | Us, with customer sign-off | Engine code with versioned rule IDs; thresholds configurable |

Nothing in the illustrative policy is "the Indian standard". In particular, **there is no universal calculation order** (trace 2 shows the order of co-pay versus the sum-insured cap moves the payable by ₹8,500), and the standardised non-medical item lists' current regulatory force is unclear because the 2020 standardisation master circular was superseded (E-REG-02; OQ-20).

## 2. Rule representation

**Two layers.**

1. *Rule definitions* are code in the engine, each with a stable ID (`R-…`), a semantic version, typed inputs, declared `blocked_scopes` it respects, and unit tests. Code is the right home for logic like "remaining-amount semantics" or "decision invariance" that must not vary by customer.
2. *Rule parameters* live in customer configuration artifacts validated by JSON Schema (`schemas/policy-config.schema.json`): percentages, amounts, category lists, lists of codes, calculation order, rounding mode. Example: `config/policy-ILL-INDEMNITY-A.v2026.1.0.json`.

**Rule definition template (every catalog entry below follows it):** ID · version · applicability (workflow, product config, customer, jurisdiction) · authority (document + clause) · effective dates · inputs · conditions · formula · exceptions · precedence · result (adjustment / finding / block) · evidence attached · tests.

**Versioning and effective dates.**
- Every evaluation records `config_versions` (`artifact@version` for policy config, NME list, tariff, and every rule ID@version) and an `input_hash`.
- The applicable policy config is the one whose `effective_from ≤ admission_date ≤ effective_to` *and* which is linked to the policy record; the applicable tariff is the one effective on the admission date for that hospital. If no artifact is effective → `CONFIGURATION_MISSING` blocking finding (not a silent fallback).
- **Stale policy versions are prevented** by: (a) published artifacts are immutable (`config_artifact` is keyed by version; publishing requires an approver distinct from the author — DB check); (b) selection is by admission date, never "latest"; (c) when a new version is published, open claims whose effective version changes are marked `STALE` only if the customer's change-control setting says the new version applies retrospectively (default: it does not — TC-CFG-02).

**Authority on every adjustment.** Each adjustment carries `authority = {artifact@version, doc_id, clause}`:
- for policy rules, including R-LINE-NONPAYABLE and R-LINE-DUPLICATE, from the policy config's `clause_refs` (e.g. R-CLAIM-COPAY → ILL-WORDING-A-2026 "3.4 Co-payment"; R-LINE-NONPAYABLE → "4.1 Non-payable items"), with the artifact recorded as `policy config@version`;
- for R-LINE-TARIFF, from the tariff's `agreement_doc_id` and `agreement_clause`.

If a rule would deduct but its configuration has no clause reference, the engine raises `ConfigurationError` and the evaluation fails. It never deducts without a citable clause (TC-CFG-03). The DB rejects an adjustment without authority (`adjustment_authority_check`), and the decision letter quotes the clause (E-REG-01 ¶17b; E-REG-04).

**Reviewer overrides survive re-evaluation only if the line is unchanged.** An override is keyed by (line, rule) and stores a `line_fingerprint` (hash of description, category, billed amount, quantity, unit rate, ward context, invoice number and service date). On re-evaluation the engine re-applies the override with `origin = REVIEWER_OVERRIDE`, keeps the `engine_amount` it would have deducted, and links the reviewer action (`override_ref`). If the fingerprint no longer matches, the engine applies its own amount and raises `OVERRIDE_NEEDS_RECONFIRMATION` (TC-REV-03; trace 2b).

**Preventing double deductions and incompatible adjustments.**
- Each bill line carries `remaining`. Rules apply in configured order and act only on `remaining`; a fully disallowed line is skipped by every later rule (FI-04, property-tested).
- At most one adjustment per (evaluation, line, rule) — enforced in code (FI-05) and in the DB (`UNIQUE (tenant_id, evaluation_id, bill_line_id, rule_execution_id)`).
- Mutually exclusive rule pairs are declared: package replacement (R-LINE-PACKAGE, P1) consumes component lines so tariff caps and proportionate deduction cannot also hit them; ICU-context lines are exempt from proportionate deduction by configuration.
- Duplicates are removed before any other line rule so a duplicated non-payable is not deducted twice under two reason codes.
- Claim-level rules apply to the running admissible amount, never to billed totals.

## 3. Default calculation order (illustrative configuration)

```
Gates          R-GATE-IDENTITY → R-GATE-DATES → R-GATE-ITEMISATION → R-GATE-LINE-CATEGORY (workbench engine only)
Eligibility    R-ELIG-POLICY-ACTIVE → R-ELIG-WAITING            (findings only; never deductions)
Line rules     R-LINE-DUPLICATE → R-LINE-NONPAYABLE → R-LINE-TARIFF → R-LINE-ROOM-CAP → R-LINE-PROPORTIONATE
Claim rules    R-CLAIM-SUBLIMIT → R-CLAIM-DEDUCTIBLE → R-CLAIM-COPAY → R-CLAIM-SI-CAP → R-CLAIM-ROUNDING
Anomaly        R-ANOM-*                                          (flags only)
```

Rationale for the illustrative order (each step is configurable and must be confirmed against the customer's wording and claims manual — OQ-22): remove what should never have been billed (duplicates, non-payables) before pricing what remains; price against agreed tariffs before applying entitlement ratios, so the proportionate deduction is computed on the amount the insurer would otherwise pay; apply per-claim financial terms last, with the sum-insured cap after co-pay because the Customer Information Sheet defines co-payment as a specified amount or percentage of the admissible claim amount (E-REG-03 Schedule D). Schedule C requires both co-pay and sub-limits to be disclosed, but the order of co-pay and the SI cap is product-specific.

## 4. Recommendation type derivation

| Condition (evaluated in this order) | `recommendation_type` |
|---|---|
| Any finding routed `CRC_REFERRAL_CANDIDATE` (e.g. policy not in force) | `REFER_CRC` |
| Any blocking finding **and** an open medical-officer finding | `QUERY_AND_REFER_MEDICAL` |
| Any blocking finding | `QUERY` |
| Open medical-officer finding, computation complete | `REFER_MEDICAL` (payable shown as "if cleared") |
| Open FWA finding of severity ≥ HIGH (P1) | `INVESTIGATE` |
| Payable = billed | `PAY_FULL` |
| Otherwise | `PAY_PARTIAL` |

`human_decision_required` is always `true`.

## 5. Rule catalog

Implemented in the verification harness (✓) or catalogue-only (○). Versions match `verification/engine.py`.

The Phase 1 workbench engine (`workbench/src/aw/engine/core.py`, `aw-engine-1.0.0`) is a port of the harness with two deliberate changes, marked **WB** below. Apart from those two changes, the port reproduces every trace in §7 (`workbench/tests/test_engine_equivalence.py`).

- R-GATE-IDENTITY 1.1.0 uses scored name matching.
- A new gate, R-GATE-LINE-CATEGORY, has been added.

| Rule | v | ✓/○ | Applicability | Authority | Inputs → result | Exceptions / precedence | Tests |
|---|---|---|---|---|---|---|---|
| R-GATE-IDENTITY | 1.0.0 | ✓ | All workflows | Proposed control (supports correct-claimant obligations) | Identity observations vs member record → blocking `IDENTITY_CONFLICT` (scope ALL_FINANCIAL) + hospital query | Harness uses exact match after normalisation; transliteration-variant scoring (CAP-06) is ○. Evaluated first. Eligibility rules then use only documents whose identity matches | TC-MAT-01, trace 3a |
| R-GATE-DATES | 1.0.0 | ✓ | IPD workflows | Proposed control | Admission-date observations from identity-matched documents → blocking `DATE_CONFLICT` (scopes ROOM_DAYS, WAITING_PERIOD, PRE_POST_WINDOW) + admission-record query | Eligibility rules may proceed only if their outcome is identical for every candidate date (decision invariance) | TC-RCN-01, TC-ELG-04, TC-ELG-07 |
| R-GATE-ITEMISATION | 1.0.0 | ✓ | IPD | Proposed control | Itemised bill present; Σlines = stated total → else blocking (scope LINE_RULES) | Stated discounts/advances reconciled before comparison (P1) | TC-BIL-01, TC-DOC-04 |
| R-GATE-IDENTITY (WB) | 1.1.0 | WB | All workflows | Proposed control | As 1.0.0, but names are scored: transliteration folding plus Jaro-Winkler. Score ≥ 0.95 passes. Score ≥ 0.80 raises a non-blocking `IDENTITY_NEEDS_REVIEW` for the processor. A lower score, or a gender conflict, gives a blocking `IDENTITY_CONFLICT` | Thresholds are illustrative and need tuning on real member data (BL-11) | Workbench `test_engine_equivalence` (transliteration variant passes; similar name goes to review) |
| R-GATE-LINE-CATEGORY (WB) | 1.0.0 | WB | All workflows with bill lines | Proposed control (CAP-07) | Any line the classifier map (`config/classifier-map-*.json`) could not categorise (`UNCLASSIFIED`) gives a blocking `LINE_CATEGORY_UNCONFIRMED` (scope LINE_RULES) until a reviewer confirms the category | Reason: a wrong category moves money through the proportionate, NME and tariff rules. Passes on every pack trace | Workbench `test_workflow` (blocks until reclassified) |
| R-ELIG-POLICY-ACTIVE | 1.0.0 | ✓ | All | Policy schedule | Admission date ∈ policy period → else `POLICY_NOT_IN_FORCE` → `REFER_CRC` | Grace-period cover rules (E-REG-01 ¶9; UNVERIFIED paraphrase) configurable, priority P1 | TC-ELG-01 |
| R-ELIG-WAITING | 1.1.0 | ✓ | All | Policy wording; PED cap 36 months (E-REG-09, secondary — verify) | Continuous-cover months vs initial/specific/PED periods; PED signals from history text → REVIEW findings to medical officer + queries | Never deducts; runs on identity-matched candidate dates only, and only if the outcome is the same for all of them (else blocked); accident exemption for initial period | TC-ELG-02..04, TC-ELG-07 |
| R-ELIG-EXCLUSION | — | ○ | All | Policy wording exclusion list | Diagnosis/procedure text vs configured exclusions → REVIEW finding | Never deducts automatically | TC-ELG-05 |
| R-ELIG-PREPOST-WINDOW | — | ○ | Reimbursement | Policy wording (e.g. 30/60 days) | Service dates of pre/post bills vs admission/discharge → line flag; P1 deduction when unambiguous | Blocked by DATE_CONFLICT | TC-ELG-06 |
| R-DOC-COMPLETENESS | 1.0.0 | ✓ | Per workflow checklist (`config/checklist-IPD-REIMB.v2026.1.0.json`) | Customer checklist; E-REG-01 ¶17c, E-REG-03 | Required items, including conditional ones (pharmacy bill only if pharmacy is billed; investigation report only if diagnostics are billed; implant invoice only if implants are billed) vs documents present → non-blocking `DOCUMENT_INCOMPLETE` finding + query to the configured addressee. Items already enforced by a gate (itemised bill) are skipped | Never blocks or closes the claim on its own | TC-DOC-04, TC-DOC-06, TC-QRY-02 |
| R-LINE-DUPLICATE | 1.0.0 | ✓ | All | Proposed control | Same invoice no. + date + amount + category → full deduction on the later line | Runs before NME so duplicates aren't double-counted | TC-CAL-05, trace 2 L11 |
| R-LINE-NONPAYABLE | 1.0.0 | ✓ | All | Customer NME list (structure per E-REG-07) | Description matches list item → full deduction on remaining, reason `NME_<category>` | If the policy covers List-I optional items (add-on), treatment changes by config | TC-NME-01..02 |
| R-LINE-TARIFF | 1.0.0 | ✓ | Network hospital with effective tariff | Hospital agreement / tariff | remaining − (tariff rate × qty) when positive | Missing item → flag only; package rule (P1) takes precedence | TC-TAR-01..02 |
| R-LINE-PACKAGE | — | ○ | Network, package procedures | Hospital agreement | Replace component lines with package price; consume components | Mutually exclusive with R-LINE-TARIFF and R-LINE-PROPORTIONATE on consumed lines | TC-TAR-03 |
| R-LINE-IMPLANT-INVOICE | — | ○ | Implant billed | Customer manual | Implant line requires invoice/sticker evidence → else block that line + query | — | TC-DOC-05 |
| R-LINE-ROOM-CAP | 1.1.0 | ✓ | Room limit configured | Policy wording (room-rent clause) | remaining − (limit/day × days) for ROOM and ICU_ROOM lines. Also compares billed room days with the stay (`room_day_count: MIDNIGHTS` in the illustrative config); excess days raise a non-blocking `ROOM_DAYS_EXCEED_STAY` finding for review, with no deduction | Blocked by DATE_CONFLICT (days); limit base excludes cumulative bonus (config) | TC-CAL-01, TC-CAL-09 |
| R-LINE-PROPORTIONATE | 1.1.0 | ✓ | Room above eligibility; enabled | Policy wording (proportionate-deduction clause; Schedule C disclosure, E-REG-03) | Associated categories (configured) in non-ICU context: remaining × (1 − eligible/actual). Actual rate = day-weighted average of ward room rates (`actual_rate_basis: DAY_WEIGHTED`; `HIGHEST` is the alternative), so the result does not depend on line order in a multi-room stay | Exempt categories (pharmacy, consumables, implants, diagnostics in the illustrative config); skipped when the hospital's tariff does not vary by room; interpretation flagged | TC-CAL-02, TC-CAL-08, FI-04, FI-10 |
| R-CLAIM-SUBLIMIT | 1.0.0 | ✓ | Procedure codes with sub-limits | Policy wording | max(0, running − sub-limit) | Applies once per configured sub-limit | TC-CAL-06 |
| R-CLAIM-DEDUCTIBLE | 1.0.0 | ✓ | Deductible configured | Policy wording | min(deductible, running) | — | TC-CAL-07 |
| R-CLAIM-COPAY | 1.0.0 | ✓ | Co-pay conditions met | Policy wording (illustrative clause 3.4); co-payment is defined in the Customer Information Sheet as a share of the admissible claim amount (E-REG-03 Schedule D) | running × % (quantised to paise) | Base is configurable | TC-CAL-03 |
| R-CLAIM-SI-CAP | 1.0.0 | ✓ | All | Policy schedule | running − available SI, where available = base SI + CB − paid this policy year (from the SI ledger) | Concurrent claims reserve against the ledger (05 §1.4) | TC-CAL-03 |
| R-CLAIM-ROUNDING | 1.0.0 | ✓ | All | Customer convention | running → rounded per config; difference recorded as signed adjustment `ROUNDING` | Only adjustment allowed to be negative (DB check) | TC-CAL-04 |
| R-ANOM-BILLNO-REUSE | 0.9.0 | ✓ | All | Proposed RFI (E-REG-06 concept) | Same bill no. + hospital, different member → MEDIUM flag to FWA review | Innocent explanations listed in text; never "fraud" | TC-ANO-01 |
| R-ANOM-DUP-CLAIM | — | ○ | All | Proposed RFI | Same member + overlapping dates + similar amounts across claims → flag | — | TC-ANO-03 |
| R-ANOM-LOS-OUTLIER | — | ○ | IPD | Customer norms table | LOS outside configured range for procedure → MO question | Needs clinical-advisor sign-off on norms | TC-CLN-03 |
| R-TAT-CLOCK | — | ○ (impl. in CAP-23) | Per workflow | E-REG-01 ¶15–16; E-REG-03 | Clock start/stop, due time, breach alerts | Query-pause behaviour configurable (OQ-21) | TC-TAT-01 |
| R-CLIN-SUMMARY | — | ○ | IPD | Proposed | Cited clinical summary for MO | No verdicts; 07 §5 | TC-CLN-01..02 |

## 6. Money handling

- **Representation:** integer paise in storage (`BIGINT`, DB checks for non-negativity except `ROUNDING`); `Decimal` in computation; decimal strings with two places in APIs. No floats anywhere (schema regex rejects them — mutation test in `validate_contracts.py` run).
- **Rounding:** every line-level result is quantised to paise with ROUND_HALF_UP at the step that produces it; percentages are applied to the paise-exact base; the final payable is rounded per configuration (illustrative: nearest rupee, half-up) and the difference is recorded as a `ROUNDING` adjustment so reconciliation stays exact.
- **Reconciliation invariants** (all executed in `test_invariants.py` over 3,000 random claims, plus DB reconciliation in `validate_db.sh`):
  - FI-01 billed = payable + Σ adjustments (to the paisa)
  - FI-02 Σ deductions on a line ≤ billed on that line
  - FI-03 0 ≤ payable ≤ available SI (+ rounding tolerance)
  - FI-04 no deduction after a line is fully disallowed
  - FI-05 at most one adjustment per (line, rule)
  - FI-06 every adjustment carries rule ID, version and clause authority
  - FI-07 any blocking scope ⇒ no payable computed
  - FI-08 recommendation type never a final rejection; human decision always required
  - FI-09 deterministic output hash
  - FI-10 payable invariant to bill-line order
  - FI-11 inflating a non-payable line never changes the payable

Targeted rule tests in `verification/test_rules.py` (all pass): TC-ELG-04, TC-ELG-07, TC-CAL-08, TC-CAL-09, TC-REV-03, TC-EVD-01, TC-CFG-03, TC-CFG-04, TC-DOC-06, TC-MAT-01. Descriptions are in 10 §3.

## 7. Worked traces

Common setup: `config/policy-ILL-INDEMNITY-A.v2026.1.0.json` (ILLUSTRATIVE) — room limit 1% of base SI/day, ICU 2%/day, proportionate deduction on professional fees, nursing, OT, procedure and other hospital services in ward context (pharmacy, consumables, implants, diagnostics exempt), co-pay 10% at age ≥ 61, no deductible, PED 36 months, specific waiting 24 months for cholecystectomy, final rounding to nearest rupee half-up. NME list `config/nme-list-ILL-A.v2026.1.0.json`; network tariff `config/tariff-ILL-HOSP-NW-01.v2026.07.json` (CT abdomen capped at ₹4,000; surgeon fee for laparoscopic cholecystectomy capped at ₹35,000). Inputs are reviewer-confirmed facts at the moment of the rule run (`fixtures/claims/*.input.json`); outputs and hash-chained audit events are alongside.

### Trace 1 — straightforward review (CLM-DEMO-0001)
34-year-old, acute appendicitis, laparoscopic appendicectomy, non-network hospital, twin-sharing room at ₹3,500/day (limit ₹5,000), 2 days. Four non-payable lines (registration, toiletries, mineral water, gown) totalling ₹1,770. No co-pay, no tariff, SI ₹5,00,000 available. Payable ₹1,07,590.50 → rounded ₹1,07,591.00 (rounding adjustment −₹0.50 recorded). Processor approves after checking the four deductions against bill page 2.

### Trace 2 — multiple interacting adjustments (CLM-DEMO-0002)
63-year-old, calculous cholecystitis, laparoscopic cholecystectomy, network hospital, single AC room ₹6,000/day for 3 days + 1 ICU day at ₹9,000; base SI ₹3,00,000 (room limit ₹3,000/day, ICU ₹6,000/day), cumulative bonus ₹30,000, ₹2,45,000 already paid this policy year (available SI ₹85,000). Interactions demonstrated:
- a photocopied pharmacy invoice duplicated (L11, ₹3,420) — removed first;
- non-payables including a *bed pan billed under nursing* (L19) — fully disallowed by R-LINE-NONPAYABLE, so the proportionate rule correctly skips it (no double deduction);
- surgeon fee above tariff (₹45,000 → ₹35,000) *then* proportionate deduction on the tariff-capped remainder (₹35,000 × ½ → ₹17,500 deducted);
- room and ICU caps; ICU-context nursing and intensivist lines exempt from proportionate deduction; CT capped to tariff but exempt from proportion (diagnostics);
- co-pay 10% on admissible ₹1,00,885.75 = ₹10,088.58 (₹10,088.575 rounded half-up at paise);
- sum-insured cap binds: ₹90,797.17 → ₹85,000.00.
Independent recomputation (hand-coded, no engine): payable ₹85,000.00 — match. **Order sensitivity:** if the SI cap were applied before co-pay the payable would be ₹76,500.00 — a ₹8,500 difference, which is why order is a wording question (OQ-22). A second approval is required under the illustrative workflow config (`config/workflow-TENANT-DEMO.v2026.1.0.json`) because total deductions (₹87,455.75) are over 30% of billed. Processor PROC-11 (limit ₹1,00,000) records the decision and supervisor SUP-02 approves it (DEC-0002).

### Trace 2b — reviewer override, what-if branch (CLM-DEMO-0002)
Same inputs as trace 2, plus one reviewer action. RA-0207 overrides the tariff deduction on L14 (CT abdomen, ₹5,500 against a ₹4,000 tariff item) to ₹0.00, because the scan was done as an emergency at an outside imaging centre and the hospital's tariff item does not apply. The engine keeps its own figure (`engine_amount` ₹1,500.00) beside the override. Line deductions fall to ₹70,070.00 and admissible rises to ₹1,02,385.75. Co-pay rises with it, but the sum-insured cap still binds, so the payable stays ₹85,000.00. The trace is a what-if branch from trace 2's RECOMMENDATION_CREATED audit event; it is not loaded into the demo database. TC-REV-03 shows the override is dropped, with a reconfirmation finding, if the line changes.

### Trace 3a — insufficient and conflicting evidence (CLM-DEMO-0003, first run)
52-year-old, type 2 diabetes with foot ulcer, debridement. The bill names "Mr. Sunil Sharma" (claim form and discharge summary: Sunita Sharma, F); the discharge summary says admission 03/09/2026 while the bill says 02/09/2026; only a category-wise summary bill is available; history states "known case of type 2 diabetes mellitus for 6 years"; policy cover is 27 months old under a 36-month PED waiting period; the same bill number appears on another member's claim from the same hospital. Result: no payable computed (identity, dates and itemisation all block). The PED question goes to the medical officer. Eligibility uses identity-matched documents only, so the bill's date (02/09, on a document naming another person) is not a candidate; the waiting-period rule ran on the discharge-summary date 2026-09-03 alone (27 months of cover). How the rule behaves when identity-matched documents disagree on the date is tested separately: TC-ELG-04 (same outcome on every candidate date, so it runs) and TC-ELG-07 (different outcomes, so it is blocked). Anomaly flagged for FWA review with innocent explanations; five query items drafted (four to the hospital, one to the insurer for the proposal form). Recommendation `QUERY_AND_REFER_MEDICAL`.

### Trace 3b — after new evidence (CLM-DEMO-0003, second run)
The hospital sends a corrected itemised bill and the admission record (admitted 23:40 on 02/09 via emergency). The previous evaluation is marked `STALE`; the processor records conflict resolutions; a new evaluation `EVAL-0003-v2` supersedes v1 and continues the same audit hash chain. Line rules now run: two non-payables (₹280) deducted; payable ₹85,570.00 (₹85,570.25 rounded). Recommendation `REFER_MEDICAL`: the amount is shown as payable *if* the medical officer clears the PED question; a PED conclusion against the claimant would require the insurer's CRC for repudiation (E-REG-01 ¶17a).

### Generated trace tables

_Generated by `verification/render_traces.py` from `fixtures/claims/*.output.json`. Money in ₹; amounts in the Deduction column are positive when they reduce the payable._

#### Output: trace-1-straightforward

Recommendation **PAY_PARTIAL** · computed: True · recommended payable: 107,591.00 · billed (lines): 109,360.50 · stated bill total: 109,360.50

| Line | Description | Category | Context | Billed (₹) | Payable (₹) |
|---|---|---|---|---:|---:|
| L01 | Room charges - twin sharing | ROOM | WARD | 7,000.00 | 7,000.00 |
| L02 | Nursing charges | NURSING | WARD | 2,400.00 | 2,400.00 |
| L03 | Surgeon fee - laparoscopic appendicectomy | PROFESSIONAL_FEES | WARD | 30,000.00 | 30,000.00 |
| L04 | Anaesthetist fee | PROFESSIONAL_FEES | WARD | 9,000.00 | 9,000.00 |
| L05 | Operation theatre charges | OT_CHARGES | WARD | 22,000.00 | 22,000.00 |
| L06 | Pharmacy - drugs and IV fluids | PHARMACY | WARD | 18,640.50 | 18,640.50 |
| L07 | Surgical consumables | CONSUMABLES | WARD | 9,850.00 | 9,850.00 |
| L08 | Investigations - CBC, LFT, USG abdomen | DIAGNOSTICS | WARD | 6,300.00 | 6,300.00 |
| L09 | Consultant visits | PROFESSIONAL_FEES | WARD | 2,400.00 | 2,400.00 |
| L10 | Admission / registration charges | OTHER_HOSPITAL_SERVICES | WARD | 1,000.00 | 0.00 |
| L11 | Toothpaste and toothbrush | OTHER_HOSPITAL_SERVICES | WARD | 180.00 | 0.00 |
| L12 | Mineral water | OTHER_HOSPITAL_SERVICES | WARD | 240.00 | 0.00 |
| L13 | Patient gown | OTHER_HOSPITAL_SERVICES | WARD | 350.00 | 0.00 |

| # | Rule (version) | Level / line | Reason | Origin | Base before (₹) | Deduction (₹) | Remaining (₹) | Authority (clause) | Formula |
|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | R-LINE-NONPAYABLE (1.0.0) | LINE L10 | NME_SUBSUMED_TREATMENT | ENGINE | 1,000.00 | 1,000.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 2 | R-LINE-NONPAYABLE (1.0.0) | LINE L11 | NME_SUBSUMED_ROOM | ENGINE | 180.00 | 180.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 3 | R-LINE-NONPAYABLE (1.0.0) | LINE L12 | NME_NON_PAYABLE | ENGINE | 240.00 | 240.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 4 | R-LINE-NONPAYABLE (1.0.0) | LINE L13 | NME_SUBSUMED_ROOM | ENGINE | 350.00 | 350.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 5 | R-CLAIM-ROUNDING (1.0.0) | CLAIM  | ROUNDING | ENGINE | 107,590.50 | -0.50 | 107,591.00 | 2.4 Rounding of settlement amounts | `107590.50 -> 107591 (RUPEE_HALF_UP)` |

Rule execution order:

| Step | Rule | Status | Key detail |
|---|---|---|---|
| 1 | R-GATE-IDENTITY | PASSED | `{"sources_checked": 3, "method": "exact normalised match (harness)"}` |
| 2 | R-GATE-DATES | PASSED | `{"admission_date": "2026-08-10"}` |
| 3 | R-GATE-ITEMISATION | PASSED | `{"stated_total": "109360.50", "sum_of_lines": "109360.50"}` |
| 4 | R-DOC-COMPLETENESS | PASSED | `{"required": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "PHARMACY_BILL", "INVESTIGATION_REPORT", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS"],…` |
| 5 | R-ELIG-POLICY-ACTIVE | PASSED | `{"evaluated_dates": ["2026-08-10"], "invariant_under_date_conflict": false, "period": ["2026-06-01", "2027-05-31"]}` |
| 6 | R-ELIG-WAITING | PASSED | `{"continuous_cover_months": 26, "evaluated_dates": ["2026-08-10"], "invariant_under_date_conflict": false}` |
| 7 | R-LINE-DUPLICATE | NOT_APPLICABLE | `{"duplicate_lines": []}` |
| 8 | R-LINE-NONPAYABLE | APPLIED | `{"matches": [{"line_id": "L10", "item_code": "NME-301"}, {"line_id": "L11", "item_code": "NME-101"}, {"line_id": "L12", "item_code": "NME…` |
| 9 | R-LINE-TARIFF | NOT_APPLICABLE | `{"reason": "no applicable network tariff"}` |
| 10 | R-LINE-ROOM-CAP | NOT_APPLICABLE | `{"eligible_normal_per_day": "5000.00", "eligible_icu_per_day": "10000.00", "actual_normal_per_day": "3500.00", "actual_rate_basis": "DAY_…` |
| 11 | R-LINE-PROPORTIONATE | NOT_APPLICABLE | `{"reason": "actual room rate within eligibility", "eligible": "5000.00", "actual": "3500.00"}` |
| 12 | R-CLAIM-SUBLIMIT | NOT_APPLICABLE | `{"sub_limits": []}` |
| 13 | R-CLAIM-DEDUCTIBLE | NOT_APPLICABLE | `{"deductible": "0.00"}` |
| 14 | R-CLAIM-COPAY | NOT_APPLICABLE | `{"age_at_admission": 34}` |
| 15 | R-CLAIM-SI-CAP | NOT_APPLICABLE | `{"available_si": "500000.00"}` |
| 16 | R-CLAIM-ROUNDING | APPLIED | `{"before": "107590.50", "after": "107591.00"}` |
| 17 | R-ANOM-BILLNO-REUSE | NOT_APPLICABLE | `{"other_claims": []}` |

Audit events (hash-chained; full list in the `.audit.json` fixture):

| Seq | Time (IST) | Actor | Event | Payload (abridged) |
|---|---|---|---|---|
| 25 | 10:06:50.000 | SYSTEM | RULE_RUN_STARTED | `{"evaluation_id": "EVAL-0001-v1", "config_versions": "POLCFG-ILL-INDEMNITY-A@2026.1.0", "input_hash": "sha256:cbc0365…` |
| 43 | 10:06:50.244 | SYSTEM | RECOMMENDATION_CREATED | `{"evaluation_id": "EVAL-0001-v1", "type": "PAY_PARTIAL", "recommended_payable": "107591.00", "output_hash": "sha256:f…` |
| 44 | 10:07:35.244 | USER:PROC-07 | REVIEWER_VIEWED_RECOMMENDATION | `{}` |
| 45 | 10:08:20.244 | USER:PROC-07 | DECISION_RECORDED | `{"decision": "APPROVED_PARTIAL", "approved_payable": "107591.00", "second_approval": "not required (payable ≤ PROC-07…` |
| 46 | 10:09:05.244 | SYSTEM | SETTLEMENT_WORKSHEET_EXPORTED | `{"format": "JSON+PDF", "target": "TMS_STUB"}` |

(46 events in total, including 8 DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)

#### Output: trace-2-interacting-adjustments

Recommendation **PAY_PARTIAL** · computed: True · recommended payable: 85,000.00 · billed (lines): 172,455.75 · stated bill total: 172,455.75

| Line | Description | Category | Context | Billed (₹) | Payable (₹) |
|---|---|---|---|---:|---:|
| L01 | Room charges - single AC | ROOM | WARD | 18,000.00 | 9,000.00 |
| L02 | ICU charges | ICU_ROOM | ICU | 9,000.00 | 6,000.00 |
| L03 | Nursing charges - ward | NURSING | WARD | 4,500.00 | 2,250.00 |
| L04 | Nursing charges - ICU | NURSING | ICU | 3,000.00 | 3,000.00 |
| L05 | Surgeon fee - laparoscopic cholecystectomy | PROFESSIONAL_FEES | WARD | 45,000.00 | 17,500.00 |
| L06 | Anaesthetist fee | PROFESSIONAL_FEES | WARD | 12,000.00 | 6,000.00 |
| L07 | Operation theatre charges | OT_CHARGES | WARD | 28,000.00 | 14,000.00 |
| L08 | Consultant visits - ward | PROFESSIONAL_FEES | WARD | 4,000.00 | 2,000.00 |
| L09 | Intensivist visit - ICU | PROFESSIONAL_FEES | ICU | 2,500.00 | 2,500.00 |
| L10 | Pharmacy invoice PH-2291 | PHARMACY | WARD | 3,420.00 | 3,420.00 |
| L11 | Pharmacy invoice PH-2291 | PHARMACY | WARD | 3,420.00 | 0.00 |
| L12 | Pharmacy invoice PH-2307 | PHARMACY | WARD | 11,865.75 | 11,865.75 |
| L13 | Laparoscopic consumables | CONSUMABLES | WARD | 14,500.00 | 14,500.00 |
| L14 | CT scan abdomen (contrast) | DIAGNOSTICS | WARD | 5,500.00 | 4,000.00 |
| L15 | Laboratory investigations | DIAGNOSTICS | WARD | 4,850.00 | 4,850.00 |
| L16 | Television charges | OTHER_HOSPITAL_SERVICES | WARD | 600.00 | 0.00 |
| L17 | Telephone charges | OTHER_HOSPITAL_SERVICES | WARD | 350.00 | 0.00 |
| L18 | Infusion pump charges | OTHER_HOSPITAL_SERVICES | WARD | 1,800.00 | 0.00 |
| L19 | Nursing - bed pan | NURSING | WARD | 150.00 | 0.00 |

| # | Rule (version) | Level / line | Reason | Origin | Base before (₹) | Deduction (₹) | Remaining (₹) | Authority (clause) | Formula |
|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | R-LINE-DUPLICATE (1.0.0) | LINE L11 | DUPLICATE_LINE | ENGINE | 3,420.00 | 3,420.00 | 0.00 | 7.2 Expenses actually incurred | `remaining (full)` |
| 2 | R-LINE-NONPAYABLE (1.0.0) | LINE L16 | NME_NON_PAYABLE | ENGINE | 600.00 | 600.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 3 | R-LINE-NONPAYABLE (1.0.0) | LINE L17 | NME_NON_PAYABLE | ENGINE | 350.00 | 350.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 4 | R-LINE-NONPAYABLE (1.0.0) | LINE L18 | NME_SUBSUMED_TREATMENT | ENGINE | 1,800.00 | 1,800.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 5 | R-LINE-NONPAYABLE (1.0.0) | LINE L19 | NME_SUBSUMED_ROOM | ENGINE | 150.00 | 150.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 6 | R-LINE-TARIFF (1.0.0) | LINE L05 | TARIFF_EXCESS | ENGINE | 45,000.00 | 10,000.00 | 35,000.00 | Schedule 2 Item rates | `remaining 45000.00 - tariff 35000.00 x qty 1` |
| 7 | R-LINE-TARIFF (1.0.0) | LINE L14 | TARIFF_EXCESS | ENGINE | 5,500.00 | 1,500.00 | 4,000.00 | Schedule 2 Item rates | `remaining 5500.00 - tariff 4000.00 x qty 1` |
| 8 | R-LINE-ROOM-CAP (1.1.0) | LINE L01 | ROOM_RENT_EXCESS | ENGINE | 18,000.00 | 9,000.00 | 9,000.00 | 3.1 Room rent | `remaining 18000.00 - limit 3000.00/day x 3 days` |
| 9 | R-LINE-ROOM-CAP (1.1.0) | LINE L02 | ICU_RENT_EXCESS | ENGINE | 9,000.00 | 3,000.00 | 6,000.00 | 3.1 Room rent | `remaining 9000.00 - limit 6000.00/day x 1 days` |
| 10 | R-LINE-PROPORTIONATE (1.1.0) | LINE L03 | PROPORTIONATE_DEDUCTION | ENGINE | 4,500.00 | 2,250.00 | 2,250.00 | 3.2 Proportionate deduction | `remaining 4500.00 x (1 - 3000.00/6000.00)` |
| 11 | R-LINE-PROPORTIONATE (1.1.0) | LINE L05 | PROPORTIONATE_DEDUCTION | ENGINE | 35,000.00 | 17,500.00 | 17,500.00 | 3.2 Proportionate deduction | `remaining 35000.00 x (1 - 3000.00/6000.00)` |
| 12 | R-LINE-PROPORTIONATE (1.1.0) | LINE L06 | PROPORTIONATE_DEDUCTION | ENGINE | 12,000.00 | 6,000.00 | 6,000.00 | 3.2 Proportionate deduction | `remaining 12000.00 x (1 - 3000.00/6000.00)` |
| 13 | R-LINE-PROPORTIONATE (1.1.0) | LINE L07 | PROPORTIONATE_DEDUCTION | ENGINE | 28,000.00 | 14,000.00 | 14,000.00 | 3.2 Proportionate deduction | `remaining 28000.00 x (1 - 3000.00/6000.00)` |
| 14 | R-LINE-PROPORTIONATE (1.1.0) | LINE L08 | PROPORTIONATE_DEDUCTION | ENGINE | 4,000.00 | 2,000.00 | 2,000.00 | 3.2 Proportionate deduction | `remaining 4000.00 x (1 - 3000.00/6000.00)` |
| 15 | R-CLAIM-COPAY (1.0.0) | CLAIM  | CO_PAYMENT | ENGINE | 100,885.75 | 10,088.58 | 90,797.17 | 3.4 Co-payment | `100885.75 x 10.0%` |
| 16 | R-CLAIM-SI-CAP (1.0.0) | CLAIM  | SUM_INSURED_EXHAUSTED | ENGINE | 90,797.17 | 5,797.17 | 85,000.00 | 6.1 Sum insured | `90797.17 - available SI 85000.00` |

Rule execution order:

| Step | Rule | Status | Key detail |
|---|---|---|---|
| 1 | R-GATE-IDENTITY | PASSED | `{"sources_checked": 3, "method": "exact normalised match (harness)"}` |
| 2 | R-GATE-DATES | PASSED | `{"admission_date": "2026-07-01"}` |
| 3 | R-GATE-ITEMISATION | PASSED | `{"stated_total": "172455.75", "sum_of_lines": "172455.75"}` |
| 4 | R-DOC-COMPLETENESS | PASSED | `{"required": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "PHARMACY_BILL", "INVESTIGATION_REPORT", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS"],…` |
| 5 | R-ELIG-POLICY-ACTIVE | PASSED | `{"evaluated_dates": ["2026-07-01"], "invariant_under_date_conflict": false, "period": ["2026-04-10", "2027-04-09"]}` |
| 6 | R-ELIG-WAITING | PASSED | `{"continuous_cover_months": 62, "evaluated_dates": ["2026-07-01"], "invariant_under_date_conflict": false, "WP-SPEC-GALLBLADDER": {"requi…` |
| 7 | R-LINE-DUPLICATE | APPLIED | `{"duplicate_lines": ["L11"]}` |
| 8 | R-LINE-NONPAYABLE | APPLIED | `{"matches": [{"line_id": "L16", "item_code": "NME-002"}, {"line_id": "L17", "item_code": "NME-003"}, {"line_id": "L18", "item_code": "NME…` |
| 9 | R-LINE-TARIFF | APPLIED | `{"capped_lines": ["L05", "L14"]}` |
| 10 | R-LINE-ROOM-CAP | APPLIED | `{"eligible_normal_per_day": "3000.00", "eligible_icu_per_day": "6000.00", "actual_normal_per_day": "6000.00", "actual_rate_basis": "DAY_W…` |
| 11 | R-LINE-PROPORTIONATE | APPLIED | `{"ratio": "3000.00/6000.00", "lines": ["L03", "L05", "L06", "L07", "L08"]}` |
| 12 | R-CLAIM-SUBLIMIT | NOT_APPLICABLE | `{"sub_limits": []}` |
| 13 | R-CLAIM-DEDUCTIBLE | NOT_APPLICABLE | `{"deductible": "0.00"}` |
| 14 | R-CLAIM-COPAY | APPLIED | `{"age_at_admission": 63, "percent": "10.0", "base": "100885.75"}` |
| 15 | R-CLAIM-SI-CAP | APPLIED | `{"available_si": "85000.00"}` |
| 16 | R-CLAIM-ROUNDING | NOT_APPLICABLE | `{"before": "85000.00", "after": "85000.00"}` |
| 17 | R-ANOM-BILLNO-REUSE | NOT_APPLICABLE | `{"other_claims": []}` |

Audit events (hash-chained; full list in the `.audit.json` fixture):

| Seq | Time (IST) | Actor | Event | Payload (abridged) |
|---|---|---|---|---|
| 31 | 11:26:02.000 | SYSTEM | RULE_RUN_STARTED | `{"evaluation_id": "EVAL-0002-v1", "config_versions": "POLCFG-ILL-INDEMNITY-A@2026.1.0", "input_hash": "sha256:f651c90…` |
| 49 | 11:26:02.244 | SYSTEM | RECOMMENDATION_CREATED | `{"evaluation_id": "EVAL-0002-v1", "type": "PAY_PARTIAL", "recommended_payable": "85000.00", "output_hash": "sha256:40…` |
| 50 | 11:26:47.244 | USER:PROC-11 | REVIEWER_VIEWED_RECOMMENDATION | `{}` |
| 51 | 11:27:32.244 | USER:PROC-11 | REVIEWER_CONFIRMED_FINDING | `{"adjustment_rule": "R-LINE-DUPLICATE", "line_id": "L11", "comment": "DOC-0002-PH1-COPY is a photocopy of PH-2291."}` |
| 52 | 11:28:17.244 | USER:PROC-11 | APPROVAL_REQUESTED | `{"proposed_disposition": "APPROVED_PARTIAL", "approved_payable": "85000.00", "reason": "Second approval required by W…` |
| 53 | 11:29:02.244 | USER:SUP-02 | APPROVAL_GRANTED | `{}` |
| 54 | 11:29:47.244 | SYSTEM | DECISION_RECORDED | `{"decision": "APPROVED_PARTIAL", "approved_payable": "85000.00", "decided_by": "PROC-11", "second_approver": "SUP-02"}` |
| 55 | 11:30:32.244 | SYSTEM | SETTLEMENT_WORKSHEET_EXPORTED | `{"format": "JSON+PDF", "target": "TMS_STUB"}` |

(55 events in total, including 10 DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)

#### Output: trace-2b-reviewer-override

_What-if branch of trace 2 (not loaded into the DB): right after the first recommendation, PROC-11 overrides the CT tariff deduction instead of approving. The audit chain forks from trace 2's RECOMMENDATION_CREATED event._

Recommendation **PAY_PARTIAL** · computed: True · recommended payable: 85,000.00 · billed (lines): 172,455.75 · stated bill total: 172,455.75

| Line | Description | Category | Context | Billed (₹) | Payable (₹) |
|---|---|---|---|---:|---:|
| L01 | Room charges - single AC | ROOM | WARD | 18,000.00 | 9,000.00 |
| L02 | ICU charges | ICU_ROOM | ICU | 9,000.00 | 6,000.00 |
| L03 | Nursing charges - ward | NURSING | WARD | 4,500.00 | 2,250.00 |
| L04 | Nursing charges - ICU | NURSING | ICU | 3,000.00 | 3,000.00 |
| L05 | Surgeon fee - laparoscopic cholecystectomy | PROFESSIONAL_FEES | WARD | 45,000.00 | 17,500.00 |
| L06 | Anaesthetist fee | PROFESSIONAL_FEES | WARD | 12,000.00 | 6,000.00 |
| L07 | Operation theatre charges | OT_CHARGES | WARD | 28,000.00 | 14,000.00 |
| L08 | Consultant visits - ward | PROFESSIONAL_FEES | WARD | 4,000.00 | 2,000.00 |
| L09 | Intensivist visit - ICU | PROFESSIONAL_FEES | ICU | 2,500.00 | 2,500.00 |
| L10 | Pharmacy invoice PH-2291 | PHARMACY | WARD | 3,420.00 | 3,420.00 |
| L11 | Pharmacy invoice PH-2291 | PHARMACY | WARD | 3,420.00 | 0.00 |
| L12 | Pharmacy invoice PH-2307 | PHARMACY | WARD | 11,865.75 | 11,865.75 |
| L13 | Laparoscopic consumables | CONSUMABLES | WARD | 14,500.00 | 14,500.00 |
| L14 | CT scan abdomen (contrast) | DIAGNOSTICS | WARD | 5,500.00 | 5,500.00 |
| L15 | Laboratory investigations | DIAGNOSTICS | WARD | 4,850.00 | 4,850.00 |
| L16 | Television charges | OTHER_HOSPITAL_SERVICES | WARD | 600.00 | 0.00 |
| L17 | Telephone charges | OTHER_HOSPITAL_SERVICES | WARD | 350.00 | 0.00 |
| L18 | Infusion pump charges | OTHER_HOSPITAL_SERVICES | WARD | 1,800.00 | 0.00 |
| L19 | Nursing - bed pan | NURSING | WARD | 150.00 | 0.00 |

| # | Rule (version) | Level / line | Reason | Origin | Base before (₹) | Deduction (₹) | Remaining (₹) | Authority (clause) | Formula |
|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | R-LINE-DUPLICATE (1.0.0) | LINE L11 | DUPLICATE_LINE | ENGINE | 3,420.00 | 3,420.00 | 0.00 | 7.2 Expenses actually incurred | `remaining (full)` |
| 2 | R-LINE-NONPAYABLE (1.0.0) | LINE L16 | NME_NON_PAYABLE | ENGINE | 600.00 | 600.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 3 | R-LINE-NONPAYABLE (1.0.0) | LINE L17 | NME_NON_PAYABLE | ENGINE | 350.00 | 350.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 4 | R-LINE-NONPAYABLE (1.0.0) | LINE L18 | NME_SUBSUMED_TREATMENT | ENGINE | 1,800.00 | 1,800.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 5 | R-LINE-NONPAYABLE (1.0.0) | LINE L19 | NME_SUBSUMED_ROOM | ENGINE | 150.00 | 150.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 6 | R-LINE-TARIFF (1.0.0) | LINE L05 | TARIFF_EXCESS | ENGINE | 45,000.00 | 10,000.00 | 35,000.00 | Schedule 2 Item rates | `remaining 45000.00 - tariff 35000.00 x qty 1` |
| 7 | R-LINE-TARIFF (1.0.0) | LINE L14 | TARIFF_EXCESS | REVIEWER_OVERRIDE | 5,500.00 | 0.00 | 5,500.00 | Schedule 2 Item rates | `reviewer override RA-0207 (TARIFF_ITEM_NOT_APPLICABLE); engine computed 1500.00` |
| 8 | R-LINE-ROOM-CAP (1.1.0) | LINE L01 | ROOM_RENT_EXCESS | ENGINE | 18,000.00 | 9,000.00 | 9,000.00 | 3.1 Room rent | `remaining 18000.00 - limit 3000.00/day x 3 days` |
| 9 | R-LINE-ROOM-CAP (1.1.0) | LINE L02 | ICU_RENT_EXCESS | ENGINE | 9,000.00 | 3,000.00 | 6,000.00 | 3.1 Room rent | `remaining 9000.00 - limit 6000.00/day x 1 days` |
| 10 | R-LINE-PROPORTIONATE (1.1.0) | LINE L03 | PROPORTIONATE_DEDUCTION | ENGINE | 4,500.00 | 2,250.00 | 2,250.00 | 3.2 Proportionate deduction | `remaining 4500.00 x (1 - 3000.00/6000.00)` |
| 11 | R-LINE-PROPORTIONATE (1.1.0) | LINE L05 | PROPORTIONATE_DEDUCTION | ENGINE | 35,000.00 | 17,500.00 | 17,500.00 | 3.2 Proportionate deduction | `remaining 35000.00 x (1 - 3000.00/6000.00)` |
| 12 | R-LINE-PROPORTIONATE (1.1.0) | LINE L06 | PROPORTIONATE_DEDUCTION | ENGINE | 12,000.00 | 6,000.00 | 6,000.00 | 3.2 Proportionate deduction | `remaining 12000.00 x (1 - 3000.00/6000.00)` |
| 13 | R-LINE-PROPORTIONATE (1.1.0) | LINE L07 | PROPORTIONATE_DEDUCTION | ENGINE | 28,000.00 | 14,000.00 | 14,000.00 | 3.2 Proportionate deduction | `remaining 28000.00 x (1 - 3000.00/6000.00)` |
| 14 | R-LINE-PROPORTIONATE (1.1.0) | LINE L08 | PROPORTIONATE_DEDUCTION | ENGINE | 4,000.00 | 2,000.00 | 2,000.00 | 3.2 Proportionate deduction | `remaining 4000.00 x (1 - 3000.00/6000.00)` |
| 15 | R-CLAIM-COPAY (1.0.0) | CLAIM  | CO_PAYMENT | ENGINE | 102,385.75 | 10,238.58 | 92,147.17 | 3.4 Co-payment | `102385.75 x 10.0%` |
| 16 | R-CLAIM-SI-CAP (1.0.0) | CLAIM  | SUM_INSURED_EXHAUSTED | ENGINE | 92,147.17 | 7,147.17 | 85,000.00 | 6.1 Sum insured | `92147.17 - available SI 85000.00` |

Rule execution order:

| Step | Rule | Status | Key detail |
|---|---|---|---|
| 1 | R-GATE-IDENTITY | PASSED | `{"sources_checked": 3, "method": "exact normalised match (harness)"}` |
| 2 | R-GATE-DATES | PASSED | `{"admission_date": "2026-07-01"}` |
| 3 | R-GATE-ITEMISATION | PASSED | `{"stated_total": "172455.75", "sum_of_lines": "172455.75"}` |
| 4 | R-DOC-COMPLETENESS | PASSED | `{"required": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "PHARMACY_BILL", "INVESTIGATION_REPORT", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS"],…` |
| 5 | R-ELIG-POLICY-ACTIVE | PASSED | `{"evaluated_dates": ["2026-07-01"], "invariant_under_date_conflict": false, "period": ["2026-04-10", "2027-04-09"]}` |
| 6 | R-ELIG-WAITING | PASSED | `{"continuous_cover_months": 62, "evaluated_dates": ["2026-07-01"], "invariant_under_date_conflict": false, "WP-SPEC-GALLBLADDER": {"requi…` |
| 7 | R-LINE-DUPLICATE | APPLIED | `{"duplicate_lines": ["L11"]}` |
| 8 | R-LINE-NONPAYABLE | APPLIED | `{"matches": [{"line_id": "L16", "item_code": "NME-002"}, {"line_id": "L17", "item_code": "NME-003"}, {"line_id": "L18", "item_code": "NME…` |
| 9 | R-LINE-TARIFF | APPLIED | `{"capped_lines": ["L05", "L14"]}` |
| 10 | R-LINE-ROOM-CAP | APPLIED | `{"eligible_normal_per_day": "3000.00", "eligible_icu_per_day": "6000.00", "actual_normal_per_day": "6000.00", "actual_rate_basis": "DAY_W…` |
| 11 | R-LINE-PROPORTIONATE | APPLIED | `{"ratio": "3000.00/6000.00", "lines": ["L03", "L05", "L06", "L07", "L08"]}` |
| 12 | R-CLAIM-SUBLIMIT | NOT_APPLICABLE | `{"sub_limits": []}` |
| 13 | R-CLAIM-DEDUCTIBLE | NOT_APPLICABLE | `{"deductible": "0.00"}` |
| 14 | R-CLAIM-COPAY | APPLIED | `{"age_at_admission": 63, "percent": "10.0", "base": "102385.75"}` |
| 15 | R-CLAIM-SI-CAP | APPLIED | `{"available_si": "85000.00"}` |
| 16 | R-CLAIM-ROUNDING | NOT_APPLICABLE | `{"before": "85000.00", "after": "85000.00"}` |
| 17 | R-ANOM-BILLNO-REUSE | NOT_APPLICABLE | `{"other_claims": []}` |

Audit events (hash-chained; full list in the `.audit.json` fixture):

| Seq | Time (IST) | Actor | Event | Payload (abridged) |
|---|---|---|---|---|
| 50 | 11:31:45.000 | USER:PROC-11 | REVIEWER_ACTION_RECORDED | `{"action": "OVERRIDE_ADJUSTMENT", "override_id": "RA-0207", "line_id": "L14", "rule_id": "R-LINE-TARIFF", "after_amou…` |
| 51 | 11:32:30.000 | SYSTEM | RECOMMENDATION_MARKED_STALE | `{"evaluation_id": "EVAL-0002-v1", "reason": "REVIEWER_CORRECTION"}` |
| 52 | 11:32:32.000 | SYSTEM | RULE_RUN_STARTED | `{"evaluation_id": "EVAL-0002-v2", "config_versions": "POLCFG-ILL-INDEMNITY-A@2026.1.0", "input_hash": "sha256:d015461…` |
| 70 | 11:32:32.244 | SYSTEM | RECOMMENDATION_CREATED | `{"evaluation_id": "EVAL-0002-v2", "type": "PAY_PARTIAL", "recommended_payable": "85000.00", "output_hash": "sha256:5e…` |

(21 events in total, including 0 DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)

#### Output: trace-3a-insufficient-conflicting

Recommendation **QUERY_AND_REFER_MEDICAL** · computed: False · recommended payable: — · billed (lines): 0.00 · stated bill total: 85,850.25

Rule execution order:

| Step | Rule | Status | Key detail |
|---|---|---|---|
| 1 | R-GATE-IDENTITY | BLOCKED | `{"mismatch_count": 1, "method": "exact normalised match (harness)"}` |
| 2 | R-GATE-DATES | BLOCKED | `{"distinct_admission_dates": ["2026-09-02", "2026-09-03"]}` |
| 3 | R-GATE-ITEMISATION | BLOCKED | `{"itemised": false}` |
| 4 | R-DOC-COMPLETENESS | PASSED | `{"required": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS"], "missing": []}` |
| 5 | R-ELIG-POLICY-ACTIVE | PASSED | `{"evaluated_dates": ["2026-09-03"], "invariant_under_date_conflict": false, "period": ["2026-05-15", "2027-05-14"]}` |
| 6 | R-ELIG-WAITING | REVIEW | `{"continuous_cover_months": 27, "evaluated_dates": ["2026-09-03"], "invariant_under_date_conflict": false, "ped_signal": "known case of t…` |
| 7 | R-LINE-DUPLICATE | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 8 | R-LINE-NONPAYABLE | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 9 | R-LINE-TARIFF | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 10 | R-LINE-ROOM-CAP | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 11 | R-LINE-PROPORTIONATE | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 12 | R-CLAIM-SUBLIMIT | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 13 | R-CLAIM-DEDUCTIBLE | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 14 | R-CLAIM-COPAY | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 15 | R-CLAIM-SI-CAP | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 16 | R-CLAIM-ROUNDING | SKIPPED_BLOCKED | `{"reason": "blocked scopes ['ALL_FINANCIAL', 'LINE_RULES', 'PRE_POST_WINDOW', 'ROOM_DAYS', 'WAITING_PERIOD']"}` |
| 17 | R-ANOM-BILLNO-REUSE | FLAGGED | `{"other_claims": ["CLM-DEMO-0088"]}` |

| Finding | Category | Kind | Severity | Blocking | Routed to | Summary |
|---|---|---|---|---|---|---|
| FND-0001 | IDENTITY | IDENTITY_CONFLICT | HIGH | True | PROCESSOR | Patient identity on one or more documents does not match the policy member record. |
| FND-0004 | DOCUMENT | DATE_CONFLICT | HIGH | True | PROCESSOR | Date of admission differs across documents: ['2026-09-02', '2026-09-03']. |
| FND-0007 | DOCUMENT | DOCUMENT_INCOMPLETE | HIGH | True | PROCESSOR | Only a summary bill is available; line-level rules cannot run without an itemised break-up. |
| FND-0012 | CLINICAL | POSSIBLE_PED_WITHIN_WAITING_PERIOD | HIGH | False | MEDICAL_OFFICER | Clinical history mentions 'known case of type 2 diabetes mellitus for 6 years, on oral hypoglycaemic agents'. Continuous cover is 27 months, below the 36-month PED waiting period. Whether the condition is a PED as defined, and whether it is related to this admission, needs medical-officer review. No deduction or denial is applied by the engine. |
| FND-0026 | ANOMALY | ANOMALY_BILL_NUMBER_REUSE | MEDIUM | False | FWA_REVIEW | Bill number SH/26/0915 from the same hospital also appears on claim(s) ['CLM-DEMO-0088'] for a different member. This is a pattern for review, not a fraud determination. |

| Query item | To | Document requested | Text |
|---|---|---|---|
| QRY-0002 | HOSPITAL | FINAL_BILL_CORRECTED | Please provide a corrected final bill showing the patient's name and gender exactly as on the admission record, or confirm the identity of the patient billed. |
| QRY-0005 | HOSPITAL | ADMISSION_RECORD | Please confirm the date and time of admission with a copy of the admission record / indoor case papers. |
| QRY-0008 | HOSPITAL | FINAL_BILL_ITEMISED | Please provide the itemised final bill with date-wise break-up of room, pharmacy, consumables, investigations and professional fees. |
| QRY-0013 | HOSPITAL | PAST_TREATMENT_RECORDS | Please provide the first consultation / past treatment records for the condition noted in the history, if available with the hospital. |
| QRY-0014 | INSURER | PROPOSAL_FORM | Please share the proposal form and underwriting disclosures for the policy, for PED assessment. |

Audit events (hash-chained; full list in the `.audit.json` fixture):

| Seq | Time (IST) | Actor | Event | Payload (abridged) |
|---|---|---|---|---|
| 22 | 09:49:14.000 | SYSTEM | RULE_RUN_STARTED | `{"evaluation_id": "EVAL-0003-v1", "config_versions": "POLCFG-ILL-INDEMNITY-A@2026.1.0", "input_hash": "sha256:bcc9091…` |
| 40 | 09:49:14.244 | SYSTEM | RECOMMENDATION_CREATED | `{"evaluation_id": "EVAL-0003-v1", "type": "QUERY_AND_REFER_MEDICAL", "recommended_payable": null, "output_hash": "sha…` |
| 41 | 09:49:59.244 | USER:PROC-04 | REVIEWER_VIEWED_RECOMMENDATION | `{}` |
| 42 | 09:50:44.244 | USER:PROC-04 | QUERY_APPROVED | `{"query_items": 5, "channel": "TMS_STUB", "addressees": ["HOSPITAL", "INSURER"]}` |
| 43 | 09:51:29.244 | USER:MO-01 | MEDICAL_REVIEW_OPENED | `{"finding_kind": "POSSIBLE_PED_WITHIN_WAITING_PERIOD"}` |
| 44 | 09:52:14.244 | USER:FWA-01 | ANOMALY_TRIAGED | `{"finding_kind": "ANOMALY_BILL_NUMBER_REUSE", "disposition": "ACCEPTED_FOR_REVIEW"}` |

(44 events in total, including 7 DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)

#### Output: trace-3b-after-new-evidence

Recommendation **REFER_MEDICAL** · computed: True · recommended payable: 85,570.00 · billed (lines): 85,850.25 · stated bill total: 85,850.25

| Line | Description | Category | Context | Billed (₹) | Payable (₹) |
|---|---|---|---|---:|---:|
| L01 | Room charges - twin sharing | ROOM | WARD | 14,000.00 | 14,000.00 |
| L02 | Nursing charges | NURSING | WARD | 4,500.00 | 4,500.00 |
| L03 | Surgeon fee - debridement | PROFESSIONAL_FEES | WARD | 18,000.00 | 18,000.00 |
| L04 | Operation theatre charges | OT_CHARGES | WARD | 9,500.00 | 9,500.00 |
| L05 | Pharmacy - drugs, insulin, antibiotics | PHARMACY | WARD | 21,340.25 | 21,340.25 |
| L06 | Dressing materials | CONSUMABLES | WARD | 6,780.00 | 6,780.00 |
| L07 | Investigations - HbA1c, culture, X-ray foot | DIAGNOSTICS | WARD | 7,950.00 | 7,950.00 |
| L08 | Physician visits | PROFESSIONAL_FEES | WARD | 3,500.00 | 3,500.00 |
| L09 | Urine bag | OTHER_HOSPITAL_SERVICES | WARD | 120.00 | 0.00 |
| L10 | Hand wash | OTHER_HOSPITAL_SERVICES | WARD | 160.00 | 0.00 |

| # | Rule (version) | Level / line | Reason | Origin | Base before (₹) | Deduction (₹) | Remaining (₹) | Authority (clause) | Formula |
|---|---|---|---|---|---:|---:|---:|---|---|
| 1 | R-LINE-NONPAYABLE (1.0.0) | LINE L09 | NME_SUBSUMED_TREATMENT | ENGINE | 120.00 | 120.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 2 | R-LINE-NONPAYABLE (1.0.0) | LINE L10 | NME_SUBSUMED_ROOM | ENGINE | 160.00 | 160.00 | 0.00 | 4.1 Non-payable items | `remaining (full)` |
| 3 | R-CLAIM-ROUNDING (1.0.0) | CLAIM  | ROUNDING | ENGINE | 85,570.25 | 0.25 | 85,570.00 | 2.4 Rounding of settlement amounts | `85570.25 -> 85570 (RUPEE_HALF_UP)` |

Rule execution order:

| Step | Rule | Status | Key detail |
|---|---|---|---|
| 1 | R-GATE-IDENTITY | PASSED | `{"sources_checked": 3, "method": "exact normalised match (harness)"}` |
| 2 | R-GATE-DATES | PASSED | `{"admission_date": "2026-09-02"}` |
| 3 | R-GATE-ITEMISATION | PASSED | `{"stated_total": "85850.25", "sum_of_lines": "85850.25"}` |
| 4 | R-DOC-COMPLETENESS | PASSED | `{"required": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "INVESTIGATION_REPORT", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS"], "missing": []}` |
| 5 | R-ELIG-POLICY-ACTIVE | PASSED | `{"evaluated_dates": ["2026-09-02"], "invariant_under_date_conflict": false, "period": ["2026-05-15", "2027-05-14"]}` |
| 6 | R-ELIG-WAITING | REVIEW | `{"continuous_cover_months": 27, "evaluated_dates": ["2026-09-02"], "invariant_under_date_conflict": false, "ped_signal": "known case of t…` |
| 7 | R-LINE-DUPLICATE | NOT_APPLICABLE | `{"duplicate_lines": []}` |
| 8 | R-LINE-NONPAYABLE | APPLIED | `{"matches": [{"line_id": "L09", "item_code": "NME-303"}, {"line_id": "L10", "item_code": "NME-104"}]}` |
| 9 | R-LINE-TARIFF | NOT_APPLICABLE | `{"reason": "no applicable network tariff"}` |
| 10 | R-LINE-ROOM-CAP | NOT_APPLICABLE | `{"eligible_normal_per_day": "4000.00", "eligible_icu_per_day": "8000.00", "actual_normal_per_day": "2800.00", "actual_rate_basis": "DAY_W…` |
| 11 | R-LINE-PROPORTIONATE | NOT_APPLICABLE | `{"reason": "actual room rate within eligibility", "eligible": "4000.00", "actual": "2800.00"}` |
| 12 | R-CLAIM-SUBLIMIT | NOT_APPLICABLE | `{"sub_limits": []}` |
| 13 | R-CLAIM-DEDUCTIBLE | NOT_APPLICABLE | `{"deductible": "0.00"}` |
| 14 | R-CLAIM-COPAY | NOT_APPLICABLE | `{"age_at_admission": 52}` |
| 15 | R-CLAIM-SI-CAP | NOT_APPLICABLE | `{"available_si": "400000.00"}` |
| 16 | R-CLAIM-ROUNDING | APPLIED | `{"before": "85570.25", "after": "85570.00"}` |
| 17 | R-ANOM-BILLNO-REUSE | FLAGGED | `{"other_claims": ["CLM-DEMO-0088"]}` |

| Finding | Category | Kind | Severity | Blocking | Routed to | Summary |
|---|---|---|---|---|---|---|
| FND-0006 | CLINICAL | POSSIBLE_PED_WITHIN_WAITING_PERIOD | HIGH | False | MEDICAL_OFFICER | Clinical history mentions 'known case of type 2 diabetes mellitus for 6 years, on oral hypoglycaemic agents'. Continuous cover is 27 months, below the 36-month PED waiting period. Whether the condition is a PED as defined, and whether it is related to this admission, needs medical-officer review. No deduction or denial is applied by the engine. |
| FND-0023 | ANOMALY | ANOMALY_BILL_NUMBER_REUSE | MEDIUM | False | FWA_REVIEW | Bill number SH/26/0915 from the same hospital also appears on claim(s) ['CLM-DEMO-0088'] for a different member. This is a pattern for review, not a fraud determination. |

| Query item | To | Document requested | Text |
|---|---|---|---|
| QRY-0007 | HOSPITAL | PAST_TREATMENT_RECORDS | Please provide the first consultation / past treatment records for the condition noted in the history, if available with the hospital. |
| QRY-0008 | INSURER | PROPOSAL_FORM | Please share the proposal form and underwriting disclosures for the policy, for PED assessment. |

Audit events (hash-chained; full list in the `.audit.json` fixture):

| Seq | Time (IST) | Actor | Event | Payload (abridged) |
|---|---|---|---|---|
| 47 | 15:10:55.000 | SYSTEM | RECOMMENDATION_MARKED_STALE | `{"evaluation_id": "EVAL-0003-v1", "reason": "NEW_EVIDENCE"}` |
| 52 | 15:12:42.000 | USER:PROC-04 | REVIEWER_ACTION_RECORDED | `{"action": "RESOLVE_CONFLICT", "finding_kind": "DATE_CONFLICT", "resolution": "2026-09-02", "evidence": "DOC-0003-AR …` |
| 53 | 15:13:27.000 | USER:PROC-04 | REVIEWER_ACTION_RECORDED | `{"action": "RESOLVE_CONFLICT", "finding_kind": "IDENTITY_CONFLICT", "resolution": "Corrected bill DOC-0003-FB2 supers…` |
| 54 | 15:13:29.000 | SYSTEM | RULE_RUN_STARTED | `{"evaluation_id": "EVAL-0003-v2", "config_versions": "POLCFG-ILL-INDEMNITY-A@2026.1.0", "input_hash": "sha256:d7e286f…` |
| 72 | 15:13:29.244 | SYSTEM | RECOMMENDATION_CREATED | `{"evaluation_id": "EVAL-0003-v2", "type": "REFER_MEDICAL", "recommended_payable": "85570.00", "output_hash": "sha256:…` |
| 73 | 15:14:14.244 | USER:MO-01 | MEDICAL_REVIEW_PENDING | `{"finding_kind": "POSSIBLE_PED_WITHIN_WAITING_PERIOD", "awaiting": ["PAST_TREATMENT_RECORDS", "PROPOSAL_FORM"]}` |

(29 events in total, including 2 DOCUMENT_RECEIVED and the per-document classification/extraction and per-rule RULE_EXECUTED events not listed here.)

## 8. Regulatory obligations and how they shape rules

| Obligation | Source | Type | Product implication | Qualified review needed? |
|---|---|---|---|---|
| Cashless decision ≤ 1 h; discharge final authorisation ≤ 3 h; insurer bears hospital charges for delay | E-REG-01 ¶15–16 | Documented obligation (on insurers) | Latency SLOs for P1 workflows; clock display; degraded-mode manual path | No (clear text); SLA allocation in contracts: yes |
| Repudiation only with PMC/CRC approval; CRC decides independently | E-REG-01 ¶17a, Ch.II A(I)(4)(b) | Documented obligation | No `REJECT` recommendation; `REFER_CRC`; decision requires CRC reference | No |
| TPA may admit/authorise/recommend; cannot itself repudiate; repudiation decided and communicated only by the insurer; must state granular disallowances and reasons | E-REG-04 | Documented obligation (on TPAs) | Deduction explanations per line with reasons. For a TPA tenant the workflow config fixes repudiation to `RECORD_INSURER_OUTCOME_ONLY`: AW records the insurer's decision and CRC reference and generates no repudiation letter (schema-enforced in `workflow-config.schema.json`; DB requires `communicated_by = INSURER`) | No |
| Where a TPA disallows any part of a claim, the communication must include the grievance procedure, grievance officer and ombudsman details | E-REG-04 (settlement communication) | Documented obligation (on TPAs) | Worksheet and letter template carry a grievance block whenever any adjustment is non-zero | No |
| Partial disallowance communicated with specific policy clause references | E-REG-01 ¶17b; E-REG-03 | Documented obligation | Every adjustment carries `authority {artifact@version, doc_id, clause}` from `clause_refs` or the tariff agreement; evaluation fails without it (FI-06, TC-CFG-03, DB check) | No |
| Insurers/TPAs collect documents from hospitals; no rejection/closure for want of documents | E-REG-01 ¶17c; E-REG-03 | Documented obligation | Queries default to hospital; no auto-closure | How this applies to reimbursement at non-network hospitals: yes (OQ-23) |
| Reimbursement settled within 15 days of submission; interest bank rate + 2% suo-moto from the date of intimation | E-REG-03 | Documented obligation | Clock starts at first submission (`submitted_at`); interest exposure accrues from intimation (`intimated_at`); workflow config `tat` block | Whether queries pause the clock: yes (OQ-21) |
| Proportionate deductions, sub-limits, package rates, co-pay disclosed in policy (Schedule C); co-payment defined in the Customer Information Sheet as a share of the admissible claim amount (Schedule D) | E-REG-03 | Documented obligation | These rules are only applied when the customer's config cites the clause | No |
| PED waiting period ≤ 36 months; moratorium 60 months | E-REG-09 (secondary), E-REG-01 ¶13 | Documented obligation (secondary source for PED cap) | Config schema caps PED months at 36; moratorium check before any non-disclosure finding (P1) | Verify primary regulation text: yes |
| Standardised NME lists (List I–IV) | E-REG-07; superseded consolidation E-REG-02 | Status unclear | Lists are customer-supplied per wording | Yes (OQ-20) |
| Red flag indicators for fraud monitoring | E-REG-06 | Documented framework (insurers/distribution channels) | Anomaly flags framed as RFIs for review | Applicability to TPAs: yes |
| TPA must not outsource servicing of policies | E-REG-04 code of conduct (v) | Documented obligation | AW is software operated by the TPA's staff; no vendor-side adjudication service in the base offer | Yes — classification of SaaS vs outsourcing (OQ-24) |
| Express consent for sharing medical records | E-REG-01 Ch.III II(3) | Documented obligation (insurer) | Consent status captured from the customer; no secondary use | Yes |

## 9. Clinical and anomaly boundaries

- Clinical outputs are questions with citations, routed to a medical officer; they carry an uncertainty note (DB-enforced) and cannot produce deductions. The engine never states medical necessity, never infers a diagnosis absent from documents, and never writes denial wording.
- Anomaly outputs are patterns with severity, evidence and listed innocent explanations, routed to FWA review; they never block payment by themselves (only humans can hold a claim for investigation) and never use the words fraud/fraudulent/fake.
- Both have false-positive budgets and escalation-quality metrics in `10-validation-plan.md` (M-CLN-*, M-ANO-*).
