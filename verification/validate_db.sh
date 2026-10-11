#!/usr/bin/env bash
# Validate db/schema.sql on a throwaway PostgreSQL 16 cluster, load the trace outputs,
# run the reconciliation query, the negative tests, and an RLS isolation test.
# Usage (from pack root): bash verification/validate_db.sh   — requires PostgreSQL 16 binaries (PGBIN or on PATH).
# As root it runs the server as the 'postgres' OS user; otherwise as the current user (macOS, CI runners).
set -euo pipefail
PACK="$(cd "$(dirname "$0")/.." && pwd)"
PGBIN="${PGBIN:-$(dirname "$(command -v initdb 2>/dev/null || echo /usr/lib/postgresql/16/bin/initdb)")}"
export LC_ALL="${LC_ALL:-C}"   # macOS: the postmaster aborts without a valid locale
WORK="$(mktemp -d /tmp/aw-validate-XXXXXX)"
if [ "$(id -u)" = "0" ]; then chown postgres "$WORK"; as_pg() { su postgres -c "$1"; }; else as_pg() { bash -c "$1"; }; fi
PORT=55433
python3 "$PACK/verification/db_load_sql.py" > "$WORK/load.sql"
cp "$PACK/db/schema.sql" "$WORK/schema.sql"
cat > "$WORK/rls.sql" <<'SQL'
CREATE ROLE app_rw LOGIN NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO app_rw;
SET ROLE app_rw;
SET app.tenant_id = 'SOME-OTHER-TENANT';
SELECT 'rows visible to other tenant' AS check, count(*) AS n FROM claim;
SET app.tenant_id = 'TENANT-DEMO';
SELECT 'rows visible to own tenant' AS check, count(*) AS n FROM claim;
RESET ROLE;
SQL
if [ "$(id -u)" = "0" ]; then chown postgres "$WORK"/*; fi
as_pg "$PGBIN/initdb -D $WORK/data -A trust -U postgres -E UTF8 --locale=C >/dev/null"
as_pg "$PGBIN/pg_ctl -D $WORK/data -o '-p $PORT -k $WORK -c listen_addresses=' -l $WORK/log -w start >/dev/null"
trap 'as_pg "$PGBIN/pg_ctl -D $WORK/data -m fast stop >/dev/null" || true; rm -rf "$WORK"' EXIT
PSQL="$PGBIN/psql -h $WORK -p $PORT -U postgres -v ON_ERROR_STOP=1 -q"
as_pg "$PSQL -f $WORK/schema.sql"
echo "schema applied: $(as_pg "$PSQL -tAc \"select count(*) from information_schema.tables where table_schema='public'\"") tables"
as_pg "$PSQL -f $WORK/load.sql" 2>&1 | sed 's/^psql:[^ ]* //'
as_pg "$PSQL -f $WORK/rls.sql"
