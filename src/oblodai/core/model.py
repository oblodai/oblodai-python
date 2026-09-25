"""The base the generated models stand on.

Generated models are frozen dataclasses deriving from :class:`Model`. Parsing is tolerant by
design: a field the SDK does not know yet lands in ``extra`` and an enum value it does not know
yet stays a plain ``str`` (:func:`parse_enum`), so a new server release never breaks an old SDK.

Request parameters come either as a model / mapping or as keyword arguments;
:func:`merge_params` folds both into one body, with :data:`UNSET` marking a keyword the caller
did not pass (``None`` is a value: it is sent as JSON ``null``).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Type, TypeVar, Union

from .errors import ConfigError
from .logger import is_sensitive, redact

__all__ = ["REPR_LIMIT", "UNSET", "Model", "Unset", "merge_params", "parse_enum"]

E = TypeVar("E", bound=Enum)

#: The longest ``repr`` a model produces; anything longer is cut and ends with ``...)``.
REPR_LIMIT = 1024

_REDACTED = "[redacted]"


class Model:
    """Base class of every response and request model.

    Subclasses are ``@dataclass(frozen=True, repr=False)`` with an ``extra`` field that keeps the
    fields this SDK version does not know. ``repr`` is short (at most :data:`REPR_LIMIT`
    characters), omits fields that are ``None`` and never shows the value of a field whose name
    looks secret (``secret``, ``token``, ``signature``, ...).
    """

    #: Fields of the answer this SDK version does not know yet, exactly as received.
    extra: Mapping[str, Any]

    def __repr__(self) -> str:
        parts = []
        for field in dataclasses.fields(self):  # type: ignore[arg-type]
            value = getattr(self, field.name)
            if value is None or (field.name == "extra" and not value):
                continue
            if is_sensitive(field.name):
                shown = _REDACTED
            elif isinstance(value, (Mapping, list)):
                shown = repr(redact(value))
            else:
                shown = repr(value)
            parts.append(f"{field.name}={shown}")
        text = f"{type(self).__name__}({', '.join(parts)})"
        if len(text) > REPR_LIMIT:
            text = text[: REPR_LIMIT - 4] + "...)"
        return text


def parse_enum(cls: Type[E], value: Any) -> Union[E, str]:
    """The member of ``cls`` for ``value``; an unknown value stays a plain ``str``."""
    try:
        return cls(value)
    except ValueError:
        return str(value)


class Unset:
    """The type of :data:`UNSET`: "this keyword argument was not passed"."""

    _instance: Optional[Unset] = None

    def __new__(cls) -> Unset:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNSET"


#: Default of every optional keyword parameter: dropped from the request body.
UNSET = Unset()


def merge_params(params: Union[Model, Mapping[str, Any], None], /, **fields: Any) -> Dict[str, Any]:
    """One request body from ``params`` (a model, a mapping or ``None``) and keyword ``fields``.

    Keywords left :data:`UNSET` are dropped. A field given both ways (a ``params`` value that is
    not ``None`` or ``""``) is :class:`~oblodai.ConfigError` ``sdk.bad_config`` before anything is
    sent, as in every Oblodai SDK: silently preferring one would hide a bug in the caller - and for
    the sandbox faucet's ``idempotency_key`` a wrong guess re-credits or refuses a retry.
    """
    if params is None:
        body: Dict[str, Any] = {}
    elif isinstance(params, Model):
        body = dict(params.to_dict())  # type: ignore[attr-defined]
    elif isinstance(params, Mapping):
        body = dict(params)
    else:
        raise TypeError(f"params must be a model or a mapping, not {type(params).__name__}")
    for name, value in fields.items():
        if isinstance(value, Unset):
            continue
        if body.get(name) not in (None, ""):
            raise ConfigError(
                "sdk.bad_config",
                f"{name!r} is given both in params and as a keyword argument; keep one",
                name,
            )
        body[name] = value
    return body
