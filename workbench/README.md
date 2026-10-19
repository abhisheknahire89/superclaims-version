# Adjudication Workbench — local synthetic product

AW reads documents locally, recommends evidence-linked adjustments and lets a person record the disposition. It covers IPD reimbursement, provisional cashless preauthorization/enhancement, cashless discharge and OPD reimbursement. Only synthetic data is supported by this delivery. No hosted model/OCR, paid application service or external delivery is enabled.

## Run it

Keep `workbench/` inside this repository: its parent provides the normative API, schemas, configs and fixtures. Prerequisites: Python3.11+ (tested3.13.15), PostgreSQL16 server binaries, Tesseract5, and Chromium for browser verification. On the tested Mac, PostgreSQL16 is under `/opt/homebrew/opt/postgresql@16/bin`; the scripts detect it. Existing Homebrew prerequisites can be installed by the user with `brew install postgresql@16 tesseract` if absent.

```bash
cd /Users/abhishekpravinnahire/Desktop/SUperclaims/workbench
make setup
make check
make serve
```

`make setup` creates `.venv` and installs pinned Python dependencies; it needs a package source or populated pip cache. `make serve` creates private ignored `.env` secrets, starts a loopback PostgreSQL16 cluster, applies migrations0001–0006, seeds six undecided synthetic claims and starts FastAPI, the worker and maintenance scheduler at [localhost8080](http://127.0.0.1:8080/). `/healthz` is liveness; `/readyz` checks DB/storage/worker configuration. Ctrl-C stops the application; `make db-stop` stops its DB. Keep `.env` and `.devdb.env` private; never print or commit them.

All TENANT-DEMO seed accounts use **Synthetic-demo-2026!**, a public password for synthetic development accounts only. User IDs: PROC-07 (processor,₹150000 limit), PROC-11 (processor,₹100000), SUP-02 (supervisor,₹500000), MO-01 (medical officer,₹100000), FWA-01, AUD-01, CFG-01 (configuration author), ADM-01 (tenant administrator/second publisher), RO-01 (masked read-only). Login accepts tenant/user/password; local sessions are HttpOnly, CSRF-protected, revocable and expire after8hours. OIDC is an unconfigured future interface. Production mode does not expose demo login buttons; this synthetic seed is not a production identity deployment.

For an isolated fresh demo, leaving existing state intact:

```bash
make serve AW_DEV_DIR=/tmp/aw-fresh-demo AW_DEV_PORT=55470 AW_OBJECT_STORE_DIR=/tmp/aw-fresh-demo/objects
```

Use a new directory/unused port each time a **fresh** seed is needed. Seed startup does not erase prior decisions. The default DB is `.devdb`/55440 and default objects `.objects`; `PORT` controls the HTTP port. Do not run `serve`, `db`, `demo` or `backup` commands concurrently: they share `.devdb.env`. Browser flows below require HTTP8080.

## Verify

```bash
make test-all
make pack-check
make demo AW_DEV_DIR=/tmp/aw-trace-demo AW_DEV_PORT=55471 AW_OBJECT_STORE_DIR=/tmp/aw-trace-demo/objects
```

The full suite currently contains71 tests on **each** psycopg and pgwire, with required DB tests (no silent skips). The pack also runs rule traces,3000 property cases, schema checks, mutation tests and negative DB/RLS checks. Five exact traces must remain:109360.50→107591.00;172455.75→85000.00;L14override admissible102385.75/payable85000.00;3a no payable/QUERY_AND_REFER_MEDICAL;3b85570.00/REFER_MEDICAL. `demo` records human fixture actions through the services, not automatic decisions.

Install the browser once if missing (a development dependency, not an application service):

```bash
.venv/bin/python -m playwright install chromium
```

Start a fresh `make serve` in one terminal, then in another:

```bash
make e2e
```

This sequentially measures evidence-highlight timing and submits an override; runs queue/second approval/audit smoke; manual source-grounded and explicit human-transcription entry; assignment/filter/KPI/queryPDF/reply/admin screens; all four human-decision workflows and linked enhancement registration; and config draft/validation/replay/four-eyes publication with password confirmation. It mutates the demo. Screenshots are in `e2e-shots/` and `evidence/2026-10-12/`; timing samples are in `reviewer-ui-benchmark.json`. Run against a new seed each time. `make ui-smoke` runs only the original smoke subset.

## Backup and restore

Stop the writing app first for a consistent local drill; the DB remains running. Use the SAME DB/object settings as its startup:

```bash
make backup AW_DEV_DIR=/tmp/aw-fresh-demo AW_DEV_PORT=55470 AW_OBJECT_STORE_DIR=/tmp/aw-fresh-demo/objects
make restore BACKUP=.backups/<reported-backup-id>
```

The backup is a PostgreSQL custom dump plus immutable objects and a hash manifest. Restore verifies the exact file set and hashes, refuses symlinks/existing targets, creates a NEW `aw_restore_*` database/object directory, then verifies all original hashes against the DB, referenced pages/local exports, audit chains and anchors. It never replaces a running DB. A failed post-restore validation leaves the newly named target for diagnosis; do not treat it as verified. Restored object directories default inside the source backup; use a separate object destination through `python -m aw.backup restore ... --objects ...` if retaining a pristine reusable backup. The stopped-writer drill was actually run; no online atomic-snapshot guarantee is claimed.

Actual final drill: eight claims,32documents,five human decisions,eight verified chains,109referenced object reads; restricted restored-app login/read200 and other-tenant0visible claims. See `evidence/2026-10-12/m6-{backup,restore,restored-app}.log`.

## Review and configure

The queue masks names and sorts deadlines. Filter by status/workflow/assignment/deadline/reference; supervisors assign active reviewers. The workspace shows source pages with quote/bbox highlights, bill deductions and policy/tariff authority, manual corrections with preserved provenance, findings, queries, human decision/second approval/insurer CRC path, audit and local exports. Keyboard: J/K rows, E evidence, G then D decision, N next claim, ? help; forms have accessible labels. Native/scanned PDF,PNG/JPG,multiple uploads and bounded ZIP are supported; OCR uses local Tesseract, deskew/denoise and generic rules. Visual transcription explicitly records the reviewer and immutable image hash; it never pretends to be machine extraction.

Configuration supports local version/draft/validate/diff/replay/publish for policies, tariffs/packages,NME,checklists,workflow ordering/limits and classifier maps. CSV/XLSX imports patch local configuration only and reject formulas. Publication needs a distinct administrator and password confirmation. Retroactive updates explicitly queue eligible open claims; decisions remain human. Operations shows actual queue/decision/job/query/correction/override counts. Tenant administration manages local users/roles/limits/activation/password resets, preserves role history and revokes sessions; last-supervisor/self-lockout protections apply.

## Limits and status

See [DELIVERY.md](DELIVERY.md) for the three-state feature matrix,10-minute demo, measured accuracy and customer materials. Extraction performance is inadequate for unattended hospital-document reading: original blind held-back results were poor. Revised-layout regression results are labelled revealed and are not presented as blind accuracy. Material identity/date/amount conflicts and untrusted/low-confidence evidence abstain; targeted product probes verify refusal of blocked approvals. No accuracy on handwriting or real claims is claimed.

Local immutable files/checksum sidecars and append-only audit anchors resist application mutation; a host administrator controlling DB and disk can replace both. They are not an external trusted anchor or compliance WORM guarantee. Security findings and actual remediation checks are in `evidence/2026-10-12/final-independent-review.md` and ADR13–19. Original migrations0001/0002 remain unchanged; new schema is numbered0003–0006.

Docker definitions and CI are **not run here**: Docker daemon unavailable, no remote CI triggered. To enable a future Docker run, open Docker Desktop and wait until its engine is running. `make docker-up` is supplied but unverified; do not infer native-test results prove containers. Existing bulk-import/TMS receiver routes are inherited; no new integration,webhook/API key,TMS adapter,cloud storage,hosted AI or external query delivery was built. A shared-platform security guard now blocks unauthorized withdrawal through the inherited receiver; its handler/schema are unchanged (ADR19). React migration, production IdP,real customer rulebooks and independent external security/compliance acceptance are outside this local delivery.

## Insurance Policy Intelligence (local, shadow only)

`http://127.0.0.1:8080/#/policy` provides source-page review, explicit interpretation,
ordered validation/review and separate-user approval/publication. Use CFG-01 and ADM-01
in TENANT-DEMO with the synthetic demo password. Published policy-intelligence records
are shadow mappings and never update the demonstration's runtime rules.

From the repository root, using the existing local environment:

```sh
PYTHONPATH=workbench/src workbench/.venv/bin/python -m aw.policy_intelligence.acquisition --root workbench/.policy-research import /absolute/path/corrected-manifest.csv
PYTHONPATH=workbench/src workbench/.venv/bin/python -m aw.policy_intelligence.acquisition --root workbench/.policy-research report
PYTHONPATH=workbench/src workbench/.venv/bin/python -m aw.policy_intelligence.acquisition --root workbench/.policy-research download 'IMPORT_SHA:LINE'
PYTHONPATH=workbench/src workbench/.venv/bin/python -m aw.policy_intelligence.extraction --root workbench/.policy-research 'IMPORT_SHA:LINE'
PYTHONPATH=workbench/src workbench/.venv/bin/python -m aw.policy_intelligence.illustrative --root workbench/.policy-illustrative
```

Manifest columns: insurer_name, product_name, uin, url; optional revision,
wording_effective_from/wording_effective_to, referrer_url and verification_status.
Research labels and supplied dates remain untrusted. Exact UIN reuse across conflicting
names, malformed rows, placeholders and nonofficial/webpage URLs are quarantined.
The downloader respects robots, refuses redirects/protection bypass, retains old bytes,
uses strong-ETag resume, and records actual hashes/pages/UINs. CLI extraction produces
nonexecutable UNINTERPRETED proposals only; application extraction requires separate
human source approval. Originals and transport journals are in ignored isolated roots.
Back these roots up separately from operational object storage.

The delivered preview translates only unconditional copay/per-claim deductible into the
existing deterministic engine. Unknown coverage, tariff, effective dates, options or
unsupported conditions/dependencies block effects. Complete illustrative bundles are
interface simulations; customer/insurer evidence verification is not connected and
`definitive_payable` is always null. See [POLICY_INTELLIGENCE_DELIVERY.md](POLICY_INTELLIGENCE_DELIVERY.md)
for executed proof, source coverage, limits and the demonstration script.

Product history and quarantine controls are on the same review screen. Rename/withdrawal
evidence needs exact source pages, independently checked titles and distinct approval.
The optional downloader `--quarantine-evidence` flag permits only name-reuse conflicts,
keeps them quarantined and never approves sources. Review decisions stay tenant-scoped
in PostgreSQL; malformed identity/URL conflicts require a corrected manifest.
