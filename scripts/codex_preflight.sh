#!/usr/bin/env bash
# Read-only environment inventory. No installations or network calls.
set -u
printf 'Environment inventory (read-only)\n'
printf '%-21s %s\n' 'OS:' "$(uname -s) $(uname -m)"
printf '%-21s %s\n' 'Working directory:' "$PWD"
for name in python3 pip3 npm node git docker psql initdb pg_ctl tesseract make; do
  bin="$(command -v "$name" 2>/dev/null || true)"
  if [ -z "$bin" ]; then
    printf '%-21s MISSING\n' "$name:"
  else
    printf '%-21s %s\n' "$name:" "$bin"
  fi
done
if command -v python3 >/dev/null 2>&1; then python3 --version 2>&1; fi
if command -v npm >/dev/null 2>&1; then npm --version 2>&1; fi
if command -v psql >/dev/null 2>&1; then psql --version 2>&1; fi
if command -v tesseract >/dev/null 2>&1; then tesseract --version 2>&1 | head -1; fi
if command -v docker >/dev/null 2>&1; then docker info --format 'Docker daemon: {{.ServerVersion}}' 2>/dev/null || printf '%s\n' 'Docker daemon: NOT REACHABLE'; fi
if [ -f PROJECT_CONTEXT.txt ] && [ -d workbench ]; then printf '%s\n' 'Project pack: PRESENT'; else printf '%s\n' 'Project pack: INCOMPLETE or working directory incorrect'; fi
if [ -d .git ]; then printf '%s\n' 'Git: repository present'; git status --short; else printf '%s\n' 'Git: repository not initialised here'; fi
printf '%s\n' 'No dependencies installed, commands modified, or network connections initiated by this script.'
