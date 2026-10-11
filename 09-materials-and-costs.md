# 09 — Materials, dependencies and economics

Status:

- **Prices** marked SOURCED come from vendor pages read on 9 Oct 2026 (E-PRC-*). Prices change, so re-check before any commitment.
- **Every other number is an ASSUMPTION or PROPOSED estimate.**
- **Exchange rate:** ₹96.35/US$. This is the PTI-reported prior close on 6 Oct 2026 (E-FX-01). It is a point-in-time market rate, not an RBI/FBIL reference rate.
- **Licences:** stated as understood from public project information. Confirm with counsel before commercial use.

## 1. Materials register

Availability classes:

- **PUB**: public
- **CUST**: customer-supplied
- **PERM**: permissioned (needs consent or agreement)
- **LIC**: commercially licensed
- **PROP**: our proprietary work
- **MISS**: currently missing

| ID | Item | Purpose | Candidate / selected | Licence / access | Commercial-use notes | Dependencies | Limitations | Cost basis | Validation required | Class |
|---|---|---|---|---|---|---|---|---|---|---|
| M-01 | Python 3.12, FastAPI, Pydantic | API and workers | Selected (ADR-01) | PSF; MIT | Permissive | — | — | Free | — | PUB |
| M-02 | PostgreSQL 16 (RDS) | System of record + queue | Selected (ADR-02); DDL validated on 16 | PostgreSQL Licence | Permissive | AWS RDS | — | Managed DB, in infra estimate | Load test (BL-31) | PUB |
| M-03 | React, TypeScript, PDF.js | Reviewer UI, evidence viewer | Selected (ADR-09) | MIT; Apache-2.0 | Permissive | — | PDF.js rendering of odd scans | Free | Accessibility audit | PUB |
| M-04 | pdfplumber | Native PDF text + boxes | Selected | MIT | Permissive | — | Text-layer quality varies | Free | Bake-off | PUB |
| M-05 | Amazon Textract | OCR + tables | Candidate (ADR-05) | AWS terms | Customer data processing terms; region | AWS account | Indic scripts and handwriting untested | SOURCED: US$0.0015/page text, US$0.015/page tables (US West list, E-PRC-02) | India-region availability and price (OQ-41); accuracy bake-off | LIC |
| M-06 | Google Document AI | OCR alternative | Candidate | Google Cloud terms | India processing location unconfirmed | GCP | — | SOURCED: US$1.50/1,000 pages OCR (E-PRC-03) | Residency | LIC |
| M-07 | Azure Document Intelligence | OCR alternative | Candidate | Azure terms | — | Azure | Prices not readable on fetch | UNKNOWN (E-PRC-07) | Price quote | LIC |
| M-08 | PaddleOCR / Tesseract | Self-hosted OCR fallback | Candidate | Apache-2.0 | Permissive; model weights' licence to check per model | GPU/CPU hosting | Quality lower on poor scans (to test) | Compute only | Bake-off | PUB |
| M-09 | Claude via Amazon Bedrock, India geo profile | Classification, extraction, cited summaries | Default candidate (ADR-06) | AWS + model terms | AWS states India-profile requests route only between ap-south-1 and ap-south-2, and that Bedrock does not store model inputs or outputs by default; some models need AWS human review of flagged content (E-PRC-05, COMPANY-REPORTED; confirm in contract, OQ-44) | AWS account; model access approval | Models limited to Opus 5, Sonnet 5, Haiku 4.5 in the profile; prices for the profile unconfirmed | Proxy: Anthropic list prices (Haiku 4.5 US$1/US$5; Sonnet 5 US$2/US$10 per M tokens; E-PRC-01). Anthropic adds 10% for regional endpoints; Bedrock prices independently | India-profile price (OQ-42); bake-off | LIC |
| M-10 | Alternative LLMs (Gemini, Azure OpenAI, open weights) | Cost and resilience options | Candidates | Vendor terms / model licences | Gemini paid tier: data not used to improve products (E-PRC-04); India residency unconfirmed | — | — | SOURCED Gemini prices (E-PRC-04) | Residency, quality | LIC/PUB |
| M-11 | AWS ap-south-1 / ap-south-2 | Hosting, DR | Selected (ADR-04) | AWS terms | MeitY empanelment and STQC status to confirm (OQ-40) | — | — | ASSUMPTION: US$2k/month pilot stack | Pricing calculator quote | LIC |
| M-12 | S3 Object Lock, KMS | Immutable evidence, keys | Selected | AWS | — | — | — | Storage ASSUMPTION US$0.025/GB-month | Calculator | LIC |
| M-13 | OpenTelemetry, CloudWatch/Grafana | Observability | Selected | Apache-2.0; vendor | PHI-free telemetry | — | — | In infra estimate | — | PUB/LIC |
| M-14 | Keycloak or customer IdP | Identity | Customer IdP preferred | Apache-2.0 | — | Customer IT | — | Ops effort | IdP integration test | PUB/CUST |
| M-15 | Product name and trademark search | Brand | MISSING | — | Must not collide with existing marks | Counsel | — | Counsel fees | Search before naming | MISS |
| M-16 | Policy wordings, CIS, claims manual, calculation-order conventions | Rule configuration | Customer-supplied | Customer confidential | Use only for that customer | Customer claims team | Wordings differ by product and version | Configuration effort (§4) | Clause-by-clause sign-off by customer SME | CUST (MISS today) |
| M-17 | Hospital tariffs, PPN/GIPSA-type rates, packages | Tariff rules | Customer-supplied | Contractual (hospital agreements) | Confidential; often PDFs or Excel | Customer network team | Effective dates often unclear | Loading effort | Reconcile against sample bills | CUST/PERM (MISS) |
| M-18 | Non-medical item lists | NME rules | Customer list per wording; structure from 2019 IRDAI annexure (E-REG-07) | Public structure; customer content | Current regulatory force unclear (OQ-20) | — | — | — | Customer confirmation | PUB/CUST |
| M-19 | Historical claim files with documents and final decisions | Evaluation (and later calibration) | Permissioned, de-identified sample (10 §1) | Customer data under DPA + consent basis (⚖) | **Historical decisions are not automatically correct labels.** They include errors, inconsistent practice and later reversals | Customer legal and IT | Selection bias; missing documents | Annotation cost (§5) | Independent re-adjudication of a sample | PERM (MISS) |
| M-20 | Clinical reference content (ICD-10 tabular list, LOS norms, standard treatment guidelines, clinical criteria) | Clinical questions (P1/P2) | ICD-10 code lists for validation only; customer LOS norms; licensed criteria later | ICD-10 licence terms to confirm (WHO); commercial criteria products are licensed | Do not invent clinical rules | Clinical advisor | Indian practice variation | Licence fees UNKNOWN | Advisor sign-off | LIC/CUST (MISS) |
| M-21 | Hospital registry IDs (e.g. ROHINI) | Hospital identity matching | Via customer | Permissioned | — | Customer | — | — | — | PERM |
| M-22 | NHCX specifications and sandbox | P2 integration | NHA | Public spec / permissioned sandbox | — | NHA onboarding | Specs change (seven DHIS corrigenda noted in E-REG-11) | Effort | Sandbox test | PUB/PERM |
| M-23 | TMS API specifications | Integration | Customer-supplied | Customer/vendor confidential | — | TMS vendor | Many legacy systems lack APIs | Effort per adapter | Integration test | CUST (MISS) |
| M-24 | Human expertise: claims SME, medical officers/advisor, insurance and data-protection counsel, security auditor | Configuration, labels, clinical boundaries, legal positions | To hire or contract | — | — | — | — | In team and assurance budget (§7) | — | MISS |
| M-25 | Label Studio | Annotation tool | Candidate | Apache-2.0 | Self-host in tenant account | — | — | Free | — | PUB |
| M-26 | Golden evaluation dataset | Release gates | To build (10 §1) | Ours, from customer data | Stays in the customer's account | M-19, M-24 | — | Annotation effort | Inter-annotator agreement | PROP (MISS) |
| M-27 | ClamAV (malware scan) | Upload security | Candidate | GPL-2.0 (run as a separate process) | Licence compatible when not linked; confirm | — | — | Free | — | PUB |
| M-28 | Atkinson Hyperlegible, IBM Plex Mono | UI fonts | Proposed (03 §10) | SIL OFL 1.1 | Embedding permitted under OFL | — | — | Free | Reconfirm licences | PUB |
| M-29 | Synthetic claim generator and fixtures | Tests | Started (`fixtures/`, `verification/`) | Ours | — | — | Synthetic ≠ real-world accuracy | — | — | PROP |

## 2. Data-access realities

- **No public dataset of Indian health-claim documents with adjudication labels was found.** An open-source model or OCR engine brings no claims data. Every accuracy number we will ever quote must come from customer-permissioned data.
- **Historical decisions are noisy labels.** Use them to sample cases and as one reviewer's opinion. Ground truth for the golden set is an independent re-adjudication by two experienced reviewers, with a third resolving disagreements (10 §1).
- **Policy wordings and tariffs are the real bottleneck** (OQ-12, OQ-13). Without them, nothing beyond extraction and illustrative rules can be validated.

## 3. Sourced vs assumed prices

- **Sourced:** Claude, Textract, Document AI and Gemini list prices (E-PRC-01..04); the regional premium note (E-PRC-01); the FX rate (E-FX-01).
- **Assumed:**
  - India-region prices for all of the above;
  - infrastructure, storage and staff costs;
  - pages per claim, tokens per claim, human minutes per claim;
  - average claim value. The ₹40,000 figure is the competitor's own unsourced number (E-LI-12), used only as a placeholder.

## 4. Onboarding and configuration effort (PROPOSED estimates)

| Task | Estimate | Assumption |
|---|---|---|
| Encode one product wording into a policy configuration (room rent, proportionate deduction, co-pay, sub-limits, waiting periods, exclusions list) | 3–5 person-days (SME + engineer) | Wording available as a document; customer SME answers within 2 days |
| Load one hospital tariff with item caps (packages later) | 1–2 days | Spreadsheet available; ≤ 500 items |
| NME list + synonyms per customer | 2 days, then ongoing curation | Start from the four-list structure |
| Golden-claim replay set for the product (30–50 claims) | 5–8 days of annotation | Permissioned files available |
| TMS adapter | 15–30 days | Depends on the TMS API (M-23) |

**Per product, before the TMS adapter:** 6–9 person-days to encode and load the configuration (wording 3–5, tariff 1–2, NME list 2), plus 5–8 days of golden-claim annotation. That is 11–17 person-days, or about 2–3.5 weeks elapsed with SME turnaround. 08 §9 and 11 §5 use the same figure.

## 5. Cost model

Formulas:

- **Variable technology ₹/claim** = [(pages × scanned share × OCR price + bill pages × table price) + (small-model tokens × prices + large-model tokens × prices)/10⁶ × regional premium × retry overhead + MB/1,024 × storage price × (hot months + 0.2 × archive months)] × FX.
- **Human ₹/claim** = processor minutes × (processor CTC × loading ÷ productive minutes) + MO minutes × (MO CTC × loading ÷ productive minutes).
- **All-in ₹/claim** = infrastructure/month ÷ claims/month + team/year ÷ 12 ÷ claims/month + variable technology + human (assisted). Infrastructure and team cost are assumed **per volume tier** (they grow with scale; see the tier table below), so they are fixed only within a tier.

The "all-in" figure deliberately adds the *customer's* reviewer time to *our* costs. It is the total cost of processing a claim with AW, to compare with the customer's manual baseline. The table "What the customer's own cost changes by" isolates the customer's saving from our costs.

### Generated cost tables

_Generated by `verification/cost_model.py`; edit inputs there, not here._

Exchange rate: ₹96.35 per US$ (E-FX-01). All figures are estimates unless marked SOURCED.

#### Inputs

| Input | Value | Basis |
|---|---:|---|
| `pages_per_claim` | 30 | ASSUMPTION — median IPD file; validate on 200 de-identified files (range 15–80) |
| `scanned_share` | 0.70 | ASSUMPTION — share of pages without a usable text layer |
| `bill_pages_needing_tables` | 6 | ASSUMPTION — itemised bill + pharmacy pages |
| `ocr_usd_per_page` | 0.0015 | SOURCED E-PRC-02/E-PRC-03 — Textract DetectDocumentText first 1M pages (US West list) / Document AI Enterprise OCR $1.50 per 1,000; India-region price to confirm |
| `table_usd_per_page` | 0.015 | SOURCED E-PRC-02 — Textract AnalyzeDocument Tables first 1M pages (US West list) |
| `small_llm_in_usd_per_mtok` | 1.00 | SOURCED E-PRC-01 — Claude Haiku 4.5 list price on the Anthropic page; Bedrock India price to confirm |
| `small_llm_out_usd_per_mtok` | 5.00 | SOURCED E-PRC-01 — Claude Haiku 4.5 list price |
| `large_llm_in_usd_per_mtok` | 3.00 | ASSUMPTION (conservative) — the Anthropic page lists Sonnet 5 at $2/$10 (E-PRC-01), but Bedrock prices independently and no India-profile price was found; the Sonnet 4.5/4.6 list price $3/$15 (E-PRC-01) is used as a buffer |
| `large_llm_out_usd_per_mtok` | 15.00 | ASSUMPTION — as above |
| `regional_premium` | 1.10 | ASSUMPTION based on E-PRC-01 — Anthropic charges a 10% premium for regional over global endpoints; Bedrock and Vertex price independently, so the India-profile premium is unconfirmed |
| `small_in_tok` | 120000 | ASSUMPTION — classification of 30 pages + structured extraction of ~15 key pages |
| `small_out_tok` | 18000 | ASSUMPTION |
| `large_in_tok` | 12000 | ASSUMPTION — clinical summary with citations over discharge summary + investigations |
| `large_out_tok` | 2000 | ASSUMPTION |
| `retry_overhead` | 1.15 | ASSUMPTION — retries, re-runs after new evidence, eval sampling |
| `mb_per_claim` | 12 | ASSUMPTION — originals ~9 MB + derived text/images ~3 MB |
| `storage_usd_per_gb_month` | 0.025 | ASSUMPTION — object storage standard tier in an India region; confirm with provider calculator |
| `retention_months_hot` | 12 | ASSUMPTION — then archive tier at ~20% of the price |
| `retention_months_archive` | 108 | ASSUMPTION — total 10 years pending legal advice on retention (see 08) |
| `processor_ctc_inr` | 250000 | COMPANY-REPORTED upper bound for a junior 'Health Claims Processor' role at Superclaims, E-LI-07 (₹1.8–2.5 LPA); used only as a market data point |
| `mo_ctc_inr` | 800000 | ASSUMPTION — medical officer (MBBS/BAMS) reviewer; validate with customer HR data |
| `loading` | 1.4 | ASSUMPTION — benefits, seat, supervision, attrition |
| `productive_min_per_year` | 80640 | ASSUMPTION — 240 days x 7 h x 60 min x 0.8 utilisation |

Volume-tier assumptions (not single inputs because they change with scale):

| Tier | Claims / month | Infra US$/month (ASSUMPTION) | Team ₹/year (ASSUMPTION; grows with tier) |
|---|---:|---:|---:|
| Pilot | 2,000 | 2,000 | 24,000,000 |
| Growth | 20,000 | 5,000 | 40,000,000 |
| Scale | 100,000 | 12,000 | 70,000,000 |

#### Variable technology cost per claim (₹)

| Component | Formula | ₹ / claim |
|---|---|---:|
| OCR + tables | pages × scanned_share × ocr + bill_pages × table, × FX | 11.71 |
| LLM inference | (small tokens × price + large tokens × price) / 1e6 × regional_premium × retry_overhead × FX | 33.64 |
| Storage (lifetime, hot + archive) | MB/1024 × $/GB-month × (hot_months + 0.2 × archive_months) × FX | 0.95 |
| **Total variable technology** | | **46.29** |

Loaded cost per minute: processor ₹4.34, medical officer ₹13.89 (CTC × loading ÷ productive minutes).

#### Human review cost per claim (₹)

| Scenario | Processor min | MO min | ₹ / claim | Basis |
|---|---:|---:|---:|---|
| Manual baseline | 28 | 10 | 260.42 | ASSUMPTION — needs time-and-motion study; company claims of 90 or 300+ min are not comparable (different definitions) |
| Assisted (target) | 10 | 5 | 112.85 | PROPOSED target, unvalidated |
| Assisted (conservative) | 16 | 8 | 180.56 | PROPOSED downside case |

#### All-in cost per claim by volume (₹)

| Volume tier | Claims / month | Fixed infra ₹/claim | Fixed team ₹/claim | Variable tech ₹/claim | Human (assisted target) ₹/claim | All-in assisted ₹/claim | Manual baseline human ₹/claim |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pilot | 2,000 | 96.35 | 1000.00 | 46.29 | 112.85 | 1255.49 | 260.42 |
| Growth | 20,000 | 24.09 | 166.67 | 46.29 | 112.85 | 349.90 | 260.42 |
| Scale | 100,000 | 11.56 | 58.33 | 46.29 | 112.85 | 229.04 | 260.42 |

#### What the customer's own cost changes by (₹ per claim, human time only)

- Target case saves ₹147.57 per claim (56.67% of baseline human cost).
- Conservative case saves ₹79.86 per claim (30.67%).
- A per-claim price must sit below the customer's saving plus the value of leakage control and TAT compliance, and above our all-in cost. These numbers bound a pricing hypothesis; they are not a price.

#### Leakage sensitivity (₹ per claim)

Average paid claim assumed ₹40,000 (E-LI-12, company-reported; replace with customer data).

| Net leakage reduction (share of paid amount) | Value per claim (₹) | Compared with assisted all-in cost at Scale (₹) |
|---:|---:|---:|
| 0.25% | 100.00 | 229.04 |
| 0.5% | 200.00 | 229.04 |
| 1.0% | 400.00 | 229.04 |
| 2.0% | 800.00 | 229.04 |

Leakage reduction must be measured as *correct* deductions the manual process missed, net of wrong deductions later reversed (see M-FIN-04 in 10-validation-plan.md). Deductions that are reversed on grievance or ombudsman review are cost, not value.

## 6. What the numbers say

1. **Technology is cheap; people are not.**
   - Variable technology ≈ ₹46 per IPD claim at the assumed budgets. LLM inference is the largest part (≈ ₹34).
   - Human review is ≈ ₹260 at the assumed manual baseline and ≈ ₹113 in the assisted target. The baseline needs a time-and-motion study (BL-03) before anyone quotes it.
2. **Time saving alone does not carry the business at pilot scale.**
   - At 2,000 claims a month, our team cost (assumed ₹2.4 crore a year at the pilot tier) works out to ~₹1,000 per claim. That is far above the ~₹148 of reviewer time saved per claim in the target case.
   - Even at 100,000 claims a month, the all-in assisted cost (~₹229) is only modestly below the manual human baseline (~₹260).
   - The economic case therefore rests on three things:
     - (a) volume across several customers;
     - (b) leakage control: each 0.5% of net correct additional deductions on a ₹40,000 claim is worth ₹200, but only if those deductions are not reversed later (M-FIN-04);
     - (c) regulatory TAT compliance. Late cashless discharge costs fall on the insurer (E-REG-01 ¶16); late reimbursement accrues interest (E-REG-03).
   - This is consistent with the competitor's emphasis on leakage and speed (E-LI-02, E-LI-17), but their figures are undefined.
3. **Pricing hypothesis to test, not assert.**
   - Per-claim fees in the range ₹60–150 for IPD claims, plus a fixed platform fee per customer during the pilot.
   - Validate with five buyer interviews (BL-02) against their measured baseline and leakage numbers.
   - The competitor's price points are UNKNOWN; it charges per claim (E012).
4. **Sensitivities that move the answer most** (change the inputs in `cost_model.py` and re-run):
   - reviewer minutes saved;
   - LLM token budget (a smaller model or self-hosting could roughly halve the ₹34);
   - pages per claim;
   - team cost per tier (an assumption that grows about 3x from pilot to scale);
   - claim volume.

## 7. Recommended initial setup and growth path

- **Build phase (Phase 1 technical proof, ~14 weeks; 11 §2):**
  - one AWS staging account in ap-south-1;
  - Bedrock India profile and Textract on pay-as-you-go;
  - no commitments, no new SaaS subscriptions;
  - development tooling the team already has. For you, that includes ChatGPT/Codex for coding assistance, which is unrelated to production inference.
  - Expected cloud spend: low hundreds of US$ a month (ASSUMPTION).
- **Pilot:**
  - one dedicated tenant account (≈ US$2k/month assumed);
  - external penetration test;
  - a clinical advisor retainer;
  - insurance and data-protection counsel for OQ-24, OQ-27 and OQ-45.
- **Growth:**
  - committed-use discounts once volume is stable;
  - re-run the OCR and LLM bake-off yearly;
  - consider pooled multi-tenancy (ADR-03) only when serving more than ~10 small customers.
- **Not recommended now:**
  - Temporal or Kafka;
  - fine-tuning;
  - licensed clinical-criteria content (until priority P2);
  - multi-cloud.

**Team budget (ASSUMPTION, used in the model).**

- Roles: two backend/platform engineers, one front-end engineer, one document-AI/ML engineer, a product/claims lead, a QA engineer (0.5), a claims SME (contract) and a medical advisor (retainer).
- Cost: ≈ ₹2.4 crore a year fully loaded at pilot scale.
- Indian salary assumptions are not sourced. Replace them with your own.
- Timeline: 11 §2.
