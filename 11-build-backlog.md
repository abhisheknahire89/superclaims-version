# 11 — Build plan, backlog and council review

Status: **PROPOSED**. Naming: **Phase 0–5** are delivery phases in time (§2). **P0/P1/P2** are priorities used in 02: P0 = first slice (Phases 1–2), P1 = next release (Phase 3, e.g. cashless discharge, TMS adapter, packages), P2 = after the pilot. Effort figures are person-day estimates for a mid-level team familiar with the stack. They assume the materials marked MISSING in 09 arrive on time. They are planning numbers, not commitments.

## 1. First end-to-end slice

| Dimension | Choice |
|---|---|
| User | TPA claims processor, plus a medical officer for flagged claims, plus a supervisor for second approval |
| Workflow | IPD reimbursement (02 §4) |
| Policy configuration | One retail indemnity product of the pilot customer, encoded from its wording, effective-dated. Until that wording is available: `POLCFG-ILL-INDEMNITY-A` (illustrative) |
| Tariff | One network hospital tariff with item caps (packages deferred) |
| Documents | Claim form, discharge summary, itemised final bill, pharmacy bills, investigation reports, payment receipts. English, typed or printed. Native PDFs and scans |
| Out of slice | Pre-auth, cashless discharge, OPD, packages, Hindi and regional OCR, NHCX, statistical FWA |
| Done means | G1 evidence (10 §6) on 50 permissioned claims, demonstrated in the reviewer UI with a human decision recorded and a settlement worksheet exported |

## 2. Phases

| Phase | Weeks (indicative) | Goal | Backlog items | Exit evidence |
|---|---|---|---|---|
| Phase 0 Discovery and access (runs alongside Phase 1) | 0–4 | Customer, data and legal positions | BL-01..03 | Signed DPA; wording, tariff and 50 claim files received; baseline time study; answers to OQ-10/12/13/24 |
| Phase 1 Technical proof | 1–14 | Engine + extraction + the reviewer screens G1 needs (queue, workspace, bill and deductions, decision, worksheet) on one slice | BL-04..17, BL-21, BL-23, BL-24 (≈ 168 pd) | G1 |
| Phase 2 Reviewer workflow completion | 13–20 | Findings UI, queries, audit timeline, TAT clocks, ops metrics, accessibility | BL-18, 19, 22, 25, 26, 28, 32 | TC-UX-*, TC-QRY-*, TC-DEC-* green; usability test with 5 reviewers |
| Phase 3 Configuration and integration | 17–26 | Config authoring + replay; TMS adapter; cashless discharge path | BL-20, 27, 30, 31 | First TMS round-trip; replay used for a real config change; discharge latency measured |
| Phase 4 Supervised pilot | 24–36 | Live use, human decision on every claim | BL-29, 33, 34, 35, 38 before entry | G2 entry, then 3 months of metrics toward G3 |
| Phase 5 Operational hardening | 30–40 | DR, on-call, cyber audit support, ISMS | BL-34 follow-ups; ISMS controls | G3 evidence |

## 3. Backlog

| ID | Item | Purpose | Depends on | Data / rule requirements | Acceptance | Tests | Effort (pd) |
|---|---|---|---|---|---|---|---|
| BL-01 | Data and legal access package | Unblock everything | — | DPA; consent basis (OQ-31); de-identification protocol | Signed; 50 files in tenant account | — | 10 (PM + counsel) |
| BL-02 | Buyer and pricing interviews (5 TPAs/insurers) | Validate buyer, value and price | — | Interview guide | Written synthesis with pricing range | — | 8 |
| BL-03 | Baseline time-and-motion study | Real baseline for M-OPS-03 | BL-01 | 30 claims observed | Minutes per claim by step, with variance | — | 6 |
| BL-04 | Repo, CI, IaC skeleton, staging account (ap-south-1) | Foundation | — | — | Deploy pipeline green; `verification/*` in CI | — | 8 |
| BL-05 | DB schema v1 + migrations | System of record | BL-04 | `db/schema.sql` | `validate_db.sh` in CI | TC-AUD-01, TC-SEC-01 | 4 |
| BL-06 | Document ingest: upload slots, hash, Object Lock, page split, text-layer detection | CAP-02 | BL-05 | — | Duplicate idempotency; quarantine path | TC-DOC-01, TC-SEC-05 | 8 |
| BL-07 | OCR/LLM bake-off on 200 pages | Pick providers (ADR-05/06) | BL-01, BL-06 | Stratified pages, panel labels for C1 fields | Decision record with metrics | TC-EXT-01 (partial) | 12 |
| BL-08 | OCR pipeline + page quality score | CAP-04 | BL-07 | — | Unreadable pages detected | TC-DOC-02 | 8 |
| BL-09 | Model gateway (Bedrock India adapter, schema output, metering, kill-switch, PHI-free logs) | ADR-06 | BL-04 | Prompt registry | Gateway metrics; log CI test | TC-SEC-04, TC-REL-02 | 10 |
| BL-10 | Extraction (classification, fields, lines) + grounding check + normalisation | CAP-04 | BL-08, BL-09 | Field catalogue (07 §3) | M-EXT thresholds (proto) on 50 claims | TC-EXT-01..04, TC-SEC-03 | 20 |
| BL-11 | Fact resolution, conflicts, member matching | CAP-05/06 | BL-10 | Matching thresholds | Trace 3a behaviour on real data | TC-RCN-01, TC-MAT-01..02 | 10 |
| BL-12 | Bill line model + categorisation (dictionary → model) | CAP-07 | BL-10 | Customer NME list and synonyms | M-BIL thresholds (proto) | TC-BIL-01..02 | 10 |
| BL-13 | Rule engine v1 (port harness to production module; config loading by effective date) | CAP-08..11 | BL-05 | Policy config with `clause_refs`, tariff, NME list, checklist | All harness traces, rule tests and FI tests pass in CI | TC-CAL-*, TC-FIN-*, TC-TAR-01..02, TC-NME-*, TC-ELG-04/07, TC-REV-03, TC-EVD-01, TC-CFG-03/04, TC-DOC-06 | 12 |
| BL-14 | Encode pilot product wording + tariff + NME list (with customer SME) | Real configuration | BL-01, BL-13 | M-16, M-17, M-18 | Clause-by-clause sign-off; replay on 30 claims | TC-CFG-01 | 8 |
| BL-15 | Evaluation persistence, STALE/SUPERSEDED, re-evaluation triggers | CAP-14, CAP-18 | BL-13 | — | Trace 3a → 3b on real files | TC-RPR-01, TC-DOC-03, TC-REL-04 | 6 |
| BL-16 | Reviewer workspace: queue, three-pane workspace, evidence viewer | S-01..S-03 | BL-15 | — | TC-UX-02 ≤ 300 ms | TC-UX-01, -02, -04 | 20 |
| BL-17 | Bill & deductions UI, overrides, claim ladder | S-04 | BL-16 | — | Ladder reconciles; override flow | TC-REV-01..02 | 10 |
| BL-18 | Findings UI (blocks, clinical, anomaly) | S-05 | BL-16 | — | Wording lint passes | TC-CLN-02, TC-ANO-01 | 6 |
| BL-19 | Queries (draft, approve, export) | CAP-16, S-06 | BL-16 | Letter templates | Unapproved never released | TC-QRY-01..02 | 6 |
| BL-20 | TMS adapter for pilot customer | CAP-19 | BL-01 | TMS API spec (M-23) | Round-trip claim → decision → export | TC-EXP-01..02, TC-REL-03 | 20 |
| BL-21 | Decisions, approval limits, second-approval rule from workflow config, CRC path (TPA tenants record the insurer's outcome only), settlement worksheet with grievance block | CAP-17 | BL-17 | Letter content per E-REG-04; `config/workflow-*.json` | DB and API checks | TC-DEC-01..03 | 8 |
| BL-22 | Audit timeline UI + chain verification + anchoring job | CAP-20 | BL-05 | — | Verified chain shown | TC-AUD-01 | 5 |
| BL-23 | Clinical summary with citations + lint; PED signal finding | CAP-12 | BL-10 | Medical advisor review of boundaries | M-CLN-02 100% | TC-CLN-01..02 | 8 |
| BL-24 | Anomaly v1: bill-number reuse, duplicate lines, cross-claim duplicates | CAP-13 | BL-13 | Portfolio index | Flag rate ≤ 5% on sample | TC-ANO-01..03 | 6 |
| BL-25 | TAT clocks and alerts | CAP-23 | BL-15 | Clock rules from workflow config: reimbursement clock from first submission, interest from intimation (OQ-21 for query pauses) | Due times and interest exposure correct | TC-TAT-01 | 4 |
| BL-26 | Mock grievance file test (explainability) | Differentiation hypothesis 1 | BL-21 | 10 decided claims | Independent reviewer reconstructs each deduction from the worksheet alone | TC-RCM-02 | 3 |
| BL-27 | Config authoring + replay UI | CAP-21, S-09 | BL-14 | — | Replay diff on golden claims | TC-CFG-01..02 | 12 |
| BL-28 | Ops metrics | CAP-22, S-10 | BL-15 | Metric definitions (10 §2) | Reconciles with DB | TC-OPS-01 | 8 |
| BL-29 | Golden set build (300 claims, double annotation, adjudication) | G2 evidence | BL-01 | Annotators, MO | κ reported; set frozen | TC-EXT-01, TC-RCM-02 | 30 (annotation) + 5 |
| BL-30 | Cashless discharge path (prioritised queue, pre-extraction during stay, manual fallback) | Priority P1 workflow (Phase 3) | BL-20 | Pre-auth history from TMS | p95 ≤ 20 min in staging load | TC-REL-01..02 | 15 |
| BL-31 | Load and soak test (3× peak) | NFR | BL-15 | Synthetic generator | SLOs met | — | 5 |
| BL-32 | Accessibility audit and fixes | NFR-07 | BL-17 | — | WCAG 2.2 AA | TC-UX-03 | 6 |
| BL-33 | Penetration test (external, grey box) + fixes | G2 | BL-21 | — | No open critical or high findings | — | 5 + vendor |
| BL-34 | Incident runbooks, on-call, restore drill | G2 | BL-04 | — | Drill passed (hashes recompute) | — | 6 |
| BL-35 | Pilot training and reviewer playbook | G2 | BL-21 | — | Reviewers certified on 10 practice claims | — | 4 |
| BL-36 | Pre-auth assist (no Reject type) | Priority P2 | BL-30 | Clinical criteria content (M-20) | Design review with insurer | — | 25 |
| BL-37 | OPD rule pack | Priority P2 | BL-13 | OPD wording | — | — | 20 |
| BL-38 | Independent review of rule catalogue and traces (claims expert + actuary/counsel) | Proof status | BL-14 | — | Written review; issues resolved | all TC-CAL | 5 + external |
| BL-39 | Hindi/Indic OCR evaluation | 07 §2 | BL-07 | Sample pages | Go/no-go decision | — | 6 |
| BL-40 | NHCX adapter feasibility | Priority P2 | — | Current NHA specs (OQ-51) | Sandbox exchange | — | 10 |

Indicative Phase 1 total: BL-04..BL-15 and BL-23..24 (130 pd) plus the G1 screens BL-16, BL-17 and BL-21 (38 pd) ≈ 168 person-days. That is about 14 weeks for a 4–5 person engineering team (front-end from week 6), allowing for integration overhead. Assumes BL-01 and BL-07 are not delayed.

## 4. Critical path, materials and staffing

1. **Critical path:** BL-01 (data and legal) → BL-07 (bake-off) → BL-10 (extraction) → BL-13/14 (engine + real configuration) → BL-16/17 (workspace) → BL-21 (decision + worksheet) → G1, all inside Phase 1. The two external dependencies on this path are customer files and wording (M-16, M-19), and a legal position on processing them (OQ-24, OQ-31).
2. **Second path:** TMS spec (M-23) → BL-20 → cashless discharge (BL-30). Without a TMS integration, the competitor's headline workflow (cashless discharge) cannot be matched.
3. **Staffing:**
   - From week 1: product/claims lead; 2 backend; 1 document-AI/ML; 1 front-end (from week 6); QA (0.5).
   - Contracted: claims SME (from week 1); medical advisor (from week 4); counsel (weeks 1–6).
   - Annotators: weeks 8–20.

## 5. Council review

These are simulated review perspectives, not real participants. Each perspective names gaps, challenges an assumption, and proposes a validation method. Several AI-generated perspectives do **not** count as independent corroboration. The executed checks in 10 §7 and the planned customer evidence are the basis for conclusions.

| Perspective | Gaps found in this pack | Assumption challenged | Validation method |
|---|---|---|---|
| Product & discovery | Buyer (TPA vs insurer) and willingness to pay are unverified. Reimbursement-first may be the wrong wedge if customers mainly feel cashless pain | "Reviewer time saving sells." The cost model (09 §6) suggests value depends on leakage and TAT, not minutes | BL-02 interviews with pricing questions; BL-03 baseline; ask each buyer to rank pre-auth / discharge / reimbursement pain |
| Insurer/TPA claims operations | The calculation order, the proportionate-deduction scope, ICU treatment and GST handling vary by insurer and product. Package handling is deferred, though packages are common in network claims | That one illustrative order is "typical". Trace 2 shows ₹8,500 swings on order alone | Collect claims manuals from two insurers; encode both; replay the same claims under both (BL-14, BL-27) |
| Clinical review | PED signals from history text will produce many false positives. LOS norms and protocol checks need licensed or customer content | That a cited summary saves medical-officer time without increasing risk | MO time study with and without summary on 30 claims; M-CLN-01/03; advisor sign-off before pilot |
| Staff software architect | Single-tenant per customer raises cost and operations at 10+ customers. The SI ledger reservation needs TMS utilisation feeds | That the Postgres queue and a monolith suffice for cashless latency | BL-31 load test at 3× peak; discharge latency measurement in Phase 3 |
| Document AI & evaluation | Indic and handwritten content is untested. Calibration requires labelled data we don't yet have. Grounding by substring may fail on OCR noise | That managed OCR is good enough on Indian hospital scans | BL-07 bake-off with stratified pages; reliability diagrams; BL-39 |
| Enterprise UX | Reviewer over-trust (rubber-stamping) is a real risk. Agreement rate can look good while accuracy is poor | That showing "proposed" values with dashed outlines is enough to prevent anchoring | Usability study: seeded errors in 10% of recommendations, measure detection rate (target ≥ 80%) |
| Security & privacy | TPA outsourcing and data-sharing clauses vs SaaS; full IRDAI 2026 guidelines unread; DPDP primary text unread | That single-tenant AWS in India satisfies every customer | Counsel opinion (OQ-24/45/46); customer security questionnaire in week 2 |
| QA & reliability | No tests yet against real documents. Property tests use the engine's own generator (shared blind spots) | That FI-01..11 cover the money risks | Add an independent oracle: a claims expert recomputes 30 real claims by hand (BL-38); extend mutation testing from the contract validator (done) to the engine |
| Commercial & implementation | Configuration effort per product is a guess. Hospital tariffs may arrive as hundreds of PDFs | That onboarding takes ~2–3.5 weeks per product (09 §4: 6–9 pd to encode and sign off, plus 5–8 pd of product-specific golden cases) | Time the first two product onboardings; set the price floor on measured effort |

Contradictions repaired during this review (logged for transparency):

- Example adjustment IDs in the API docs did not match the fixture output. They now reference real fixture IDs, and `check_refs.py` fails the build if a doc or API example cites an ID that no fixture contains.
- Trace 3a's stated bill total was aligned with the corrected bill.
- Trace 3b's audit chain was changed to continue 3a's chain rather than restarting at GENESIS.
- The build script quoting was fixed so contract checks run in CI.

A second, independent review (a separate agent that had not written the pack) found 25 defects. All were repaired, and each fix is covered by a check that now runs:

| Defect found | Repair | Check |
|---|---|---|
| A validator mutation test was reported but did not exist | Written: 8 broken inputs, all rejected | `mutation_test_contracts.py` |
| Payable depended on bill-line order in multi-room stays | Day-weighted actual room rate (configurable) | TC-CAL-08; FI-10 with multi-room claims |
| Deductions did not carry the authorising clause | Required `authority` on every adjustment; evaluation fails without it | TC-EVD-01, TC-CFG-03, DB check |
| Regulatory citations not backed by stored excerpts; some went beyond the text | Excerpts added or claims softened; TPA repudiation is recorded as the insurer's outcome only; reimbursement clock from first submission, interest from intimation | `raw/E-REG-…`, ledger, workflow-config schema |
| Vendor data-handling claims lacked a source | AWS passage re-read and quoted in E-PRC-05 | Ledger |
| Second-approval rule contradicted itself | One rule in workflow config; illustrative approver limits | `workflow-config.schema.json`; DEC-0002 |
| Re-run after a tariff or NME change could return the old evaluation | `input_hash` covers claim and all config versions | TC-CFG-04 |
| Trace 3b audit events out of causal order | Documents now arrive before STALE and resolutions | Time-ordering check in `render_traces.py` |
| Identity scoring described as implemented; ALL scope undefined | Scoring marked ○; scope renamed ALL_FINANCIAL; eligibility uses identity-matched documents only | TC-MAT-01, TC-ELG-07 |
| Checklist contradicted fixtures and wireframe | Checklist artifact, conditional items, fixtures list documents present | TC-DOC-06 |
| Unlabelled competitor findings; one misquote; non-standard labels; three LinkedIn records missing | Labels added, quote corrected, ledger at 64 rows | `check_refs.py` |
| Room-rent cap never checked stay dates | Billed room days vs MIDNIGHTS count → review finding | TC-CAL-09 |
| G1 scope and phase plan disagreed; P-numbers meant two things | Phases renamed Phase 0–5; G1 screens moved into Phase 1 | This file §2 |
| Cost tiers hidden; wrong price citation | Tier inputs printed as ASSUMPTION; citation corrected | `cost_model.py` |
| API and schemas missing endpoints, engine input, tariff/NME/checklist schemas, audit event list, override semantics | 32 paths; 10 JSON Schemas; 38 audit event types; override fingerprint rule (now 33 paths, 11 schemas and 53 checks after the workbench build added `GET /me` and the classifier map) | `validate_contracts.py` |
| State-machine gaps | CRC-declined exit, FAILED evaluation path, CLOSED_DUPLICATE path, READ_ONLY role | 03 §2–4; DB enums |
| Personal data and copied third-party text in `raw/` | Signatory redacted; founders' ages removed; competitor pages reduced to notes with short quotes | `raw/README.md` |
| UI examples and decider IDs did not match traces | Examples and fixtures aligned | `db_load_sql.py`, 03 §5 |
| Onboarding estimates disagreed | One figure: 6–9 pd plus 5–8 pd golden cases | 08, 09, 11 |

## 6. Phase 1 build status (11 October 2026)

The workbench in `workbench/` implements parts of the following items on synthetic data:

- BL-05, BL-06, BL-10 to BL-13, BL-15 to BL-17 and BL-21, with BL-04, BL-09, BL-18, BL-19 and BL-22 to BL-27 in part.
- BL-07, BL-08, BL-14, BL-20 and every item that needs real data or people have not started.

Each item's code, tests and remaining gap are in `workbench/docs/traceability.md`. Where the build departs from ADR-01/02/04/09/10, ADR-12 explains why.

The critical path (§4) is unchanged. G1 still waits on BL-01 (data and legal access) and BL-07 (bake-off).

## 7. Top risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No access to real wordings, tariffs or claims within 6 weeks | Medium | Blocks G1 | Start BL-01 in week 0; work on synthetic and illustrative data meanwhile; pick a design-partner TPA |
| The competitor's integration routes (API, TMS, portal; COMPANY-REPORTED, E001; no TMS vendor named, so depth is UNKNOWN) and ekincare's distribution (COMPANY-REPORTED, E010, E011) | High | Sales | Differentiate on traceability and configuration replay; target customers outside ekincare's base |
| Large TPAs build in-house (E-CMP-01) | High | Market size | Sell to mid-size TPAs and insurers; component licensing (engine + workspace) |
| Regulatory interpretation (outsourcing, data sharing) restricts the SaaS model | Medium | Product shape | Counsel early (OQ-24); design as a customer-operated tool |
| LLM provider residency or price changes | Medium | Cost/compliance | Gateway abstraction; yearly bake-off; self-hosted fallback |
