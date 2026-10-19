#!/usr/bin/env bash
# Print the directory holding PostgreSQL 16 server binaries (initdb, pg_ctl, psql, pg_dump).
# Order: $PGBIN; Homebrew postgresql@16 (Apple Silicon, Intel); Debian/Ubuntu; any initdb on PATH reporting 16.
# Exits 1 with advice when none is found. PostgreSQL 17 is accepted as a fallback (not the tested version).
set -euo pipefail
is_ok() { [ -x "$1/initdb" ] && "$1/initdb" --version 2>/dev/null | grep -Eq " (16|17)\."; }
for d in "${PGBIN:-}" /opt/homebrew/opt/postgresql@16/bin /usr/local/opt/postgresql@16/bin /usr/lib/postgresql/16/bin \
         "$(dirname "$(command -v initdb 2>/dev/null || echo /nonexistent/initdb)")" /opt/homebrew/opt/postgresql@17/bin /usr/lib/postgresql/17/bin; do
  if [ -n "$d" ] && is_ok "$d"; then echo "$d"; exit 0; fi
done
echo "PostgreSQL 16 server binaries not found. On macOS: brew install postgresql@16 (or set PGBIN)." >&2
exit 1
