# 12 — Open questions, blockers and owners

This is the single place for every open question in the pack (product-research discipline, E-SK-01). Each entry gives its impact, the evidence or decision that would resolve it, a proposed owner, and the gate it blocks (10 §6).

**Owners**

- **You:** the person commissioning this work.
- **PM:** product/claims lead.
- **Counsel:** insurance and data-protection lawyer.
- **Customer:** the pilot customer.
- **Eng:** engineering.

## A. Competitor (cannot be resolved from public evidence)

| ID | Question | Impact | Current evidence | Resolves it | Owner | Blocks |
|---|---|---|---|---|---|---|
| OQ-01 | How does the Superclaims product actually behave (UI, flows, corrections, failure handling)? | Feature parity is unknowable; our design is independent | Marketing pages only (01 §1) | Authorised demo or customer reference (01 §8). Not attempted, per your instructions | You | None (parity is a research target, not a gate) |
| OQ-02 | Definitions behind "~10 min", ">97% precision", "~70% cost", "100K+/month", "10% claims-value impact" | Benchmarks for sales positioning | Inconsistent values (01 §4) | Demo Q2; customer reference | PM | None |
| OQ-03 | Who are the customers? Insurer vs TPA split? | Competitive targeting | ">10 insurers and TPAs" (E012) | References; market intelligence | PM | None |
| OQ-04 | Do Superclaims staff verify claims for customers (a managed service)? | Comparability of speed claims; regulatory model | Job post for "Health Claims Processor" to "verify AI-processed claims" (E-LI-07) | Demo or reference | PM | None |

## B. Customer, data and product

| ID | Question | Impact | Current evidence | Resolves it | Owner | Blocks |
|---|---|---|---|---|---|---|
| OQ-10 | Is the first buyer a TPA or an insurer? Which workflow hurts most? | Wedge (reimbursement vs discharge), integration, pricing | Provisional assumption: TPA, reviewer-assist | BL-02 interviews | You/PM | G1 scope confirmation |
| OQ-11 | Willingness to pay and pricing model (per claim, platform fee) | Business viability | Competitor charges per claim (E012); our ₹60–150 range is a hypothesis | BL-02 | PM | G2 commercial terms |
| OQ-12 | Will the pilot customer supply hospital tariffs, packages and their effective dates in usable form? | Tariff rules (CAP-09) | None | Customer data inventory | Customer | G1 (tariff checks) |
| OQ-13 | Will the customer supply product wordings and claims manuals, including calculation-order conventions? | All money rules | None | Customer | Customer | **G1** |
| OQ-14 | What is the real manual baseline (minutes per claim, by step) and the claim-value distribution? | Cost model, success metrics | Competitor numbers undefined; our ASSUMPTIONS (09) | BL-03 time study; customer MIS | PM | G2 metric targets |
| OQ-20 | Do the standardised non-medical lists (List I–IV) still bind insurers after the 2020 standardisation master circular was superseded, or only through filed wordings? | NME rule authority | E-REG-02, E-REG-07 | Counsel; customer compliance | Counsel | G2 (wording-based config is the workaround) |
| OQ-21 | Does an open query pause the 15-day reimbursement clock? Does "submission" mean first submission even if documents are missing? | TAT display, interest exposure | E-REG-03 states "within fifteen days from submission of claim" and interest "from the date of receipt of intimation". The pack's default starts the clock at first submission, accrues interest from intimation and does not pause on queries (workflow config `tat`) | Counsel; customer practice | Counsel | G2 |
| OQ-22 | Calculation order (co-pay vs sum-insured cap; proportionate deduction before or after tariff; deductible placement) per customer product | Payable correctness (₹8,500 swing in trace 2) | Product-specific | Customer claims manual | Customer | **G1** |
| OQ-23 | How do "insurer/TPA collects documents from hospitals" obligations apply to reimbursement at non-network hospitals? | Query addressee, claimant burden | E-REG-01 ¶17c | Counsel | Counsel | G2 |
| OQ-25 | Day-count convention for room days (calendar days vs midnights; admission after 23:00) | Room cap arithmetic | Varies | Customer manual | Customer | G1 |
| OQ-26 | Can the TMS supply sum-insured utilisation and prior claims in real time? | SI cap correctness, concurrency | — | TMS spec | Customer | G1 (manual input as fallback) |
| OQ-28 | GST treatment on billed items and how discounts are allocated across lines | Reconciliation and payable | — | Customer manual | Customer | G1 |
| OQ-30 | Clinical boundary: which clinical questions may the system raise, and with what reference content? | Medical-officer workload and risk | Proposed boundary (07 §5) | Medical advisor review | PM | G1 |
| OQ-31 | The customer's legal basis for sharing de-identified claim files with us for evaluation | Evaluation dataset | DPDP obligations from 2027 (E-REG-10) | Counsel + customer DPO | Counsel | **G1** |
| OQ-32 | Source of length-of-stay norms and procedure lists | Clinical P1 rules | None | Customer guidelines or licensed content | PM | Priority P1 features |

## C. Regulatory and legal

| ID | Question | Impact | Current evidence | Resolves it | Owner | Blocks |
|---|---|---|---|---|---|---|
| OQ-24 | Does a SaaS review tool operated by a TPA's own staff conflict with the TPA rule against outsourcing policy servicing, or with its data-sharing restriction? Would a vendor-staffed review service conflict? | Product and service model | E-REG-04 Reg 19(7) and code of conduct (v) | Counsel opinion | Counsel | **G2** |
| OQ-27 | How long must claim documents and decision records be retained, and by whom (insurer vs TPA vs processor)? | Storage cost, deletion design | E-REG-04 Reg 19(2) defers to the Authority | Counsel | Counsel | G2 |
| OQ-45 | Confirm DPDP Rules 2025 obligations and dates from the primary Gazette text | Privacy programme timing | Secondary law-firm summary (E-REG-10) | Read the primary text | Counsel | G2 |
| OQ-46 | Full IRDAI Information & Cybersecurity Guidelines 2026 (Annexure B): controls that flow to TPA vendors | Security scope | Only the summary annexure read (E-REG-05) | Read Annexure B; customer's vendor questionnaire | Eng/Counsel | G2 |
| OQ-52 | Re-capture verbatim text for E-REG-01 ¶9, ¶15(a), ¶16(c), the full TPA grievance-communication paragraph, PPI Schedule D (co-payment) and the cyber guidelines' Annexure A row 14 | Four requirements cite paraphrases (labelled UNVERIFIED) | irdai.gov.in returned 504 on 10 Oct | Re-read the PDFs; add to `raw/E-REG-regulatory-excerpts.txt` | Eng/Counsel | G1 (before any customer-facing use) |
| OQ-43 | CERT-In incident reporting window and log-retention requirements applicable to us and to customers | Ops runbooks, log retention | Commonly cited 6 h / 180 days (not verified here) | Primary CERT-In directions | Counsel | G2 |
| OQ-47 | Is the PED cap of 36 months correct per the primary IRDAI (Insurance Products) Regulations 2024 text, including transition for older policies? | Config schema cap | Secondary (E-REG-09) | Primary regulation | Counsel | G1 (config schema) |

## D. Technical and vendor

| ID | Question | Impact | Current evidence | Resolves it | Owner | Blocks |
|---|---|---|---|---|---|---|
| OQ-40 | MeitY empanelment and STQC audit status of the AWS services and regions we plan to use | IRDAI cyber control (E-REG-05) | Not checked | MeitY empanelment list; AWS compliance docs | Eng | G2 |
| OQ-41 | Is Amazon Textract (text + tables) available in ap-south-1, and at what price? | OCR residency and cost | US West list prices only (E-PRC-02) | AWS console / pricing calculator | Eng | G1 |
| OQ-42 | Price of Claude models through the Bedrock India geographic profile | Inference cost | Anthropic list + regional premium note (E-PRC-01) | AWS pricing | Eng | G1 (cost model) |
| OQ-44 | Provider-side human review of flagged content: does it apply to our use, and is it acceptable to customers? | Privacy | AWS blog: "certain models require human review by AWS" when safety classifiers flag content; models not named (E-PRC-05) | Provider terms | Counsel/Eng | G2 |
| OQ-50 | Does the pilot customer's TMS have an API and accept webhooks? | Integration pattern | — | Integration questionnaire | Customer | Phase 3 |
| OQ-51 | Current NHCX FHIR profiles, protocol (encryption, signatures) and onboarding steps for TPAs | Priority P2 integration | Vendor blog (E-REG-11); IRDAI 2023 circular (E-REG-08) | NHA specifications and sandbox | Eng | After the pilot (priority P2) |

## E. Decisions only you can make (provisional choices in use)

| Decision | Provisional choice in this pack | Reversible? | Effect if changed |
|---|---|---|---|
| Buyer and setting | Insurer/TPA reviewer assistance in India, not a hospital desk | Yes (early) | Hospital-side would need a different PRD |
| First workflow | IPD reimbursement, then cashless discharge | Yes | Discharge-first moves BL-20/BL-30 onto the critical path (+6–8 weeks before G1) |
| Cloud and region | AWS Mumbai/Hyderabad, Bedrock India | Yes, at a cost that grows after Phase 1 | Azure-first changes ADR-04/05/06 |
| Tenancy | Single-tenant per pilot customer | Yes | Pooled needs RLS hardening and noisy-neighbour controls |
| Implementation start | Not started (per your brief: implementation is a subsequent task) | — | — |
