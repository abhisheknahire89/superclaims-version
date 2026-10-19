# Local synthetic delivery — 13 October 2026

Milestones 0–6 were executed in order against the existing Adjudication Workbench. The native application is running at http://127.0.0.1:8080 with six fresh undecided synthetic claims. This is a working local demonstration with measured limitations, not an acceptance result for real claims. Automatic extraction on unfamiliar layouts is inadequate; manual review and source-grounded correction remain necessary.

## Startup and identities

The final startup actually used:

```bash
cd /Users/abhishekpravinnahire/Desktop/SUperclaims/workbench
make serve AW_DEV_DIR=/tmp/aw-delivered AW_DEV_PORT=55465 AW_OBJECT_STORE_DIR=/tmp/aw-delivered/objects
```

The process is left running. Stop it before starting another HTTP8080 server. Reusing this directory preserves decisions; choose a new directory and unused DB port for a fresh seed. Setup, verification, backup/restore and browser commands are in [README.md](README.md). Native environment: macOS arm64, Python 3.13.15, PostgreSQL 16, local Tesseract 5, Chromium, FastAPI and psycopg 3; pgwire remains tested. Private ignored secrets were generated locally and never included in the verification checkout.

Tenant **TENANT-DEMO**; all seed users have public synthetic password **Synthetic-demo-2026!**. PROC-07 and PROC-11 review claims; SUP-02 supervises and second-approves; MO-01 records medical findings; FWA-01 reviews FWA; AUD-01 audits; CFG-01 authors configuration; ADM-01 administers/publishes; RO-01 reads masked data. These are development identities, not production credentials.

## Feature status matrix

Each row reports execution in this run. A working implementation does not imply acceptable clinical accuracy or customer acceptance.

| Feature | State | Executed proof / remaining limit |
|---|---|---|
| Native seeded FastAPI app, PostgreSQL migrations, both DB drivers | **BUILT AND RUN HERE** | Fresh startup, readiness, login, six-claim queue and 107591.00 workspace verified; 71 tests per driver |
| PDF/text/scanned PDF, PNG/JPG, multi-upload, bounded ZIP, local Tesseract/cleanup | **BUILT AND RUN HERE** | Document tests, corpus scoring and independent probes; poor unseen-layout results below |
| Classification, lines, reconciliation, grounding, critical-field abstention | **BUILT AND RUN HERE** | Quotes/bboxes/source values checked; low-confidence/conflicting evidence blocks; no acceptable generic extraction accuracy claimed |
| Manual entry/correction and explicit visual transcription provenance | **BUILT AND RUN HERE** | Browser submission and immutable source/reviewer provenance tests |
| Exact-money recommendations and authority-linked adjustments | **BUILT AND RUN HERE** | All five historical traces; rounding, co-pay before SI cap, authority/evidence gates and concurrency tests |
| Six configuration kinds, version/draft/validate/diff/replay, CSV/XLSX patch import, effective dates and four-eyes publish | **BUILT AND RUN HERE** | Configuration service and browser tests, distinct publisher/password confirmation; illustrative configs only |
| IPD, preauth/enhancement, discharge, OPD state machines | **BUILT AND RUN HERE** | Four browser decision workflows plus enhancement registration; cumulative reservations and OPD caps tested |
| Human disposition, limits/second approval, insurer CRC versus TPA outcome recording | **BUILT AND RUN HERE** | Service/API and smoke tests; blocked/stale evaluations cannot be approved |
| Queue/assignment/filter/deadline/workspace/evidence/override/audit | **BUILT AND RUN HERE** | Browser screenshots; actual override201; warm loaded-page highlight maximum18.8ms |
| Query template/PDF/JSON, local export, replies/reprocessing/reminders | **BUILT AND RUN HERE** | Downloaded PDF, evidence reply and job tests; no external delivery |
| Supervisor KPIs and tenant user/role/limit/password administration | **BUILT AND RUN HERE** | Operations browser and tests; revocation, last-supervisor protections and append-only history |
| Local password/session/CSRF/lockout/RBAC/RLS | **BUILT AND RUN HERE** | Eight-role matrix, negative tenant tests, immediate revocation and actor-bound idempotency |
| Workers/retries/leases/fencing, health and safe logs | **BUILT AND RUN HERE** | Killed actual worker before commit, rollback/reclaim/exactly-one evaluation; failure visibility and readiness tests |
| Immutable local originals, checksum crash recovery, audit chains/anchors | **BUILT AND RUN HERE** | Storage mutation/recovery tests and verified restored chains; host administrator can replace DB and disk together |
| Backup/restore and clean checkout | **BUILT AND RUN HERE** | Stopped-writer drill and new DB/object target; fresh offline venv, both drivers, pack, demo and six browser flows |
| Docker definitions and GitHub CI | **BUILT NOT RUN HERE** | Docker daemon unavailable; no remote CI authorized. Exact prerequisite: open Docker Desktop and wait for its engine to run |
| Existing integration routes | **BUILT NOT RUN HERE** as external integrations | Inherited routes retained, authorization guard tested; no external-system round trip executed or new integration delivered |
| OIDC provider, cloud storage, TMS adapter, new bulk import endpoint, API keys/webhooks | **NOT BUILT** | Future interface or explicitly excluded scope; no customer connection |
| Paid/hosted AI/OCR, external query sending, automatic final approvals/denials | **NOT BUILT** | Explicit product constraints; recommendations require a person |
| Handwriting support, customer-specific rulebooks, production identity/deployment, real-data acceptance | **NOT BUILT** | No handwriting/real-claim accuracy claimed; customer inputs and acceptance still required |

## Executed verification

* `make test-all`: **71 passed, zero failed/skipped on each driver**. Includes TC-REV-01, TC-QRY-01, TC-REL-04, TC-SEC-02; TC-UX-02 runs in Chromium. Intentional quarantine tests log a failed job, while their assertions pass.
* `make pack-check`: 59 contract checks, eight caught mutations, 3000 property cases (2715 computed/285 blocked), exact traces, rule/reference checks, 31-table normative schema, 11 rejected-invalid DB writes and negative RLS (other tenant0/own3). The final log audit caught an earlier mutation runner socket-copy failure concealed by shell `&&`; the runner now copies only validator inputs and the pack exits on its failure. Both final pack runs passed.
* Exact trace1 billed109360.50/payable107591.00; trace2 billed172455.75/payable85000.00; trace2b admissible102385.75/payable85000.00; trace3a no payable/QUERY_AND_REFER_MEDICAL; trace3b85570.00/REFER_MEDICAL. Clean-checkout `make demo` reproduced all five.
* Six sequential Chromium flows: evidence timing/override, original smoke/second approval/audit, manual entry, operations/query/admin, four claim workflows/enhancement, configuration. All passed with zero page errors. Timing is ten real clicks on a loaded warm-cache localhost page: mean17.07ms/max18.8ms; it does not measure cold network/image loading.
* Independent review reproduced five authorization/integrity defects, then verified fixes: missing second-approver limit, closed-query changes, cross-user cached idempotency, restore manifest/object integrity and inherited receiver withdrawal authorization. Additional checksum publication recovery and restore connection cleanup verified. This was a bounded code/security review, not an external penetration audit.
* Stopped-writer backup244 files including sidecars; restored **8 claims/32 documents/5 human decisions**, eight verified chains and109 referenced object reads. Restricted `aw_app` restored login/read200; other tenant0 claims. Corrupt/omitted/unlisted/symlink objects fail validation. No online atomic snapshot guarantee.
* Clean source checkout in `/tmp/aw-clean-checkout` from a local snapshot including pending implementation, excluding secrets/runtime/evidence. Fresh venv installed pinned dependencies from53 local cached wheels. Source snapshot commit `7a777f8`; original repository HEAD remains `6bba0ddf48be5b2b738bcec6ca54252f7da39525`. Source was clean before runs; generated evidence appeared afterward. No push or hosted application service used.

## Extraction benchmark and safety limits

**44 distinct labelled synthetic claims, 414 document artifacts, seven structural templates.** Eleven layout IDs include five minor variations of one training template; they are not eleven independent templates. Six reserved structural layouts were generated independently; the final two remained unseen until blind scoring finished. Corpus includes skew/noise/stamps, multi-page tables, missing documents, conflicting values, duplicates and injected instructions.

| Recorded snapshot | Exact fields | Exact description/amount lines | Bills reconciling | Labelled document abstention |
|---|---:|---:|---:|---:|
| Training | 396/400 (99%) | 43/60 (71.67%) | 15/40 | 45/60 |
| Original blind reserved | 100/1132 (8.83%) | 0/400 | 0/44 | 8/8 |
| Challenge blind reserved | 157/876 (17.92%) | 0/256 | 0/36 | 8/8 |
| Final untouched reserved | 158/610 (25.90%) | 0/156 | 0/30 | 10/12 |

These are recorded extractor snapshots, not implied current-code accuracy. Per-type/per-quality metrics, definitions, hashes and revealed regression scores are in [the benchmark report](evidence/2026-10-12/extraction-benchmark-summary.md). Raster variants repeat clinical content. Reconciled totals do not prove row semantics; quantity/rate correctness was NOT RUN. Document-only abstention scoring is not calibrated claim-level sensitivity. Final reserved classification was0/70. No acceptable blind performance or automatic reading readiness is claimed.

Actual isolated product ingestion/evaluation of three challenge and six final reserved bundles produced **9/9 BLOCKED/null payable, 9/9 approvals refused, zero decisions**,59 successful jobs; two duplicate uploads were deduplicated. Unknown classification/reading also blocks these bundles, so this does not isolate identity/date-conflict recognition. Full-corpus claim-level conflict sensitivity, handwriting/real-claim accuracy, full WCAG audit, containers and remote CI are **NOT RUN** for the reasons above.

## Ten-minute synthetic demo

1. **0–1min:** Login PROC-07/TENANT-DEMO. Show six claims and workflow/status/deadline filters. Explain recommendations and human disposition.
2. **1–3min:** Open CLM-DEMO-0001. Select a deduction, inspect page/quote/bbox and policy/tariff authority; payable107591.00. Show manual correction provenance and audit. Record the synthetic human decision only when desired.
3. **3–4min:** Open CLM-DEMO-0002. Explain SI cap85000.00, change L14 to0.00 with reason/comment, show payable stays capped. PROC-11 requests second approval; SUP-02 reviews it.
4. **4–5min:** Open CLM-DEMO-0003. Show conflicting facts/no payable; draft a query, approve/download its local letter. Upload synthetic evidence reply and inspect reprocessing. No letter is sent externally.
5. **5–7min:** Show CLM-DEMO-PREAUTH and enhancement registration, CLM-DEMO-DISCHARGE final settlement, and CLM-DEMO-OPD annual/per-claim caps. Each final disposition requires a person; preauth recommendation is provisional.
6. **7–8min:** CFG-01 creates a draft, validates/replays and views the diff; ADM-01 separately confirms password and publishes. Use an effective date appropriate to the synthetic example.
7. **8–9min:** SUP-02 assigns a claim and inspects real operations counts; ADM-01 demonstrates local role history/revocation. AUD-01 verifies the hash chain and local export.
8. **9–10min:** Show held-back failures/manual workflow and the actual restore/clean-checkout evidence. Discuss customer inputs and acceptance gaps. Restart with a new isolated seed before repeating mutated browser demos.

## Proof artifacts and pilot materials

* Final test logs: [both drivers](evidence/2026-10-12/m6-verified-tests.log), [pack](evidence/2026-10-12/m6-pack-verified.log), [clean pack](evidence/2026-10-12/clean-pack-verified.log), [clean browser](evidence/2026-10-12/clean-browser.log), [clean demo](evidence/2026-10-12/clean-demo.log), [checkout proof](evidence/2026-10-12/clean-checkout-proof.json).
* [Independent review](evidence/2026-10-12/final-independent-review.md), [benchmark details](evidence/2026-10-12/extraction-benchmark-summary.md), [backup](evidence/2026-10-12/m6-backup.log), [restore](evidence/2026-10-12/m6-restore.log), [restricted restored app](evidence/2026-10-12/m6-restored-app.log).
* [Fresh queue](evidence/2026-10-12/delivered-queue.png), [workspace](evidence/2026-10-12/delivered-workspace.png); all workflow screenshots in `evidence/2026-10-12/clean-browser-artifacts/workflows/`, operations/admin/query/override evidence alongside them; downloaded query letter in `clean-browser-artifacts/query-letter.pdf`.
* Customer handover materials: this demo/status/benchmark report, README runbook, normative OpenAPI/schema/config fixtures, traceability and ADR13–19, restore evidence and synthetic generators. These support a synthetic evaluation pilot.
* Before any real-data pilot, the customer must supply approved policy wording with versioned clauses, hospital tariffs/packages/NME synonyms, checklists/limits/SLAs, insurer-versus-TPA permissions, approved letters/grievance wording, medical review ownership, identity/access and retention requirements, an authorized acceptance dataset and pass criteria. Customer security/privacy/compliance and rule-owner acceptance remain outstanding. No real patient data was introduced here and no public deployment was performed.
