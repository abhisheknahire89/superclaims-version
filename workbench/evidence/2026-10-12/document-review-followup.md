# Independent follow-up review — Milestone 1 remediation

12 October 2026. Same scope/limits as document-review.md. Reviewer changed no implementation; the parent implemented remediation while this review was running. No credentials read or external services called.

## Final executed evidence

`cd workbench && AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=src:tests .venv/bin/python -m unittest tests.test_document_reading -v`: **15 passed, 0 failed/skipped**, 3.282 seconds in final reviewer rerun. This includes actual native/JPG/PNG/scanned-PDF reading, schema/value/bbox rejection, minimum stacked confidence, pre-render raster rejection, manual/human evidence, negative tenant RLS and append-only update rejection, oversized signed upload and unreadable continuation gating.

An independent ephemeral integration probe (not added to implementation) verifies that setting one active bill page to NONE puts that document in `build_engine_input().document_reading_blocks`. It also exercises a signed upload with declared size/hash for `1234`: short body `12` is rejected **422**, then correct retry accepted **201** and stored bytes equal `1234`.

## Original findings disposition

| Original finding | Current disposition / evidence |
|---|---|
| Stacked OCR confidence inflated | Fixed: both stacked-label branches take minimum source confidence and union geometry. Targeted test runs .40 value-confidence case. |
| Unbounded upload/staging | Fixed for per-request limits: stream stops at declared/50 MB ceiling; exact size/hash checked before write. Generic JSON capped at 2 MB. Oversize test + short-upload recovery probe executed. |
| Unbounded PDF raster/pages | Fixed for declared page/dimension budgets: 100 pages, 40M pixels/page, 200M total rendered pixels; render itself checks dimensions. Oversized page test executed. This is not an exhaustive PDF parser complexity audit. |
| Unreadable continuation absent from gates | Fixed: original document_page NONE rows require human reviewed_complete record; otherwise document blocks financial calculation. Explicit continuation test and independent gate probe executed. |
| Manual entry requires successful OCR | Fixed: human transcription references source image SHA-256, page/geometry, user and full-page review state; immutable rows in migration 0003 have forced tenant RLS and append-only trigger. Empty-OCR test executed. |
| Malformed ZIP unexpected error | Expected BadZipFile/RuntimeError/NotImplementedError mapped to safe 422 by current code. Traversal/safe ZIP tests ran. Specific bad CRC/encryption/unsupported compression API trials NOT RUN by reviewer. |
| Automatic quote-only grounding | Fixed for reviewed money/date/text/line values and bounded overlapping geometry through verify_record. True quote + false money and invalid bbox test executed. |

## Additional defects found and resolved during follow-up

An independent repeat-transcription probe initially showed first manual fact tagged HUMAN_TRANSCRIPTION with a transcription id, but re-confirming the same quote lost the provenance link. `manual.py` now detects existing human lines and preserves transcription_ids; explicit human confirmation always records an image-bound transcription. UI now submits full-page review whenever human-source checkbox is selected, including an existing OCR quote. The repeated-confirmation regression is included in final passing HumanTranscription test.

A second executed staging probe initially accepted short bytes (201), returned 200 on a correct retry and retained size 2. Exact size/hash validation before persistence fixes this; final independent probe confirms 422 then 201 recovery.

The new repeated-confirmation test exposed request-body mutation: injected provenance fields made subsequent schema validation fail. Intermediate reviewer rerun: 14 tests, 13 passed/1 error (invalid-manual-reading at test_document_reading.py repeated confirmation). `confirm()` now deep-copies its body. Final 15-test rerun passed; the intermediate failure is retained here for honest evidence.

## Remaining review limits

No unresolved blocker from the original seven findings was established in the final reviewed tree. This does not certify production security or document-reading accuracy. Human transcription explicitly relies on an authorised person's visual assertion; it is not machine proof that pixels contain a quote. Whole-page completion must remain a deliberate reviewer assertion. Full suite, all browser paths, adversarial parser fuzzing, multi-user resource exhaustion, malicious ZIP matrix and host-admin tamper resistance were NOT RUN by this reviewer; parent milestone evidence must cover required broader verification. Human transcription status/link visibility in the evidence viewer was inspected in code but not browser-verified here.
