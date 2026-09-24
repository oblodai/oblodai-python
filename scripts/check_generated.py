"""Fail when ``src/oblodai/generated`` is not what the generator makes of the gateway's contract.

Regenerates into a temporary directory with the backend's ``tools/sdkgen`` (from
``services/core/api/openapi.json``, checked against ``names.lock``) and compares file by file.
The backend checkout is ``$OBLODAI_BACKEND``, else ``../oblodai-backend`` next to this repository.
Without a backend that has ``tools/sdkgen`` the check is skipped, loudly; with ``--require`` it
fails instead. Fix drift by regenerating (``make sdk`` in the backend), never by hand.
"""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "src" / "oblodai" / "generated"


def backend_root() -> Path:
    configured = os.environ.get("OBLODAI_BACKEND")
    return Path(configured) if configured else ROOT.parent / "oblodai-backend"


def py_files(directory: Path) -> List[str]:
    return sorted(p.name for p in directory.glob("*.py"))


def main(argv: List[str]) -> int:
    backend = backend_root()
    sdkgen = backend / "tools" / "sdkgen"
    spec = backend / "services" / "core" / "api" / "openapi.json"
    if not (sdkgen / "cmd" / "sdkgen").is_dir() or not spec.is_file():
        message = f"no generator at {sdkgen} (set OBLODAI_BACKEND to the backend checkout)"
        if "--require" in argv:
            print(f"check_generated: {message}", file=sys.stderr)
            return 1
        print(f"  (skipped: {message})")
        return 0
    env = dict(os.environ)
    env.setdefault("GOTOOLCHAIN", "go1.26.6")
    with tempfile.TemporaryDirectory() as tmp:
        # The generator's `ruff format` must see this repository's settings (line length).
        shutil.copy(ROOT / "pyproject.toml", Path(tmp) / "pyproject.toml")
        cmd = [
            "go",
            "run",
            "./cmd/sdkgen",
            "-spec",
            str(spec),
            "-lang",
            "python",
            "-out",
            tmp,
            "-lock",
            str(ROOT / "names.lock"),
        ]
        done = subprocess.run(cmd, cwd=sdkgen, env=env, capture_output=True, text=True)
        if done.returncode != 0:
            print(f"check_generated: sdkgen failed:\n{done.stderr}", file=sys.stderr)
            return 1
        fresh = Path(tmp) / "src" / "oblodai" / "generated"
        want, have = py_files(fresh), py_files(GENERATED)
        stale = sorted(set(want) ^ set(have))
        _, differ, errors = filecmp.cmpfiles(fresh, GENERATED, want, shallow=False)
        bad = sorted(set(stale) | set(differ) | set(errors))
        if bad:
            print(
                "check_generated: src/oblodai/generated is stale ("
                + ", ".join(bad)
                + "); regenerate with `make sdk` in the backend",
                file=sys.stderr,
            )
            return 1
    print(f"generated code matches {spec}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
