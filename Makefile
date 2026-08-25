PY := .venv/bin/python
BIN := .venv/bin

.PHONY: ci codegen lint typecheck test live drift

ci:            ## every gate CI runs
	./scripts/ci.sh

live:          ## the live tier too (needs OBLODAI_LIVE_URL)
	./scripts/ci.sh --live

codegen:       ## regenerate contract/ mirrors and the async resources
	$(PY) scripts/codegen.py
	$(PY) scripts/gen_async.py

drift:         ## fail when the generated files are stale
	$(PY) scripts/check_drift.py

lint:
	$(BIN)/ruff format --check .
	$(BIN)/ruff check .

typecheck:
	$(BIN)/mypy

test:
	$(PY) -m pytest tests/unit tests/contract -q
