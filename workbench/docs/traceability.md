# Current milestone traceability — 13 October 2026

The current executed feature matrix, tests, benchmark limitations and pilot gaps are in [DELIVERY.md](../DELIVERY.md). Milestones0–6 extend the existing implementation; the older Phase1 table below is retained as historical context and is not a current status report.

| Milestone | Current implementation | Actual proof |
|---|---|---|
| 0 native baseline | FastAPI/psycopg, native PostgreSQL startup, preserved legacy driver | Final71 tests each driver, five exact demo traces, full pack |
| 1 local reading | `extraction/{ocr,pages,providers,grounding,manual}.py`, `bundles.py`, migration0003 | `test_document_reading`, manual browser; independent per-type/quality/held-back metrics in delivery; accuracy inadequate |
| 2 config admin | `config_admin.py`, `web/config.js`, config routes, extended engine | `test_config_admin`, browser draft/replay/four-eyes publish |
| 3 workflows | `workflows.py`, `workflow_demo.py`, migration0004, checklists | `test_workflows`, four browser workflows and enhancement |
| 4 platform | `local_auth.py`, sessions, jobs/worker/maintenance, anchors, backup, migration0005 | `test_platform`, RLS/role/CSRF/revocation, actual kill/recovery and restored restricted app |
| 5 operations | `queries.py`, operations API/UI, migration0006 | `test_operations` including TC-QRY-01, query PDF/reply/assignment/admin browser |
| 6 hardening | `test_hardening`, reviewer timing, independent review, clean snapshot | TC-REV-01/REL-04/SEC-02; browser TC-UX-02; corrected mutation runner/full pack, actual DR |

Docker and remote CI are NOT RUN. New external integrations, hosted application AI/OCR and customer production deployment are NOT BUILT. See the delivery matrix for precise three-state reporting and per-feature limits.

# Historical Phase1 backlog → code → tests

This table maps the backlog in `../11-build-backlog.md` to what the Phase 1 workbench build contains.

- **Built** — works end to end on synthetic data, and a test proves it.
- **Partial** — some of the item exists; the gap is named.
- **Not started** — nothing written yet.

None of these statuses mean an item is ready for real claims. Every item still needs the real-data acceptance named in the backlog.

| BL | Item | Status | Code | Tests (in `tests/`) | Gap to the backlog's acceptance |
|---|---|---|---|---|---|
| BL-04 | Repo, CI, IaC, staging | Partial | `pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `Dockerfile` | — | The CI workflow and Dockerfile have **not been run**. No IaC or staging account |
| BL-05 | DB schema v1 + migrations | Built | `migrations/0001_schema.sql` (= `db/schema.sql`), `0002_app_support.sql`, `aw/db/migrate.py` | `test_foundation`: Migrations, WireClientAndRls, AuditChain | Run `validate_db.sh` in CI |
| BL-06 | Document ingest | Built (local store) | `aw/ingest.py`, `aw/storage.py`, `aw/extraction/pages.py`, upload slots and signed URLs in `aw/api/app.py` | `test_workflow` SafetyAndIntegrity.test_quarantine_and_duplicates; `test_api` (upload flow, signed URLs) | S3 Object Lock adapter not executed (ADR-12.6) |
| BL-07 | OCR/LLM bake-off | Not started | — | — | Needs 200 real pages (BL-01) |
| BL-08 | OCR pipeline + page quality | Not started | Pages with no text layer fail with `NO_TEXT_LAYER_OCR_NOT_CONFIGURED` | — | No OCR, so scanned documents cannot be read |
| BL-09 | Model gateway | Partial (stub) | `BedrockClaudeProvider` in `aw/extraction/providers.py` | — | Never called. No metering, kill-switch or prompt registry |
| BL-10 | Extraction + grounding + normalisation | Built for synthetic layouts | `aw/extraction/` (heuristic and fixture providers, schema validation, grounding, injection detection, normalisation) | SafetyAndIntegrity.test_ungrounded_values_are_never_used and .test_injected_instructions_have_no_effect; DemoReproducesPack | The heuristic provider only reads the synthetic PDFs. M-EXT thresholds have not been measured |
| BL-11 | Fact resolution, conflicts, member matching | Built | `aw/facts.py`, `aw/matching.py`, R-GATE-IDENTITY 1.1.0 in `aw/engine/core.py` | DemoReproducesPack (date conflict in 3a, resolved in 3b); test_engine_equivalence (transliteration, similar names) | Matching thresholds still need tuning on real member data |
| BL-12 | Bill lines + categorisation (dictionary) | Built (dictionary only) | `aw/facts.py` (`categorise`, `sync_bill_lines`), `config/classifier-map-ILL-A.v2026.1.0.json`, R-GATE-LINE-CATEGORY | OverridesAndCorrections.test_unclassified_line_blocks_until_reclassified; test_engine_equivalence.test_unclassified_line_blocks_line_rules | No model fallback. Needs the customer's NME list and synonyms |
| BL-13 | Rule engine v1 | Built | `aw/engine/core.py` (`aw-engine-1.0.0`), `aw/configs.py` (effective dating) | test_engine_equivalence (all pack traces) | Rule tests and FI tests from `verification/` are not yet re-run against the workbench engine in CI |
| BL-14 | Encode pilot product | Not started | Illustrative configs only | — | Needs the customer's wording, tariff and NME list |
| BL-15 | Evaluation persistence, STALE/SUPERSEDED | Built | `aw/evaluations.py`, `aw/handlers.py`, `aw/jobs.py` | SafetyAndIntegrity.test_stale_evaluation_cannot_be_decided; DemoReproducesPack (3a → 3b) | — |
| BL-16 | Queue, workspace, evidence viewer | Built (vanilla JS) | `aw/web/` | `tests/ui_smoke.py` (Playwright; `make ui-smoke`) | TC-UX-02 (≤ 300 ms) not measured. React rebuild planned (ADR-12.4) |
| BL-17 | Bill & deductions UI, overrides, ladder | Built | `aw/web/app.js` (bill tab, override form), `aw/review.py` | OverridesAndCorrections.test_override_reproduces_trace_2b_and_fingerprint_guard (service level); ui_smoke shows the ladder and deduction evidence but does not submit an override | — |
| BL-18 | Findings UI | Built (basic) | `aw/web/app.js` findings tab | ui_smoke | Wording lint not built |
| BL-19 | Queries | Partial | `aw/queries.py`, queries tab | DemoReproducesPack (claim 3 queries) | No letter template or export. "Sent" is a status only |
| BL-20 | TMS adapter | Not started | `LocalFileExporter` writes export records to the object store | — | Needs the TMS spec (M-23) |
| BL-21 | Decisions, limits, second approval, CRC, worksheet | Built | `aw/decisions.py`, `aw/exports.py` | test_api.test_full_flow_claim_1_and_2; SafetyAndIntegrity.test_si_ledger_prevents_double_spend and .test_tpa_repudiation_records_insurer_outcome_without_letter | The grievance block is placeholder text until counsel writes it (E-REG-04) |
| BL-22 | Audit timeline + chain verification + anchoring | Partial | `aw/audit.py`, audit tab | AuditChain.test_chain_appends_verifies_and_detects_tampering | No anchoring job |
| BL-23 | Clinical summary + PED signal | Partial | PED signal finding from the engine; medical-officer resolution in `aw/review.py` | DemoReproducesPack (claim 3) | No cited clinical summary |
| BL-24 | Anomaly v1 | Partial | Bill-number reuse and duplicate lines in the engine; seeded prior claim CLM-DEMO-0088 | DemoReproducesPack | No cross-claim duplicate index beyond bill numbers |
| BL-25 | TAT clocks and alerts | Partial | Due time from workflow config in the claim view | — | No alerts. Query pauses depend on OQ-21 |
| BL-27 | Config authoring + replay | Partial | `aw/configs.py`: drafts, four-eyes publish, effective dating; API endpoints | Configuration.test_four_eyes_and_effective_dating | No replay or authoring UI |
| BL-26, 28–40 | — | Not started | — | — | — |

## Test inventory

The suite is run with `make test`. A run on 11 Oct 2026 had 27 tests passing:

- `test_engine_equivalence` — 5
- `test_foundation` — 9
- `test_api` — 3
- `test_workflow` — 10

The UI smoke test (`tests/ui_smoke.py`, run with `make ui-smoke`) is separate. It needs the Python `playwright` package, a Chromium build and a freshly seeded running server, so it is not part of `make test`. On 11 Oct 2026 it walked this path with no console or HTTP errors:

1. Sign in.
2. Open the queue.
3. Open claim 2 and its deduction evidence (page highlight and zoom).
4. Request second approval.
5. Supervisor approves.
6. Check the audit-chain verification.
7. Open blocked claim 3: findings, evidence and drafted queries.

Policy intelligence: ADR-20, migrations0007–0008, aw.policy_intelligence and
api.policy_intelligence implement isolated public provenance, evidence candidates,
four-eyes shadow publication and blocked unknown private inputs. Executed proof and
remaining gaps are in POLICY_INTELLIGENCE_DELIVERY.md and evidence/2026-10-13.
