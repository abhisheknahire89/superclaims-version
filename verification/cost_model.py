"""Transparent cost-per-claim model for 09-materials-and-costs.md.

Every input is labelled SOURCED (with evidence ID) or ASSUMPTION. Change the inputs, re-run, and the
tables in verification/cost-tables.md are regenerated. Usage: python3 verification/cost_model.py
"""
from decimal import Decimal as D, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FX = D("96.35")  # INR per USD — SOURCED E-FX-01: PTI via HDFC Sky, prior close 6 Oct 2026 (point-in-time, not an official reference rate)

INPUTS = {
    # document profile (IPD reimbursement) — ASSUMPTIONS to be replaced by the pilot's measured distribution
    "pages_per_claim": (D("30"), "ASSUMPTION — median IPD file; validate on 200 de-identified files (range 15–80)"),
    "scanned_share": (D("0.70"), "ASSUMPTION — share of pages without a usable text layer"),
    "bill_pages_needing_tables": (D("6"), "ASSUMPTION — itemised bill + pharmacy pages"),
    # vendor list prices
    "ocr_usd_per_page": (D("0.0015"), "SOURCED E-PRC-02/E-PRC-03 — Textract DetectDocumentText first 1M pages (US West list) / Document AI Enterprise OCR $1.50 per 1,000; India-region price to confirm"),
    "table_usd_per_page": (D("0.015"), "SOURCED E-PRC-02 — Textract AnalyzeDocument Tables first 1M pages (US West list)"),
    "small_llm_in_usd_per_mtok": (D("1.00"), "SOURCED E-PRC-01 — Claude Haiku 4.5 list price on the Anthropic page; Bedrock India price to confirm"),
    "small_llm_out_usd_per_mtok": (D("5.00"), "SOURCED E-PRC-01 — Claude Haiku 4.5 list price"),
    "large_llm_in_usd_per_mtok": (D("3.00"), "ASSUMPTION (conservative) — the Anthropic page lists Sonnet 5 at $2/$10 (E-PRC-01), but Bedrock prices independently and no India-profile price was found; the Sonnet 4.5/4.6 list price $3/$15 (E-PRC-01) is used as a buffer"),
    "large_llm_out_usd_per_mtok": (D("15.00"), "ASSUMPTION — as above"),
    "regional_premium": (D("1.10"), "ASSUMPTION based on E-PRC-01 — Anthropic charges a 10% premium for regional over global endpoints; Bedrock and Vertex price independently, so the India-profile premium is unconfirmed"),
    # token budget per claim — ASSUMPTIONS until measured in the prototype
    "small_in_tok": (D("120000"), "ASSUMPTION — classification of 30 pages + structured extraction of ~15 key pages"),
    "small_out_tok": (D("18000"), "ASSUMPTION"),
    "large_in_tok": (D("12000"), "ASSUMPTION — clinical summary with citations over discharge summary + investigations"),
    "large_out_tok": (D("2000"), "ASSUMPTION"),
    "retry_overhead": (D("1.15"), "ASSUMPTION — retries, re-runs after new evidence, eval sampling"),
    # storage
    "mb_per_claim": (D("12"), "ASSUMPTION — originals ~9 MB + derived text/images ~3 MB"),
    "storage_usd_per_gb_month": (D("0.025"), "ASSUMPTION — object storage standard tier in an India region; confirm with provider calculator"),
    "retention_months_hot": (D("12"), "ASSUMPTION — then archive tier at ~20% of the price"),
    "retention_months_archive": (D("108"), "ASSUMPTION — total 10 years pending legal advice on retention (see 08)"),
    # human review (dominant)
    "processor_ctc_inr": (D("250000"), "COMPANY-REPORTED upper bound for a junior 'Health Claims Processor' role at Superclaims, E-LI-07 (₹1.8–2.5 LPA); used only as a market data point"),
    "mo_ctc_inr": (D("800000"), "ASSUMPTION — medical officer (MBBS/BAMS) reviewer; validate with customer HR data"),
    "loading": (D("1.4"), "ASSUMPTION — benefits, seat, supervision, attrition"),
    "productive_min_per_year": (D("80640"), "ASSUMPTION — 240 days x 7 h x 60 min x 0.8 utilisation"),
}

SCENARIOS = {
    # minutes of human time per claim: (processor, medical officer)
    "Manual baseline": {"proc_min": D("28"), "mo_min": D("10"), "note": "ASSUMPTION — needs time-and-motion study; company claims of 90 or 300+ min are not comparable (different definitions)"},
    "Assisted (target)": {"proc_min": D("10"), "mo_min": D("5"), "note": "PROPOSED target, unvalidated"},
    "Assisted (conservative)": {"proc_min": D("16"), "mo_min": D("8"), "note": "PROPOSED downside case"},
}
VOLUMES = {"Pilot": 2000, "Growth": 20000, "Scale": 100000}
FIXED_INFRA_USD = {"Pilot": D("2000"), "Growth": D("5000"), "Scale": D("12000")}  # ASSUMPTION — single-tenant stack incl. HA DB, logging, WAF, backups; confirm with calculator
FIXED_TEAM_INR_PER_YEAR = {"Pilot": D("24000000"), "Growth": D("40000000"), "Scale": D("70000000")}  # ASSUMPTION — engineering, claims SME, support


def v(k):
    return INPUTS[k][0]


def r2(x):
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def variable_tech_cost_inr():
    ocr = v("pages_per_claim") * v("scanned_share") * v("ocr_usd_per_page") + v("bill_pages_needing_tables") * v("table_usd_per_page")
    llm_small = (v("small_in_tok") * v("small_llm_in_usd_per_mtok") + v("small_out_tok") * v("small_llm_out_usd_per_mtok")) / D(1_000_000)
    llm_large = (v("large_in_tok") * v("large_llm_in_usd_per_mtok") + v("large_out_tok") * v("large_llm_out_usd_per_mtok")) / D(1_000_000)
    llm = (llm_small + llm_large) * v("regional_premium") * v("retry_overhead")
    gb = v("mb_per_claim") / D(1024)
    storage = gb * v("storage_usd_per_gb_month") * (v("retention_months_hot") + v("retention_months_archive") * D("0.2"))
    return {"ocr": ocr * FX, "llm": llm * FX, "storage_lifetime": storage * FX}


def per_min(ctc):
    return ctc * v("loading") / v("productive_min_per_year")


lines = ["<!-- Generated by verification/cost_model.py — do not hand-edit -->", "",
         f"Exchange rate: ₹{FX} per US$ (E-FX-01). All figures are estimates unless marked SOURCED.", "",
         "### Inputs", "", "| Input | Value | Basis |", "|---|---:|---|"]
for k, (val, basis) in INPUTS.items():
    lines.append(f"| `{k}` | {val} | {basis} |")

tech = variable_tech_cost_inr()
lines += ["", "Volume-tier assumptions (not single inputs because they change with scale):", "",
          "| Tier | Claims / month | Infra US$/month (ASSUMPTION) | Team ₹/year (ASSUMPTION; grows with tier) |", "|---|---:|---:|---:|"]
for tier, vol in VOLUMES.items():
    lines.append(f"| {tier} | {vol:,} | {FIXED_INFRA_USD[tier]:,} | {FIXED_TEAM_INR_PER_YEAR[tier]:,} |")
lines += ["", "### Variable technology cost per claim (₹)", "", "| Component | Formula | ₹ / claim |", "|---|---|---:|",
          f"| OCR + tables | pages × scanned_share × ocr + bill_pages × table, × FX | {r2(tech['ocr'])} |",
          f"| LLM inference | (small tokens × price + large tokens × price) / 1e6 × regional_premium × retry_overhead × FX | {r2(tech['llm'])} |",
          f"| Storage (lifetime, hot + archive) | MB/1024 × $/GB-month × (hot_months + 0.2 × archive_months) × FX | {r2(tech['storage_lifetime'])} |",
          f"| **Total variable technology** | | **{r2(sum(tech.values()))}** |"]

pm, mm = per_min(v("processor_ctc_inr")), per_min(v("mo_ctc_inr"))
lines += ["", f"Loaded cost per minute: processor ₹{r2(pm)}, medical officer ₹{r2(mm)} (CTC × loading ÷ productive minutes).", "",
          "### Human review cost per claim (₹)", "", "| Scenario | Processor min | MO min | ₹ / claim | Basis |", "|---|---:|---:|---:|---|"]
human = {}
for s, cfg in SCENARIOS.items():
    human[s] = cfg["proc_min"] * pm + cfg["mo_min"] * mm
    lines.append(f"| {s} | {cfg['proc_min']} | {cfg['mo_min']} | {r2(human[s])} | {cfg['note']} |")

lines += ["", "### All-in cost per claim by volume (₹)", "",
          "| Volume tier | Claims / month | Fixed infra ₹/claim | Fixed team ₹/claim | Variable tech ₹/claim | Human (assisted target) ₹/claim | All-in assisted ₹/claim | Manual baseline human ₹/claim |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
for tier, vol in VOLUMES.items():
    infra = FIXED_INFRA_USD[tier] * FX / D(vol)
    team = FIXED_TEAM_INR_PER_YEAR[tier] / D(12) / D(vol)
    var = sum(tech.values())
    allin = infra + team + var + human["Assisted (target)"]
    lines.append(f"| {tier} | {vol:,} | {r2(infra)} | {r2(team)} | {r2(var)} | {r2(human['Assisted (target)'])} | {r2(allin)} | {r2(human['Manual baseline'])} |")

saving = human["Manual baseline"] - human["Assisted (target)"]
saving_c = human["Manual baseline"] - human["Assisted (conservative)"]
lines += ["", "### What the customer's own cost changes by (₹ per claim, human time only)", "",
          f"- Target case saves ₹{r2(saving)} per claim ({r2(saving / human['Manual baseline'] * 100)}% of baseline human cost).",
          f"- Conservative case saves ₹{r2(saving_c)} per claim ({r2(saving_c / human['Manual baseline'] * 100)}%).",
          "- A per-claim price must sit below the customer's saving plus the value of leakage control and TAT compliance, and above our all-in cost. "
          "These numbers bound a pricing hypothesis; they are not a price.", ""]

AVG_CLAIM_INR = D("40000")  # COMPANY-REPORTED average claim value in a Superclaims LinkedIn post (E-LI-12); ASSUMPTION for our planning
lines += ["### Leakage sensitivity (₹ per claim)", "",
          f"Average paid claim assumed ₹{AVG_CLAIM_INR:,} (E-LI-12, company-reported; replace with customer data).", "",
          "| Net leakage reduction (share of paid amount) | Value per claim (₹) | Compared with assisted all-in cost at Scale (₹) |", "|---:|---:|---:|"]
scale_allin = FIXED_INFRA_USD["Scale"] * FX / D(VOLUMES["Scale"]) + FIXED_TEAM_INR_PER_YEAR["Scale"] / D(12) / D(VOLUMES["Scale"]) + sum(tech.values()) + human["Assisted (target)"]
for pct in (D("0.25"), D("0.5"), D("1.0"), D("2.0")):
    val = AVG_CLAIM_INR * pct / 100
    lines.append(f"| {pct}% | {r2(val)} | {r2(scale_allin)} |")
lines += ["", "Leakage reduction must be measured as *correct* deductions the manual process missed, net of wrong deductions later reversed "
          "(see M-FIN-04 in 10-validation-plan.md). Deductions that are reversed on grievance or ombudsman review are cost, not value.", ""]
(ROOT / "verification/cost-tables.md").write_text("\n".join(lines))
print("\n".join(lines))
