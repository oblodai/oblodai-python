# Releasing

This package (`oblodai`) is published to **PyPI** by CI when a `v*` tag is pushed.

## Setup (one-time)
**Repo secret:** `PYPI_API_TOKEN` — a PyPI API token. (Or configure PyPI **Trusted Publishing / OIDC** and remove the `password:` line — the workflow already requests `id-token: write`.)

## Cut a release
1. Bump `version` in `pyproject.toml`.
2. `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The **Release** workflow builds sdist+wheel and uploads to PyPI.

## Before tagging

`make ci` must be green: contract drift, ruff, mypy, unit and contract tests. Run the live tier too
when a gateway is reachable: `OBLODAI_LIVE_URL=... make live`.

CI (build + tests) runs on every push and pull request via `.github/workflows/ci.yml`.
