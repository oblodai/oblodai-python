#!/usr/bin/env python3
"""Turning one route's JSON request schema into TypedDict classes.

Split out of ``codegen.py``: this is the only genuinely intricate part of the generator, and it
is easier to read on its own. ``codegen.py`` owns the file layout and the overrides; this owns
the shape of a body.
"""

from __future__ import annotations

import json
import keyword
import re
from typing import Any, Dict, List, Tuple

__all__ = [
    "FIELD_DROPS",
    "FIELD_ENUMS",
    "MONEY_FIELD",
    "OPTIONAL_OVERRIDES",
    "REQUEST_OVERRIDES",
    "REQUIRED_OVERRIDES",
    "ROUTE_FIELD_ENUMS",
    "RequestEmitter",
    "camel",
    "render_class_body",
    "wrap_comment",
]

MONEY_FIELD = re.compile(r"(^|_)(amount|min_amount|max_amount|amount_fixed)$")


# Request fields drawn from a generated enum. `<Name>Arg` is `Union[<Name>, str]`, so the editor
# suggests the vocabulary while a value newer than this snapshot still type-checks.
FIELD_ENUMS = {
    "network": "Network",
    "pinned_network": "Network",
    "on_error": "BatchOnError",
    "fee_bearer": "FeeBearer",
    "amount_mode": "AmountMode",
}
ROUTE_FIELD_ENUMS = {
    "POST /v1/payment/history#status": "PaymentStatus",
    "POST /v1/payout/history#status": "PayoutStatus",
    "POST /v1/payout/history#kind": 'Literal["payout", "refund"]',
    "POST /v1/payment/resolve#action": 'Literal["accept", "refund"]',
    "POST /v1/test-webhook/payment#status": "PaymentStatus",
    "POST /v1/test-webhook/payout#status": "PayoutStatus",
    "POST /v1/test-webhook/wallet#status": 'Literal["paid"]',
    "POST /v1/payment/testing-webhook#status": "PaymentStatus",
}
# Fields the handler requires although the shared DTO marks them optional (batch items reuse the
# single-create DTO, where the core backfills the key from the Idempotency-Key header).
REQUIRED_OVERRIDES = {
    "POST /v1/payment/batch": ["payments.order_id"],
    "POST /v1/payout/batch": ["payouts.order_id"],
    "POST /v1/refund/batch": ["refunds.reference"],
    "POST /v1/transfer/batch": [
        "transfers.order_id",
        "transfers.amount",
        "transfers.currency",
    ],
    "POST /v1/payout/link/batch": ["items.reference"],
    "POST /v1/transfer/to-user": ["amount", "currency"],
    "POST /v1/claim/{token}": ["address"],
}

# Fields a shared DTO carries that this route ignores. `payment/history` reuses the DTO of
# `payout/history`, whose `kind` filter the core's own description marks "only for
# /v1/payout/history"; offering it here would only invite a filter that does nothing.
FIELD_DROPS = {"POST /v1/payment/history": {"kind"}}

# Fields the shared DTO marks required although this route does not need them: `payout/validate`
# is a dry run of `payout/create`, and a dry run needs no merchant reference.
OPTIONAL_OVERRIDES = {"POST /v1/payout/validate": ["order_id"]}

# Request schemas for routes whose core DTO is not declared in docsapi (kept in one place so a
# future undocumented route has somewhere to go; remove an entry once the core documents it).
REQUEST_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "POST /v1/merchants": {
        "type": "object",
        "properties": {
            "email": {"type": "string", "example": "owner@shop.example"},
            "name": {"type": "string", "example": "Acme"},
        },
        "required": ["email"],
    },
}


def camel(text: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[^0-9a-zA-Z]+", text) if part)


class RequestEmitter:
    """Turns one route's JSON schema into TypedDict classes (nested objects get their own)."""

    def __init__(self, descriptions: Dict[str, Any]) -> None:
        self.descriptions = descriptions
        self.blocks: List[str] = []
        self.missing: List[str] = []

    def emit(self, route_key: str, name: str, schema: Dict[str, Any]) -> None:
        self._object(route_key, name, schema, prefix="", doc=f"Request body of `{route_key}`.")

    def _field_type(
        self, route_key: str, prefix: str, field: str, schema: Dict[str, Any], owner: str
    ) -> str:
        kind = schema.get("type")
        if kind == "string":
            enum = ROUTE_FIELD_ENUMS.get(f"{route_key}#{field}") or FIELD_ENUMS.get(field)
            if enum:
                return enum if enum.startswith("Literal[") else f"{enum}Arg"
            if field and MONEY_FIELD.search(field):
                return "Money"
            return "str"
        if kind == "integer":
            return "int"
        if kind == "number":
            return "float"
        if kind == "boolean":
            return "bool"
        if kind == "array":
            items = schema.get("items") or {}
            inner = self._field_type(route_key, f"{prefix}{field}.", "", items, f"{owner}Item")
            return f"List[{inner}]"
        if kind == "object":
            if schema.get("properties"):
                self._object(
                    route_key,
                    owner,
                    schema,
                    prefix=prefix,
                    doc=f"Nested body object of `{route_key}`.",
                )
                return f'"{owner}"'
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict):
                inner = self._field_type(route_key, prefix, "", extra, f"{owner}Value")
                return f"Dict[str, {inner}]"
            return "Dict[str, Any]"
        return "Any"

    def _object(
        self, route_key: str, name: str, schema: Dict[str, Any], prefix: str, doc: str
    ) -> None:
        required = set(schema.get("required") or [])
        for override in REQUIRED_OVERRIDES.get(route_key, []):
            if override.startswith(prefix) and "." not in override[len(prefix) :]:
                required.add(override[len(prefix) :])
        for override in OPTIONAL_OVERRIDES.get(route_key, []):
            if override.startswith(prefix) and "." not in override[len(prefix) :]:
                required.discard(override[len(prefix) :])
        properties: Dict[str, Any] = {
            name: spec
            for name, spec in (schema.get("properties") or {}).items()
            if not (prefix == "" and name in FIELD_DROPS.get(route_key, ()))
        }
        # A field named like a Python keyword (`from`) cannot be a class attribute: those objects
        # are emitted with the functional TypedDict syntax instead.
        functional = any(keyword.iskeyword(field) for field in properties)
        fields_required: List[Tuple[str, str, List[str]]] = []
        fields_optional: List[Tuple[str, str, List[str]]] = []
        for field in sorted(properties):
            spec = properties[field]
            key = f"{prefix}{field}"
            described = (self.descriptions.get("request", {}).get(route_key) or {}).get(key)
            if not described and spec.get("description"):
                self.missing.append(f"{route_key}#{key}")
            example = spec.get("example")
            comment = described or ""
            # The core's examples are written for its own (Russian) docs; only an ASCII one can
            # go into an English SDK verbatim.
            if example is not None:
                rendered_example = json.dumps(example, ensure_ascii=False)
                if rendered_example.isascii():
                    comment = f"{comment} Example: {rendered_example}.".strip()
            rendered = self._field_type(
                route_key, prefix, field, spec, f"{name}{camel(field)}".replace("Body", "")
            )
            entry = (field, rendered, wrap_comment(comment) if comment else [])
            (fields_required if field in required else fields_optional).append(entry)

        if not properties:
            self.blocks.append(f'class {name}(TypedDict, total=False):\n    """{doc}"""\n')
            return
        if functional:
            self.blocks.extend(self._functional(name, doc, fields_required, fields_optional))
            return
        if fields_required and fields_optional:
            base = f"_{name}Required"
            self.blocks.append(f"class {base}(TypedDict):\n{render_class_body(fields_required)}\n")
            self.blocks.append(
                f'class {name}({base}, total=False):\n    """{doc}"""\n\n'
                f"{render_class_body(fields_optional)}\n"
            )
        elif fields_required:
            self.blocks.append(
                f'class {name}(TypedDict):\n    """{doc}"""\n\n'
                f"{render_class_body(fields_required)}\n"
            )
        else:
            self.blocks.append(
                f'class {name}(TypedDict, total=False):\n    """{doc}"""\n\n'
                f"{render_class_body(fields_optional)}\n"
            )

    @staticmethod
    def _functional(
        name: str,
        doc: str,
        fields_required: List[Tuple[str, str, List[str]]],
        fields_optional: List[Tuple[str, str, List[str]]],
    ) -> List[str]:
        blocks: List[str] = []
        bases: List[str] = []
        for suffix, fields, total in (
            ("Required", fields_required, True),
            ("Optional", fields_optional, False),
        ):
            if not fields:
                continue
            base = f"_{name}{suffix}"
            bases.append(base)
            blocks.append(
                f'{base} = TypedDict(\n    "{base}",\n    {{\n'
                + render_dict_body(fields)
                + "\n    },\n"
                + ("" if total else "    total=False,\n")
                + ")\n"
            )
        blocks.append(f'class {name}({", ".join(bases)}):\n    """{doc}"""\n')
        return blocks


def render_class_body(fields: List[Tuple[str, str, List[str]]]) -> str:
    lines: List[str] = []
    for field, rendered, comment in fields:
        lines.extend(f"    #: {chunk}" for chunk in comment)
        lines.append(f"    {field}: {rendered}")
    return "\n".join(lines)


def render_dict_body(fields: List[Tuple[str, str, List[str]]]) -> str:
    lines: List[str] = []
    for field, rendered, comment in fields:
        lines.extend(f"        # {chunk}" for chunk in comment)
        lines.append(f'        "{field}": {rendered},')
    return "\n".join(lines)


def wrap_comment(text: str, width: int = 92) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]
