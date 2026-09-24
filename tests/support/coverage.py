"""The coverage ledger: which client method calls which operation, worked out from the code.

Every namespace method is called once on a probe whose ``_request`` records the route instead of
sending it, so the ledger cannot drift from the generated resources. Path parameters get a
placeholder; everything else is left to its default.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Tuple

from oblodai import Oblodai
from oblodai.aio import AsyncOblodai
from oblodai.core.route import RouteSpec

__all__ = ["COVERAGE", "call", "method_of", "namespaces"]

#: The value every path parameter gets in a probe or a wiring test.
PATH_VALUE = "x1"


class _Probe(Exception):
    def __init__(self, route: RouteSpec) -> None:
        super().__init__(route.operation_id)
        self.route = route


def _probe_request(*args: Any, **kwargs: Any) -> Any:
    raise _Probe(args[0])


def namespaces(client: Any) -> Dict[str, Any]:
    """``name -> namespace`` of a client: every public attribute that is a generated resource."""
    return {
        name: value
        for name, value in vars(client).items()
        if type(value).__module__.startswith("oblodai.generated.")
    }


def _positional(method: Callable[..., Any]) -> List[str]:
    """Path parameters: the positional-only parameters other than ``params``."""
    return [
        p.name
        for p in inspect.signature(method).parameters.values()
        if p.kind is inspect.Parameter.POSITIONAL_ONLY and p.name != "params"
    ]


def call(client: Any, operation_id: str, *args: Any, **kwargs: Any) -> Any:
    """Call the method behind ``operation_id`` with placeholder path parameters."""
    namespace, name = method_of(operation_id, asynchronous=isinstance(client, AsyncOblodai))
    method = getattr(getattr(client, namespace), name)
    return method(*[PATH_VALUE] * len(_positional(method)), *args, **kwargs)


def _ledger(client: Any) -> Dict[str, Tuple[str, str]]:
    out: Dict[str, Tuple[str, str]] = {}
    for namespace, resource in namespaces(client).items():
        for name, method in inspect.getmembers(resource, inspect.ismethod):
            if name.startswith("_"):
                continue
            resource._request = _probe_request
            try:
                result = method(*[PATH_VALUE] * len(_positional(method)))
                if inspect.iscoroutine(result):
                    result.send(None)
            except _Probe as probe:
                op = probe.route.operation_id
                assert op not in out, f"{op}: reached by {out[op]} and {(namespace, name)}"
                out[op] = (namespace, name)
            finally:
                del resource._request
    return out


_SYNC = _ledger(Oblodai(public_id="p", secret="s" * 32, env={}))
_ASYNC = _ledger(AsyncOblodai(public_id="p", secret="s" * 32, env={}))

#: ``operationId -> (namespace, method)`` of the synchronous client.
COVERAGE: Dict[str, Tuple[str, str]] = _SYNC


def method_of(operation_id: str, *, asynchronous: bool = False) -> Tuple[str, str]:
    return (_ASYNC if asynchronous else _SYNC)[operation_id]
