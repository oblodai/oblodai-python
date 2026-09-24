"""The package version, taken from the installed distribution - never a second copy to drift.

``pyproject.toml`` is the single source. When the SDK runs from a source checkout that was never
installed, the version is read from that file directly; only a checkout with neither falls back to
a placeholder, and it says so.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

__all__ = ["SDK_VERSION"]

_UNKNOWN = "0.0.0+unknown"


def _from_pyproject() -> str:
    """`version = "X.Y.Z"` out of the repository's own pyproject.toml, if it is next to us."""
    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = path.read_text("utf-8")
    except OSError:
        return _UNKNOWN
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    return match.group(1) if match else _UNKNOWN


def _resolve() -> str:
    try:
        return version("oblodai")
    except PackageNotFoundError:
        return _from_pyproject()


SDK_VERSION = _resolve()
