#!/usr/bin/env python3
"""CI gate: the committed src/oblodai/contract and src/oblodai/aio must be what the generators produce.

Non-destructive: the generators write into a temporary directory and the result is compared with
what is on disk, so a failing gate never leaves a half-regenerated working tree behind (and the
check is safe to run on a dirty checkout).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from toolchain import ROOT

PACKAGE_DIR = ROOT / "src" / "oblodai"
CONTRACT_NAMES = ("routes.py", "enums.py", "requests.py", "version.py")


def snapshot(root: Path) -> Dict[str, str]:
    """``{"contract/routes.py": <text>, "aio/resources/payments.py": <text>, ...}``."""
    out: Dict[str, str] = {}
    for name in CONTRACT_NAMES:
        path = root / "contract" / name
        if path.exists():
            out[f"contract/{name}"] = path.read_text("utf-8")
    for path in sorted((root / "aio" / "resources").glob("*.py")):
        out[f"aio/resources/{path.name}"] = path.read_text("utf-8")
    return out


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="oblodai-drift-") as tmp:
        out = Path(tmp)
        for script in ("codegen.py", "gen_async.py"):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / script), "--out", str(out)], check=True
            )
        fresh = snapshot(out)
    committed = snapshot(PACKAGE_DIR)

    drifted: List[str] = sorted(
        name for name in set(committed) | set(fresh) if committed.get(name) != fresh.get(name)
    )
    if drifted:
        print(
            "contract drift: "
            + ", ".join(drifted)
            + " differ from the generators - run `make codegen` and commit the result",
            file=sys.stderr,
        )
        return 1
    print(f"check-drift: {len(fresh)} generated files are in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
