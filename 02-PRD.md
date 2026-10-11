# 02 — Product requirements (PRD)

Everything in this file is **PROPOSED** unless a line cites competitor evidence (E…) or regulation (E-REG…). Working name: **Adjudication Workbench (AW)**. This is a descriptive placeholder, not a brand (see 03 §9 for the design direction).

## 1. Problem and product

Health-claim processors and medical officers at insurers and TPAs reconstruct each claim by hand from 15–80 pages of mixed documents. That means scanned bills, discharge summaries, pharmacy invoices and investigation reports. They then apply policy terms, tariffs and non-payable lists line by line and write deduction reasons that must survive grievance and ombudsman review.

The work is slow and inconsistent between reviewers. It is also time-boxed by regulation:

- cashless authorisation within 1 hour;
- final discharge authorisation within 3 hours;
- reimbursement settlement within 15 days of submission, with interest if late (E-REG-01, E-REG-03).

AW is a **review assistant**. It turns the document bundle into structured, evidence-linked facts. It runs the customer's own configured rules deterministically to produce a recommended payable amount with line-level deductions and reasons. It flags clinical and anomaly questions for the right human, and drafts queries. **A human always makes the final decision.** A full repudiation can only be recorded with the insurer's Claims Review Committee (CRC) reference (E-REG-01 ¶17(a); E-REG-04).

## 2. Buyer, users, authority, geography, system of record

| Item | Provisional answer | Basis / status |
|---|---|---|
| Buyer | Head of claims or COO at a TPA (first), or the health claims head at a general/standalone health insurer | INFERRED from competitor positioning (E001) and market structure. Validate in discovery (OQ-10) |
| Daily users | Claims processors (non-medical scrutiny); medical officers, i.e. MBBS/BAMS/BHMS doctors (medical scrutiny); supervisors (approval, allocation); auditors (post-payment sampling); FWA analysts | Industry convention; competitor hires pharma/nursing graduates as "claims processors" (E-LI-07) |
| Final decision authority | Payment or partial disallowance: TPA or insurer user within their delegated approval limit. Full repudiation: insurer, with CRC approval. A TPA cannot repudiate on its own | E-REG-01, E-REG-04 (regulation). Product enforcement is PROPOSED |
| Geography | India; INR; Indian date formats; English documents first; Hindi and regional-language documents detected and routed | Provisional (per your brief) |
| System of record | The customer's TMS/claims system remains the system of record for claim status and payment. AW is the system of record for evidence, rule runs, recommendations and reviewer actions | PROPOSED. Avoids replacing core systems in a pilot |
| Hospital insurance desk (provider side) | **Out of scope.** Different buyer and incentives (maximise approval, revenue-cycle management), different documents and workflow | Deliberate. The competitor's earlier posts touched hospital revenue-cycle management (E-LI-10) |

## 3. Non-negotiable product principles

1. **Human authority.** The engine outputs a *recommendation*. It never records a disposition. "Reject" does not exist as a recommendation type. The strongest negative output is `REFER_CRC` (FI-08).
2. **Deterministic money.** Every rupee is computed by versioned, testable rules over decimal arithmetic. Models never compute amounts.
3. **Evidence or nothing.** Every extracted fact, finding and deduction links to a document page, a region of it, and a quote. Every deduction links to a rule version and the policy or tariff clause that authorises it.
4. **Abstain when uncertain.** Identity, date or itemisation conflicts block the computations they affect (they do not get guessed). The output then becomes a query or review task (trace 3a).
5. **Customer-authored rules.** Policy terms, tariffs and non-payable lists come from the customer's wording, claims manual and hospital agreements. They are versioned with effective dates and approved by two people. General model knowledge is never a source of policy or tariff truth.
6. **Clinical humility.** Clinical and anomaly outputs are questions for qualified humans, with evidence and stated uncertainty. They are not conclusions. An anomaly flag is never presented as fraud.
7. **Regulatory clocks are first-class.** Every claim shows its applicable time clock and remaining time.

## 4. Workflows: separate analysis

| Workflow | Trigger and inputs | Clock | What the reviewer decides | Data quality | Priority (delivery phase, 11 §2) |
|---|---|---|---|---|---|
| **Pre-authorisation (cashless initial)** | Hospital request: pre-auth form, doctor's notes, provisional diagnosis, estimate, investigations | ≤1 hour from receipt (E-REG-01 ¶15b) | Approve an initial amount / query / deny. A TPA may authorise; denial routes to the insurer | Thin. Estimates, not bills | P2 (after the pilot). Needs real-time TMS integration and clinical criteria content |
| **Enhancement** | Revised estimate during the stay | Insurer practice (not in reviewed excerpts) | Approve additional amount / query | Thin | P2 (after the pilot) |
| **Cashless discharge (final authorisation)** | Final bill, discharge summary, prior authorisations | ≤3 hours from the discharge request. Delay cost falls on the insurer (E-REG-01 ¶16) | Final approved amount and deductions vs authorised amount | Good (itemised bill) but time-critical | **P1 (Phase 3).** Same bill engine as reimbursement plus TMS integration and a latency SLO |
| **IPD reimbursement** | Claim form, discharge summary, itemised bill, pharmacy and investigation bills, payment receipts, KYC/bank details | Settle within 15 days of submission; interest at bank rate + 2% from intimation if late (E-REG-03) | Payable, deductions, queries | Mixed scans, often incomplete | **P0 (Phases 1–2), first slice** |
| **OPD (reimbursement/cashless)** | Prescription, consultation and pharmacy bills, diagnostics | Product-specific | Wallet/benefit limits, eligibility, FWA | Very high volume, low value, many photos | P2 (after the pilot). Separate rule pack. ekincare already has one (E017) |

**Why reimbursement first** (council decision; see 11 §5): it exercises the full bill-review engine without the 1-hour or 3-hour integration risk. Complete closed files exist for evaluation. The financial rules (the hardest to get right) are identical to cashless discharge. The trade-off: insurers are expected to aim for fully cashless settlement and keep reimbursement to a minimum (E-REG-01 ¶15a; UNVERIFIED: paraphrase, verbatim re-capture pending), so reimbursement alone is a weak long-term wedge. Cashless discharge must follow as priority P1, in Phase 3, to match the competitor's main claim (E010).

## 5. Capability requirements

Priorities: **P0** = first slice (delivered in Phases 1–2), **P1** = next release (Phase 3), **P2** = after the pilot. Phases are defined in 11 §2.

Format per capability: user/purpose · trigger & prerequisites · inputs & permissions · processing & branches · output & financial effect · states · human review · dependencies · acceptance (test IDs in `10-validation-plan.md`) · evidence status · priority.

### CAP-01 Claim intake and registration (FR-INT)
- **User/purpose:** TMS integration or processor registers a claim so documents and rules attach to one record.
- **Trigger & prerequisites:** `POST /claims` from the TMS adapter, a portal upload, or an NHCX adapter (P2). The policy, member and product configuration must exist or be importable.
- **Inputs & permissions:** external reference, workflow, policy number, member ID, hospital, admission and discharge dates, claimed amount. Requires the `claims.write` scope or the PROCESSOR role.
- **Processing:**
  1. Validate the schema.
  2. Make the call idempotent on `Idempotency-Key`. A duplicate `external_ref` in the same tenant returns 409.
  3. Resolve the policy configuration version effective on the admission date. If the admission date is unknown, record the candidates and resolve after extraction.
  4. Start the TAT clock per workflow (CAP-23).
- **Output:** claim in `INTAKE`. No financial effect.
- **States:** loading (create in flight) · empty (no documents → `DOCS_INCOMPLETE` after the intake grace window) · conflicting (dates disagree with extracted facts → finding) · failed (unknown policy → 422 with problem detail) · success (201 + ETag).
- **Human review:** a processor can correct header fields through reviewer actions (audited).
- **Dependencies:** policy/member import (CAP-21), TMS adapter.
- **Acceptance:** TC-INT-01, TC-INT-02.
- **Evidence status:** the competitor names API, TMS and portal routes (E001). Our contract is PROPOSED.
- **Priority:** P0 (portal + API), P1 (TMS adapter), P2 (NHCX).

### CAP-02 Document ingestion and preservation (FR-DOC-A)
- **User/purpose:** keep every original byte, immutable and hashed, so every later fact can be traced to it.
- **Trigger:** upload slot request → PUT to storage → `:complete`.
- **Inputs & permissions:** PDF/JPEG/PNG/TIFF ≤ 50 MB, SHA-256 hash, declared type. PROCESSOR or integration scope.
- **Processing:**
  1. Verify the hash.
  2. Store in a write-once bucket under a tenant key.
  3. Exact duplicates (same hash on the same claim) return the existing record.
  4. Malware scan; file-type sniffing. A mismatch → `QUARANTINED`.
  5. Split into pages and record whether each page has a native text layer.
  6. Enqueue classification, OCR and extraction jobs.
- **Output:** `document` and `document_page` rows; audit event `DOCUMENT_RECEIVED`.
- **States:** `RECEIVED → STORED → CLASSIFYING → CLASSIFIED → EXTRACTING → EXTRACTED`. Side states: `NEEDS_REVIEW`, `FAILED_UNREADABLE`, `FAILED_TECHNICAL`, `QUARANTINED`, `SUPERSEDED` (03 §2).
- **Human review:** a processor can reclassify, mark a page unreadable, or mark one document as superseding another.
- **Acceptance:** TC-DOC-01, TC-DOC-03, TC-SEC-05.
- **Evidence status:** PROPOSED. The competitor does not describe storage.
- **Priority:** P0.

### CAP-03 Document classification and completeness (FR-DOC-B)
- **User/purpose:** tell the processor at once what is missing for this workflow and product.
- **Trigger:** each document reaches `CLASSIFIED`; the claim's document set changes.
- **Processing:**
  1. Page-level type classification, then grouping into logical documents.
  2. Compare against the workflow's checklist, a versioned config artifact (`config/checklist-IPD-REIMB.v2026.1.0.json`, ILLUSTRATIVE; schema `schemas/checklist.schema.json`). The illustrative IPD reimbursement list has nine items: claim form, discharge summary, itemised final bill, payment receipt, ID proof, bank details, and three conditional items (pharmacy invoices when pharmacy is billed, investigation reports when diagnostics are billed, implant invoice/sticker when an implant is billed). The itemised bill is enforced by R-GATE-ITEMISATION, so the checklist rule skips it.
  3. Each missing item produces a non-blocking `DOCUMENT_INCOMPLETE` finding and a draft query item to the item's configured addressee. Hospital documents go to the **hospital**, because regulation says insurers/TPAs collect documents from hospitals and the policyholder is not required to submit them (E-REG-01 ¶17c). Only items the claimant alone holds (claim form, ID proof, bank details) go to the claimant.
  4. Never close or reject a claim for missing documents (E-REG-03).
- **Output:** checklist with status per item. No financial effect except blocking line rules when the itemised bill is missing (R-GATE-ITEMISATION).
- **States:** empty checklist (unknown workflow config → configuration error banner) · incomplete · complete.
- **Acceptance:** TC-DOC-04, TC-DOC-06 (executed), TC-QRY-02.
- **Evidence status:** comparable products do completeness checks (E-CMP-03). The regulatory basis is OBSERVED; our implementation is PROPOSED.
- **Priority:** P0.

### CAP-04 Extraction (FR-EXT)
- **User/purpose:** turn pages into typed, grounded facts and bill lines.
- **Processing:**
  1. Use the native text layer when present; otherwise OCR (07 §2).
  2. Extract layout-aware tables for bills, including tables that continue across pages.
  3. Structured extraction with the strict schema `schemas/extraction-output.schema.json`. Every field and line carries a verbatim quote and the page number.
  4. **Grounding check:** each quote must be found, after normalisation, in the page's text layer. Otherwise the fact is stored as `NOT_FOUND` and cannot be used by rules.
  5. Normalise dates, Indian number formats ("1,72,455.75"), names, and units.
- **Output:** `extracted_fact` and candidate `bill_line` rows with confidence values.
- **States:** partial (some pages failed) · low-confidence (`NEEDS_REVIEW`) · failed (provider outage → retry with backoff; claim stays `PROCESSING` and the processor sees the reason) · success.
- **Human review:** a side-by-side correction view (03 S-03). Each correction creates a `resolved_fact` with basis `REVIEWER_ENTERED` and triggers re-evaluation.
- **Acceptance:** TC-EXT-01..04, TC-SEC-03.
- **Evidence status:** the competitor claims "100+ structured attributes" (E001). Ours is PROPOSED. Field list in 07 §3.
- **Priority:** P0.

### CAP-05 Fact reconciliation and conflict detection (FR-RCN)
- **User/purpose:** pick one value per fact, or surface a conflict instead of choosing silently.
- **Processing:**
  - For each field (admission date, discharge date, patient name, gender, age, bill total, room category), compare all grounded observations.
  - Agreement → `AUTO_AGREEMENT`. One source → `AUTO_SINGLE_SOURCE`, permitted only for fields configured as low-risk.
  - Disagreement → a `DATE_CONFLICT`, `IDENTITY_CONFLICT` or `BILL_TOTAL_MISMATCH` finding that blocks the dependent scopes.
  - **Decision invariance:** an eligibility rule may still run under a date conflict if its outcome is the same for every candidate value. Candidates come only from documents whose identity matches the member, so a bill naming someone else cannot supply a date (TC-ELG-04 runs; TC-ELG-07 blocks; trace 3a).
- **Output:** resolved facts; blocking findings with `blocked_scopes`.
- **Human review:** the processor selects a value with evidence (`RESOLVE_CONFLICT`). A comment is mandatory when the chosen value contradicts a majority of sources.
- **Acceptance:** TC-RCN-01, TC-ELG-04, TC-ELG-07, trace 3a → 3b.
- **Priority:** P0.

### CAP-06 Patient/member matching (FR-MAT)
- **Processing:** compare name (transliteration-aware normalisation and token similarity), gender, age/date of birth, policy number, and any member ID on documents against the policy member record.
  - Score ≥ high threshold with no hard mismatch → pass.
  - Gender mismatch, or name similarity below the low threshold → `IDENTITY_CONFLICT`, blocking scope `ALL_FINANCIAL` (no line or claim rule runs and no payable is computed). Eligibility rules still run, on identity-matched documents only.
  - In between → review task (not blocking).
  - Thresholds are calibrated in the pilot (07 §6).
  - The reference harness implements only exact matching after normalisation. Similarity scoring is P0 build work (BL-11), not yet built.
- **Acceptance:** TC-MAT-01 (executed), TC-MAT-02.
- **Priority:** P0.

### CAP-07 Bill line categorisation (FR-BIL)
- **Processing:**
  1. Dictionary match first (the customer's NME list and synonyms; the tariff item `match_keys`).
  2. Then a model suggestion with confidence.
  3. Then a ward context of ICU or ward, from dates and labels.
  - Lines below the confidence threshold are routed to the processor before line rules run on them. Only those lines are blocked.
  - Check that the sum of lines equals the stated bill total, net of stated discounts and advances. A mismatch → `BILL_TOTAL_MISMATCH` blocks line rules.
- **Output:** `bill_line` rows with `category`, `category_source`, `ward_context`.
- **Acceptance:** TC-BIL-01, TC-BIL-02.
- **Evidence status:** "categorizes bill line items" (E001, COMPANY-REPORTED).
- **Priority:** P0.

### CAP-08 Policy eligibility (FR-ELG)
- **Processing:** policy in force on the admission date; initial waiting period; specific waiting periods by procedure/condition; pre-existing disease (PED) waiting period signals from history text; permanent exclusions (P1); pre- and post-hospitalisation windows (P1).
  - Waiting-period and exclusion results are `REVIEW` findings routed to the medical officer. **The engine never deducts or denies on these grounds.**
  - Policy not in force → `REFER_CRC` candidate.
- **Output:** findings and rule executions. Financial effect only through human action.
- **Acceptance:** TC-ELG-01..04, TC-ELG-07.
- **Evidence status:** PED cap of 36 months and moratorium of 60 months (E-REG-09, secondary; E-REG-01 for moratorium). Our automation boundary is PROPOSED.
- **Priority:** P0 (in-force, waiting-period signals), P1 (exclusion catalogue, pre/post windows).

### CAP-09 Tariff and package checks (FR-TAR)
- **Processing:**
  - Network hospital with an applicable tariff version on the admission date → cap matched items at the agreed rate × quantity.
  - Package procedures (P1) → replace component lines with the package amount and apply the package's inclusion list.
  - An item with no tariff entry → flag; no deduction (`on_missing_tariff_item`).
  - A stale tariff version (not effective on the admission date) cannot be selected; the publication workflow enforces effective dates.
- **Acceptance:** TC-TAR-01, TC-TAR-02, TC-CFG-01.
- **Evidence status:** the competitor claims "Hospital tariff validation", "SOC checks" (E001). Ours is PROPOSED.
- **Priority:** P0 (item caps), P1 (packages).

### CAP-10 Non-medical expense identification (FR-NME)
- **Processing:** match lines against the customer's versioned NME list (categories modelled on the four-list structure; E-REG-07). Treatment comes from the policy configuration. A line already fully disallowed is not touched again.
- **Acceptance:** TC-NME-01, TC-NME-02.
- **Evidence status:** "NME identification" (E001). Whether the lists still have regulatory force is UNKNOWN (E-REG-02; OQ-20).
- **Priority:** P0.

### CAP-11 Deduction calculations (FR-CAL)
- **Processing:** the configured sequence in 06 §3: duplicate → NME → tariff → room/ICU cap → proportionate deduction → sub-limits → deductible → co-pay → sum-insured cap → rounding. Paise arithmetic; one adjustment per rule per line; remaining-amount semantics.
- **Output:** adjustments with formula, base, reason code, rule version, evidence, and the authorising clause (`authority`: artifact@version, document, clause). No clause, no deduction: the evaluation fails with a configuration error instead (06 §2). Recommended payable.
- **Room rules:** in a multi-room stay the proportionate deduction uses a day-weighted actual room rate (configurable), so line order cannot change the payable. Billed room days are compared with the stay under the configured day-count convention; excess days raise a review finding.
- **Acceptance:** TC-CAL-01..05, TC-CAL-08, TC-CAL-09, TC-EVD-01, TC-CFG-03 (executed), TC-FIN-01..11 (property tests FI-01..FI-11, executed: `verification/test_invariants.py`).
- **Priority:** P0.

### CAP-12 Clinical review support (FR-CLN)
- **User/purpose:** help the medical officer review faster without the system making medical judgements.
- **Processing:** a structured clinical summary of the admission (presenting complaint, diagnosis, procedure, course, history statements, investigations). Every sentence cites a page and quote.
  - Rule-based prompts generate questions for the medical officer, for example: history statement suggests a pre-existing condition within the waiting period; LOS outside the configured range for the procedure (P1); procedure not consistent with diagnosis text (P2, needs licensed clinical content).
  - Outputs carry an `uncertainty_note` (required by the DB check) and the route `MEDICAL_OFFICER`.
- **Must not:** produce denial wording, medical-necessity conclusions, or ICD codes not present in the documents (07 §5).
- **Acceptance:** TC-CLN-01, TC-CLN-02.
- **Evidence status:** "Detailed medical scrutiny" (E001, COMPANY-REPORTED). Our boundary is PROPOSED with clinical-advisor review required (OQ-30).
- **Priority:** P0 (summary + PED signal), P1 (LOS norms), P2 (protocol checks).

### CAP-13 Anomaly flags (FR-ANO)
- **Processing:** deterministic signals first:
  - bill-number reuse across members at the same hospital;
  - identical line sets across claims;
  - documents dated after the payment date;
  - PDF metadata edits after the stated issue date (P1);
  - statistical outliers on cost per day by procedure and hospital (P2, needs portfolio data).
  - Every flag: severity, evidence, innocent explanations, route `FWA_REVIEW`.
- **Must not:** contain the words "fraud", "fraudulent" or "fake" in system-generated text. Use "pattern for review".
- **Acceptance:** TC-ANO-01, TC-ANO-02 (false-positive budget, 10 §2).
- **Evidence status:** "FWA detection" (E001). Red flag indicators are a regulatory concept (E-REG-06). Ours is PROPOSED.
- **Priority:** P0 (bill-number reuse, duplicate lines), P1/P2 (others).

### CAP-14 Recommendation assembly (FR-RCM)
- **Processing:** derive `recommendation_type` from findings and blocks (06 §4). Compose the reviewer explanation: a summary, then deductions grouped by reason with policy clause references in plain language, then open questions.
- **States:** `RUNNING → COMPUTED | BLOCKED | FAILED`; later `STALE` (new evidence or correction) → `SUPERSEDED` (by the next evaluation).
- **Acceptance:** TC-RCM-01, TC-RCM-02 (explanation quality rubric).
- **Priority:** P0.

### CAP-15 Reviewer corrections and overrides (FR-REV)
- **Actions:** correct fact; resolve conflict; reclassify line; override/add/remove adjustment; resolve or dismiss finding; return for rework; escalate (medical / CRC / FWA).
- **Rules:**
  - Overrides, additions, removals and dismissals require a reason code and a comment.
  - Every action is an append-only `reviewer_action`.
  - Actions that change rule inputs queue a new evaluation.
  - The UI shows extracted value, reviewer value and final value distinctly (03 §5).
  - An override of an adjustment is stored against (line, rule) with a fingerprint of the line. When the claim is re-evaluated, the override is re-applied only if the line is unchanged; the engine's own figure is kept beside it. If the line changed, the engine figure applies and the reviewer must reconfirm (`OVERRIDE_NEEDS_RECONFIRMATION`).
- **Permissions:** 03 §4 matrix.
- **Acceptance:** TC-REV-01, TC-REV-02, TC-REV-03 (executed), TC-SEC-02.
- **Priority:** P0.

### CAP-16 Queries (FR-QRY)
- **Processing:**
  - Query items are generated from findings and edited by the processor.
  - Default addressee is the hospital (E-REG-01 ¶17c).
  - A supervisor or processor (per configuration) approves the letter. Only approved letters are released through the TMS.
  - Reminders follow the customer's schedule.
  - Answers arrive as documents linked to query items.
  - The claim never auto-closes on non-response; it goes to a supervisor work queue.
- **Acceptance:** TC-QRY-01, TC-QRY-02.
- **Priority:** P0 (draft + approve + export), P1 (reminders, TMS round-trip).

### CAP-17 Approval and final disposition (FR-DEC)
- **Processing:** a decision is recorded against a specific, non-stale evaluation.
  - Approval limits per user (`role_assignment.approval_limit_paise`).
  - A second approver is required when any rule in the tenant's workflow config fires (`config/workflow-TENANT-DEMO.v2026.1.0.json`, ILLUSTRATIVE): the payable exceeds the deciding user's limit; the decision deviates from the recommendation by more than ₹5,000; or total deductions exceed 30% of the billed amount. Trace 2 triggers the third rule (deductions ≈ 51% of billed), so PROC-11 records and SUP-02 approves (DEC-0002). Trace 1 (₹1,07,591) is within PROC-07's illustrative ₹1,50,000 limit, so no second approval is needed (DEC-0001). The approver must differ from the requester (DB check).
  - `REPUDIATED_WITH_CRC_APPROVAL` requires an insurer CRC reference and `communicated_by = INSURER`.
  - **TPA tenants:** a TPA cannot itself repudiate, and the repudiation decision and communication are sent only by the insurer (E-REG-04). The workflow config fixes TPA repudiation behaviour to `RECORD_INSURER_OUTCOME_ONLY`: AW records the insurer's outcome and CRC reference, and generates no repudiation letter.
  - The settlement worksheet and letter give the amount paid and each amount disallowed with its reason and clause (E-REG-01 ¶17b; E-REG-04). When any part of the claim is disallowed, they also carry the grievance procedure, grievance officer and ombudsman details (E-REG-04, settlement communication).
- **Acceptance:** TC-DEC-01..03.
- **Priority:** P0.

### CAP-18 Reprocessing after new evidence (FR-RPR)
- **Processing:**
  - A new document, a reviewer correction or a configuration change marks the current evaluation `STALE`.
  - A new evaluation runs. It supersedes the old one and keeps continuity of findings: resolved findings stay resolved unless their evidence changed.
  - A decision cannot be recorded on a stale evaluation (409).
  - Late documents after a decision → claim `REOPENED` (supervisor permission) with a new evaluation and a decision delta.
- **Acceptance:** TC-RPR-01, TC-DEC-02, trace 3a → 3b.
- **Priority:** P0.

### CAP-19 Export and integration (FR-EXP)
- **Processing:** a decision produces a settlement worksheet (JSON + PDF; `schemas/settlement-worksheet.schema.json`; examples in `fixtures/worksheets/`) and an export to the TMS. No repudiation letter is generated for a TPA tenant (CAP-17). Exports are idempotent: one per decision per target. Webhooks are delivered at-least-once with `event_id` de-duplication, and dead-lettered after 24 h of retries.
- **Acceptance:** TC-EXP-01, TC-EXP-02, TC-REL-03.
- **Priority:** P0 (worksheet + API), P1 (TMS adapters).

### CAP-20 Audit history (FR-AUD)
- **Processing:** append-only, hash-chained events per claim covering documents, extraction, rule runs, recommendations, reviewer actions, queries, decisions and exports. Viewable on the claim timeline and exportable for inspection.
- **Acceptance:** TC-AUD-01 (chain self-consistency checked in `render_traces.py`, which also writes the chain; append-only enforced and tested in `validate_db.sh`). The audit event types are listed in `schemas/audit-event.schema.json`.
- **Priority:** P0.

### CAP-21 Customer configuration (FR-CFG)
- **Processing:** CONFIG_ADMIN authors policy configurations, NME lists, tariffs and checklists.
  1. Schema validation.
  2. Diff against the previous version.
  3. Replay on golden cases: the change shows which reference claims' payables would change.
  4. A second person approves.
  5. Publish with effective dates.
  - Claims evaluate against the version effective on the admission date.
- **Acceptance:** TC-CFG-01, TC-CFG-02.
- **Priority:** P0 (JSON authoring + replay), P1 (form-based editor).

### CAP-22 Operational metrics (FR-OPS)
- **Metrics:** queue age, TAT compliance by workflow, recommendation-vs-decision agreement, correction rate by field, override rate by rule, blocked-claim reasons, model and provider error rates, cost per claim. Metric definitions are in 10 §2.
- **Priority:** P1.

### CAP-23 TAT clock (FR-TAT)
- **Processing:** clock rules per workflow:
  - pre-auth 60 minutes from receipt;
  - discharge 180 minutes from the discharge request;
  - reimbursement: due 15 days from the **first** submission of the claim (`submitted_at`), not from the date the file became complete; interest exposure at bank rate + 2% accrues from the date of intimation (`intimated_at`) (E-REG-03).
  - Clock rules live in the workflow config's `tat` block.
  - Whether open queries pause the clock is configurable and unresolved (OQ-21).
  - Alerts at configurable thresholds.
- **Acceptance:** TC-TAT-01.
- **Priority:** P0 (reimbursement display), P1 (discharge alerts).

## 6. Non-functional requirements

| ID | Requirement | Target (PROPOSED, to calibrate) |
|---|---|---|
| NFR-01 | Reimbursement: time from documents complete to evaluation computed | p95 ≤ 15 min (batch acceptable) |
| NFR-02 | Cashless discharge (P1): time from final bill received to evaluation | p95 ≤ 20 min, leaving ≥ 2 h of the 3-hour clock for humans |
| NFR-03 | UI: open a claim workspace | p95 ≤ 2 s; evidence jump ≤ 300 ms after first load |
| NFR-04 | Availability (business hours IST, pilot) | 99.5% monthly; 99.9% before cashless go-live |
| NFR-05 | Degraded mode | If OCR or LLM providers fail, claims queue with visible status. Manual entry stays possible. No partial evaluations |
| NFR-06 | Determinism | Same inputs and config versions → identical output hash (FI-09) |
| NFR-07 | Accessibility | WCAG 2.2 AA for reviewer screens; full keyboard operation |
| NFR-08 | Data residency | Customer data and model inference in India regions unless the customer contract allows otherwise (08 §3) |
| NFR-09 | Recovery | RPO ≤ 15 min, RTO ≤ 4 h (pilot) |

## 7. Feature matrix: competitor evidence → our requirement

| Capability | Competitor evidence (status) | Our requirement | Priority | Key dependency | Tests | Deliberate difference |
|---|---|---|---|---|---|---|
| Intake via API/TMS/portal | E001 (COMPANY-REPORTED) | CAP-01, CAP-19 | P0/P1 | TMS adapter per customer | TC-INT-01, TC-EXP-01 | — |
| Structured extraction "100+ attributes" | E001 | CAP-04 with grounding check | P0 | OCR + LLM provider in India | TC-EXT-01..04 | Facts that fail grounding are unusable by rules |
| Line-item categorisation | E001 | CAP-07 | P0 | Customer dictionaries | TC-BIL-01..02 | Dictionary-first; low-confidence lines block only themselves |
| Tariff / SOC validation | E001, E003 | CAP-09 | P0/P1 | Customer tariff data (OQ-12) | TC-TAR-01..02 | Missing tariff item → flag, not deduct |
| Policy benefit validation | E001 | CAP-08, CAP-11 | P0 | Policy wording → config | TC-ELG-*, TC-CAL-* | Waiting periods and exclusions → review only |
| NME identification | E001, E003 | CAP-10 | P0 | Customer NME list | TC-NME-01..02 | — |
| Deduction calculations | E001 | CAP-11 | P0 | Calculation order per wording | TC-CAL-*, TC-FIN-* | Order is configuration, proven to matter (₹8,500 in trace 2) |
| Medical scrutiny | E001 | CAP-12 | P0/P1/P2 | Clinical advisor; licensed content | TC-CLN-01..02 | No medical-necessity verdicts |
| FWA detection | E001 | CAP-13 | P0/P1 | Portfolio data | TC-ANO-01..02 | "Pattern for review", never "fraud" |
| Pre-auth recommendation Approve/Query/Reject | E002 (Jan 2026, later dropped) | Not in P0. P2 pre-auth assist without "Reject" | P2 | Real-time integration | — | No "Reject" type at all |
| "Payment triggers fired automatically" | E002 | **Not offered** | — | — | FI-08 | Every payment needs a human decision |
| Audit trail | E001 | CAP-20, hash-chained | P0 | — | TC-AUD-01 | Tamper-evident chain |
| Reviewer validation | E001 | CAP-15, CAP-17 | P0 | — | TC-REV-*, TC-DEC-* | Extracted vs reviewer vs final values shown separately |
| Queries | Implied by "Query" (E002) | CAP-16, hospital-first | P0 | TMS messaging | TC-QRY-* | Never auto-closes |
| IPD + OPD | E001, E011 | IPD first; OPD P2 | — | — | — | Phased |
| ISO 27001 | E004 | 08 control plan: ISMS controls built from Phase 1; certification audit after Phase 5. Not a claim | P2 | Auditor | — | — |

## 8. Differentiation hypotheses (to test, not assumed)

1. **Traceable money.** Each rupee is linked to rule, clause and evidence, with replay. This hypothesis wins TPA quality and audit teams, and it lowers grievance reversals. Test with a mock grievance file (11 BL-26).
2. **Customer-owned configuration with replay.** A configuration change shows its payable impact on golden claims before it is published. Test: time to onboard one product.
3. **Honest abstention.** Fewer wrong deductions at the cost of more queries. Test: the net leakage metric M-FIN-04, not deduction volume.
4. **India-resident inference by default** (E-PRC-05). Test: procurement questionnaires.

## 9. Out of scope (this build)

- Hospital-side claim preparation.
- Automatic payment.
- Automatic repudiation.
- Underwriting.
- Clinical coding (ICD/PCS assignment) beyond reading codes written on documents.
- Group policy endorsement processing.
- Government schemes (PM-JAY) rule packs.
- Fraud investigation case management (we hand off).
- Non-English OCR beyond detection and routing (P1 research item, 07 §2).
