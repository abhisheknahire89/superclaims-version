# Superclaims research and Adjudication Workbench engineering pack

Prepared 9–10 October 2026; the Phase 1 workbench build (`workbench/`) was added on 10–11 October. Evidence was accessed on 9 October unless the ledger says otherwise; a few sources were re-read on 10 October. The pack has two layers, kept apart:

- **Competitor layer** (`01`, `source-ledger.csv`, `raw/`). What Superclaims shows publicly, what it claims, and what is unknown. Every finding is labelled OBSERVED, COMPANY-REPORTED, INDEPENDENTLY CORROBORATED, INFERRED or UNKNOWN. Labels appear in brackets below.
- **Our product layer** (`02`–`12`). A proposed claims-review assistant for Indian insurers and TPAs, working name *Adjudication Workbench (AW)*. Everything here is PROPOSED unless it cites evidence. Policies, tariffs and claims in examples are **illustrative or synthetic**.

## Key findings

1. **Only Superclaims' marketing is visible; the product is not.** [OBSERVED absence] The operating product sits behind a founder-led demo. We found no public screenshots, docs, API reference, case studies or independent evaluations. Everything about how it works is [COMPANY-REPORTED] (01 §1).
2. **The website's positioning moved from autonomous to assistive; LinkedIn messaging remains mixed.** [OBSERVED wording; the reading of intent is INFERRED] January 2026: autonomous agents that "reads, reasons, and decides", with "payment triggers fired automatically" and a pre-auth agent recommending "Approve, Query, or Reject" (E002). Live site: a "Review-ready decision package" for "reviewer validation" (E001). Founders' op-ed principle: "Humans remain accountable" (E-LI-04). But an August 2026 company post still promotes "autonomous claims adjudication" (E-LI-06). Indian rules point toward assistance: only the insurer's Claims Review Committee (CRC) may repudiate, and a TPA cannot repudiate on its own (E-REG-01, E-REG-04) [OBSERVED, primary text].
3. **Its headline metrics conflict and are undefined.** [COMPANY-REPORTED] Turnaround claims include ~10 min vs 300+ min, 5 min vs 90 min, and "days to minutes"; speed multiples of "10x" and "up to 30x". Quality claims are given as both ">97% precision" and "99%/99%+ accuracy", with no unit or ground truth (01 §4). Do not benchmark against them until they are defined.
4. **Company facts.** Cardit Labs Pvt Ltd, Hyderabad [OBSERVED on the certificate]. Founded 2024 [COMPANY-REPORTED]. ISO/IEC 27001:2022 certificate, scope "software development and support" for health-claims processing (E004) [OBSERVED; not checked against the registrar]. 100% acquired by ekincare in July 2026 [COMPANY-REPORTED by both parties]. 11–50 staff [COMPANY-REPORTED]. In October 2025 it advertised for "Health Claims Processors" to verify AI-processed claims (E-LI-07) [OBSERVED post]. That suggests vendor-side human work, whose role in the reported speed is UNKNOWN [INFERRED].
5. **Indian regulation shapes the product more than the competitor does.** [OBSERVED in primary IRDAI texts; interpretation for a software vendor needs counsel]
   - Cashless authorisation within 1 hour; discharge authorisation within 3 hours (E-REG-01).
   - Reimbursement within 15 days, with interest if late (E-REG-03).
   - Partial disallowances must be explained with policy-clause references.
   - Insurers/TPAs, not policyholders, collect documents from hospitals.
   - TPA communications must give "granular" disallowance reasons (E-REG-04).
   - The 2026 IRDAI cyber guidelines apply to TPAs and expect MeitY-empanelled cloud and group/vendor segregation (E-REG-05).
6. **The standard non-medical item lists may no longer have direct regulatory force.** [INFERRED from E-REG-02; UNKNOWN until counsel confirms] The 2020 standardisation master circular was superseded in 2024 (E-REG-02). Non-payable lists must come from each customer's wording (OQ-20).
7. **Calculation order is product configuration, not an industry constant.** [PROPOSED design, shown with synthetic data] In worked trace 2, applying co-pay before or after the sum-insured cap changes the payable by ₹8,500 (06 §7).
8. **Economics hinge on volume, leakage and turnaround compliance, not minutes alone.** [PROPOSED model; inputs are assumptions] Modelled technology cost is ≈ ₹46 per IPD claim. At pilot volume, fixed team cost (~₹1,000 per claim) dwarfs the reviewer time saved (~₹148 per claim). Value must come from scale, net leakage control and turnaround compliance (09 §6). All inputs are assumptions except the cited vendor prices.

## Decisions taken (provisional, reversible; see 12 §E)

| Decision | Choice | Where |
|---|---|---|
| Buyer and setting | Reviewer assistance for insurers and TPAs in India (not a hospital desk). A human makes every decision. No "Reject" output; strongest negative is `REFER_CRC` | 02 §2–3 |
| First slice | IPD reimbursement, one product configuration, one network tariff, English documents. Cashless discharge next | 02 §4, 11 §1 |
| Money | Deterministic engine, paise integers, remaining-amount semantics, configuration-driven order, rounding recorded | 06 |
| AI | Native text first; managed OCR; schema-bound, quote-grounded extraction; models never compute money; clinical and anomaly outputs are cited questions | 07 |
| Architecture | Python/FastAPI modular monolith; PostgreSQL as system of record and job queue; single-tenant AWS Mumbai/Hyderabad; Bedrock India geographic profile for LLMs | 04 |
| Data and API | 31-table schema with append-only evidence and decision tables, hash-chained audit and RLS; OpenAPI 3.1 contract with idempotency, ETags and RFC 9457 errors | 05, `db/`, `api/` |

## What was actually run (all synthetic, all reproducible)

`bash verification/build_all.sh` reruns everything:

| Check | Result |
|---|---|
| Five worked traces (1, 2, 2b reviewer override, 3a blocked, 3b after new evidence) through the reference rule harness, with reconciliation and an independent recomputation of trace 2 | Pass |
| Rule unit tests (TC-ELG-04/07, TC-CAL-08/09, TC-REV-03, TC-EVD-01, TC-CFG-03/04, TC-DOC-06, TC-MAT-01) | 10/10 pass |
| Property tests FI-01..FI-11 on 3,000 random claims | Pass (0 violations) |
| PostgreSQL 16: 31-table DDL applied; trace outputs and two decisions loaded; billed = payable + adjustments reconciled in SQL; every adjustment carries clause authority; 11 constraint negative tests; RLS cross-tenant test | Pass |
| JSON Schemas (11, including the bill-line classifier map), fixtures, configs, OpenAPI `$ref`s (33 paths, 36 operations), request examples, enum parity across DB, API and schemas | 53/53 pass |
| Mutation test of the contract validator (8 deliberately broken inputs) | 8/8 caught |
| Settlement worksheets generated from decisions; disallowances reconcile | Pass |
| Audit hash chains for all traces (including a branched what-if for 2b), events in causal order | Self-consistent (the same script writes and checks the chains; not an independent audit) |
| Cost model | Generated |

None of this measures real-world accuracy. No real claim documents were processed. Proof status per item is in 10 §7.

## Phase 1 workbench build (`workbench/`)

The first build of the product, written against this pack's own contracts. It runs on synthetic data only.

- **What it is.** A Python service: PostgreSQL 16 schema (the pack's DDL, byte-identical) plus app migrations; document ingest to a write-once store; text-layer extraction with schema validation, quote grounding and injection detection; fact resolution with conflicts; the rule engine ported from the harness (`aw-engine-1.0.0`); persisted evaluations with STALE/SUPERSEDED; reviewer actions, overrides, queries, decisions with second approval and the SI ledger; settlement worksheets (JSON and PDF); a hash-chained audit trail; the HTTP API from `api/openapi.yaml`; and a browser reviewer UI (queue, three-pane workspace with page-image evidence highlights, findings, queries, decision, audit).
- **What was run.**
  - 27 automated tests pass. They include an end-to-end run that generates synthetic PDFs, uploads them, extracts, evaluates and decides. It reproduces the pack's traces 1, 2, 2b, 3a and 3b to the paisa.
  - A headless-browser smoke test walks the reviewer path through the UI with no errors: queue → evidence → second approval → audit → blocked claim → queries.
  - Details are in `workbench/README.md` and `workbench/docs/traceability.md`.
- **Substitutions.** These come from the build sandbox (no package index), so the build differs from the ADRs here (ADR-12 in `workbench/docs/`): Starlette instead of FastAPI; a stdlib PostgreSQL client with psycopg as the drop-in; plain JavaScript instead of React; development sign-in instead of OIDC; and a local write-once store instead of S3 Object Lock.
- **Not yet executed.** The psycopg, Bedrock, S3 and OIDC adapters, the CI workflow, and the Docker files are written but have never been run. There is no OCR, so scans cannot be read. The heuristic extractor only reads the synthetic layouts.

## Readiness

| Gate | Status | What's missing |
|---|---|---|
| G1 Technical prototype | **In progress.** The workbench runs end to end on synthetic claims (see above); G1 evidence on real files has not started | Customer wording, tariff and 50 permissioned files (OQ-13, OQ-12, OQ-31); OCR/LLM bake-off (BL-07) and an OCR path (BL-08); legal basis for evaluation data; verbatim re-capture of four regulatory passages now cited as paraphrases (OQ-52) |
| G2 Supervised pilot | Not started | G1; 300-claim golden set; counsel opinions (OQ-24, OQ-27, OQ-45); penetration test; restore drill |
| G3 Production | Not started | G2 plus 3 months of stable pilot metrics |

No certification, regulatory approval, clinical validation or production readiness is claimed.

## Navigation

| File | Contents |
|---|---|
| `01-competitor-evidence.md` | Sourced dossier, metric reconciliation, technology signals, demo questions, coverage matrix, skill mapping |
| `02-PRD.md` | Scope, users, principles, workflows, 23 capabilities with states and acceptance criteria, feature matrix, non-functional requirements |
| `03-workflows-and-UX.md` | Four state machines, reviewer journey, permissions, screens S-01..S-11, wireframes, components, accessibility, design direction |
| `04-architecture.md` | Decisions ADR-01..12, components, sequence, reliability, lineage, observability, DR, failure modes, invalidation tests |
| `05-data-and-API.md` | Entity model, field definitions, money/dates, SI ledger, retention, API summary, payloads, integration patterns, terminology cross-check |
| `06-rule-catalog.md` | Rule sources, representation, order, catalogue (25 rules), money handling, invariants, five worked traces with tables and audit events, regulatory mapping |
| `07-AI-and-document-processing.md` | Task split, OCR, field tiers, grounding, calibration, retrieval boundaries, injection and leakage defences, bake-off plan |
| `08-security-and-operations.md` | Obligations, access, separation, residency, keys, retention, audit, incidents, SDLC, threat model, assurance roadmap |
| `09-materials-and-costs.md` | Materials register (M-01..M-29), data realities, cost formulas and generated tables, setup and growth path |
| `10-validation-plan.md` | Dataset design, 30+ defined metrics, test catalogue with status, edge cases, change gates, readiness gates, proof register |
| `11-build-backlog.md` | First slice, phases, BL-01..BL-40, critical path, staffing, council review, Phase 1 build status, risks |
| `12-open-questions.md` | All open questions with owner, impact, resolution and the gate they block |
| `source-ledger.csv` | 64 evidence records (ID, status, URL, owner, type, dates, passage, limitations, where used) |
| `raw/` | Observation notes with short quotations for the website, archive snapshots and LinkedIn company posts (no viewer or employee data); verbatim regulatory excerpts; certificate screenshots (signatory redacted); `research-state.json` |
| `config/`, `fixtures/`, `schemas/`, `api/`, `db/` | Machine-readable configuration, synthetic claims, schemas, OpenAPI, DDL |
| `verification/` | Reference harness and every check script; generated reports |
| `wireframes/claim-workspace.html` | Clickable wireframe of the claim workspace (synthetic trace 2; PROPOSED) |
| `workbench/` | Phase 1 build: service, migrations, reviewer UI, tests, ADR-12 and backlog traceability (`README.md` explains how to run it) |
| `.github/workflows/workbench-ci.yml` | CI for the pack checks and the workbench (written, not yet run) |

## Methods and tools used

- **Tools.** Built-in browser on your Mac for public pages, the Internet Archive and the Superclaims LinkedIn company page. That browser profile already had a LinkedIn session; only company content was recorded. Also used: web search and fetch, Python, and PostgreSQL 16 in a cloud workspace. The workbench build also used headless Chromium through Playwright, against the local development server only.
- **Not done, per your instructions.** No demo booked, no forms submitted, no accounts created, no charges, no messages sent.
- **Skills.** `HaoNan2k/product-research` v1.1.0 and `rxdaozhang/product-reverse` were cloned and read, not installed. Their methods are applied and mapped in 01 §10. product-reverse's UI step depends on a third skill (`ui-ux-pro-max`); that step was replaced by our own design direction (03 §10).
- **Re-checks on 10 October.** The live Superclaims page, the AWS Bedrock India post, the Anthropic price page and the NHCX blog were re-read to confirm quoted wording. irdai.gov.in and policyholder.gov.in returned HTTP 504 all day, so four regulatory passages remain paraphrases, labelled UNVERIFIED where cited (OQ-52).
- **Expert review.** Council perspectives (11 §5) are simulated review roles, not real participants. They are not independent corroboration.
- **Independent check of the pack.** A separate agent that had not written the pack reviewed it and found 25 defects: unbacked claims, contradictions and gaps an engineer would have to guess at. All were repaired. The fixes are listed in 11 §5, and the new checks above cover them. This is still not a human expert review (BL-38).
