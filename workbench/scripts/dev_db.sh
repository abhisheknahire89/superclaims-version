#!/usr/bin/env bash
# Start a throwaway PostgreSQL 16 cluster for development and tests, create the roles, run migrations.
# Usage: scripts/dev_db.sh start|stop|env   (state lives in $AW_DEV_DIR, default ./.devdb)
# Prints export lines for AW_OWNER_DSN, AW_DATABASE_URL and AW_WORKER_DSN on `start` and `env`.
set -euo pipefail
# macOS: without a valid LC_ALL the postmaster aborts with "postmaster became multithreaded during startup"
export LC_ALL="${LC_ALL:-C}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="${AW_DEV_DIR:-$ROOT/.devdb}"
PGBIN="${PGBIN:-$(dirname "$(command -v initdb 2>/dev/null || echo /usr/lib/postgresql/16/bin/initdb)")}"
PORT="${AW_DEV_PORT:-55440}"
RUNAS=""
if [ "$(id -u)" = "0" ]; then RUNAS="su postgres -c"; fi
run() { if [ -n "$RUNAS" ]; then su postgres -c "$*"; else bash -c "$*"; fi; }
APP_PW="${AW_DEV_APP_PASSWORD:-dev-only-app-pw}"
WK_PW="${AW_DEV_WORKER_PASSWORD:-dev-only-worker-pw}"
dsns() {
  echo "export AW_OWNER_DSN='postgresql://postgres@localhost:$PORT/aw?host=$DIR/sock'"
  echo "export AW_DATABASE_URL='postgresql://aw_app:$APP_PW@127.0.0.1:$PORT/aw?sslmode=disable'"
  echo "export AW_WORKER_DSN='postgresql://aw_worker:$WK_PW@127.0.0.1:$PORT/aw?sslmode=disable'"
}
case "${1:-start}" in
  start)
    mkdir -p "$DIR/sock"
    if [ -n "$RUNAS" ]; then chown -R postgres "$DIR"; fi
    if [ ! -f "$DIR/data/PG_VERSION" ]; then
      run "$PGBIN/initdb -D $DIR/data -U postgres -A trust --auth-host=scram-sha-256 -E UTF8 --locale=C >/dev/null"
      # local socket: trust for the owner (dev only); TCP: SCRAM for the app roles
    fi
    if ! run "$PGBIN/pg_ctl -D $DIR/data status >/dev/null 2>&1"; then
      run "$PGBIN/pg_ctl -D $DIR/data -o '-p $PORT -k $DIR/sock -c listen_addresses=127.0.0.1' -l $DIR/log -w start >/dev/null"
    fi
    PSQL="$PGBIN/psql -h $DIR/sock -p $PORT -U postgres -v ON_ERROR_STOP=1 -q"
    run "$PSQL -d postgres -tc \"SELECT 1 FROM pg_database WHERE datname='aw'\"" | grep -q 1 || run "$PSQL -d postgres -c 'CREATE DATABASE aw'"
    run "$PSQL -d aw -c \"DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aw_app') THEN CREATE ROLE aw_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '$APP_PW'; END IF; IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aw_worker') THEN CREATE ROLE aw_worker LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '$WK_PW'; END IF; END \\\$\\\$;\""
    eval "$(dsns)"
    PYTHONPATH="$ROOT/src" python3 -m aw.db.migrate "$AW_OWNER_DSN" "$ROOT/migrations" >&2
    dsns
    ;;
  stop)
    run "$PGBIN/pg_ctl -D $DIR/data -m fast stop >/dev/null" || true
    ;;
  env)
    dsns
    ;;
  *) echo "usage: $0 start|stop|env" >&2; exit 2 ;;
esac
