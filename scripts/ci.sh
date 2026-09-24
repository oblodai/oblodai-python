#!/usr/bin/env bash
# Every gate the CI runs, in the order that fails fastest. Usage: ./scripts/ci.sh [--live]
#
# Works both in a repository-local .venv and on a clean checkout where `pip install -e ".[dev]"`
# put the tools on PATH: each tool is looked up, never assumed to sit next to the interpreter.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -x ".venv/bin/python" ]; then
  export PATH="$PWD/.venv/bin:$PATH"
fi
PY="$(command -v python3 || command -v python)"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing $1 - run: python -m venv .venv && .venv/bin/pip install -e \".[dev]\"" >&2
    exit 1
  }
}
need ruff
need mypy

echo "== generated code drift"
"$PY" scripts/check_generated.py

echo "== lint"
ruff format --check .
ruff check .

echo "== typecheck"
mypy

echo "== unit + contract + conformance tests"
"$PY" -m pytest tests/unit tests/contract tests/conformance -q

echo "== package"
if "$PY" -c "import build" >/dev/null 2>&1; then
  rm -rf dist
  "$PY" -m build >/dev/null
  "$PY" - <<'EOF'
import pathlib, tarfile, zipfile, sys

dist = pathlib.Path("dist")
sdist = next(dist.glob("*.tar.gz"))
names = tarfile.open(sdist).getnames()
for path in ("contract/webhook-samples.json", "AGENTS.md", "examples/accept_payment.py"):
    if not any(name.endswith("/" + path) for name in names):
        sys.exit(f"sdist is missing {path}")
wheel = next(dist.glob("*.whl"))
if "oblodai/AGENTS.md" not in zipfile.ZipFile(wheel).namelist():
    sys.exit("wheel is missing oblodai/AGENTS.md")
print(f"package: {sdist.name} and {wheel.name} carry the recordings, AGENTS.md and examples")
EOF
else
  echo "  (skipped: install the 'build' package to run the packaging gate locally)"
fi

if [ "${1:-}" = "--live" ]; then
  echo "== live tests against ${OBLODAI_LIVE_URL:?set OBLODAI_LIVE_URL}"
  "$PY" -m pytest tests/live -q
fi

echo "all gates green"
