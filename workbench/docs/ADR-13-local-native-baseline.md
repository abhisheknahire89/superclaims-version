# ADR-13 — Native Mac baseline

Accepted 12 October 2026. The current assignment supersedes ADR-12's sandbox substitutions: use the existing FastAPI migration and psycopg 3, retain the ES-module UI and local storage. Delivered document reading uses local Tesseract; hosted OCR/models are outside scope. Preserve the original migrations and integration endpoints.

The starting working tree already contained the FastAPI route split and pinned dependencies. This run restored the missing tests/__init__.py so documented unittest discovery works. Verification: 27 tests on psycopg 3.3.6 and 27 on pgwire, five end-to-end money traces, headless UI smoke (zero errors), and full pack verification on native PostgreSQL 16.15. Docker daemon unavailable; Docker verification NOT RUN.
