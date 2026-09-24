"""`str(e)` reads in a log line: `[code] message (request_id=...)`."""

from __future__ import annotations

import pytest

from oblodai.core.errors import ConfigError, ContractError, TransportError, ValidationError


def test_str_carries_code_message_and_request_id() -> None:
    err = ValidationError("payment.bad_amount", "bad", request_id="rq-9")
    assert str(err) == "[payment.bad_amount] bad (request_id=rq-9)"
    assert err.message == "bad"
    assert err.args == ("[payment.bad_amount] bad (request_id=rq-9)",)


def test_str_without_request_id_has_no_suffix() -> None:
    err = ValidationError("payment.bad_amount", "bad")
    assert str(err) == "[payment.bad_amount] bad"
    assert err.message == "bad"


def test_every_subclass_renders_the_same_way() -> None:
    assert (
        str(ConfigError("sdk.float_amount", "no floats", "amount"))
        == "[sdk.float_amount] no floats"
    )
    assert str(TransportError("transport.timeout", "slow")) == "[transport.timeout] slow"
    assert str(ContractError("odd", 502)) == "[sdk.bad_envelope] odd"


def test_raised_error_shows_the_rendered_text() -> None:
    with pytest.raises(ValidationError, match=r"^\[payment\.bad_amount\] bad \(request_id=rq-1\)$"):
        raise ValidationError("payment.bad_amount", "bad", request_id="rq-1")
