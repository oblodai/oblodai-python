#!/usr/bin/env python3
"""Generate src/oblodai/contract/{routes,enums,requests,version}.py from contract/contract.json.

contract.json is exported by the core's own conformance table (TestSDKContract_Export);
contract/descriptions.en.json carries the English field documentation. Nothing in the generated
files is edited by hand: run `python scripts/codegen.py`, and `python scripts/check_drift.py`
in CI to prove the committed files still match the snapshot.
"""

from __future__ import annotations

import hashlib
import json
import keyword
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_DIR = ROOT / "contract"
OUT_DIR = ROOT / "src" / "oblodai" / "contract"

GENERATED = ("routes.py", "enums.py", "requests.py", "version.py")

# Read-only routes: a transport failure may be retried without risking a duplicate side effect.
SAFE_SUFFIX = re.compile(
    r"/(info|history|list|calculate|validate|services|get|balance|qr|deliveries)$"
)
# Paths that look read-only but whose body can mutate state.
NOT_SAFE = {"POST /v1/vrcs"}
# Operational endpoints outside the merchant surface.
SKIP_PATH = re.compile(r"^/(healthz|readyz|docs|openapi\.json|internal)")

ENUM_NAMES = {
    "payment_status": "PaymentStatus",
    "payout_status": "PayoutStatus",
    "payout_link_status": "PayoutLinkStatus",
    "delivery_status": "DeliveryStatus",
    "network": "Network",
    "fee_bearer": "FeeBearer",
    "fee_bearer_result": "FeeBearerResult",
    "batch_on_error": "BatchOnError",
    "webhook_kind": "WebhookKind",
    "error_kind": "ErrorKind",
}
# Vocabularies the core does not export as enums yet; pinned here from its handlers.
LOCAL_ENUMS = {"AmountMode": ("fixed", "open", "range")}

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
MONEY_FIELD = re.compile(r"(^|_)(amount|min_amount|max_amount|amount_fixed)$")

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


def header(core_commit: str) -> str:
    return (
        f"# GENERATED FILE - do not edit. Source: contract/contract.json "
        f"(core {core_commit[:12]}).\n"
        "# Regenerate with: python scripts/codegen.py\n"
    )


def is_safe(route: Dict[str, Any]) -> bool:
    key = f"{route['method']} {route['path']}"
    if key in NOT_SAFE:
        return False
    return bool(route["method"] == "GET" or SAFE_SUFFIX.search(route["path"]))


def camel(text: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[^0-9a-zA-Z]+", text) if part)


def type_name(route_key: str, used: Dict[str, str]) -> str:
    method, path = route_key.split(" ", 1)
    base = camel(path.replace("/v1/", "/").replace("{", "").replace("}", ""))
    name = f"{base}Body"
    if name in used and used[name] != route_key:
        name = f"{camel(method)}{name}"
    used[name] = route_key
    return name


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
        properties: Dict[str, Any] = schema.get("properties") or {}
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
            if example is not None:
                comment = f"{comment} Example: {json.dumps(example, ensure_ascii=False)}.".strip()
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


def literal_of(values: Tuple[str, ...]) -> str:
    return "Literal[" + ", ".join(json.dumps(v) for v in values) + "]"


def render_tuple(values: Tuple[str, ...], per_line: int = 4, indent: str = "    ") -> str:
    lines = []
    for i in range(0, len(values), per_line):
        chunk = ", ".join(json.dumps(v) for v in values[i : i + per_line])
        lines.append(f"{indent}{chunk},")
    return "\n".join(lines)


def main() -> int:
    raw = (CONTRACT_DIR / "contract.json").read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    descriptions_path = CONTRACT_DIR / "descriptions.en.json"
    descriptions: Dict[str, Any] = (
        json.loads(descriptions_path.read_text("utf-8"))
        if descriptions_path.exists()
        else {"request": {}, "response": {}}
    )
    head = header(contract["core_commit"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    routes = sorted(
        (r for r in contract["routes"] if not SKIP_PATH.match(r["path"])),
        key=lambda r: (r["path"], r["method"]),
    )

    # --- routes.py ---------------------------------------------------------------------------
    out = [
        head,
        '"""Every merchant-facing route the core declares, keyed as its conformance table keys it."""\n',
        "from __future__ import annotations\n",
        "from typing import Mapping\n",
        "from .types import RouteSpec\n",
        "ROUTES: Mapping[str, RouteSpec] = {",
    ]
    for route in routes:
        key = f"{route['method']} {route['path']}"
        list_kind = f'"{route["list"]}"' if route.get("list") else "None"
        out.append(
            f'    "{key}": RouteSpec('
            f'method="{route["method"]}", path="{route["path"]}", auth="{route["auth"]}", '
            f"idempotent={route['idempotent']}, safe={is_safe(route)}, bare={route['bare']}, "
            f"list_kind={list_kind}),"
        )
    out.append("}\n")
    out.append("ROUTE_KEYS = tuple(ROUTES)\n")
    (OUT_DIR / "routes.py").write_text("\n".join(out), "utf-8")

    # --- enums.py ----------------------------------------------------------------------------
    lines = [
        head,
        '"""Vocabularies the core declares: statuses, networks, event and error codes."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Literal, Tuple, Union",
        "",
    ]
    for source, name in ENUM_NAMES.items():
        values = tuple(contract["enums"].get(source) or ())
        if not values:
            raise SystemExit(f"enum {source} missing from contract.json")
        const = re.sub(r"([a-z])([A-Z])", r"\1_\2", name).upper() + (
            "ES" if name[-1] == "s" else "S"
        )
        lines.append(f"{const}: Tuple[str, ...] = (\n{render_tuple(values)}\n)")
        lines.append(f"{name} = {literal_of(values)}")
        lines.append(f"{name}Arg = Union[{name}, str]")
        lines.append("")
    for name, values in LOCAL_ENUMS.items():
        const = re.sub(r"([a-z])([A-Z])", r"\1_\2", name).upper() + "S"
        lines.append(f"{const}: Tuple[str, ...] = (\n{render_tuple(values)}\n)")
        lines.append(f"{name} = {literal_of(values)}")
        lines.append(f"{name}Arg = Union[{name}, str]")
        lines.append("")
    event_types = tuple(contract["event_types"])
    lines.append('"""Webhook event types: `invoice.<status>`, `payout.<status>`, `wallet.paid`."""')
    lines.append(f"EVENT_TYPES: Tuple[str, ...] = (\n{render_tuple(event_types)}\n)")
    lines.append(f"EventType = {literal_of(event_types)}")
    lines.append("EventTypeArg = Union[EventType, str]")
    lines.append("")
    error_codes = tuple(contract["error_codes"])
    lines.append('"""Every error code the core source can emit (`family.reason`)."""')
    lines.append(f"ERROR_CODES: Tuple[str, ...] = (\n{render_tuple(error_codes)}\n)")
    lines.append(f"ErrorCode = {literal_of(error_codes)}")
    lines.append("ErrorCodeArg = Union[ErrorCode, str]")
    lines.append("")
    (OUT_DIR / "enums.py").write_text("\n".join(lines), "utf-8")

    # --- requests.py -------------------------------------------------------------------------
    emitter = RequestEmitter(descriptions)
    used: Dict[str, str] = {}
    exported: List[Tuple[str, str]] = []
    for route in routes:
        key = f"{route['method']} {route['path']}"
        schema = route.get("request_schema") or REQUEST_OVERRIDES.get(key)
        if not schema:
            continue
        name = type_name(key, used)
        emitter.emit(key, name, schema)
        exported.append((key, name))

    enum_imports = sorted(
        {
            f"{e}Arg"
            for e in list(FIELD_ENUMS.values()) + list(ROUTE_FIELD_ENUMS.values())
            if not e.startswith("Literal[")
        }
    )
    body = [
        head,
        '"""Request bodies by route, generated from the core\'s documented DTOs\n'
        '(field names, required flags, descriptions and examples)."""',
        "from __future__ import annotations",
        "from typing import Any, Dict, List, Literal, Mapping, TypedDict",
        "",
        f"from .enums import {', '.join(enum_imports)}",
        "from .models.common import Money",
        "",
    ]
    body.extend(emitter.blocks)
    body.append("#: Route key -> the TypedDict describing its request body.")
    body.append("REQUEST_BODIES: Mapping[str, str] = {")
    for key, name in exported:
        body.append(f'    "{key}": "{name}",')
    body.append("}")
    body.append("")
    (OUT_DIR / "requests.py").write_text("\n\n".join(body), "utf-8")

    # --- version.py --------------------------------------------------------------------------
    digest = hashlib.sha256(raw).hexdigest()
    (OUT_DIR / "version.py").write_text(
        head
        + "\n"
        + f'CONTRACT_CORE_COMMIT = "{contract["core_commit"]}"\n'
        + f'CONTRACT_EXPORTED_AT = "{contract["exported_at"]}"\n'
        + f'CONTRACT_HASH = "{digest}"\n',
        "utf-8",
    )

    ruff = ROOT / ".venv" / "bin" / "ruff"
    if ruff.exists():
        targets = [str(OUT_DIR / f) for f in GENERATED]
        subprocess.run(
            [str(ruff), "check", "-q", "--fix-only", "--unsafe-fixes", *targets], check=False
        )
        subprocess.run([str(ruff), "format", "-q", *targets], check=True)
        subprocess.run([str(ruff), "check", "-q", *targets], check=True)

    if emitter.missing:
        print(
            f"codegen: {len(emitter.missing)} request fields lack an English description:\n  "
            + "\n  ".join(emitter.missing),
            file=sys.stderr,
        )
    print(
        f"codegen: {len(routes)} routes, {len(contract['error_codes'])} error codes, "
        f"{len(exported)} request bodies, contract {digest[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
