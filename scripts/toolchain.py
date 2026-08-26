"""Locating the developer tools the generators shell out to.

The generators must work on a clean checkout - a CI job that ran ``pip install -e ".[dev]"``
has ``ruff`` on ``PATH`` and no ``.venv`` at all - so they look it up rather than assuming a
repository-local virtualenv.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

__all__ = ["ROOT", "find_ruff"]


def find_ruff() -> Optional[str]:
    """The ``ruff`` executable: ``PATH`` first, then this repository's ``.venv``."""
    found = shutil.which("ruff")
    if found:
        return found
    local = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "ruff"
    return str(local) if local.exists() else None
