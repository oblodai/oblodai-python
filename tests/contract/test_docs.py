"""The documentation is checked like code, because a payments SDK's docs are load-bearing.

Every Python block in the prose must parse; every SDK name it mentions must exist; every route,
error-code and environment-variable count it quotes must be the real one. A doc that lies about
which key a route needs costs somebody a production incident, not five minutes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

import oblodai
from oblodai import ERROR_CODES, ROUTES

ROOT = Path(oblodai.__file__).resolve().parents[2]
DOCS = ("README.md", "AGENTS.md", "MIGRATION-1.3.md", "CHANGELOG.md", "RELEASING.md")
_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def read(name: str) -> str:
    return (ROOT / name).read_text("utf-8")


def python_blocks() -> List[Tuple[str, int, str]]:
    """``(document, block index, source)`` for every fenced Python block in the prose."""
    out: List[Tuple[str, int, str]] = []
    for name in DOCS:
        for index, match in enumerate(_BLOCK.finditer(read(name))):
            out.append((name, index, match.group(1)))
    return out


BLOCKS = python_blocks()


def test_the_docs_have_python_blocks_to_check() -> None:
    assert len(BLOCKS) >= 8


@pytest.mark.parametrize(
    ("document", "index", "source"), BLOCKS, ids=[f"{d}#{i}" for d, i, _ in BLOCKS]
)
def test_every_python_block_in_the_docs_parses(document: str, index: int, source: str) -> None:
    try:
        ast.parse(source)
    except SyntaxError as err:  # pragma: no cover - the message is the point
        pytest.fail(f"{document} block #{index} does not parse: {err}")


def test_every_sdk_name_the_docs_import_exists() -> None:
    """`from oblodai import X` in the prose must be an X that is actually exported."""
    missing: List[str] = []
    for document, index, source in BLOCKS:
        for node in ast.walk(ast.parse(source)):
            name = node.module or "" if isinstance(node, ast.ImportFrom) else ""
            if not name.startswith("oblodai"):
                continue
            module = __import__(name, fromlist=["_"])
            assert isinstance(node, ast.ImportFrom)
            for alias in node.names:
                if not hasattr(module, alias.name):
                    missing.append(f"{document}#{index}: {name}.{alias.name}")
    assert not missing, f"the docs import names that do not exist: {missing}"


def test_the_route_and_error_code_counts_the_docs_quote_are_the_real_ones() -> None:
    routes, codes = len(ROUTES), len(ERROR_CODES)
    assert (routes, codes) == (107, 471), "the counts below need updating with the contract"
    for name in ("README.md", "AGENTS.md", "CHANGELOG.md"):
        text = read(name)
        for wrong in (f"{routes - 1} routes", f"{routes + 1} routes"):
            assert wrong not in text, f"{name} quotes {wrong}"
        for wrong in (f"{codes - 1} error codes", f"{codes - 2} error codes", f"({codes - 1} codes"):
            assert wrong not in text, f"{name} quotes {wrong}"
    assert f"({codes} codes)" in read("README.md")
    assert f"`ERROR_CODES` ({codes})" in read("AGENTS.md")
    assert f"({routes})" in read("README.md")
    assert f"`ROUTES` ({routes} routes" in read("AGENTS.md")


def test_the_docs_name_every_environment_variable_the_client_reads() -> None:
    """A variable the client honours but the docs never mention is a variable nobody sets."""
    source = (Path(oblodai.__file__).parent / "config.py").read_text("utf-8")
    honoured = set(re.findall(r'environ\.get\("(OBLODAI_[A-Z_]+)"\)', source))
    assert honoured, "config.py stopped reading the environment the way this test expects"
    for name in ("README.md", ".env.example"):
        text = (ROOT / name).read_text("utf-8")
        undocumented = sorted(variable for variable in honoured if variable not in text)
        assert not undocumented, f"{name} does not mention {undocumented}"


def test_the_payout_key_route_list_is_the_same_everywhere() -> None:
    """README and AGENTS.md must not disagree about which routes need the payout key."""
    marks = ("payouts.", "refunds.", "payout_links.", "transfers.", "splits.")
    for name in ("README.md", "AGENTS.md"):
        text = read(name)
        for mark in ("wallets.refund_blocked_deposit", 'webhooks.test("payout"', "sandbox.faucet"):
            assert mark in text, f"{name} omits {mark} from the payout-key list"
        assert all(mark in text for mark in marks)


def test_every_namespace_and_method_the_readme_tabulates_exists() -> None:
    """The resource table in the README is a promise; check it against the real client."""
    api = oblodai.Oblodai(base_url="https://api.test", env={})
    try:
        rows = re.findall(r"^\| `([a-z_]+)` +\| (.+?) \|$", read("README.md"), re.M)
        assert len(rows) >= 15, "the README resource table went missing"
        wrong: List[str] = []
        for namespace, methods in rows:
            target = getattr(api, namespace, None)
            if target is None:
                wrong.append(f"client.{namespace}")
                continue
            for method in re.findall(r"`([a-z_]+)`", methods):
                if not hasattr(target, method):
                    wrong.append(f"{namespace}.{method}")
        assert not wrong, f"the README table promises methods that do not exist: {wrong}"
    finally:
        api.close()


def test_the_docs_are_english_only() -> None:
    """Generated examples and prose alike: no leftover source-language text."""
    offenders: Dict[str, str] = {}
    for name in DOCS + (".env.example",):
        for line in (ROOT / name).read_text("utf-8").split("\n"):
            if re.search(r"[Ѐ-ӿ]", line):
                offenders[name] = line.strip()[:80]
                break
    assert not offenders, f"non-English text left in the docs: {offenders}"
