PY := .venv/bin/python
BIN := .venv/bin

.PHONY: ci lint typecheck test live drift

ci:            ## every gate CI runs
	./scripts/ci.sh

live:          ## the live tier too (needs OBLODAI_LIVE_URL)
	./scripts/ci.sh --live

drift:         ## fail when src/oblodai/generated is stale (backend: OBLODAI_BACKEND or ../oblodai-backend)
	PATH="$(CURDIR)/$(BIN):$$PATH" $(PY) scripts/check_generated.py --require

lint:
	$(BIN)/ruff format --check .
	$(BIN)/ruff check .

typecheck:
	$(BIN)/mypy

test:
	$(PY) -m pytest tests/unit tests/contract -q
