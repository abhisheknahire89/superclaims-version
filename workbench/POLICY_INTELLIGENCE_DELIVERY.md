# Insurance Policy Intelligence — executed delivery

13 October 2026. Extension of the existing Adjudication Workbench. The delivered code
was backed up before edits; original repository HEAD remains6bba0ddf. No push, paid
application service, hosted model/OCR, patient information or public deployment.

The working review screen is http://127.0.0.1:8080/#/policy. Public wording, issued
member contract, current coverage and hospital agreement remain separate. A PDF is
never evidence of a member's remaining cover or negotiated tariff. All public sources
remain pending human approval. Only an expressly illustrative derivative was approved
in the automated browser simulation. No extracted public rule was auto-approved.

| Feature | Status | Executed proof / limit |
|---|---|---|
| CSV validation, quarantine reasons, preserved raw input | Built and tested | Old102-row catalogue:101 quarantined,1 discovered; labels never promote trust |
| Local bounded HTTPS downloader, HTML rejection, strong-ETag resume | Built and tested | Controlled failure/resume tests; official-host retrieval, robots restrictions respected |
| Hash deduplication, changed URL, append-only provenance, original versions | Built and tested | Same/different-import changes retain old bytes; integrity and archive/restore checks |
| Insurer/UIN/revision registry, tenant RLS, immutable audit | Built and tested | New0007–0010, source quotes, conflicts, negative tenant tests |
| Clause scanner, source SHA/page/quote/bounding box/context | Built and tested | 344 native-PDF proposals; exact quotations/boxes checked, interpretations UNKNOWN |
| Source-page admin review and four-eyes shadow lifecycle | Built and tested | Browser rejects author approval; separate user approves/publishes illustrative rule |
| Deterministic preview adapter | Built and tested | Unconditional COPAY/per-claim DEDUCTIBLE only; same engine; no runtime writes |
| Missing member/coverage/tariff dependency and state matrix | Built and tested | Blank proofs, stale coverage, reservations, unknown dependencies/dates/options block effects |
| Public PDF source/product contractual approval | Blocked by missing evidence | Machine matches are not human review; unknown revision dates remain UNKNOWN |
| Five verified products for each of four insurers | Blocked by missing evidence | Current coverage below; no invented documents or UINs |
| Named audit workbook and corrected research exports | Blocked by missing evidence | File not found; inspection NOT RUN, pending supplied local path |
| Actual issued schedules, live balances, endorsements, contracted tariffs | Requires customer/insurer data | Interfaces only; private proofs not independently connected |
| Conditional/group/restoration/room-rate and other clause translations | Not built | Draft categories exist; unsupported financial translation generates review task |
| Evidence-reviewed product names and withdrawal history | Built and tested | Grounded names/status/date, canonical SHA, distinct author/approver; historical originals retained |
| Interactive quarantine resolution/rejection workflow | Built and tested | Tenant-scoped atomic audit overlays; same approved hash/identity required; bad metadata needs corrected import |
| Live insurer/TPA integration, bulk operational import or auto-disposition | Not built | Existing integration routes unchanged; definitive payable always null |
| Policy-wording scan/OCR-quality validation | Built but not tested | No labelled policy-rule ground truth; confidence UNMEASURED, no accuracy claim |

## Actual public source coverage

All original PDFs are isolated in ignored `workbench/.policy-research/originals/`.
Illustrative derivatives are isolated in `.policy-illustrative/`. Acquisition journals
retain URL, original CSV/hash/row, retrieval time, HTTP metadata, actual UINs and SHA.

| Insurer / candidate | Result | Original |
|---|---|---|
| Niva Bupa / ReAssure | Downloaded45pages; unique actual UIN NBHHLIP26050V042526; source review pending | SHA366e08afe7e9b71238d74db9e9988767c901b8e3eabca7ffc30c4892c6b210c5 |
| Niva Bupa / Health Companion | Downloaded37pages; unique actual UIN NBHHLIP26051V092526; source review pending | SHA209a0e88f19e44f5b414955b014856d68235a3fbbcd3aa158a2183e2a4622303 |
| Care Health / Care Classic | Downloaded38pages; METADATA_CONFLICT, two actual UINs CHIHLIP22047V012122/CHIHLIP22071V012122 | SHAefc6006f49c97cc3e4532f85ba86efc266c20e5763c6b7c2af345aa88b7ef302 |
| HDFC ERGO / Optima Secure | Robots denied; no local PDF or verified content | Not downloaded |
| Star Health / SuperStar CDN candidate | Robots permission unavailable; no bypass | Not downloaded |

The two Niva wordings came from official transactions.nivabupa.com; the Care candidate
from cms.careinsurance.com. Full original URLs, responses and quarantine reasons are in
[evidence/source coverage](evidence/2026-10-13/source-coverage.json). No effective dates
or contractual revision labels were guessed. Care's conflicting identifiers are not
usable financial authority. The requested target of20 verified products is not met.

ReAssure native extraction:201 candidates across45pages in7.044s. Health Companion:
143 candidates across37pages in4.285s, on this Mac. These are keyword/context proposals,
not validated contractual rules or measured accuracy. [Benchmark](evidence/2026-10-13/policy-benchmark.json),
[ReAssure drafts](evidence/2026-10-13/niva-reassure-draft-proposals.json),
[Health Companion drafts](evidence/2026-10-13/niva-companion-draft-proposals.json).

## Execution evidence

Baseline71 tests per driver passed before edits. Final suite95 tests per driver;
exact duplicate inherited test methods were deduplicated without removing any unique
assertion. [Final tests](evidence/2026-10-13/m7-final-95-tests.log).
[Clean local checkout](evidence/2026-10-13/clean-checkout-proof.json) repeated the earlier89-test baseline on both drivers,
full pack, fresh startup and exact demo before the product-history addition; existing installed local venv reused, no installer.
[Runtime integrity](evidence/2026-10-13/policy-runtime-integrity.json) confirms identical
configuration hashes and evaluation/ledger/decision counts across the delivered browser run.
[Full pack](evidence/2026-10-13/m7-pack-check.log):59 contracts,8 mutation catches,
3000 financial-property cases, negative DB/RLS checks. Existing five exact-money traces
unchanged; [end-to-end demo](evidence/2026-10-13/m7-6-demo.log).

[Policy browser](evidence/2026-10-13/m7-history-browser-final.log) and
[structured proof](evidence/2026-10-13/policy-browser-proof.json) exercise actual source
intake/page viewing, unapproved-source rejection, illustrative evidence interpretation,
ordered four-eyes publication, blocked unknown inputs and same-engine comparison.
Baseline107591.00 versus illustrative shadow96831.00 is not a complete real policy
calculation. All deductions retain evidence and contractual authority; definitive
payable remains null. Tests assert zero evaluation/ledger/runtime configuration writes.

[Existing browser pack](evidence/2026-10-13/m7-existing-browser.log) passed reviewer,
manual reading, query, operations, all four workflows and configuration flows in a
separate fresh test seed. Its test publication did not modify the delivered review DB.
[Independent review](evidence/2026-10-13/policy-independent-review.md) reproduced and
retested fixes for private proofs, expiry-date grounding and corrected-import versioning.
It was a targeted review, not an exhaustive security audit.

Public research [backup](evidence/2026-10-13/public-backup-drill.json) and
[restore](evidence/2026-10-13/public-restore-drill.json) executed. Stopped-writer review DB
[backup](evidence/2026-10-13/m7-review-backup.log),
[restore](evidence/2026-10-13/m7-review-restore.json) and
[restored policy integrity](evidence/2026-10-13/m7-restored-policy-integrity.json) executed;
original source hashes and negative tenant visibility checked after restoration.

Screenshots: [public PDF](evidence/2026-10-13/policy-public-source.png),
[reviewed evidence](evidence/2026-10-13/policy-reviewed-evidence.png),
[missing-input refusal](evidence/2026-10-13/policy-blocked-inputs.png),
[shadow comparison](evidence/2026-10-13/policy-shadow-preview.png).

## Startup and ten-minute demonstration

From repository root:

```sh
make -C workbench serve PORT=8080 AW_DEV_DIR=/tmp/aw-m7-delivered AW_DEV_PORT=55592 AW_OBJECT_STORE_DIR=/tmp/aw-m7-delivered/objects
```

Stop the current HTTP process before restarting. Reuse this directory to preserve
review records; select a new directory and free DB port for a fresh demonstration.
Tenant TENANT-DEMO, CFG-01 author and ADM-01 approver; password Synthetic-demo-2026!.
The private generated `.env` must remain private. README contains import/download/
report/offline-extraction/illustrative-fixture commands. No model download required.

1. Minutes0–2: open Policy Intelligence as CFG-01; inspect quarantined research report,
   a downloaded Niva source's SHA/UIN/original page and pending human identity approval.
2. Minutes2–4: select the clearly illustrative source; show its original synthetic
   clause and independently verified identity/revision. Public approval is still pending.
3. Minutes4–6: show DRAFT interpretation, exact evidence, conditions/exceptions and date
   quote. Validate/review; demonstrate author self-approval refusal. ADM-01 approves and
   publishes the shadow rule with password confirmation.
4. Minutes6–8: preview empty member/coverage/tariff layers. Read verification tasks;
   missing remaining cover and tariffs yield no draft financial effects.
5. Minutes8–10: use the explicit illustrative bundle in browser proof, with coverage
   snapshot updated to today's IST date. Show the exact synthetic comparison, deduction
   authority, unchanged runtime rules and null definitive payable. Explain that actual
   member/insurer evidence and contract review are required before any customer pilot.

Pilot prerequisite checklist: qualified policy reviewers verify source identity,
revision, complete clauses and date evidence; customer supplies issued schedules/options,
renewal/endorsement information, authoritative current SI/reservations/utilisation and
signed hospital agreements. Agree a labelled validation corpus and accuracy/abstention
acceptance thresholds. No operational publication or live/private-data adapter is
claimed here. PROJECT_CONTEXT records each milestone's executed results and limits.

Source and research originals have durable local backups under workbench/.backups/;
[Source backup manifest](evidence/2026-10-13/final-source-backup.json) records the exact
archive/hash. Original repository HEAD remains unchanged; no push was performed.

Product-history extension: rename proposals must bind an existing marketing identity
and independently verified source titles, with canonical SHA/page quotations. Withdrawal
needs explicit original evidence and blocks unsupported continuation assumptions.
Name-conflict evidence can be downloaded only with explicit CLI --quarantine-evidence,
stays quarantined, and cannot feed candidate extraction before distinct-user alias
approval and source review. Malformed/UIN/host conflicts cannot use that exception.
Quarantine rejection/resolution is a tenant-scoped append-only PostgreSQL overlay;
it never mutates the shared acquisition journal, is atomic with its review audit and
binds resolutions to the exact current hash. See [history browser](evidence/2026-10-13/m7-history-browser-final.log),
[history screenshot](evidence/2026-10-13/policy-product-history.png) and
[quarantine screenshot](evidence/2026-10-13/policy-quarantine-review.png).

Git handover19October2026: user authorised pushing to the named GitHub repository.
Local secrets/runtime stores/research originals remain excluded. Current95-test
execution evidence is preserved; no fresh test run is claimed for this publishing task.
