# Releasing

This package (`oblodai`) is published to **PyPI** by CI when a `vX.Y.Z` tag is pushed.

**The version bump is scripted for the whole SDK family.** From the backend checkout,
`tools/sdkgen/release.sh X.Y.Z` raises the version in all eight SDKs (manifest, version constant,
lock files, the install lines of the READMEs), closes the `## [X.Y.Z] — Unreleased` (or
`## [Unreleased]`) section of every `CHANGELOG.md` with today's date, commits and tags `vX.Y.Z`
locally; `-n` only checks. Pushing the tag — the step that publishes — stays manual.

## Setup (one-time)

**Repo secret:** `PYPI_API_TOKEN` — a PyPI API token scoped to this project. The workflow uploads
with `twine`, so nothing else is required; there is no OIDC/Trusted Publishing configured and the
workflow does not request `id-token: write`.

The `publish` job runs in the `pypi` GitHub environment — put the token there (and any required
reviewers) if you want a manual approval step before an upload.

## Cut a release

1. Bump `version` in `pyproject.toml` (it is the single source: `oblodai.__version__` reads the
   installed distribution's metadata, so nothing else needs editing).
2. Add the release's entry to `CHANGELOG.md`.
3. `git tag vX.Y.Z && git push origin vX.Y.Z` — the tag must match the `pyproject.toml` version,
   and the workflow fails if it does not.
4. The **Release** workflow re-runs every CI gate, builds sdist + wheel, runs `twine check` and
   uploads.

Only `vX.Y.Z` tags trigger it; a tag like `vendor-x` does not.

## Before tagging

`make ci` must be green: contract drift, ruff, mypy, unit and contract tests. Run the live tier too
when a gateway is reachable: `OBLODAI_LIVE_URL=... make live`.

CI (tests, quality gates and a packaging check) runs on every push and pull request via
`.github/workflows/ci.yml`.
