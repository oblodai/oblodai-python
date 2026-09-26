"""The documentation is checked like code, because a payments SDK's docs are load-bearing.

Every Python block in the prose must parse; every SDK name it mentions must exist; every route,
error-code and environment-variable count it quotes must be the real one. A doc that lies about
what a route needs costs somebody a production incident, not five minutes.

The Russian README is held to the same standard, plus one of its own: its code blocks must be
byte-identical to the English ones, so a reader of either file runs the same snippets.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

import oblodai
from oblodai import ROUTES, ErrorCode
from tests.support.coverage import COVERAGE

ERROR_CODES = [code.value for code in ErrorCode]

ROOT = Path(oblodai.__file__).resolve().parents[2]
#: The English prose. Checked for English-only text.
DOCS = (
    "README.md",
    "AGENTS.md",
    "MIGRATION-1.3.md",
    "MIGRATION-2.0.md",
    "CHANGELOG.md",
    "RELEASING.md",
)
#: Translations. Same code, same claims, another language.
TRANSLATIONS = ("README.ru.md",)
ALL_DOCS = DOCS + TRANSLATIONS
#: Both READMEs make the same promises about keys, routes and the environment.
READMES = ("README.md",) + TRANSLATIONS
_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
#: The one line where the other language is allowed to appear: the link to the translation.
_SIBLING_LINK = "README.ru.md"


def read(name: str) -> str:
    return (ROOT / name).read_text("utf-8")


def python_blocks() -> List[Tuple[str, int, str]]:
    """``(document, block index, source)`` for every fenced Python block in the prose."""
    out: List[Tuple[str, int, str]] = []
    for name in ALL_DOCS:
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


def test_the_docs_quote_no_route_or_error_code_count_by_hand() -> None:
    """Counts go stale with the next route; the only one allowed is the generated method table's."""
    routes, codes = len(ROUTES), len(ERROR_CODES)
    for name in ("README.md", "README.ru.md", "AGENTS.md"):
        text = outside_methods_section(read(name))
        for count in (routes, codes):
            quoted = re.findall(rf"(?<![\d.]){count}(?![\d.])", text)
            assert not quoted, f"{name} quotes the count {count} by hand"


def test_the_docs_name_every_environment_variable_the_client_reads() -> None:
    """A variable the client honours but the docs never mention is a variable nobody sets."""
    source = (Path(oblodai.__file__).parent / "config.py").read_text("utf-8")
    honoured = set(re.findall(r'environ\.get\("(OBLODAI_[A-Z_]+)"\)', source))
    assert honoured, "config.py stopped reading the environment the way this test expects"
    for name in READMES + (".env.example",):
        text = (ROOT / name).read_text("utf-8")
        undocumented = sorted(variable for variable in honoured if variable not in text)
        assert not undocumented, f"{name} does not mention {undocumented}"


#: The two-key model of 1.2, in every spelling the prose used to carry.
_RETIRED_KEY_MODEL = (
    "payout key",
    "Payout key",
    "payment key",
    "Payment key",
    "payout_public_id",
    "payout_secret",
    "OBLODAI_PAYOUT_PUBLIC_ID",
    "OBLODAI_PAYOUT_SECRET",
    "prefer_payout_key",
)
#: The same claim in Russian, for the translation. ("выплатные ссылки" is a product, not a key.)
_RETIRED_KEY_MODEL_RU = (
    "выплатной ключ",
    "выплатного ключа",
    "выплатным ключом",
    "платёжный ключ",
    "платёжного ключа",
    "Видов ключей два",
)


@pytest.mark.parametrize("document", ALL_DOCS + (".env.example",))
def test_no_document_still_describes_the_retired_two_key_model(document: str) -> None:
    """A merchant has ONE key. A doc that says otherwise sends somebody hunting for a second."""
    text = read(document)
    if document in ("CHANGELOG.md", "MIGRATION-1.3.md", "MIGRATION-2.0.md"):
        # These two exist to say what went away, so they may name it - in the past tense.
        return
    marks = _RETIRED_KEY_MODEL + (_RETIRED_KEY_MODEL_RU if document in TRANSLATIONS else ())
    left = sorted({mark for mark in marks if mark in text})
    assert not left, f"{document} still describes the two-key model: {left}"


def test_the_readmes_agree_that_one_key_signs_every_route() -> None:
    """The claim itself, not just the absence of the old one: both READMEs must make it."""
    for name in READMES + ("AGENTS.md",):
        text = read(name)
        for mark in ("public_id", "secret", "OBLODAI_PUBLIC_ID", "OBLODAI_SECRET"):
            assert mark in text, f"{name} does not say how the API key is configured"
        assert "X-Admin-Token" in text or "admin_token" in text, (
            f"{name} does not say what the admin token is for"
        )


def test_the_legacy_key_kind_error_is_documented_exactly_once() -> None:
    """`merchant.wrong_key_kind` left the catalogue; it survives only as a legacy-pair note."""
    assert "merchant.wrong_key_kind" not in ERROR_CODES
    for name in READMES:
        assert read(name).count("merchant.wrong_key_kind") == 1, (
            f"{name} should mention the legacy split-key error once, as legacy"
        )
    for name in ("AGENTS.md",):
        assert "merchant.wrong_key_kind" not in read(name), (
            f"{name} lists it among live codes; it is not in the catalogue any more"
        )


METHODS_BEGIN, METHODS_END = "<!-- sdkgen:methods -->", "<!-- /sdkgen:methods -->"


def methods_section(text: str) -> str:
    """What the generator wrote between the method-table markers."""
    assert text.count(METHODS_BEGIN) == text.count(METHODS_END) == 1
    return text.split(METHODS_BEGIN, 1)[1].split(METHODS_END, 1)[0]


def outside_methods_section(text: str) -> str:
    if METHODS_BEGIN not in text:
        return text
    return text.split(METHODS_BEGIN, 1)[0] + text.split(METHODS_END, 1)[1]


@pytest.mark.parametrize("document", READMES)
def test_the_readme_method_table_is_exactly_the_client(document: str) -> None:
    """The generator writes the table from the contract; it must list the client, no more, no less."""
    section = methods_section(read(document))
    rows = re.findall(r"^\| `([a-z_]+)` \| (.+) \|$", section, re.M)
    tabulated = sorted(
        f"{namespace}.{method}"
        for namespace, methods in rows
        for method in re.findall(r"`([a-z_]+)`", methods)
    )
    assert tabulated == sorted(f"{ns}.{name}" for ns, name in COVERAGE.values())
    resources = len({ns for ns, _ in COVERAGE.values()})
    counter = (
        f"{resources} resources, {len(COVERAGE)} methods."
        if document == "README.md"
        else f"{resources} ресурс"
    )
    assert counter in section, f"{document}: the counter is not the client's"


def test_the_english_docs_are_english_only() -> None:
    """Generated examples and prose alike: no leftover source-language text."""
    offenders: Dict[str, str] = {}
    for name in DOCS + (".env.example",):
        for line in (ROOT / name).read_text("utf-8").split("\n"):
            if _SIBLING_LINK in line:  # the link to the translation, in its own language
                continue
            if re.search(r"[Ѐ-ӿ]", line):
                offenders[name] = line.strip()[:80]
                break
    assert not offenders, f"non-English text left in the docs: {offenders}"


def test_the_russian_readme_is_a_translation_of_the_english_one() -> None:
    """Same header, same structure, same runnable snippets - only the prose is translated."""
    english, russian = read("README.md"), read("README.ru.md")

    assert re.search(r"[Ѐ-ӿ]", russian), "README.ru.md is not translated"
    assert "[Read in Russian →](README.ru.md)" in english
    assert "[Read in English →](README.md)" in russian

    # The branded header is the family resemblance: same logo, same badges.
    for mark in (
        "https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-white.svg",
        "https://raw.githubusercontent.com/oblodai/.github/main/brand/logo-black.svg",
        "https://img.shields.io/pypi/v/oblodai?style=flat-square&label=PyPI",
        "https://img.shields.io/github/actions/workflow/status/oblodai/oblodai-python/ci.yml",
        "https://img.shields.io/pypi/pyversions/oblodai?style=flat-square",
        "https://img.shields.io/badge/license-MIT-000000?style=flat-square",
    ):
        assert mark in english, f"README.md lost the branded header ({mark})"
        assert mark in russian, f"README.ru.md lost the branded header ({mark})"

    # A reader of either file must be able to copy the same code.
    assert _BLOCK.findall(english) == _BLOCK.findall(russian), (
        "the Python blocks of README.md and README.ru.md have drifted apart"
    )
    for language in ("bash",):
        fence = re.compile(rf"```{language}\n(.*?)```", re.S)
        assert fence.findall(english) == fence.findall(russian), (
            f"the {language} blocks of the two READMEs have drifted apart"
        )

    headings = [len(re.findall(r"^## ", text, re.M)) for text in (english, russian)]
    assert headings[0] == headings[1] == 12, f"the READMEs disagree on their sections: {headings}"


def test_the_2_0_migration_maps_every_2_0_name() -> None:
    """MIGRATION-2.0.md maps the names 2.0 shipped with (names.2.0.txt, frozen); a method added
    later is not a migration, and names.lock (which the generator extends) is not this list."""
    text = read("MIGRATION-2.0.md")
    missing = [n for n in read("names.2.0.txt").split() if f"| `{n}` |" not in text]
    assert not missing, f"MIGRATION-2.0.md does not map {missing}"
