#!/usr/bin/env bash
# Every gate the CI runs, in the order that fails fastest. Usage: ./scripts/ci.sh [--live]
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
BIN="$(dirname "$PY")"

echo "== codegen drift"
"$PY" scripts/check_drift.py

echo "== lint"
"$BIN/ruff" format --check .
"$BIN/ruff" check .

echo "== typecheck"
"$BIN/mypy"

echo "== unit + contract tests"
"$PY" -m pytest tests/unit tests/contract -q

if [ "${1:-}" = "--live" ]; then
  echo "== live tests against ${OBLODAI_LIVE_URL:?set OBLODAI_LIVE_URL}"
  "$PY" -m pytest tests/live -q
fi

echo "all gates green"
