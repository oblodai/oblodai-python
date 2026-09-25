"""The model base the generated models stand on: unknown fields and enum values never break parsing,
``repr`` stays short and never shows a secret, and request parameters merge from a model or a
mapping plus keyword arguments.

Per Ruling 4 the models here are test-local, shaped exactly as the generator emits them.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Tuple, Union

import pytest

from oblodai.core.errors import ConfigError
from oblodai.core.model import UNSET, Model, Unset, merge_params, parse_enum


class Status(str, Enum):
    PENDING = "pending"
    PAID = "paid"


@dataclasses.dataclass(frozen=True, repr=False)
class Link(Model):
    _FIELDS: ClassVar[Tuple[str, ...]] = ("id", "claim_token", "status", "note")

    id: str
    claim_token: Optional[str] = None
    status: Union[Status, str, None] = None
    note: Optional[str] = None
    extra: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Link:
        status = data.get("status")
        return cls(
            id=data["id"],
            claim_token=data.get("claim_token"),
            status=None if status is None else parse_enum(Status, status),
            note=data.get("note"),
            extra={k: v for k, v in data.items() if k not in cls._FIELDS},
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = dict(self.extra)
        out["id"] = self.id
        if self.claim_token is not None:
            out["claim_token"] = self.claim_token
        if self.status is not None:
            out["status"] = self.status.value if isinstance(self.status, Enum) else self.status
        if self.note is not None:
            out["note"] = self.note
        return out


@dataclasses.dataclass(frozen=True, repr=False)
class Holder(Model):
    webhook_secret: str
    links: List[Link]
    extra: Mapping[str, Any] = dataclasses.field(default_factory=dict)


# --- unknown fields and enum values ------------------------------------------------------------


def test_unknown_field_lands_in_extra() -> None:
    link = Link.from_dict({"id": "l1", "status": "paid", "brand_new": {"x": 1}})
    assert link.extra == {"brand_new": {"x": 1}}
    assert link.to_dict()["brand_new"] == {"x": 1}


def test_known_enum_value_parses_to_the_member() -> None:
    assert parse_enum(Status, "paid") is Status.PAID


def test_unknown_enum_value_stays_a_plain_string() -> None:
    link = Link.from_dict({"id": "l1", "status": "refunded_on_the_moon"})
    assert link.status == "refunded_on_the_moon"
    assert not isinstance(link.status, Status)


def test_model_is_a_model() -> None:
    assert isinstance(Link(id="x"), Model)


# --- repr --------------------------------------------------------------------------------------


def test_repr_masks_secret_token_and_signature_fields() -> None:
    link = Link(id="l1", claim_token="tok-SECRET", extra={"signature": "sig-SECRET", "ok": 1})
    holder = Holder(webhook_secret="whsec-SECRET", links=[link])
    text = repr(holder)
    assert "SECRET" not in text
    assert text.startswith("Holder(")
    assert "l1" in text
    assert "'ok': 1" in text


def test_repr_skips_unset_optionals_and_empty_extra() -> None:
    assert repr(Link(id="l1")) == "Link(id='l1')"


def test_repr_is_at_most_1024_characters() -> None:
    text = repr(Link(id="x" * 5000))
    assert len(text) <= 1024
    assert text.endswith("...)")


# --- merge_params ------------------------------------------------------------------------------


def test_merge_params_from_keywords_only_drops_unset() -> None:
    assert merge_params(None, amount="10", currency=UNSET, note=None) == {
        "amount": "10",
        "note": None,
    }


def test_merge_params_from_a_mapping_plus_keywords() -> None:
    assert merge_params({"amount": "10"}, currency="USDT") == {"amount": "10", "currency": "USDT"}


def test_merge_params_from_a_model_uses_to_dict() -> None:
    assert merge_params(Link(id="l1", note="n"), status="paid") == {
        "id": "l1",
        "note": "n",
        "status": "paid",
    }


def test_merge_params_same_field_twice_is_bad_config() -> None:
    """The same rule in every SDK: a field given both ways is ``sdk.bad_config`` before the network."""
    with pytest.raises(ConfigError, match="amount") as caught:
        merge_params({"amount": "10"}, amount="11")
    assert (caught.value.code, caught.value.field) == ("sdk.bad_config", "amount")


def test_merge_params_a_none_or_empty_params_field_is_no_value() -> None:
    assert merge_params({"idempotency_key": None, "note": ""}, idempotency_key="k", note="n") == {
        "idempotency_key": "k",
        "note": "n",
    }


def test_merge_params_does_not_mutate_the_callers_mapping() -> None:
    params = {"amount": "10"}
    merge_params(params, currency="USDT")
    assert params == {"amount": "10"}


def test_merge_params_rejects_other_types() -> None:
    with pytest.raises(TypeError):
        merge_params(["amount"])  # type: ignore[arg-type]


def test_unset_is_falsy_singleton() -> None:
    assert isinstance(UNSET, Unset)
    assert not UNSET
    assert repr(UNSET) == "UNSET"
    assert Unset() is UNSET
