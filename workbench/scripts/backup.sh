#!/usr/bin/env bash
set -euo pipefail
PYTHONPATH=src "${PY:-.venv/bin/python}" -m aw.backup "$@"
