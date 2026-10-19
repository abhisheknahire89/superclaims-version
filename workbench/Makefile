# Adjudication Workbench — developer commands. Run from workbench/. See README.md "Run it".
# Needs: Python >= 3.11, PostgreSQL 16 server binaries (brew install postgresql@16), Tesseract (brew install tesseract).
SHELL := /bin/bash
AW_DEV_DIR ?= $(CURDIR)/.devdb
PY ?= $(CURDIR)/.venv/bin/python
PORT ?= 8080
# .env holds generated local secrets (never committed or printed); make creates it on first use.
-include .env
export

.PHONY: help env setup check db db-stop serve worker test test-pgwire test-all demo e2e ui-smoke corpus measure pack-check \
        backup restore docker-up docker-down clean

help:
	@echo "make serve        start everything: database, migrations, demo tenant, API + worker on http://127.0.0.1:$(PORT)"
	@echo "make test         unit, integration and API tests (psycopg driver); make test-all also runs the stdlib driver"
	@echo "make e2e          headless-browser walk-through of every workflow, with screenshots in e2e-shots/"
	@echo "make demo         the pack traces end to end without the UI; exits non-zero on any difference"
	@echo "make corpus       generate the synthetic test corpus; make measure scores extraction on it"
	@echo "make pack-check   re-run the research pack's verification build"
	@echo "make backup       dump the database and object store into .backups/; make restore BACKUP=<dir> restores one"
	@echo "make docker-up    the same stack in Docker (needs Docker Desktop)"
	@echo "make clean        stop the database and remove local state"

.env:
	@python3 scripts/make_env.py .env

env: .env

setup: .venv/.installed

.venv/.installed: pyproject.toml
	@PYBIN=$$(for p in python3.13 python3.12 python3.11 python3; do command -v $$p >/dev/null 2>&1 && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' && { echo $$p; break; }; done); \
	  if [ -z "$$PYBIN" ]; then echo "Python >= 3.11 is required" >&2; exit 1; fi; \
	  [ -x .venv/bin/python ] || $$PYBIN -m venv .venv
	@$(PY) -m pip install -q --upgrade pip
	@$(PY) -m pip install -q -e ".[ui-test]"
	@touch $@

check: setup
	@scripts/find_pg.sh >/dev/null
	@command -v tesseract >/dev/null || { echo "Tesseract not found. On macOS: brew install tesseract (scanned documents need it)" >&2; exit 1; }
	@echo "prerequisites: ok"

db: setup .env
	@PY=$(PY) scripts/dev_db.sh start > .devdb.env
	@chmod 600 .devdb.env

db-stop:
	@scripts/dev_db.sh stop

serve: check db
	@. ./.devdb.env && PYTHONPATH=src $(PY) -m aw.server --seed-demo --port $(PORT)

worker: db
	@. ./.devdb.env && PYTHONPATH=src $(PY) -m aw.worker

test: setup
	AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=src:tests $(PY) -m unittest discover -s tests -p 'test_*.py' -t . -v

test-pgwire: setup
	AW_ENV=test AW_DB_DRIVER=pgwire AW_REQUIRE_DB=1 PYTHONPATH=src:tests $(PY) -m unittest discover -s tests -p 'test_*.py' -t .

test-all: test test-pgwire

demo: db
	@. ./.devdb.env && PYTHONPATH=src $(PY) -m aw.demo

e2e: setup .env
	PYTHONPATH=src:tests $(PY) tests/e2e.py e2e-shots

ui-smoke:
	$(PY) tests/ui_smoke.py http://127.0.0.1:$(PORT) ui-shots

corpus: setup
	PYTHONPATH=src $(PY) -m aw.corpus.generate corpus/out

measure: setup
	PYTHONPATH=src $(PY) -m aw.corpus.measure corpus/out

pack-check: setup
	cd .. && PATH="$(CURDIR)/.venv/bin:$$PATH" PGBIN=$$(workbench/scripts/find_pg.sh) bash verification/build_all.sh

backup: db
	@. ./.devdb.env && PY=$(PY) scripts/backup.sh backup

restore: setup
	@. ./.devdb.env && PY=$(PY) scripts/backup.sh restore "$(BACKUP)"

docker-up: .env
	docker compose up --build -d
	@echo "waiting for http://127.0.0.1:$(PORT)/readyz ..."; for i in $$(seq 1 120); do curl -sf http://127.0.0.1:$(PORT)/readyz >/dev/null && { echo ready; exit 0; }; sleep 2; done; echo "not ready; see: docker compose logs" >&2; exit 1

docker-down:
	docker compose down

clean:
	-@scripts/dev_db.sh stop
	rm -rf .devdb .devdb.env .objects ui-shots e2e-shots corpus/out
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
