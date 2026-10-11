# 01 — Competitor evidence: Superclaims

Status labels used in this file: **OBSERVED**, **COMPANY-REPORTED**, **INDEPENDENTLY CORROBORATED**, **INFERRED**, **UNKNOWN** (PROPOSED applies only to our own design, from `02` onward). Evidence IDs (E…) resolve in `source-ledger.csv`. Observation notes with short quotations are in `raw/`. Everything here describes Superclaims. Our own design starts in `02-PRD.md`.

## 1. Bottom line

What we can actually see is a marketing website and a LinkedIn page. The adjudication product sits behind a demo booking. No screenshots, documentation, API reference, customer case studies or independent evaluations of the operating product are public. Every statement below about how the product *works* is therefore COMPANY-REPORTED or INFERRED. None of it is OBSERVED behaviour.

Four points are well supported:

1. **Who they sell to and what is in scope.** Superclaims positions itself as a review assistant for insurers and third-party administrators (TPAs), covering IPD and OPD claims (E001, E003, E011).
2. **What the engine claims to do.** The company says it extracts structured claim data, categorises bill lines and applies configured checks: tariff, Schedule of Charges (SOC), policy benefit, non-medical expenses (NME), clinical scrutiny, and fraud, waste and abuse (FWA). It returns deductions, findings and reasoning for a reviewer to validate (E001).
3. **The positioning moved toward human validation.** In January 2026 the site described autonomous agents that "reads, reasons, and decides", a settle step in which "payment triggers fired automatically", and a pre-authorisation agent recommending Approve/Query/Reject (E002). The August 2026 site speaks instead of a "review-ready decision package" for "reviewer validation" (E001), and the founders' September 2026 op-ed headline principle is "Humans remain accountable" (E-LI-04). We read this as a deliberate reframing of the website toward assistive positioning (INFERRED). LinkedIn messaging remains mixed: an August 2026 post still promotes "autonomous claims adjudication" (E-LI-06). The website shift is consistent with Indian rules that keep repudiation with the insurer (E-REG-01, E-REG-04).
4. **The headline metrics are not mutually consistent and none is defined.** See §4.

## 2. Company facts

| Fact | Value | Status | Evidence |
|---|---|---|---|
| Legal entity | Cardit Labs Private Limited, Khajaguda, Hyderabad 500104 | OBSERVED (on the ISO certificate) | E004, E001 |
| Founded | 2024. One source says September 2024; the company celebrated "1 year" on 30 Dec 2025 | COMPANY-REPORTED (minor inconsistency) | E009, E012, E-LI-01, E-LI-19 |
| Founders | Bhavish Ramaswamy (co-founder & CEO), Maneesh Daithala (co-founder & CTO) | COMPANY-REPORTED | E009, E010 |
| Ownership | 100% acquired by ekincare (Hyderabad health-benefits platform), announced 6–7 July 2026. Price undisclosed. Brand operates independently; founders report to ekincare leadership | COMPANY-REPORTED by both parties. Consistent across outlets, but every outlet traces to the same announcement; no registry filing checked | E009–E014, E016, E-LI-13 |
| Size | 11–50 employees on LinkedIn (12 associated members). Seedtable estimates 11. Hiring posts for claims processors, engineers and HR (Oct 2025 – Feb 2026) | COMPANY-REPORTED / INFERRED (third-party estimate) | E-LI-01, E015, E-LI-07, E-LI-08, E-LI-20 |
| Funding | No disclosed rounds | UNKNOWN (absence of evidence) | E015 |
| Revenue | Seedtable's model estimates $2–6M | INFERRED (third-party model estimate); not used anywhere in this pack | E015 |
| Certification | ISO/IEC 27001:2022 by United Registrar of Systems, cert 146637/A/0001/UK/En, valid 14 Apr 2026 – 13 Apr 2029. Scope: "Software Development and Support to Processes Health Insurance Claims End-to-End" | OBSERVED (certificate image). Not checked against the certification body's register | E004, E005 |
| Industry membership | India Insurtech Association (Aug 2026) | COMPANY-REPORTED | E-LI-11 |

## 3. Product as described, and how the description changed

| Aspect | Jan 2026 site (E002) | Jun 2026 site (E003) | Aug 2026 site, live today (E001) | Other sources |
|---|---|---|---|---|
| Framing | Autonomous agents that "reads, reasons, and decides"; a three-step flow promising "zero manual steps" | "Automate the end-to-end claims review process" | "Review-ready decisions", "for reviewer validation" | Op-ed: "Humans remain accountable" (E-LI-04). Aug 2026 post: "autonomous claims adjudication" (E-LI-06). Messaging is mixed |
| Agents | Pre-Authorization; Non-Medico Validation; Medico Review; Audit & Compliance | Non-Medico; Medico; FWA; Audit | "Specialized agents" across four stages, unnamed | "65 AI agents" (E012). "4 AI agents: PreAuth, Non-Medico, Medico, Audit" (E-LI-09) |
| Claim types | Pre-auth explicitly named | "IPD and OPD" | "IPD and OPD" | Cashless discharge emphasised in acquisition PR (E010). OPD engine from ekincare to be merged in (E011) |
| Checks | Non-payables, tariff mismatches, policy violations, medical necessity, admission validity, anomalies | Seven: tariff, SOC, benefit plan, NME, deductions, medical scrutiny, FWA | Same seven, grouped into financial/policy, clinical/expense, fraud/audit | "Duplicate", "ineligible", "inflated" claims (E010) |
| Outputs | "Approve, Query, or Reject" recommendations; "payment triggers fired automatically" | An Audit agent handles the decision and logging (paraphrase) | Deductions, findings, reasoning, calculations, evidence | "Explainable decisions" (E010) |
| Attributes | — | "100+ structured attributes" | "100+ structured attributes" | — |
| Integration | — | API, TMS integration, secure portal | API, TMS integration, secure portal | — |

Things we did not find anywhere: screenshots of the reviewer UI, a list of supported document types or languages, OCR or handwriting behaviour, how policy wordings and tariffs are configured, how reviewers correct outputs, what happens when evidence is missing or conflicting, SLAs, data residency, or named customers. All of these are UNKNOWN.

## 4. Metric reconciliation

Each figure below is COMPANY-REPORTED. None gives a denominator, a measurement period, a definition of the clock, or exclusions.

| Metric | Values found (source, date) | Conflict or missing definition | Status |
|---|---|---|---|
| Processing time | "~10 mins … down from 300+ minutes" (E001 Aug 2026; E003 Jun 2026; E-LI-18 Jun 2026). "5 min TAT", "90min → 5min" (E002 Jan 2026). "Under 5 minutes" vs ~90 min for cashless at discharge (E010, E-LI-13, E-LI-14, Jul 2026). "Approximately 5 minutes" (E-LI-05, Sep 2026). "Several days to minutes" (E012 lede). One adjudicator handles "50+ files. Every single day." (E-LI-15, Sep 2026), which implies under ~10 minutes of manual effort per file over an 8-hour day | At least three baselines (90, 300+, "days") and two results (5, 10). Probably different scopes (cashless discharge approval vs full review effort), but no source says which. The 300-minute baseline is far above typical per-file handling. It may include waiting time, or may be cumulative across reviewers. Unknown | COMPANY-REPORTED, undefined |
| Quality | "99% Accuracy" (E002). ">97% decision precision across evaluated claims" (E001, E003). ">97% accuracy" (E012). "99% accurate" in Oct 2025 job posts (E-LI-07). "99%+ decision accuracy" (E-LI-06, Aug 2026). The same judgment "applied consistently" across 1M+ claims (E-LI-03, Oct 2026) | Accuracy and precision are different measures. Neither the unit (claim, line, deduction rupee) nor the ground truth is stated | COMPANY-REPORTED, undefined |
| Cost | "~70% operational cost reduction in deployed workflows" (E001). "3x cheaper" (E002/E003). "80%+ reduction in manual claims operations" (E-LI-06) | Baseline cost and what is counted are unspecified | COMPANY-REPORTED |
| Speed multiple | Headline "10x Faster & 3x Cheaper" (E002 Jan 2026, E003 Jun 2026). The live page's meta description says "up to 30x faster" (E001, Oct 2026), while its visible tiles say ~10 min from 300+ min | 10x and 30x are both quoted; 300 → 10 minutes is 30x, 90 → 5 minutes is 18x. The multiple depends on which baseline is used | COMPANY-REPORTED, inconsistent |
| Volume | "100K+ claims processed monthly across active deployments" (E001). "Over 1,00,000 claims monthly" (E012). Cumulative 400k (Oct 2025), 420k (Nov 2025), "1M+" (Sep–Oct 2026) (E-LI-10, E-LI-02) | The cumulative figures fit a run-rate that rose to tens of thousands per month in 2026, but 100K/month in Oct 2025 (E-LI-07 job posts) sits poorly with 420k cumulative a month later. "Processed" is undefined (pages? claims touched? fully adjudicated?) | COMPANY-REPORTED, partially inconsistent |
| Customers | "More than 10 insurers and TPAs" (E012) | None named | COMPANY-REPORTED |
| Value | "Nearly 10% claims-value impact" across 1M+ claims (E-LI-02). Illustrative "1% of ₹500 crore = ₹5 crore" (E-LI-17) | "Impact" may mean deductions recommended, which is not the same as leakage prevented. Deductions later reversed are not netted out | COMPANY-REPORTED, undefined |

What this means for us: do not set our own targets to match these numbers. Section 10 defines every metric with a denominator and ground truth. A demo or customer reference should be asked for the definitions (§8).

## 5. Technology signals

| Signal | Evidence | Status | What it does and does not show |
|---|---|---|---|
| Marketing site: static Next.js export on Amazon S3 + CloudFront (Hyderabad POP), no analytics | E008 | OBSERVED | About the marketing site only. Says nothing about the product's hosting |
| Backend engineers hired for "Python, FastAPI, LangChain, LangGraph, and GPT-class models"; "Hands-on with LLMs (Open Source, Gemini, Claude)"; "agentic AI workflows" (Oct 2025) | E-LI-08 | OBSERVED job post. Production stack INFERRED | Suggests a Python orchestration layer with graph-style agent workflows and multiple LLM providers. Alternatives: the stack changed after acquisition, or the post was aspirational. Model choices, OCR, hosting region and prompts are UNKNOWN |
| "Specialized agents … pass structured findings forward" | E001 | COMPANY-REPORTED | Consistent with a staged pipeline (intake → financial → clinical/anomaly → decision). Whether stages are LLM agents, rules or both is UNKNOWN. The "65 agents" figure (E012) could count prompts or rule modules |
| Hiring "Health Claims Processors" to "Review and verify AI-processed claims" (₹1.8–2.5 LPA, pharma/nursing graduates) | E-LI-07 | OBSERVED job post. Implication INFERRED | Superclaims advertised for human verifiers in late 2025. Whether anyone was hired, and for how long, is UNKNOWN. If they were, either (a) Superclaims sells a partly managed service, (b) staff label data or run QA, or (c) staff run pilot operations. This matters for comparability: some of the reported speed or quality may include vendor-side human work. UNKNOWN which |
| Integrations: API, TMS integration, secure portal | E001 | COMPANY-REPORTED | No API documentation, TMS vendor names, or NHCX mention found |

We were not able to collect network traces, frontend fingerprints or API shapes of the product (product-research pillars 3–4) because the product is not reachable without credentials. That gap is recorded in `12-open-questions.md` (OQ-01).

## 6. Commercial model

- **Pricing model:** charged per claim processed (usage-based), per founder statements (E012). COMPANY-REPORTED. Price points are UNKNOWN.
- **Go-to-market:** a 30-minute demo booked via Cal.com with the CEO (E001). Founder-led sales. OBSERVED.
- **Post-acquisition:** cross-sell through ekincare's employer and insurer relationships. Plans to merge ekincare's OPD claims engine and to expand internationally (E010, E011). COMPANY-REPORTED. ekincare's own OPD adjudication ("Claim Mate": 50+ fraud checks, under-48-hour TAT) overlaps with Superclaims' OPD claim (E017).

## 7. Industry context and comparable products

These sources describe common requirements. They are not evidence about Superclaims.

| Product / source | Relevant point | Status | Implication for our requirements |
|---|---|---|---|
| Medi Assist (largest TPA group): MAven IDP turns hospitalisation documents into structured clinical summaries; >50% of cashless pre-auths approved in <5 min; MAven Guard for FWA; IDP sold to outside insurers (E-CMP-01) | TPAs build in-house document AI and sell it | COMPANY-REPORTED | Large TPAs are both potential customers and competitors. Our differentiation cannot rest on document extraction alone |
| Bajaj General "Niriksha": agentic adjudication reading bills and medical documents, validating tariffs, protocols and pharmacy charges, highlighting discrepant lines, guiding adjudicators (E-CMP-02) | Insurers build in-house too | COMPANY-REPORTED | Line-level discrepancy highlighting plus guidance for adjudicators is now the expected shape |
| Policybazaar for Business ClaimSetu: reimbursement document completeness, policy mismatch, routing by complexity (E-CMP-03) | Broker-side intake checks | COMPANY-REPORTED | Completeness checking and routing are table stakes |
| ekincare Claim Mate: OPD adjudication with "deficiency loops" and audit trails (E017) | OPD is a separate, high-volume workflow | COMPANY-REPORTED | Treat OPD as a separate product line (02 §4) |
| Milliman: automation stages, plus a rules library ("ClaimsRef", 7M+ rules mapped to ICD/CPT) (E-CMP-04) | Reference-rule libraries exist commercially | OBSERVED (independent consultancy article; author is also a rules vendor) | Clinical-coding rule content is a licensable material, not something to invent (09) |

## 8. What an authorised demo or customer reference would resolve

To be asked only through a legitimate channel (a real buyer evaluation, or a customer reference that consents). No such session was attempted, per your instructions.

1. Show one claim end to end: which documents were received, what was extracted, which rules fired, how each deduction links to the bill line and the policy clause, and what the reviewer changed.
2. Define ">97% precision" and "~10 minutes": the unit, the ground truth, the sample, the period, and the clock start and stop. State whether vendor-side staff touched the claims.
3. Who configures policy wordings, tariffs/PPN rates and NME lists, and how long one product takes to configure. Show versioning and effective dates.
4. Behaviour on missing, conflicting or unreadable documents. Is a payable ever computed when identity or dates conflict?
5. Does the system ever output "Reject"? Who sees it? How is repudiation routed to the insurer's Claims Review Committee (CRC)?
6. Hosting region, model providers, data retention, subprocessors, and whether customer data trains models.
7. TMS integrations in production (vendor names), API style, webhook and callback behaviour.
8. Cashless pre-auth and discharge handling against the 1-hour and 3-hour clocks: latency distribution and fallback when the AI is down.
9. Pricing per claim and how it varies by workflow (pre-auth vs discharge vs reimbursement vs OPD).

## 9. Coverage matrix

| Area | Evidence found | Status | Remaining question | Significance | Next validation step |
|---|---|---|---|---|---|
| Positioning and buyer | Site versions, PR, LinkedIn (E001–E003, E009–E012) | COMPANY-REPORTED, consistent | Split of insurer vs TPA customers | Medium | Customer reference call |
| Workflow stages | Four stages and seven checks (E001, E003) | COMPANY-REPORTED | How stages map to claim types | High | Authorised demo (§8 Q1) |
| Pre-auth / cashless | Pre-auth agent (E002, E-LI-09); cashless 90→5 min (E010) | COMPANY-REPORTED | Is pre-auth live? Latency under the 1-hour rule? | High | Demo Q8 |
| Reimbursement / OPD | "IPD and OPD" (E001); ekincare OPD engine (E011) | COMPANY-REPORTED | Reimbursement depth; OPD rules | Medium | Demo |
| Extraction and OCR | "100+ attributes" (E001) | COMPANY-REPORTED | Languages, handwriting, accuracy by field | High | Demo plus sample-file test (with permission) |
| Rules and configuration | "Configured checks" (E001) | COMPANY-REPORTED | Rule authoring model, versioning | High | Demo Q3 |
| Clinical review | "Detailed medical scrutiny" (E001) | COMPANY-REPORTED | Scope; clinician involvement; evidence citations | High | Demo plus clinical-advisor review |
| FWA | "FWA detection" (E001); "inflated/duplicate" (E010) | COMPANY-REPORTED | Signals used; false-positive rate | Medium | Demo |
| Reviewer UI | None | UNKNOWN | Everything | High | Demo screenshots (with permission) |
| Integration/API | Three routes named (E001) | COMPANY-REPORTED | API docs, TMS names | Medium | Request API docs under NDA |
| Security/compliance | ISO 27001 certificate (E004); security page (E005) | OBSERVED (certificate) | Hosting, residency, DPDP posture, SOC 2 | High (procurement) | Security questionnaire |
| Metrics | Many, inconsistent (§4) | COMPANY-REPORTED, undefined | Definitions | High | Demo Q2 |
| Customers | ">10 insurers and TPAs" (E012) | COMPANY-REPORTED | Names | Medium | References |
| Pricing | Per-claim usage (E012) | COMPANY-REPORTED | Price points | High (our model) | Buyer interviews |
| Team and stack | Job posts (E-LI-07, E-LI-08) | OBSERVED posts / INFERRED stack | Current stack | Low (we choose independently) | None needed |
| Corporate | Acquisition (E009–E014) | COMPANY-REPORTED | Deal terms | Low | MCA filings, if needed |

## 10. How the skills' research structure maps here

product-research (E-SK-01) asks for eight documents. Here is where each one's content lives in this pack:

- `00-overview` → `00-README.md`
- `01-product-definition` → §2–§3 and §6 above
- `02-usage-flows` → not possible without access (OQ-01). Our proposed flows are in `03-workflows-and-UX.md`
- `03-network` / `04-frontend` → §5 (marketing-site fingerprint only)
- `05-differentiation` → §7 above and `02-PRD.md` §8
- `99-synthesis` → `00-README.md`
- `open-questions` → `12-open-questions.md`
- `raw/` → `raw/`

product-reverse (E-SK-02) outputs map as follows:

- `report.md` → this file
- `design-doc.md` → `02`–`04`, `11`
- `api-surface.md` → `05-data-and-API.md` §2. That section is entirely PROPOSED: no competitor endpoints were observed
- `ui-design-mockup.md` → `03-workflows-and-UX.md`
- `state.json` → `raw/research-state.json`
- `compare-diff.md` → not applicable until an implementation exists
