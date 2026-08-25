#!/usr/bin/env python3
"""CI gate: the committed src/oblodai/contract must be exactly what codegen produces.

Regenerates the generated modules (and the async resource mirror) and fails when the result
differs from what is on disk.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_OUT = ROOT / "src" / "oblodai" / "contract"
ASYNC_OUT = ROOT / "src" / "oblodai" / "aio" / "resources"
GENERATED = [CONTRACT_OUT / name for name in ("routes.py", "enums.py", "requests.py", "version.py")]


def snapshot(paths: List[Path]) -> Dict[Path, str]:
    return {p: p.read_text("utf-8") for p in paths if p.exists()}


def main() -> int:
    targets = GENERATED + sorted(ASYNC_OUT.glob("*.py"))
    before = snapshot(targets)
    for script in ("codegen.py", "gen_async.py"):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True)
    after = snapshot(sorted(set(targets) | set(ASYNC_OUT.glob("*.py"))))

    drifted = sorted(
        str(path.relative_to(ROOT))
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )
    if drifted:
        print(
            "contract drift: "
            + ", ".join(drifted)
            + " differ from the generators - commit the regenerated files",
            file=sys.stderr,
        )
        return 1
    print(f"check-drift: {len(after)} generated files are in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
