"""Generate wireframes/claim-workspace.html from trace 2 (synthetic) so the wireframe never drifts from the engine output."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
inp = json.loads((ROOT / "fixtures/claims/trace-2-interacting-adjustments.input.json").read_text())
out = json.loads((ROOT / "fixtures/claims/trace-2-interacting-adjustments.output.json").read_text())
data = {"input": inp, "output": out}

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claim Workspace Wireframe</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#1d2433;--muted:#5b6475;--paper:#fbfaf7;--panel:#ffffff;--rule:#d9d4c7;--evidence:#2f5d8a;--evidence-bg:#e7eff8;--deduct:#9a5b00;--deduct-bg:#fbf1e1;--block:#a3262a;--review:#5b4a9e;--final:#2c6e49;--focus:#1f6feb}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ink:#e8e6e1;--muted:#a7adb9;--paper:#15181f;--panel:#1c2029;--rule:#343a46;--evidence:#8db8e6;--evidence-bg:#1f2c3b;--deduct:#e3a54a;--deduct-bg:#2e2516;--block:#ef7a7d;--review:#b3a6ee;--final:#7fcf9f;--focus:#79b8ff}}
:root[data-theme="dark"]{--ink:#e8e6e1;--muted:#a7adb9;--paper:#15181f;--panel:#1c2029;--rule:#343a46;--evidence:#8db8e6;--evidence-bg:#1f2c3b;--deduct:#e3a54a;--deduct-bg:#2e2516;--block:#ef7a7d;--review:#b3a6ee;--final:#7fcf9f;--focus:#79b8ff}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 "Atkinson Hyperlegible",system-ui,sans-serif}
.mono,.amt{font-family:"IBM Plex Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.banner{background:var(--deduct-bg);color:var(--deduct);padding:6px 16px;font-size:12px;border-bottom:1px solid var(--rule)}
header{padding:12px 16px;border-bottom:1px solid var(--rule);background:var(--panel)}
header h1{font-size:16px;margin:0 0 4px}
header .meta{color:var(--muted);font-size:13px}
.rec{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:8px}
.proposed{border:1.5px dashed var(--ink);padding:4px 10px;border-radius:6px}
.btn{font:inherit;border:1px solid var(--rule);background:var(--panel);color:var(--ink);padding:5px 10px;border-radius:6px;cursor:pointer}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn:focus-visible,button:focus-visible,[tabindex]:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
main{display:grid;grid-template-columns:220px minmax(0,1fr) 380px;min-height:calc(100vh - 140px)}
@media (max-width:1100px){main{grid-template-columns:1fr}aside.docs{order:3}}
aside.docs,section.centre,aside.evidence{padding:12px 16px;border-right:1px solid var(--rule);min-width:0}
aside.evidence{border-right:0;background:var(--panel)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:4px 0 8px}
ul.doclist{list-style:none;padding:0;margin:0}
ul.doclist li{padding:4px 0;border-bottom:1px dotted var(--rule);font-size:13px}
.warn{color:var(--deduct)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--rule);margin-bottom:8px}
.tabs button{border:0;background:none;padding:6px 10px;font:inherit;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent}
.tabs button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--ink);font-weight:700}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{padding:6px 6px;border-bottom:1px solid var(--rule);vertical-align:top;text-align:left}
th{font-size:12px;color:var(--muted);font-weight:700}
td.amt,th.amt{text-align:right;white-space:nowrap}
tr.line:hover{background:var(--evidence-bg)}
tr.line.active{outline:2px solid var(--evidence);outline-offset:-2px}
.chip{display:inline-flex;gap:6px;align-items:center;margin:3px 0;padding:2px 8px;border-radius:999px;background:var(--deduct-bg);color:var(--deduct);font-size:12px;border:1px solid transparent;cursor:pointer}
.chip .minus{font-weight:700}
.evchip{color:var(--evidence);text-decoration:underline;cursor:pointer;background:none;border:0;font:inherit;font-size:12px;padding:0}
.ladder{margin-top:12px;border:1px solid var(--rule);border-radius:8px;padding:8px 12px;background:var(--panel);max-width:520px}
.ladder div{display:flex;justify-content:space-between;padding:3px 0}
.ladder .total{border-top:1px solid var(--ink);font-weight:700}
.page{border:1px solid var(--rule);background:#fff;color:#222;padding:14px;min-height:320px;font-family:"IBM Plex Mono",monospace;font-size:11.5px;position:relative}
.page .row{display:flex;justify-content:space-between;padding:2px 4px}
.page .row.hl{background:#fff2a8;outline:2px solid #2f5d8a}
.page .hdr{font-weight:700;margin-bottom:6px}
.ruleinfo{margin-top:10px;font-size:13px}
.ruleinfo dt{color:var(--muted);font-size:12px}
.ruleinfo dd{margin:0 0 6px}
.sr{position:absolute;left:-9999px}
kbd{font-family:"IBM Plex Mono",monospace;border:1px solid var(--rule);border-bottom-width:2px;border-radius:4px;padding:0 4px;font-size:11px}
.help{font-size:12px;color:var(--muted);margin-top:12px}
.finding{border-left:4px solid var(--review);padding:6px 10px;background:var(--panel);margin-bottom:8px}
.audit li{font-size:12px;margin-bottom:3px}
</style>
</head>
<body>
<div class="banner" role="note">PROPOSED wireframe — synthetic data from trace 2 (CLM-DEMO-0002). Not a real product, patient, hospital or policy. Static; nothing is saved.</div>
<header>
  <h1 id="title"></h1>
  <div class="meta" id="meta"></div>
  <div class="rec">
    <span class="proposed" id="proposed"></span>
    <button class="btn" id="whyBtn" aria-expanded="false" aria-controls="why">Why?</button>
    <button class="btn" disabled title="Wireframe">Query ▸</button>
    <button class="btn" disabled title="Wireframe">Decide ▸</button>
  </div>
  <div id="why" hidden class="help"></div>
</header>
<main>
  <aside class="docs" aria-label="Documents">
    <h2>Documents</h2>
    <ul class="doclist" id="docs"></ul>
    <p class="help" id="checklist"></p>
  </aside>
  <section class="centre" aria-label="Review">
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected="true" aria-controls="tab-bill" id="t-bill">Bill &amp; deductions</button>
      <button role="tab" aria-selected="false" aria-controls="tab-find" id="t-find">Findings (0)</button>
      <button role="tab" aria-selected="false" aria-controls="tab-rules" id="t-rules">Rule trace</button>
    </div>
    <div id="tab-bill" role="tabpanel" aria-labelledby="t-bill">
      <label><input type="checkbox" id="onlyDed" checked> Only lines with deductions</label>
      <div class="tablewrap"><table aria-describedby="title">
        <thead><tr><th>Line</th><th>Description</th><th>Category</th><th class="amt">Billed (₹)</th><th>Deductions</th><th class="amt">Payable (₹)</th></tr></thead>
        <tbody id="lines"></tbody>
      </table></div>
      <div class="ladder" id="ladder" aria-label="Claim ladder"></div>
    </div>
    <div id="tab-find" role="tabpanel" aria-labelledby="t-find" hidden>
      <p>No open findings on this claim. Blocking findings, clinical questions and patterns for review appear here (see trace 3a in 06-rule-catalog.md).</p>
    </div>
    <div id="tab-rules" role="tabpanel" aria-labelledby="t-rules" hidden>
      <div class="tablewrap"><table><thead><tr><th>#</th><th>Rule</th><th>Version</th><th>Status</th></tr></thead><tbody id="rules"></tbody></table></div>
    </div>
    <p class="help"><kbd>J</kbd>/<kbd>K</kbd> move between lines · <kbd>E</kbd> open evidence · <kbd>1</kbd>/<kbd>2</kbd>/<kbd>3</kbd> switch tabs</p>
  </section>
  <aside class="evidence" aria-label="Evidence">
    <h2>Evidence</h2>
    <div id="evhead" class="mono" style="font-size:12px;margin-bottom:6px">Select a deduction or line</div>
    <div class="page" id="page" aria-hidden="true"></div>
    <dl class="ruleinfo" id="ruleinfo"></dl>
    <div class="sr" aria-live="polite" id="announce"></div>
  </aside>
</main>
<script>
const DATA = __DATA__;
const inp = DATA.input, out = DATA.output;
const fmt = s => { if (s === null || s === undefined) return "—"; const n = Number(s); const neg = n < 0; let [i, d] = Math.abs(n).toFixed(2).split(".");
  let last3 = i.slice(-3), rest = i.slice(0, -3); if (rest) last3 = "," + last3; rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ","); return (neg ? "−" : "") + rest + last3 + "." + d; };
const byLine = {}; out.adjustments.forEach(a => { if (a.line_id) (byLine[a.line_id] = byLine[a.line_id] || []).push(a); });
const rec = out.recommendation;
document.getElementById("title").textContent = `${inp.claim_id} · IPD reimbursement · ${inp.member.name_normalised.replace(/\b(\w)(\w*)/g,(m,a,b)=>a+b.toLowerCase())} (${inp.member.gender}) · Policy ${inp.policy.policy_no}`;
document.getElementById("meta").textContent = `Admitted 01 Jul 2026 → discharged 05 Jul 2026 · ${inp.hospital_id} (network) · SI available ₹85,000.00 · Settle by 24 Jul 2026`;
document.getElementById("proposed").textContent = `Proposed: ${rec.type.replace("_"," ")} ₹${fmt(rec.recommended_payable)} of ₹${fmt(rec.billed_total)} billed`;
document.getElementById("why").textContent = `Line deductions ₹${fmt(rec.line_level_deductions)} (duplicate, non-payables, tariff caps, room/ICU caps, proportionate deduction); claim-level ₹${fmt(rec.claim_level_deductions)} (co-pay 10% at age 63; sum-insured cap). A human decision is required.`;
document.getElementById("whyBtn").onclick = e => { const w = document.getElementById("why"); w.hidden = !w.hidden; e.target.setAttribute("aria-expanded", String(!w.hidden)); };
document.getElementById("docs").innerHTML = inp.documents_present.map(d => `<li>${d.document_id.endsWith("COPY") ? '<span class="warn" aria-label="possible duplicate">⚠</span>' : "✓"} <span class="mono">${d.document_id}</span> <span class="help">${d.type.replace(/_/g," ").toLowerCase()}</span></li>`).join("");
const dc = out.rule_executions.find(r => r.rule_id === "R-DOC-COMPLETENESS").detail;
const applicable = dc.required.length + 1; // + itemised bill, enforced by R-GATE-ITEMISATION
document.getElementById("checklist").textContent = `Checklist ${applicable - dc.missing.length}/${applicable} applicable items present (itemised bill checked by its gate; implant invoice not applicable)`;
const tbody = document.getElementById("lines");
function render() {
  const only = document.getElementById("onlyDed").checked;
  tbody.innerHTML = "";
  out.lines.forEach(l => {
    const adjs = byLine[l.line_id] || []; if (only && !adjs.length) return;
    const tr = document.createElement("tr"); tr.className = "line"; tr.tabIndex = 0; tr.dataset.line = l.line_id;
    tr.innerHTML = `<td class="mono">${l.line_id}</td><td>${l.description}${l.ward_context === "ICU" ? ' <small>(ICU)</small>' : ''}</td><td><small>${l.category}</small></td>
      <td class="amt">${fmt(l.billed)}</td><td>${adjs.map(a => `<button class="chip" data-adj="${a.adjustment_id}" aria-label="${a.reason_code} minus ${fmt(a.amount)} rupees, rule ${a.rule_id}"><span class="minus">−</span><span class="amt">${fmt(a.amount)}</span> ${a.reason_code.replace(/_/g," ").toLowerCase()}</button>`).join("<br>") || '<small style="color:var(--muted)">none</small>'}</td>
      <td class="amt">${fmt(l.payable)}</td>`;
    tr.addEventListener("click", ev => { const c = ev.target.closest(".chip"); showEvidence(l.line_id, c ? c.dataset.adj : (adjs[0] || {}).adjustment_id); });
    tbody.appendChild(tr);
  });
}
function showEvidence(lineId, adjId) {
  document.querySelectorAll("tr.line").forEach(r => r.classList.toggle("active", r.dataset.line === lineId));
  const line = inp.bill_lines.find(l => l.line_id === lineId); const ev = line.evidence[0];
  const a = out.adjustments.find(x => x.adjustment_id === adjId);
  document.getElementById("evhead").textContent = `${ev.document_id} · page ${ev.page} · bbox [${ev.bbox.join(", ")}]`;
  const same = inp.bill_lines.filter(l => l.evidence[0].document_id === ev.document_id && l.evidence[0].page === ev.page);
  document.getElementById("page").innerHTML = `<div class="hdr">${ev.document_id.includes("PH") ? "PHARMACY INVOICE" : "DETAILED BILL"} — synthetic page ${ev.page}</div>` +
    same.map(l => `<div class="row${l.line_id === lineId ? " hl" : ""}"><span>${l.description}${l.quantity ? " ×" + l.quantity : ""}</span><span>${fmt(l.billed)}</span></div>`).join("");
  document.getElementById("ruleinfo").innerHTML = a ? `<dt>Rule</dt><dd class="mono">${a.rule_id} ${a.rule_version}</dd><dt>Formula</dt><dd class="mono">${a.formula}</dd><dt>Explanation</dt><dd>${a.explanation}</dd><dt>Configuration</dt><dd class="mono">${out.config_versions.policy_config}<br>${out.config_versions.tariff}</dd>` : "<dd>No deduction on this line.</dd>";
  document.getElementById("announce").textContent = `Highlighted on ${ev.document_id} page ${ev.page}: ${line.description}, ${fmt(line.billed)} rupees.`;
}
document.getElementById("onlyDed").onchange = render; render();
const ladder = [["Billed", rec.billed_total], ["− Line deductions", rec.line_level_deductions], ["= Admissible", rec.admissible_after_line_rules]];
out.adjustments.filter(a => a.level === "CLAIM").forEach(a => ladder.push([`− ${a.reason_code.replace(/_/g," ").toLowerCase()}`, a.amount]));
ladder.push(["= Proposed payable", rec.recommended_payable]);
document.getElementById("ladder").innerHTML = ladder.map((r, i) => `<div class="${i === ladder.length - 1 ? "total" : ""}"><span>${r[0]}</span><span class="amt">${fmt(r[1])}</span></div>`).join("");
document.getElementById("rules").innerHTML = out.rule_executions.map((e, i) => `<tr><td>${i + 1}</td><td class="mono">${e.rule_id}</td><td class="mono">${e.rule_version}</td><td>${e.status}</td></tr>`).join("");
const tabs = [["t-bill","tab-bill"],["t-find","tab-find"],["t-rules","tab-rules"]];
function selectTab(i){ tabs.forEach(([t,p],j)=>{ document.getElementById(t).setAttribute("aria-selected", String(i===j)); document.getElementById(p).hidden = i!==j; }); }
tabs.forEach(([t],i)=> document.getElementById(t).onclick = () => selectTab(i));
document.addEventListener("keydown", e => {
  if (["INPUT","TEXTAREA"].includes(document.activeElement.tagName)) return;
  const rows = [...document.querySelectorAll("tr.line")]; let idx = rows.findIndex(r => r.classList.contains("active"));
  if (e.key === "j" || e.key === "k") { idx = Math.max(0, Math.min(rows.length - 1, idx + (e.key === "j" ? 1 : -1))); rows[idx].focus(); rows[idx].click(); }
  if (e.key === "e" && idx >= 0) { rows[idx].click(); document.getElementById("evhead").scrollIntoView({block:"nearest"}); }
  if (["1","2","3"].includes(e.key)) selectTab(Number(e.key) - 1);
});
</script>
</body>
</html>
"""
(ROOT / "wireframes").mkdir(exist_ok=True)
(ROOT / "wireframes/claim-workspace.html").write_text(HTML.replace("__DATA__", json.dumps(data)))
print("wrote wireframes/claim-workspace.html")
