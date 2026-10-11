# Adjudication Workbench — Phase 1 build

This is the first build of the product specified in this pack. It is a claims-review service and reviewer UI for Indian health-insurance reimbursement claims. **Synthetic data only. Every decision is made by a person.** The software never repudiates, and it never decides on its own.

It runs the G1 slice end to end (`../11-build-backlog.md` §1):

1. **PDF upload.** Documents go to a write-once store and are rendered as page images.
2. **Extraction.** Each document is classified and its fields and bill lines are extracted. Every value is validated against `../schemas/extraction-output.schema.json` and must be grounded in a quote found on the page. Embedded instructions are detected and ignored.
3. **Fact resolution.** Values from different documents are resolved. Conflicts block the rules until a person resolves them.
4. **Rule engine** (`aw-engine-1.0.0`, ported from `../verification/engine.py`). The engine uses the effective-dated configs in `../config/`.
5. **Evaluation.** Each evaluation is persisted with evidence-linked deductions and findings. It goes STALE when the evidence changes.
6. **Reviewer actions.** Reviewers can correct, resolve, reclassify, override (with a fingerprint guard), escalate, hold, and draft and approve queries.
7. **Decisions.** Decisions respect approval limits and the second-approval rule from the workflow config. The SI ledger prevents double-spend. Repudiation goes only through the insurer's CRC path.
8. **Outputs.** A settlement worksheet (JSON and PDF), a hash-chained audit trail and an export record.
9. **API.** The HTTP API from `../api/openapi.yaml` validates requests against it. It uses idempotency keys, ETag/If-Match and RFC 9457 errors.
10. **Reviewer UI.** A work queue and a three-pane claim workspace.

What differs from the pack's architecture, and why, is recorded in `docs/ADR-12-phase-1-build-substitutions.md`. The status of each backlog item is mapped in `docs/traceability.md`.

## Run it

You need:

- Python 3.11 or later (tested on 3.13);
- PostgreSQL 16 server binaries (`initdb`, `pg_ctl`, `psql`) on `PATH`, or set `PGBIN`;
- the packages in `pyproject.toml`.

The repository layout matters. This folder must sit inside the research pack, because the code reads `../schemas`, `../config`, `../api` and `../fixtures`.

```bash
cd workbench
python3 -m pip install -e .            # or install the pinned dependencies listed in pyproject.toml
make test                              # 27 tests; starts a throwaway PostgreSQL cluster in /tmp for the run
make serve                             # local cluster in .devdb/, demo claims loaded, http://127.0.0.1:8080/
```

`make serve` starts a PostgreSQL cluster in `.devdb/` on port 55440, applies the migrations and creates two roles:

- `aw_app`, which the API uses;
- `aw_worker`, which the job worker uses.

Neither role can bypass row-level security. It then seeds the synthetic tenant `TENANT-DEMO` and uploads synthetic PDFs for the three demo claims. Finally it serves the API, the UI and one background worker.

To sign in, open the page and pick a synthetic user:

- `PROC-11`, a processor with a ₹1,00,000 limit;
- `SUP-02`, a supervisor;
- `MO-01`, a medical officer.

Development sign-in exists only when `AW_ENV` is `dev` or `test`. Roles and limits always come from the database, never from the token.

Other commands:

| Command | What it does |
|---|---|
| `make demo` | Runs the three demo claims through the whole pipeline without the UI and compares each evaluation with the pack's trace fixtures. Exits non-zero on any difference |
| `make ui-smoke` | Browser walk-through against a running, freshly seeded `make serve`. Needs `pip install -e ".[ui-test]"` and a Playwright Chromium |
| `make db` / `make db-stop` | Start or stop the local cluster. `source .devdb.env` gives you `AW_OWNER_DSN`, `AW_DATABASE_URL` and `AW_WORKER_DSN` |
| `make clean` | Stop the cluster and remove `.devdb/`, `.objects/` and caches |

### What a reviewer can do in the UI

- **Work queue** (S-01). Claims are sorted by settlement due time. Each row shows the recommendation, the proposed payable and the number of blocking findings. Patient names are masked.
- **Claim workspace** (S-02 to S-05). It has three panes:
  - **Left:** documents with their status, an upload form (supersede a document) and the resolved facts. A conflicting fact can be resolved by choosing the value the evidence supports.
  - **Centre:**
    - bill lines with deductions grouped by rule, plus the claim ladder;
    - findings (blocking, medical officer, pattern-for-review) with their actions;
    - drafted queries, which a person approves before they are released;
    - the decision panel, with approval limits and a request for second approval;
    - the audit trail, with chain verification.
  - **Right:** the evidence viewer. It shows the source page with the cited text highlighted, plus the rule, formula, clause authority and override form for a deduction.
- **Keyboard:** `J`/`K` move between rows, `E` opens evidence, `G` then `D` opens the decision panel, `N` opens the next claim and `?` shows help.

## Layout

| Path | Contents |
|---|---|
| `migrations/0001_schema.sql` | The pack's `db/schema.sql`, byte-identical (a test checks this) |
| `migrations/0002_app_support.sql` | Application columns, job-queue policy for the worker role, least-privilege grants |
| `src/aw/db/` | Database facade (psycopg if installed, otherwise the stdlib wire client `pgwire.py`), tenant transactions, migration runner |
| `src/aw/ingest.py`, `storage.py`, `extraction/` | Upload, quarantine, deduplication, page rendering, classification, extraction providers, grounding, normalisation |
| `src/aw/facts.py`, `matching.py` | Fact resolution, conflicts, bill-line categorisation, name matching |
| `src/aw/engine/` | Rule engine |
| `src/aw/evaluations.py` | Engine input, evaluations, findings, STALE/SUPERSEDED, diffs |
| `src/aw/review.py`, `queries.py`, `decisions.py`, `exports.py` | Reviewer actions, queries, decisions and approvals, worksheets and export |
| `src/aw/configs.py` | Configuration artifacts: drafts, four-eyes publish, effective dating |
| `src/aw/audit.py`, `jobs.py`, `auth.py` | Hash-chained audit, job queue (`SKIP LOCKED`), principals and permissions |
| `src/aw/api/` | HTTP API and the OpenAPI contract layer |
| `src/aw/web/` | Reviewer UI (no build step, no third-party code) |
| `src/aw/seed.py`, `synthetic.py`, `demo.py`, `server.py` | Synthetic tenant, synthetic PDFs, end-to-end demo, development server |
| `tests/` | Engine equivalence, foundation, API and workflow tests; browser smoke test |
| `docs/` | ADR-12 and backlog traceability |
| `Dockerfile`, `docker-compose.yml`, `../.github/workflows/workbench-ci.yml` | Container and CI definitions. **Written but not yet run** |

## Configuration

All configuration comes from environment variables (`src/aw/settings.py`).

| Variable | Meaning |
|---|---|
| `AW_DATABASE_URL` | Application role DSN (required) |
| `AW_WORKER_DSN` | Worker role DSN (required for the in-process worker) |
| `AW_OWNER_DSN` | Owner DSN, used only for migrations and `--seed-demo` |
| `AW_ENV` | `dev`, `test` or `prod`. `prod` refuses development tokens |
| `AW_DEV_TOKEN_SECRET` | HMAC secret for development tokens. A fixed development default is used in `dev` and `test` |
| `AW_OBJECT_STORE_DIR` | Directory for the local write-once store (default `.objects/`) |
| `AW_EXTRACTION_PROVIDER` | `heuristic` (default), `fixture` (with `AW_FIXTURE_DIR`) or `bedrock` (stub, never executed) |
| `AW_PACK_DIR` | Research pack root (default: the parent of this folder) |

## Limits — read before relying on anything here

- **Synthetic only.** The heuristic extractor reads the text layer of the synthetic PDFs that `synthetic.py` generates. It has not been tried on a real hospital document. Scanned pages fail with `NO_TEXT_LAYER_OCR_NOT_CONFIGURED`, because there is no OCR yet (BL-07, BL-08).
- **Illustrative configuration.** The policy, tariff, NME list and classifier map are illustrative. None is a real product wording.
- **Unexecuted adapters.** The psycopg driver path, the Bedrock provider, the S3 Object Lock store and OIDC sign-in are written but have never run. The same is true of the CI workflow, the Dockerfile and the compose file.
- **Placeholder text.** The grievance block in the worksheet is placeholder text until counsel provides the wording (E-REG-04). Query letters have no template or export yet.
- **Not built yet:**
  - TMS adapter;
  - TAT alerts;
  - config replay;
  - anchoring of audit chain heads;
  - clinical summary;
  - load testing;
  - accessibility audit.
- **Development server only.** `python -m aw.server` runs the API and one worker in a single process and binds to loopback. It is not a production deployment.
