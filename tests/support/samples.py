"""Minimal valid wire bodies for generated models, built from the models themselves.

Tests that exercise the transport (retries, keys, signing) need an answer the method can parse;
``sample(PaymentView, uuid="u")`` is every required field with a neutral value, plus overrides.
"""

from __future__ import annotations

import dataclasses
import typing
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Type, cast

import oblodai.generated.models as models
from oblodai.core.model import Model

__all__ = ["sample"]


def _value(hint: Any) -> Any:
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union or (origin is not None and type(None) in args):
        if type(None) in args:
            return None
        return _value(args[0])
    if args and type(None) in args:  # `X | None`
        return None
    if origin in (list, typing.List, tuple):
        return []
    if origin in (dict, typing.Dict) or hint is typing.Any:
        return {}
    if origin is not None and origin.__name__ in ("Mapping", "Sequence"):
        return {} if origin.__name__ == "Mapping" else []
    if isinstance(hint, type):
        if issubclass(hint, Enum):
            return next(iter(hint)).value
        if issubclass(hint, Model):
            return sample(hint)
        if hint is bool:
            return False
        if hint is int:
            return 0
        if hint is float:
            return 0.0
        if hint is Decimal:
            return "1"
        if hint is str:
            return "x"
    return None


def sample(model: Type[Model], **overrides: Any) -> Dict[str, Any]:
    """Every required field of ``model`` with a neutral wire value, then ``overrides``."""
    hints = typing.get_type_hints(model, vars(models))
    required = getattr(model, "_REQUIRED", ())
    out: Dict[str, Any] = {}
    for field in dataclasses.fields(cast(Any, model)):
        if field.name == "extra":
            continue
        wire = field.name[:-1] if field.name.endswith("_") else field.name
        if wire in required:
            out[wire] = _value(hints[field.name])
    out.update(overrides)
    return out
