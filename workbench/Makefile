# Adjudication Workbench — developer commands. Needs PostgreSQL 16 binaries (initdb, pg_ctl, psql) on PATH,
# or PGBIN pointing at them. State for `make db` lives in $(AW_DEV_DIR).
AW_DEV_DIR ?= $(CURDIR)/.devdb
PY ?= python3
export AW_DEV_DIR

.PHONY: help db db-stop test demo serve ui-smoke clean

help:
	@echo "make db        start a local PostgreSQL 16 cluster and run migrations"
	@echo "make test      run the test suite (starts its own throwaway clusters)"
	@echo "make demo      run the three demo claims end to end and compare with the pack traces"
	@echo "make serve     API + reviewer UI + worker on http://127.0.0.1:8080 with the demo claims loaded"
	@echo "make ui-smoke  browser smoke test against a running, freshly seeded server (needs playwright)"
	@echo "make clean     remove caches, the local object store and the dev cluster"

db:
	scripts/dev_db.sh start > .devdb.env
	@echo "wrote .devdb.env — run: source .devdb.env"

db-stop:
	scripts/dev_db.sh stop

test:
	AW_ENV=test AW_REQUIRE_DB=1 PYTHONPATH=src:tests $(PY) -m unittest -v tests.test_engine_equivalence tests.test_foundation tests.test_api tests.test_workflow

demo: db
	. ./.devdb.env && PYTHONPATH=src $(PY) -m aw.demo

serve: db
	. ./.devdb.env && PYTHONPATH=src $(PY) -m aw.server --seed-demo

ui-smoke:
	$(PY) tests/ui_smoke.py http://127.0.0.1:8080 ui-shots

clean:
	-scripts/dev_db.sh stop
	rm -rf .devdb .devdb.env .objects ui-shots
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
