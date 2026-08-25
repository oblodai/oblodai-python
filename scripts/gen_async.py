#!/usr/bin/env python3
"""Derive the asynchronous resource namespaces from the synchronous ones.

The resource layer is thin: every method names a route and hands a body to the transport. Writing
it twice would let the two clients drift, so ``src/oblodai/resources/*.py`` is the single source
and this script mirrors it into ``src/oblodai/aio/resources/*.py``:

* ``class Payments(Resource)`` becomes ``class AsyncPayments(AsyncResource)``;
* every method becomes ``async def`` and awaits ``self._call`` / ``self._file`` /
  ``self._plain_list`` - except the list methods, which return a lazy ``AsyncPage`` and so stay
  ordinary functions (``async for item in client.payments.history()``);
* relative imports are re-rooted one package deeper.

``python scripts/check_drift.py`` re-runs this and fails when the mirror is stale.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "oblodai" / "resources"
DST = ROOT / "src" / "oblodai" / "aio" / "resources"

#: Transport calls that become awaits inside a generated method.
AWAITED = ("self._call(", "self._file(", "self._plain_list(")
#: A method whose body contains this returns a lazy page object and must NOT become a coroutine.
LAZY = "self._page("

HEADER = (
    "# GENERATED FILE - do not edit. Source: src/oblodai/resources/{name}\n"
    "# Regenerate with: python scripts/gen_async.py\n"
)


def class_map() -> Dict[str, str]:
    """``{"Payments": "AsyncPayments", ...}`` for every resource class plus the base."""
    mapping = {"Resource": "AsyncResource", "Page": "AsyncPage"}
    for path in sorted(SRC.glob("*.py")):
        if path.name in ("__init__.py", "base.py"):
            continue
        for match in re.finditer(r"^class (\w+)\(Resource\):", path.read_text("utf-8"), re.M):
            mapping[match.group(1)] = f"Async{match.group(1)}"
    return mapping


def rewrite_imports(line: str) -> str:
    line = line.replace("from .base import", "\x00")
    line = line.replace("from ..", "from ...")
    return line.replace("\x00", "from ..base import")


def asyncify(source: str, names: Dict[str, str]) -> str:
    lines = source.split("\n")
    out: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^    def (\w+)\(", line)
        if match is None:
            out.append(line)
            index += 1
            continue
        # Collect the whole method. The signature may wrap over several lines (its closing
        # `) -> X:` sits at four spaces), so follow the parentheses first, then the indentation.
        body = [line]
        depth = line.count("(") - line.count(")")
        cursor = index + 1
        while depth > 0 and cursor < len(lines):
            body.append(lines[cursor])
            depth += lines[cursor].count("(") - lines[cursor].count(")")
            cursor += 1
        while cursor < len(lines):
            following = lines[cursor]
            if following.strip() and not following.startswith("        "):
                break
            body.append(following)
            cursor += 1
        block = "\n".join(body)
        if LAZY not in block:
            block = block.replace("    def ", "    async def ", 1)
            for call in AWAITED:
                block = block.replace(call, f"await {call}")
        out.append(block)
        index = cursor
    text = "\n".join(out)
    for old, new in sorted(names.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf"\b{old}\b", new, text)
    return text


def generate(path: Path, names: Dict[str, str]) -> str:
    source = path.read_text("utf-8")
    lines = [rewrite_imports(line) for line in source.split("\n")]
    body = asyncify("\n".join(lines), names)
    docstring_end = body.find('"""', body.find('"""') + 3) + 3
    if body.startswith('"""') and docstring_end > 3:
        return body[:docstring_end] + "\n\n" + HEADER.format(name=path.name) + body[docstring_end:]
    return HEADER.format(name=path.name) + body


def main() -> int:
    names = class_map()
    DST.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    keep = set()
    for path in sorted(SRC.glob("*.py")):
        if path.name == "base.py":
            continue
        target = DST / path.name
        target.write_text(generate(path, names), "utf-8")
        written.append(path.name)
        keep.add(path.name)
    for stale in DST.glob("*.py"):
        if stale.name not in keep:
            stale.unlink()

    ruff = ROOT / ".venv" / "bin" / "ruff"
    if ruff.exists():
        targets = [str(DST / name) for name in written]
        subprocess.run([str(ruff), "check", "-q", "--fix-only", *targets], check=False)
        subprocess.run([str(ruff), "format", "-q", *targets], check=True)
        subprocess.run([str(ruff), "check", "-q", *targets], check=True)
    print(f"gen-async: {len(written)} modules mirrored into {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
