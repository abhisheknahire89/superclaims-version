// Adjudication Workbench reviewer UI (Phase 1). Vanilla ES module, no build step, no third-party code.
// Every string that comes from a document or the API is inserted with textContent, never innerHTML.

const S = { token: null, me: null, claim: null, etag: null, ev: null, lines: [], findings: [], facts: null, docs: [],
            selected: null, tab: "bill", users: [], pollTimer: null };

// ---------------------------------------------------------------- helpers
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const $ = (sel) => document.querySelector(sel);
const say = (msg) => { $("#live").textContent = msg; };
function inr(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v); const neg = n < 0;
  let [i, d] = Math.abs(n).toFixed(2).split(".");
  let last3 = i.slice(-3), rest = i.slice(0, -3);
  if (rest) last3 = "," + last3;
  rest = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return (neg ? "−" : "") + rest + last3 + "." + d;
}
const rs = (v) => (v === null || v === undefined) ? "—" : "₹" + inr(v);
function when(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" }) + " IST";
}
function dateOnly(iso) {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}
function relDue(iso) {
  if (!iso) return "—";
  const ms = new Date(iso) - Date.now(); const neg = ms < 0; const m = Math.abs(ms) / 60000;
  const d = Math.floor(m / 1440), hr = Math.floor((m % 1440) / 60);
  const txt = d ? `${d}d ${hr}h` : `${hr}h ${Math.floor(m % 60)}m`;
  return neg ? `overdue ${txt}` : `in ${txt}`;
}
const ACRONYMS = new Set(["ipd", "opd", "icu", "nme", "ot", "crc", "fwa", "si", "tpa", "ped", "id", "los", "tms", "gst"]);
const human = (s) => (s || "").toLowerCase().replace(/_/g, " ").split(" ").map((w) => (ACRONYMS.has(w) ? w.toUpperCase() : w)).join(" ")
  .replace(/^\w/, (c) => c.toUpperCase());
function store(k, v) { try { v === null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) { /* storage unavailable */ } }
function load(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } }

async function api(method, path, { body, idem = false, ifMatch = false, raw = false } = {}) {
  const headers = { Authorization: `Bearer ${S.token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (idem) headers["Idempotency-Key"] = crypto.randomUUID();
  if (ifMatch && S.etag) headers["If-Match"] = S.etag;
  const r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (raw) return r;
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (r.status === 401) { logout(); throw new Error("signed out"); }
  return { status: r.status, ok: r.ok, data, etag: r.headers.get("ETag") };
}
function problemText(res) {
  const d = res.data || {};
  let t = d.detail || d.title || `HTTP ${res.status}`;
  if (d.triggers) t += ` (${d.triggers.map(human).join(", ")})`;
  if (d.errors) t += ": " + d.errors.map((e) => `${e.pointer} ${e.message}`).join("; ");
  return t;
}

// ---------------------------------------------------------------- auth (development sign-in)
async function showLogin() {
  const app = $("#app"); app.replaceChildren();
  const r = await fetch("/dev/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const box = h("section", { class: "login", "aria-labelledby": "lt" },
    h("h1", { id: "lt" }, "Sign in (development)"),
    h("p", { class: "cat" }, "Development sign-in for the synthetic demo tenant. Production uses your organisation's single sign-on; roles and approval limits always come from the server."));
  if (!r.ok) { box.append(h("p", { class: "err" }, "Development sign-in is disabled in this environment.")); app.replaceChildren(box); return; }
  const { users } = await r.json();
  S.users = users;
  const ul = h("ul");
  for (const u of users) {
    ul.append(h("li", {}, h("button", { class: "btn", onclick: () => login(u.user_id) },
      h("span", {}, h("strong", {}, u.user_id), " · ", u.display_name), h("span", { class: "cat" }, u.roles.join(", ")))));
  }
  box.append(ul); app.replaceChildren(box);
}
async function login(userId) {
  const r = await fetch("/dev/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId }) });
  const d = await r.json();
  S.token = d.token; store("aw.token", d.token);
  location.hash = "#/queue"; await boot();
}
function logout() {
  S.token = null; store("aw.token", null); S.me = null; $("#who").replaceChildren();
  if (location.hash.startsWith("#/login")) route(); else location.hash = "#/login";  // hashchange calls route()
}

async function boot() {
  S.token = S.token || load("aw.token");
  if (!S.token) { location.hash = "#/login"; return route(); }
  const me = await api("GET", "/v1/me");
  if (!me.ok) return logout();
  S.me = me.data;
  if (!S.users.length) { try { const r = await fetch("/dev/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); if (r.ok) S.users = (await r.json()).users; } catch (e) { /* ignore */ } }
  $("#who").replaceChildren(h("span", {}, `${S.me.display_name} · ${S.me.roles.map(human).join(", ")}`),
    S.me.approval_limit ? h("span", { class: "chip" }, `limit ${rs(S.me.approval_limit)}`) : null,
    h("button", { class: "btn small", onclick: logout }, "Sign out"));
  route();
}
const can = (...roles) => S.me && S.me.roles.some((r) => roles.includes(r));

// ---------------------------------------------------------------- router
window.addEventListener("hashchange", route);
function route() {
  clearInterval(S.pollTimer);
  const hsh = location.hash || "#/queue";
  $("#nav-queue").toggleAttribute("aria-current", hsh.startsWith("#/queue"));
  if (hsh.startsWith("#/login") || !S.token) return showLogin();
  if (hsh.startsWith("#/claim/")) return showClaim(decodeURIComponent(hsh.slice(8)));
  return showQueue();
}

// ---------------------------------------------------------------- S-01 queue
async function showQueue() {
  const app = $("#app"); app.replaceChildren(h("div", { class: "wrap" }, h("p", { class: "empty" }, "Loading…")));
  const status = new URLSearchParams(location.hash.split("?")[1] || "").get("status") || "";
  const res = await api("GET", "/v1/claims" + (status ? `?status=${status}` : ""));
  const wrap = h("div", { class: "wrap" }, h("h1", {}, "Work queue"));
  const sel = h("select", { id: "f-status", onchange: (e) => { location.hash = "#/queue" + (e.target.value ? `?status=${e.target.value}` : ""); } },
    h("option", { value: "" }, "Open claims"),
    ...["READY_FOR_REVIEW", "IN_REVIEW", "MEDICAL_REVIEW", "AWAITING_RESPONSE", "PENDING_APPROVAL", "ESCALATED_CRC", "FINALISED", "EXPORTED"]
      .map((s) => h("option", { value: s, selected: s === status }, human(s))));
  wrap.append(h("div", { class: "filters" }, h("div", {}, h("label", { for: "f-status" }, "Status"), sel),
    h("span", { class: "cat" }, "Sorted by settlement due time, earliest first. Press N to open the first claim.")));
  if (!res.ok) { wrap.append(h("p", { class: "err" }, problemText(res))); app.replaceChildren(wrap); return; }
  const items = res.data.items;
  if (!items.length) { wrap.append(h("p", { class: "empty" }, "No claims in this view.")); app.replaceChildren(wrap); return; }
  const tbody = h("tbody");
  for (const c of items) {
    const open = () => { location.hash = `#/claim/${encodeURIComponent(c.claim_id)}`; };
    tbody.append(h("tr", { class: "qrow", onclick: open },
      h("td", {}, h("a", { href: `#/claim/${encodeURIComponent(c.claim_id)}`, class: "mono" }, c.claim_id), h("div", { class: "cat" }, c.external_ref)),
      h("td", {}, c.patient_display), h("td", {}, c.hospital_name || "—"),
      h("td", {}, c.recommendation ? h("span", { class: "chip rec" }, human(c.recommendation)) : h("span", { class: "cat" }, "processing")),
      h("td", { class: "amt" }, rs(c.recommended_payable)),
      h("td", {}, c.open_blocking_findings ? h("span", { class: "chip block" }, `■ ${c.open_blocking_findings}`) : "—"),
      h("td", {}, human(c.status)),
      h("td", { title: when(c.sla_due_at) }, relDue(c.sla_due_at))));
  }
  wrap.append(h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {},
    ...["Claim", "Patient", "Hospital", "Recommendation"].map((t) => h("th", {}, t)), h("th", { class: "amt" }, "Proposed payable"),
    h("th", {}, "Blocks"), h("th", {}, "Status"), h("th", {}, "Due"))), tbody)));
  app.replaceChildren(wrap);
  S.queueFirst = items[0].claim_id;
}

// ---------------------------------------------------------------- S-02 workspace
async function loadClaim(id) {
  const c = await api("GET", `/v1/claims/${encodeURIComponent(id)}`);
  if (!c.ok) throw new Error(problemText(c));
  S.claim = c.data; S.etag = c.etag;
  const [ev, docs, lines, findings, facts] = await Promise.all([
    api("GET", `/v1/claims/${encodeURIComponent(id)}/evaluations/current`),
    api("GET", `/v1/claims/${encodeURIComponent(id)}/documents`),
    api("GET", `/v1/claims/${encodeURIComponent(id)}/bill-lines`),
    api("GET", `/v1/claims/${encodeURIComponent(id)}/findings`),
    api("GET", `/v1/claims/${encodeURIComponent(id)}/facts`)]);
  S.ev = ev.ok ? ev.data : null; S.docs = docs.ok ? docs.data.items : []; S.lines = lines.ok ? lines.data.items : [];
  S.findings = findings.ok ? findings.data.items : []; S.facts = facts.ok ? facts.data : null;
}

async function showClaim(id) {
  if (!S.claim || S.claim.claim_id !== id) { S.selected = null; S.tab = "bill"; }  // never carry evidence across claims
  $("#app").replaceChildren(h("div", { class: "wrap" }, h("p", { class: "empty" }, "Loading claim…")));
  try { await loadClaim(id); } catch (e) { $("#app").replaceChildren(h("div", { class: "wrap" }, h("p", { class: "err" }, e.message))); return; }
  renderClaim();
  const st = S.claim.evaluation_status;
  if (!S.ev || st === "STALE" || ["PROCESSING", "INTAKE"].includes(S.claim.status)) poll(id);
}
function poll(id) {
  clearInterval(S.pollTimer);
  let n = 0;
  S.pollTimer = setInterval(async () => {
    n += 1;
    const c = await api("GET", `/v1/claims/${encodeURIComponent(id)}`);
    if (c.ok && c.data.evaluation_status && c.data.evaluation_status !== "STALE" && !["PROCESSING", "INTAKE"].includes(c.data.status)
        && c.data.current_evaluation_id !== (S.ev && S.ev.evaluation_id)) {
      clearInterval(S.pollTimer); await loadClaim(id); renderClaim(); say("Recommendation updated.");
    } else if (n > 40) clearInterval(S.pollTimer);
  }, 1500);
}

function renderClaim() {
  const c = S.claim, ev = S.ev, rec = ev && ev.recommendation;
  const head = h("section", { class: "ws-head", "aria-labelledby": "ch" },
    h("h1", { id: "ch" }, h("span", { class: "mono" }, c.claim_id), ` · ${human(c.workflow)} · ${c.patient.name} (${c.patient.gender || "?"}) · Policy `, h("span", { class: "mono" }, c.policy_no)),
    h("div", { class: "meta" }, `${c.hospital_name || "—"}${c.hospital_is_network ? " (network)" : ""} · Admitted ${dateOnly(c.admission_date)} → discharged ${dateOnly(c.discharge_date)} · Sum insured ${rs(c.sum_insured.base)}`
      + (Number(c.sum_insured.cumulative_bonus) ? ` + bonus ${rs(c.sum_insured.cumulative_bonus)}` : "") + ` · Settle by ${when(c.tat.due_at)} (${relDue(c.tat.due_at)})`),
    h("div", { class: "rec" },
      rec ? h("span", { class: "proposed" }, `Proposed: ${human(rec.type)} `, h("strong", {}, rec.computed ? rs(rec.recommended_payable) : "no payable computed"), Number(rec.billed_total) > 0 ? ` of ${rs(rec.billed_total)} billed` : "") : h("span", { class: "cat" }, "No recommendation yet"),
      h("span", { class: "chip" }, human(c.status)),
      c.investigation_hold ? h("span", { class: "chip block" }, "Investigation hold") : null,
      h("button", { class: "btn", onclick: () => setTab("decide") }, "Decide ▸"),
      h("button", { class: "btn", onclick: () => setTab("queries") }, "Query ▸")));
  const banners = [];
  if (c.evaluation_status === "STALE") banners.push(h("div", { class: "banner stale", role: "status" }, "Recommendation out of date — new evidence or a correction is being processed. Decisions are disabled until it is recomputed."));
  if (rec && rec.blocked_scopes.length) banners.push(h("div", { class: "banner block" }, `Blocked: ${rec.blocked_scopes.map(human).join(", ")}. Resolve the blocking findings to compute the payable.`));
  for (const d of c.decisions) banners.push(h("div", { class: "banner final" }, h("span", { class: "chip final" }, `🔒 ${human(d.disposition)} ${d.approved_payable ? rs(d.approved_payable) : ""}`),
    ` by ${d.decided_by}${d.second_approver ? `, approved by ${d.second_approver}` : ""} · ${when(d.decided_at)} · `,
    h("button", { class: "btn small", onclick: () => openWorksheet(d.decision_id, "pdf") }, "Worksheet PDF"), " ",
    h("button", { class: "btn small", onclick: () => openWorksheet(d.decision_id, "json") }, "JSON")));
  const grid = h("div", { class: "grid" }, leftPane(), centrePane(), h("aside", { class: "pane evidence", id: "evidence", "aria-label": "Evidence" }, evidencePane()));
  $("#app").replaceChildren(head, ...banners, grid);
}

// ---------------------------------------------------------------- left: documents and facts
function leftPane() {
  const docs = h("ul", { class: "plain docs" });
  for (const d of S.docs) {
    const warn = ["NEEDS_REVIEW", "FAILED_TECHNICAL", "FAILED_UNREADABLE", "SUPERSEDED"].includes(d.status);
    docs.append(h("li", {}, h("span", { "aria-hidden": "true" }, warn ? "⚠ " : "✓ "), human(d.classified_type || d.declared_type || "document"),
      h("div", { class: "st" }, `${d.page_count || "?"} p · ${human(d.status)}`)));
  }
  const pane = h("aside", { class: "pane", "aria-label": "Documents and facts" }, h("h2", {}, "Documents"), docs);
  if (can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR")) pane.append(uploadForm());
  pane.append(h("h2", { style: "margin-top:16px" }, "Facts used by the rules"));
  if (S.facts) {
    for (const f of S.facts.items) {
      const conflict = f.basis === "UNRESOLVED";
      const row = h("div", { class: "fact" + (conflict ? " conflict" : "") },
        h("div", {}, h("strong", {}, human(f.field_path.replace(".", " "))), ": ", conflict ? h("span", { class: "chip block" }, "conflict") : h("span", { class: "mono" }, String(f.value))),
        h("div", { class: "basis" }, `${human(f.basis)}${f.observations.length ? ` · ${f.observations.length} source(s)` : ""}`));
      if (conflict && can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR")) row.append(resolveForm(f));
      pane.append(row);
    }
  }
  return pane;
}
function resolveForm(f) {
  const form = h("form", { class: "drawer", onsubmit: async (e) => {
    e.preventDefault();
    const pick = form.querySelector("input[name=v]:checked");
    if (!pick) return;
    const obs = f.observations.find((o) => o.fact_id === pick.value);
    const res = await api("POST", `/v1/claims/${S.claim.claim_id}/reviewer-actions`, { idem: true, ifMatch: true, body: {
      action: "RESOLVE_CONFLICT", target: { type: "conflict", id: f.field_path }, evaluation_id: S.ev && S.ev.evaluation_id,
      after_value: { value: String(obs.normalised_value), evidence_fact_id: obs.fact_id }, reason_code: "EVIDENCE_SELECTED",
      comment: form.querySelector("textarea").value || undefined } });
    if (!res.ok) { form.querySelector(".err").textContent = problemText(res); return; }
    say("Conflict resolved; re-evaluating."); await showClaim(S.claim.claim_id);
  } }, h("div", { class: "cat" }, "Choose the value the evidence supports:"));
  for (const o of f.observations) {
    form.append(h("label", { style: "display:flex;gap:6px;color:inherit" }, h("input", { type: "radio", name: "v", value: o.fact_id }),
      h("span", {}, h("span", { class: "mono" }, String(o.normalised_value)), ` · ${human(o.classified_type)}${o.document_status === "SUPERSEDED" ? " (superseded)" : ""}`)));
  }
  form.append(h("label", {}, "Comment (required if you go against most sources)"), h("textarea", { rows: 2, style: "width:100%" }),
    h("button", { class: "btn primary small", type: "submit" }, "Resolve"), h("div", { class: "err" }));
  return form;
}
function uploadForm() {
  const types = ["FINAL_BILL_ITEMISED", "DISCHARGE_SUMMARY", "ADMISSION_RECORD", "PHARMACY_BILL", "INVESTIGATION_REPORT", "CLAIM_FORM", "PAYMENT_RECEIPT", "ID_PROOF", "BANK_DETAILS", "OTHER"];
  const sup = h("select", {}, h("option", { value: "" }, "— none —"), ...S.docs.filter((d) => d.status !== "SUPERSEDED").map((d) => h("option", { value: d.document_id }, human(d.classified_type || "document"))));
  const form = h("form", { class: "drawer", onsubmit: async (e) => {
    e.preventDefault();
    const file = form.querySelector("input[type=file]").files[0]; if (!file) return;
    const buf = await file.arrayBuffer();
    const sha = [...new Uint8Array(await crypto.subtle.digest("SHA-256", buf))].map((b) => b.toString(16).padStart(2, "0")).join("");
    const slot = await api("POST", `/v1/claims/${S.claim.claim_id}/documents`, { idem: true, body: { declared_type: form.querySelector("select").value,
      sha256: sha, mime_type: file.type || "application/pdf", size_bytes: buf.byteLength, supersedes_document_id: sup.value || null } });
    const out = form.querySelector(".err");
    if (slot.status === 200) { out.textContent = "That file is already on this claim."; return; }
    if (!slot.ok) { out.textContent = problemText(slot); return; }
    const put = await fetch(slot.data.upload_url, { method: "PUT", body: buf });
    if (!put.ok) { out.textContent = "Upload failed."; return; }
    const done = await api("POST", `/v1/claims/${S.claim.claim_id}/documents/${slot.data.document_id}:complete`, { idem: true });
    if (!done.ok) { out.textContent = problemText(done); return; }
    say("Document received; processing."); await showClaim(S.claim.claim_id);
  } }, h("h3", {}, "Add a document"), h("input", { type: "file", accept: "application/pdf,image/png,image/jpeg,image/tiff", "aria-label": "File" }),
    h("label", {}, "Type"), h("select", {}, ...types.map((t) => h("option", { value: t }, human(t)))),
    h("label", {}, "Replaces"), sup, h("div", { style: "margin-top:8px" }, h("button", { class: "btn small", type: "submit" }, "Upload")), h("div", { class: "err" }));
  return form;
}

// ---------------------------------------------------------------- centre tabs
function setTab(t) { S.tab = t; renderClaim(); const el = $(`#tab-${t}`); if (el) el.focus(); }
function centrePane() {
  const tabs = [["bill", "Bill & deductions"], ["findings", `Findings (${S.findings.filter((f) => ["OPEN", "ACKNOWLEDGED"].includes(f.status)).length})`],
                ["queries", "Queries"], ["decide", "Decision"], ["audit", "Audit"]];
  const bar = h("div", { class: "tabs", role: "tablist" }, ...tabs.map(([k, label]) => h("button", { role: "tab", id: `tab-${k}`, "aria-selected": String(S.tab === k), onclick: () => setTab(k) }, label)));
  const body = { bill: billTab, findings: findingsTab, queries: queriesTab, decide: decideTab, audit: auditTab }[S.tab]();
  return h("section", { class: "pane", "aria-label": "Review" }, bar, h("div", { role: "tabpanel" }, body));
}

function adjByLine() {
  const m = {};
  for (const a of (S.ev ? S.ev.adjustments : [])) if (a.line_id) (m[a.line_id] = m[a.line_id] || []).push(a);
  return m;
}
function billTab() {
  if (!S.ev) return h("p", { class: "empty" }, "The bill appears once the documents are processed.");
  const m = adjByLine();
  const only = h("input", { type: "checkbox", id: "only", checked: S.onlyDed !== false, onchange: (e) => { S.onlyDed = e.target.checked; renderClaim(); } });
  const tbody = h("tbody");
  const evLines = Object.fromEntries((S.ev.lines || []).map((l) => [l.line_id, l]));
  for (const bl of S.lines) {
    const adjs = m[bl.line_no] || [];
    if (S.onlyDed !== false && !adjs.length && bl.category !== "UNCLASSIFIED") continue;
    const evl = evLines[bl.line_no] || {};
    const tr = h("tr", { class: "line" + (S.selected && S.selected.line === bl.line_no ? " active" : ""), tabindex: "0",
      onclick: () => select({ kind: "line", line: bl.line_no, refs: bl.evidence }), onkeydown: (e) => { if (e.key === "Enter" || e.key === "e") select({ kind: "line", line: bl.line_no, refs: bl.evidence }); } },
      h("td", { class: "mono" }, bl.line_no),
      h("td", {}, bl.description, h("div", { class: "cat" + (bl.category === "UNCLASSIFIED" ? " unclassified" : "") },
        `${human(bl.category)} · ${bl.category_source === "REVIEWER" ? "reviewer" : bl.category_source === "DICTIONARY" ? "dictionary" : "unconfirmed"} · ${human(bl.ward_context)}`)),
      h("td", { class: "amt" }, inr(bl.billed)),
      h("td", {}, ...adjs.map((a) => h("button", { class: "chip ded" + (a.origin === "REVIEWER_OVERRIDE" ? " override" : ""), type: "button",
        onclick: (e) => { e.stopPropagation(); select({ kind: "adj", line: bl.line_no, adj: a, refs: a.evidence_refs }); } },
        h("span", { "aria-hidden": "true" }, "−"), inr(a.amount), " ", h("span", {}, human(a.reason_code)), a.origin === "REVIEWER_OVERRIDE" ? " (override)" : ""))),
      h("td", { class: "amt" }, evl.payable === null || evl.payable === undefined ? "—" : inr(evl.payable)));
    tbody.append(tr);
  }
  const r = S.ev.recommendation;
  const claimAdj = S.ev.adjustments.filter((a) => a.level === "CLAIM");
  const ladder = h("div", { class: "ladder", "aria-label": "Claim ladder" },
    h("div", {}, h("span", {}, "Billed"), h("span", { class: "amt" }, inr(r.billed_total))),
    h("div", {}, h("span", {}, "− Line deductions"), h("span", { class: "amt" }, inr(r.line_level_deductions))),
    h("div", {}, h("span", {}, "= Admissible"), h("span", { class: "amt" }, inr(r.admissible_after_line_rules))),
    ...claimAdj.map((a) => h("div", {}, h("button", { class: "evchip btn small", onclick: () => select({ kind: "adj", adj: a, refs: a.evidence_refs }) },
      a.reason_code === "ROUNDING" ? "± Rounding" : `− ${human(a.reason_code)}`), h("span", { class: "amt" }, a.reason_code === "ROUNDING" ? (Number(a.amount) < 0 ? "+" + inr(-a.amount) : "−" + inr(a.amount)) : inr(a.amount)))),
    h("div", { class: "total" }, h("span", {}, "= Proposed payable"), h("span", { class: "amt" }, r.computed ? inr(r.recommended_payable) : "not computed")));
  return h("div", {}, h("div", { class: "filters" }, h("label", { for: "only", style: "display:flex;gap:6px;color:inherit;margin:0" }, only, "Show only lines with deductions")),
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Line"), h("th", {}, "Description"), h("th", { class: "amt" }, "Billed ₹"),
      h("th", {}, "Deductions (by rule)"), h("th", { class: "amt" }, "Payable ₹"))), tbody)), ladder);
}

function findingsTab() {
  if (!S.findings.length) return h("p", { class: "empty" }, "No findings.");
  const wrap = h("div");
  for (const f of S.findings) {
    if (f.status === "SUPERSEDED" && !S.showOld) continue;
    const cls = "finding" + (f.blocking ? " blocking" : f.category === "ANOMALY" ? " anomaly" : "");
    const card = h("article", { class: cls, tabindex: "0", "aria-label": human(f.kind) },
      h("div", { class: "head" }, f.blocking ? h("span", { class: "chip block" }, "■ Blocking") : f.category === "ANOMALY" ? h("span", { class: "chip" }, "▲ Pattern for review") :
        f.route_to === "MEDICAL_OFFICER" ? h("span", { class: "chip review" }, "◆ Medical officer") : h("span", { class: "chip" }, human(f.category)),
        h("strong", {}, human(f.kind)), h("span", { class: "status-tag" }, `${f.severity} · ${f.status}`)),
      h("div", {}, f.summary),
      f.uncertainty_note ? h("div", { class: "note" }, "Uncertainty: " + f.uncertainty_note) : null,
      f.blocked_scopes && f.blocked_scopes.length ? h("div", { class: "note" }, "Blocks: " + f.blocked_scopes.map(human).join(", ")) : null,
      f.resolution ? h("div", { class: "note" }, `Resolution by ${f.resolution.by}: ${f.resolution.comment || f.resolution.reason_code}`) : null);
    const acts = h("div", { class: "acts" });
    if ((f.evidence || []).length) acts.append(h("button", { class: "btn small", onclick: () => select({ kind: "finding", finding: f, refs: f.evidence }) }, "Evidence"));
    if (["OPEN", "ACKNOWLEDGED"].includes(f.status)) {
      if (f.blocking) acts.append(h("span", { class: "cat" }, "Clears when its cause is fixed: resolve the conflict, correct the fact, or add the missing document."));
      else if (f.category === "CLINICAL" && can("MEDICAL_OFFICER")) acts.append(findingForm(f, "RESOLVE_FINDING", "Record medical opinion", true));
      else if (f.category === "CLINICAL") acts.append(h("button", { class: "btn small", onclick: () => action({ action: "ESCALATE_MEDICAL", target: { type: "finding", id: f.finding_id }, reason_code: "MO_REVIEW_NEEDED" }) }, "Send to medical officer"));
      else if (f.category === "ANOMALY") {
        acts.append(h("button", { class: "btn small", onclick: () => action({ action: "ESCALATE_FWA", target: { type: "finding", id: f.finding_id }, reason_code: "FORWARDED" }) }, "Forward to FWA"));
        if (can("SUPERVISOR", "FWA_ANALYST") || f.severity !== "HIGH") acts.append(findingForm(f, "DISMISS_FINDING", "Dismiss", false));
      } else acts.append(h("button", { class: "btn small", onclick: () => action({ action: "ACKNOWLEDGE_FINDING", target: { type: "finding", id: f.finding_id }, reason_code: "SEEN" }) }, "Acknowledge"),
        findingForm(f, "RESOLVE_FINDING", "Resolve", false));
    }
    card.append(acts);
    wrap.append(card);
  }
  wrap.append(h("label", { style: "display:flex;gap:6px;color:inherit" }, h("input", { type: "checkbox", checked: !!S.showOld, onchange: (e) => { S.showOld = e.target.checked; renderClaim(); } }), "Show superseded findings"));
  return wrap;
}
function findingForm(f, act, label, clinical) {
  const d = h("details", {}, h("summary", { class: "btn small" }, label));
  const outcome = clinical ? h("select", {}, h("option", { value: "PAYABLE" }, "Not a reason to deny: payable"), h("option", { value: "REFER_CRC" }, "Possible repudiation: refer to the insurer's CRC")) : null;
  const ta = h("textarea", { rows: 2, style: "width:100%", required: act === "DISMISS_FINDING" || clinical });
  const err = h("div", { class: "err" });
  d.append(h("form", { class: "drawer", onsubmit: async (e) => {
    e.preventDefault();
    const res = await action({ action: act, target: { type: "finding", id: f.finding_id }, reason_code: clinical ? outcome.value : "REVIEWED",
      after_value: clinical ? { outcome: outcome.value } : {}, comment: ta.value || undefined }, err);
    if (res && clinical && outcome.value === "REFER_CRC") await action({ action: "ESCALATE_CRC", target: { type: "finding", id: f.finding_id }, reason_code: "MO_OPINION", comment: ta.value });
  } }, outcome ? h("label", {}, "Opinion") : null, outcome, h("label", {}, "Comment"), ta, h("button", { class: "btn primary small", type: "submit" }, label), err));
  return d;
}
async function action(body, errEl) {
  const res = await api("POST", `/v1/claims/${S.claim.claim_id}/reviewer-actions`, { idem: true, ifMatch: true, body: { evaluation_id: S.ev && S.ev.evaluation_id, ...body } });
  if (!res.ok) { (errEl || alertBox()).textContent = problemText(res); return null; }
  say(`${human(body.action)} recorded.`); await showClaim(S.claim.claim_id); return res.data;
}
function alertBox() { let el = $("#flash"); if (!el) { el = h("div", { id: "flash", class: "banner block", role: "alert" }); $("#app").prepend(el); } return el; }

function queriesTab() {
  if (!S.ev || !S.ev.query_items.length) return h("p", { class: "empty" }, "The current evaluation suggests no queries.");
  const groups = {};
  for (const q of S.ev.query_items) (groups[q.addressed_to] = groups[q.addressed_to] || []).push(q);
  const wrap = h("div", {}, h("p", { class: "cat" }, "Drafted from the findings. Edit the wording, then approve to release. Claims never close automatically if nobody answers."));
  for (const [addr, items] of Object.entries(groups)) {
    const areas = items.map((q) => h("textarea", { rows: 3, style: "width:100%", "aria-label": `Query item for ${addr}` }, q.text));
    const err = h("div", { class: "err" });
    wrap.append(h("form", { class: "drawer", onsubmit: async (e) => {
      e.preventDefault();
      const d = await api("POST", `/v1/claims/${S.claim.claim_id}/queries`, { idem: true, body: { addressed_to: addr,
        items: items.map((q, i) => ({ text: areas[i].value, requested_document_type: q.requested_document_type || undefined, linked_finding_ids: q.linked_findings })) } });
      if (!d.ok) { err.textContent = problemText(d); return; }
      const a = await api("POST", `/v1/queries/${d.data.query_id}:approve`, { idem: true });
      if (!a.ok) { err.textContent = problemText(a); return; }
      say(`Query to ${human(addr)} approved and sent.`); await showClaim(S.claim.claim_id);
    } }, h("h3", {}, `To: ${human(addr)}`), ...areas, h("button", { class: "btn primary small", type: "submit", disabled: !can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR") }, "Approve and send"), err));
  }
  return wrap;
}

function decideTab() {
  const c = S.claim, ev = S.ev, wrap = h("div");
  for (const ar of c.approval_requests.filter((a) => a.state === "PENDING")) {
    const err = h("div", { class: "err" });
    const mine = S.me.user_id === ar.approver;
    const ta = h("textarea", { rows: 2, style: "width:100%" });
    wrap.append(h("section", { class: "drawer" }, h("h3", {}, "Awaiting second approval"),
      h("dl", { class: "kv" }, h("dt", {}, "Proposed"), h("dd", {}, `${human(ar.proposed_disposition)} ${rs(ar.proposed_payable)}`),
        h("dt", {}, "Requested by"), h("dd", {}, ar.requested_by), h("dt", {}, "Approver"), h("dd", {}, ar.approver),
        h("dt", {}, "Why"), h("dd", {}, ar.triggers.map(human).join(", "))),
      mine ? h("div", {}, h("label", {}, "Comment (required to return)"), ta,
        h("button", { class: "btn primary small", onclick: async () => { const r = await api("POST", `/v1/approval-requests/${ar.approval_request_id}:approve`, { idem: true, body: { comment: ta.value || undefined } });
          if (!r.ok) err.textContent = problemText(r); else { say("Approved; decision recorded."); await showClaim(c.claim_id); } } }, "Approve"), " ",
        h("button", { class: "btn small", onclick: async () => { const r = await api("POST", `/v1/approval-requests/${ar.approval_request_id}:return`, { idem: true, body: { comment: ta.value } });
          if (!r.ok) err.textContent = problemText(r); else { say("Returned for rework."); await showClaim(c.claim_id); } } }, "Return")) : h("p", { class: "cat" }, "Only the named approver can act."), err));
  }
  if (c.decisions.length) { wrap.append(h("p", { class: "ok" }, "A decision is recorded for this claim. Reopen it (supervisor) to change it.")); return wrap; }
  if (!ev) return h("p", { class: "empty" }, "No evaluation yet.");
  const disabled = c.evaluation_status === "STALE" || c.investigation_hold || !can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR");
  const openBlocking = S.findings.filter((f) => f.blocking && ["OPEN", "ACKNOWLEDGED"].includes(f.status)).length;
  const openMo = S.findings.filter((f) => f.route_to === "MEDICAL_OFFICER" && ["OPEN", "ACKNOWLEDGED"].includes(f.status)).length;
  const amt = h("input", { id: "amt", class: "mono", value: ev.recommendation.recommended_payable || "", inputmode: "decimal", "aria-describedby": "amt-help" });
  const reason = h("textarea", { rows: 2, style: "width:100%" });
  const approver = h("select", {}, ...S.users.filter((u) => u.roles.includes("SUPERVISOR") && u.user_id !== S.me.user_id).map((u) => h("option", { value: u.user_id }, `${u.user_id} · ${u.display_name}`)));
  const err = h("div", { class: "err", role: "alert" });
  const second = h("div", { hidden: true }, h("label", {}, "Second approver"), approver,
    h("button", { class: "btn primary small", type: "button", onclick: async () => {
      const r = await api("POST", `/v1/claims/${c.claim_id}/approval-requests`, { idem: true, ifMatch: true, body: { evaluation_id: ev.evaluation_id,
        proposed_disposition: amt.value === ev.recommendation.billed_total ? "APPROVED_FULL" : "APPROVED_PARTIAL", proposed_payable: amt.value, approver_user_id: approver.value,
        deviation_reason: reason.value || undefined } });
      if (!r.ok) err.textContent = problemText(r); else { say("Sent for second approval."); await showClaim(c.claim_id); }
    } }, "Send for approval"));
  const form = h("form", { class: "drawer", onsubmit: async (e) => {
    e.preventDefault(); err.textContent = "";
    const r = await api("POST", `/v1/claims/${c.claim_id}/decisions`, { idem: true, ifMatch: true, body: { evaluation_id: ev.evaluation_id,
      disposition: amt.value === ev.recommendation.billed_total ? "APPROVED_FULL" : "APPROVED_PARTIAL", approved_payable: amt.value, deviation_reason: reason.value || undefined } });
    if (r.status === 409 && r.data && r.data.triggers) { err.textContent = problemText(r); second.hidden = false; return; }
    if (!r.ok) { err.textContent = problemText(r); return; }
    say("Decision recorded."); await showClaim(c.claim_id);
  } }, h("h3", {}, "Approve payment"),
    h("p", { class: "cat" }, `Recommendation ${human(ev.recommendation.type)}${ev.recommendation.computed ? ` · proposed ${rs(ev.recommendation.recommended_payable)}` : ""}. Your limit: ${rs(S.me.approval_limit)}.`),
    openBlocking ? h("p", { class: "err" }, `${openBlocking} blocking finding(s) open.`) : null,
    openMo ? h("p", { class: "err" }, `${openMo} medical-officer question(s) open.`) : null,
    h("label", { for: "amt" }, "Approved amount (₹)"), amt, h("div", { id: "amt-help", class: "cat" }, "Must not exceed the billed total. A different amount from the proposal needs a reason."),
    h("label", {}, "Reason for a different amount"), reason,
    h("div", { style: "margin-top:8px" }, h("button", { class: "btn primary", type: "submit", disabled: disabled || !ev.recommendation.computed }, "Record decision")), second, err);
  wrap.append(form);
  if (can("SUPERVISOR")) wrap.append(crcPanel());
  return wrap;
}
function crcPanel() {
  const c = S.claim, err = h("div", { class: "err" });
  const ref = h("input", { placeholder: "CRC reference", class: "mono" });
  const p = h("section", { class: "drawer" }, h("h3", {}, "Repudiation (insurer's Claims Review Committee)"),
    h("p", { class: "cat" }, "Only the insurer's CRC can repudiate. For a TPA this records the insurer's outcome; no letter is produced here."));
  if (c.status === "ESCALATED_CRC") {
    p.append(ref, " ", h("button", { class: "btn danger small", onclick: async () => {
      const r = await api("POST", `/v1/claims/${c.claim_id}/decisions`, { idem: true, ifMatch: true, body: { evaluation_id: S.ev.evaluation_id, disposition: "REPUDIATED_WITH_CRC_APPROVAL", crc_reference: ref.value, communicated_by: "INSURER" } });
      if (!r.ok) err.textContent = problemText(r); else await showClaim(c.claim_id);
    } }, "Record CRC repudiation"), " ", h("button", { class: "btn small", onclick: () => action({ action: "RECORD_CRC_DECLINED", target: { type: "claim", id: c.claim_id }, reason_code: "CRC_DECLINED", after_value: { crc_reference: ref.value } }, err) }, "CRC declined"));
  } else p.append(h("p", { class: "cat" }, "Escalate from a finding (medical opinion) to start this path."));
  p.append(err);
  return p;
}

// Returns a placeholder immediately and fills it when the audit trail arrives.
function auditTab() {
  const box = h("div", {}, h("p", { class: "empty" }, "Loading audit trail…"));
  api("GET", `/v1/claims/${encodeURIComponent(S.claim.claim_id)}/audit-events`).then((r) => {
    if (!r.ok) { box.replaceChildren(h("p", { class: "err" }, problemText(r))); return; }
    const v = r.data.verification;
    const ul = h("ol", { class: "plain audit" });
    for (const e of r.data.items.slice().reverse()) ul.append(h("li", {}, h("span", { class: "t mono" }, `#${e.seq} ${when(e.occurred_at)} `), h("strong", {}, human(e.event_type)), ` · ${e.actor}`));
    box.replaceChildren(h("p", { class: v.verified ? "ok" : "err" }, v.verified ? `Hash chain verified (${v.events} events).` : `Chain broken at event ${v.broken_at_seq}.`), ul);
  });
  return box;
}

// ---------------------------------------------------------------- right: evidence viewer
function select(sel) { S.selected = sel; renderClaim(); const ev = $("#evidence"); if (ev) ev.focus?.(); }
function evidencePane() {
  const sel = S.selected;
  const pane = h("div", {}, h("h2", {}, "Evidence"));
  if (!sel) { pane.append(h("p", { class: "cat" }, "Select a bill line, a deduction or a finding to see the page it comes from.")); return pane; }
  const docRefs = (sel.refs || []).filter((r) => r.document_id);
  const recRefs = (sel.refs || []).filter((r) => r.record_type);
  if (docRefs.length) {
    const ref = docRefs[0];
    const doc = S.docs.find((d) => d.document_id === ref.document_id);
    pane.append(h("div", { class: "cat" }, `${human(doc ? doc.classified_type : "document")} · page ${ref.page}`));
    const viewer = h("div", { class: "viewer" + (S.zoom ? " zoom" : ""), "aria-label": `Page ${ref.page}` });
    let placeBox = () => {};
    const zoomBtn = h("button", { class: "btn small", type: "button", "aria-pressed": String(!!S.zoom), onclick: () => {
      S.zoom = !S.zoom; viewer.classList.toggle("zoom", S.zoom); zoomBtn.setAttribute("aria-pressed", String(S.zoom)); placeBox(); } }, "Zoom");
    pane.append(h("div", { style: "margin:4px 0" }, zoomBtn), viewer, h("div", { class: "quote", "aria-label": "Highlighted text" }, ref.quote || ""));
    api("GET", `/v1/claims/${S.claim.claim_id}/documents/${ref.document_id}/pages/${ref.page}`).then((p) => {
      if (!p.ok) { viewer.append(h("p", { class: "err" }, problemText(p))); return; }
      const img = h("img", { src: p.data.image_url, alt: `Page ${ref.page} of ${human(doc ? doc.classified_type : "document")}` });
      viewer.append(img);
      const box = h("div", { class: "box" });
      placeBox = () => {
        if (!ref.bbox || !p.data.width_pt || !img.complete) return;
        const k = img.clientWidth / p.data.width_pt;
        const [x0, top, x1, bottom] = ref.bbox;
        Object.assign(box.style, { left: `${x0 * k - 3}px`, top: `${top * k - 3}px`, width: `${(x1 - x0) * k + 6}px`, height: `${(bottom - top) * k + 6}px` });
        if (!box.isConnected) viewer.append(box);
        viewer.scrollTop = Math.max(0, top * k - 120);
        viewer.scrollLeft = Math.max(0, x0 * k - 40);
      };
      img.addEventListener("load", placeBox);
    });
  }
  for (const r of recRefs) pane.append(h("div", { class: "quote" }, `Record: ${human(r.record_type)} ${r.record_id} · ${r.field}`));
  if (sel.kind === "adj") {
    const a = sel.adj;
    pane.append(h("dl", { class: "kv" },
      h("dt", {}, "Rule"), h("dd", { class: "mono" }, `${a.rule_id} ${a.rule_version}`),
      h("dt", {}, "Amount"), h("dd", {}, `${rs(a.amount)}${a.origin === "REVIEWER_OVERRIDE" ? ` (engine ${rs(a.engine_amount)})` : ""}`),
      h("dt", {}, "Formula"), h("dd", { class: "mono" }, a.formula),
      h("dt", {}, "Why"), h("dd", {}, a.explanation),
      h("dt", {}, "Authority"), h("dd", {}, `${a.authority.doc_id} — ${a.authority.clause}`, h("div", { class: "cat mono" }, a.authority.artifact))));
    if (a.level === "LINE" && a.reason_code !== "ROUNDING" && can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR") && !S.claim.decisions.length) pane.append(overrideForm(a));
  }
  if (sel.kind === "line") {
    const bl = S.lines.find((l) => l.line_no === sel.line);
    if (bl) {
      pane.append(h("dl", { class: "kv" }, h("dt", {}, "Line"), h("dd", { class: "mono" }, bl.line_no), h("dt", {}, "Category"), h("dd", {}, `${human(bl.category)} (${bl.category_source.toLowerCase()})`),
        h("dt", {}, "Qty × rate"), h("dd", {}, `${bl.quantity} × ${bl.unit_rate ? rs(bl.unit_rate) : "—"}`), h("dt", {}, "Billed"), h("dd", {}, rs(bl.billed))));
      if (can("PROCESSOR", "MEDICAL_OFFICER", "SUPERVISOR") && !S.claim.decisions.length) pane.append(reclassForm(bl));
    }
  }
  return pane;
}
function overrideForm(a) {
  const amt = h("input", { class: "mono", value: a.amount, inputmode: "decimal" }), reason = h("input", { value: "", placeholder: "Reason code, e.g. TARIFF_ITEM_NOT_APPLICABLE" });
  const comment = h("textarea", { rows: 2, style: "width:100%", required: true }), err = h("div", { class: "err" });
  return h("form", { class: "drawer", onsubmit: async (e) => {
    e.preventDefault();
    await action({ action: "OVERRIDE_ADJUSTMENT", target: { type: "adjustment", id: a.adjustment_id }, after_value: { amount: amt.value }, reason_code: reason.value || "REVIEWER_JUDGEMENT", comment: comment.value }, err);
  } }, h("h3", {}, "Override this deduction"), h("label", {}, "Deduct (₹)"), amt, h("label", {}, "Reason"), reason, h("label", {}, "Comment (required)"), comment,
    h("button", { class: "btn small", type: "submit" }, "Override"), err);
}
function reclassForm(bl) {
  const cats = ["ROOM", "ICU_ROOM", "NURSING", "PROFESSIONAL_FEES", "OT_CHARGES", "PROCEDURE_CHARGES", "PHARMACY", "CONSUMABLES", "IMPLANTS", "DIAGNOSTICS", "OTHER_HOSPITAL_SERVICES"];
  const sel = h("select", {}, ...cats.map((c) => h("option", { value: c, selected: c === bl.category }, human(c)))), err = h("div", { class: "err" });
  return h("form", { class: "drawer", onsubmit: async (e) => { e.preventDefault();
    await action({ action: "RECLASSIFY_LINE", target: { type: "bill_line", id: bl.bill_line_id }, after_value: { category: sel.value }, reason_code: "CATEGORY_CONFIRMED" }, err); } },
    h("h3", {}, "Category"), sel, " ", h("button", { class: "btn small", type: "submit" }, "Confirm category"), err);
}
async function openWorksheet(decisionId, fmt) {
  const r = await api("GET", `/v1/claims/${S.claim.claim_id}/decisions/${decisionId}/worksheet${fmt === "pdf" ? "?format=pdf" : ""}`, { raw: true });
  const blob = await r.blob();
  window.open(URL.createObjectURL(blob), "_blank", "noopener");
}

// ---------------------------------------------------------------- keyboard
let gPressed = false;
document.addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
  if (e.key === "?") { $("#help").showModal(); return; }
  if (e.key === "n" && (location.hash || "").startsWith("#/queue") && S.queueFirst) { location.hash = `#/claim/${encodeURIComponent(S.queueFirst)}`; return; }
  if (e.key === "g") { gPressed = true; setTimeout(() => { gPressed = false; }, 800); return; }
  if (e.key === "d" && gPressed) { setTab("decide"); return; }
  if (e.key === "j" || e.key === "k") {
    const rows = [...document.querySelectorAll("tr.line, article.finding")];
    if (!rows.length) return;
    const i = rows.indexOf(document.activeElement);
    const next = rows[Math.min(rows.length - 1, Math.max(0, i + (e.key === "j" ? 1 : -1)))];
    next.focus(); e.preventDefault();
  }
});

boot();
