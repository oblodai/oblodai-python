#!/usr/bin/env python3
"""Generate src/oblodai/contract/{routes,enums,requests,version}.py from contract/contract.json.

contract.json is exported by the core's own conformance table (TestSDKContract_Export);
contract/descriptions.en.json carries the English field documentation. Nothing in the generated
files is edited by hand: run `python scripts/codegen.py`, and `python scripts/check_drift.py`
in CI to prove the committed files still match the snapshot.

``--out DIR`` writes into ``DIR/contract`` instead of the package, which is how the drift check
regenerates without touching the working tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from emit_requests import (
    FIELD_ENUMS,
    REQUEST_OVERRIDES,
    ROUTE_FIELD_ENUMS,
    RequestEmitter,
    camel,
)
from toolchain import ROOT, find_ruff

CONTRACT_DIR = ROOT / "contract"
PACKAGE_DIR = ROOT / "src" / "oblodai"

GENERATED = ("routes.py", "enums.py", "requests.py", "version.py")

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


def header(core_commit: str) -> str:
    return (
        f"# GENERATED FILE - do not edit. Source: contract/contract.json "
        f"(core {core_commit[:12]}).\n"
        "# Regenerate with: python scripts/codegen.py\n"
    )


def is_safe(route: Dict[str, Any]) -> bool:
    """The core's own hand-classified ``safe`` flag - never a guess from the path.

    ``safe`` means the route is read-only: a transport failure may be re-sent without an
    idempotency key and without risking a duplicate side effect. The core states it per route;
    a snapshot that does not is too old to generate from.
    """
    value = route.get("safe")
    if not isinstance(value, bool):
        raise SystemExit(
            f"contract.json: {route['method']} {route['path']} has no boolean `safe` field - "
            "re-export the contract from a core that declares it"
        )
    return value


def type_name(route_key: str, used: Dict[str, str]) -> str:
    method, path = route_key.split(" ", 1)
    base = camel(path.replace("/v1/", "/").replace("{", "").replace("}", ""))
    name = f"{base}Body"
    if name in used and used[name] != route_key:
        name = f"{camel(method)}{name}"
    used[name] = route_key
    return name


def literal_of(values: Tuple[str, ...]) -> str:
    return "Literal[" + ", ".join(json.dumps(v) for v in values) + "]"


def render_tuple(values: Tuple[str, ...], per_line: int = 4, indent: str = "    ") -> str:
    lines = []
    for i in range(0, len(values), per_line):
        chunk = ", ".join(json.dumps(v) for v in values[i : i + per_line])
        lines.append(f"{indent}{chunk},")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=PACKAGE_DIR,
        help="package root to write into (default: src/oblodai)",
    )
    out_dir = parser.parse_args(argv).out / "contract"
    raw = (CONTRACT_DIR / "contract.json").read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    descriptions_path = CONTRACT_DIR / "descriptions.en.json"
    descriptions: Dict[str, Any] = (
        json.loads(descriptions_path.read_text("utf-8"))
        if descriptions_path.exists()
        else {"request": {}, "response": {}}
    )
    head = header(contract["core_commit"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # Fail loudly rather than silently guessing retry safety from the shape of a path.
    for route in contract["routes"]:
        is_safe(route)

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
    (out_dir / "routes.py").write_text("\n".join(out), "utf-8")

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
    (out_dir / "enums.py").write_text("\n".join(lines), "utf-8")

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
    (out_dir / "requests.py").write_text("\n\n".join(body), "utf-8")

    # --- version.py --------------------------------------------------------------------------
    digest = hashlib.sha256(raw).hexdigest()
    (out_dir / "version.py").write_text(
        head
        + "\n"
        + f'CONTRACT_CORE_COMMIT = "{contract["core_commit"]}"\n'
        + f'CONTRACT_EXPORTED_AT = "{contract["exported_at"]}"\n'
        + f'CONTRACT_HASH = "{digest}"\n',
        "utf-8",
    )

    ruff = find_ruff()
    if ruff:
        targets = [str(out_dir / f) for f in GENERATED]
        subprocess.run([ruff, "check", "-q", "--fix-only", "--unsafe-fixes", *targets], check=False)
        subprocess.run([ruff, "format", "-q", *targets], check=True)
        subprocess.run([ruff, "check", "-q", *targets], check=True)

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
