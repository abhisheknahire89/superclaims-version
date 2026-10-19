# Codex execution task — Adjudication Workbench

**This is an implementation assignment, not a planning exercise.** Work on the code in this repository and demonstrate functioning software. Begin by reading `PROJECT_CONTEXT.txt`, `00-README.md`, `workbench/README.md`, and `AGENTS.md`. Then inspect the code, the numbered research/design pack, ADR-12, and `workbench/docs/traceability.md`. The newer user prompt takes precedence over the historical handover.

## Immediate action: milestone 0, Mac baseline

1. Examine `git status` and record the starting commit; protect all pre-existing changes. Detect macOS architecture, Python/pip, npm, Docker, PostgreSQL 16 (`psql`, `initdb`, `pg_ctl`), `tesseract`, and available package tools. `bash scripts/codex_preflight.sh` is read-only. Report a brief inventory without printing credentials.
2. Recreate `workbench/Makefile` and `.github/workflows/workbench-ci.yml` from `workbench/README.md` only if missing.
3. Run old tests, `make demo`, `bash verification/build_all.sh`, and the existing UI smoke flow if applicable. Record exact passed/failed/skipped counts; distinguish actual Mac results from old handover claims. Repair macOS failures.
4. If dependencies install cleanly, activate and test the `psycopg 3` PostgreSQL path and replace the temporary Starlette API layer with FastAPI while preserving every OpenAPI operation and working route. Keep the existing ES-module UI unless a migration is clearly justified and demonstrably safer. If dependencies cannot install, retain the running stack and document the reason; avoid half-migrations.
5. Generate local development secrets to `.env` safely, preserve `.gitignore`, never print them, and do not check them into version control.
6. Start the seeded app natively. Save a tested startup instruction and result. Update `PROJECT_CONTEXT.txt` and record the milestone evidence.

## Continue implementation in exactly this order

### Milestone 1 — Read documents locally

Build native PDF, scanned PDF, JPG, PNG, multi-upload and safe ZIP ingestion; document classification, free local OCR, image cleanup/deskew, layout-generic line/table extraction, multi-page table stitching, subtotals, date/amount parsing, quote/page/bbox grounding and schema validation. Block financial calculation on low-confidence or conflicting critical fields. Add full manual correction/entry, preserving provenance. Never execute instructions embedded in documents. Generate a substantial synthetic corpus and hold back 2 layouts from the extraction implementer.

### Milestone 2 — Configurable adjudication

Implement admin UX and services for draft/version/validate/diff/publish of policies, tariffs/packages, nonmedical item rules, document checklists, calculation ordering, and approval limits, including validated CSV/XLSX imports where scoped to local admin configuration. Require effective dates, four-eyes publish, saved-claim replay/diff and re-evaluation; add the catalogue-only rules in `PROJECT_CONTEXT.txt` §5. Maintain original exact-money traces.

### Milestone 3 — Cashless and OPD

Complete and test explicit state machines for IPD reimbursement, cashless preauth with enhancements, cashless discharge/final bills, and OPD reimbursement according to `03-workflows-and-UX.md`. Preserve insurer-vs-TPA permissions, SLAs, escalation, queries and human decision boundaries.

### Milestone 4 — Secure local platform

Real local authentication (salted password hashes, secure sessions, lockouts) plus a future OIDC interface, DB-level tenant isolation and RBAC, worker leasing/retries/idempotency/visible status, local write-once docs, audit-chain verification and anchoring (explicitly document the limits of tamper evidence against host administrators), structured no-PHI logs, health, deadline alerts, one-command native start and Docker compose if available. Actually perform backup and restore.

### Milestone 5 — Buyer-ready UX and dashboards

Reviewer queue with assignment/deadlines/filters, claim workspace with grounded highlighted evidence, corrections/overrides, queries/letter templates/export, replies/reprocess, second approval, insurer-only repudiation path, audit, PDF/JSON/CSV exports; supervisor KPIs and admin users/roles. Accessible keyboard-operated HTML. Keep `api/openapi.yaml` contract tested and synchronised with implementation.

### Milestone 6 — Hardening and evidence

At least 30 synthetic claims and at least 7 different hospital layouts (2 unseen held-back). Include scans with skew/noise/stamps, multi-page bills, conflicting/missing documents, duplicates, prompt injection. Measure extraction fields, line accuracy, totals, abstention by type and quality; separate held-back results. Add missing security/reliability/UX tests in context §9. Headless browser per workflow with screenshots, independent agent code/security review, resolve defects, clean-checkout run based ONLY on README. End with documented 10-minute demo and precise feature status table.

## Definition of done for *each* milestone

- Actual code changes, migrations if needed, tests and documentation, not descriptions alone.
- Tests pass, application starts from a clean state, and test evidence is recorded.
- Existing five pack traces and money invariants pass to the paisa.
- `PROJECT_CONTEXT.txt` updated with new actual state, changes, failed/skipped verification and next risks.
- Commit only if locally appropriate, with clear messages. Never push or deploy without permission.

## Output at the finish

Show: the exact `make serve` command and Docker command if tested; synthetic demo URLs and logins; a concise 10-minute buyer demo script for all 4 workflows; measured accuracy table with held-back split; screenshots/log locations; backup/restore outcome; independent review findings; and **a per-feature matrix using exactly** `built and run here`, `built, not run here (why)`, or `not built (why)`. List customer-specific rulebooks, insurer/TPA access, hospital tariffs, permitted real claims and legal/compliance work still required for a production pilot.

If environmental obstacles require human intervention, describe only the precise action needed and continue unrelated development. **Do not substitute fake passing tests or call an unrun feature operational.**
