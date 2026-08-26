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

Renaming is done over the token stream, never over the raw text: a docstring that happens to start
with the word "Refunds" is prose, not a reference to the class, and must survive untouched. Only
identifiers, ``__all__`` entries and the handful of deliberate prose swaps in :data:`PROSE` change.

``python scripts/check_drift.py`` re-runs this and fails when the mirror is stale.
``--out DIR`` writes into ``DIR/aio/resources`` instead of the package.
"""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import token as token_types
import tokenize
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from toolchain import ROOT, find_ruff

SRC = ROOT / "src" / "oblodai" / "resources"
PACKAGE_DIR = ROOT / "src" / "oblodai"

#: Transport calls that become awaits inside a generated method.
AWAITED = ("self._call(", "self._file(", "self._plain_list(")
#: A method whose body contains this returns a lazy page object and must NOT become a coroutine.
LAZY = "self._page("

#: Prose that is true of the synchronous tier only. Applied to docstrings, in order.
PROSE: Tuple[Tuple[str, str], ...] = (
    ("Synchronous resource namespaces", "Asynchronous resource namespaces"),
    ("Shared plumbing for the synchronous", "Shared plumbing for the asynchronous"),
    (
        "``.first()`` gives one page, iterating the result walks every page.",
        "``await .first()`` gives one page, ``async for`` walks every page.",
    ),
)

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


def coroutine_ify(source: str) -> str:
    """``def`` -> ``async def`` and ``self._call(`` -> ``await self._call(``, method by method."""
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
    return "\n".join(out)


def _string_replacement(text: str, names: Dict[str, str]) -> Optional[str]:
    """How one STRING token changes, or ``None`` when it does not.

    A literal that is exactly a class name is a reference to it (``__all__`` entries, forward
    references); a docstring is prose and only the deliberate :data:`PROSE` swaps touch it.
    """
    quote = '"""' if text.startswith(('"""', "'''")) else text[-1]
    prefix = text[: text.index(quote)]
    inner = text[len(prefix) + len(quote) : -len(quote)]
    renamed = names.get(inner)
    if renamed is not None:
        return f"{prefix}{quote}{renamed}{quote}"
    swapped = inner
    for old, new in PROSE:
        swapped = swapped.replace(old, new)
    if swapped == inner:
        return None
    return f"{prefix}{quote}{swapped}{quote}"


def rename(source: str, names: Dict[str, str]) -> str:
    """Rewrite identifiers over the token stream, leaving comments and prose alone."""
    #: (start_row, start_col, end_row, end_col, replacement), 1-based rows as tokenize reports them.
    edits: List[Tuple[int, int, int, int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == token_types.NAME:
            replacement = names.get(tok.string)
        elif tok.type == token_types.STRING:
            replacement = _string_replacement(tok.string, names)
        else:
            continue
        if replacement is None or replacement == tok.string:
            continue
        edits.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1], replacement))

    lines = source.split("\n")
    # Back to front, so an edit never moves the coordinates of one still to be applied.
    for start_row, start_col, end_row, end_col, replacement in sorted(edits, reverse=True):
        head = lines[start_row - 1][:start_col]
        tail = lines[end_row - 1][end_col:]
        rewritten = (head + replacement + tail).split("\n")
        lines[start_row - 1 : end_row] = rewritten
    return "\n".join(lines)


def generate(path: Path, names: Dict[str, str]) -> str:
    source = path.read_text("utf-8")
    lines = [rewrite_imports(line) for line in source.split("\n")]
    body = rename(coroutine_ify("\n".join(lines)), names)
    docstring_end = body.find('"""', body.find('"""') + 3) + 3
    if body.startswith('"""') and docstring_end > 3:
        return body[:docstring_end] + "\n\n" + HEADER.format(name=path.name) + body[docstring_end:]
    return HEADER.format(name=path.name) + body


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=PACKAGE_DIR,
        help="package root to write into (default: src/oblodai)",
    )
    dst = parser.parse_args(argv).out / "aio" / "resources"

    names = class_map()
    dst.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    keep = set()
    for path in sorted(SRC.glob("*.py")):
        if path.name == "base.py":
            continue
        (dst / path.name).write_text(generate(path, names), "utf-8")
        written.append(path.name)
        keep.add(path.name)
    for stale in dst.glob("*.py"):
        if stale.name not in keep:
            stale.unlink()

    ruff = find_ruff()
    if ruff:
        targets = [str(dst / name) for name in written]
        subprocess.run([ruff, "check", "-q", "--fix-only", *targets], check=False)
        subprocess.run([ruff, "format", "-q", *targets], check=True)
        subprocess.run([ruff, "check", "-q", *targets], check=True)
    print(f"gen-async: {len(written)} modules mirrored into {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
