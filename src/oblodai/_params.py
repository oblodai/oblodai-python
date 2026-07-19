"""Белые списки полей денежных create-эндпоинтов и их проверка.

Зачем это нужно. Create-методы принимают ``**params`` и отправляют их в тело подписанного
запроса как есть. Опечатка в имени поля из-за этого НЕ вызывала ошибку: неизвестный ключ
молча долетал до шлюза, шлюз (``encoding/json``) неизвестные поля игнорирует — и денежная
операция тихо исполнялась с ДРУГИМ смыслом. Классический пример: ``amout="1"`` вместо
``amount="1"`` создаёт инвойс на нулевую сумму, а ``lifetme=600`` — со сроком по умолчанию,
и оба ответа выглядят «успешными».

Поэтому имена полей сверяются со списком, который поддерживает сам шлюз (структуры запросов
в ``services/core/internal/app/payapi``), и на неизвестное имя летит :class:`TypeError` —
до подписи и до отправки. Известные поля работают ровно как раньше: список описывает то, что
шлюз и так принимает, ничего нового не добавляя и ничего старого не запрещая.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, FrozenSet, Iterable

# ``idempotency_key`` — kwarg самого SDK (уходит в заголовок ``Idempotency-Key``, в тело
# запроса не попадает). Разрешён везде, где метод его поддерживает.
_SDK_KWARGS: FrozenSet[str] = frozenset({"idempotency_key"})

# POST /v1/payment — payapi.PaymentRequest
PAYMENT_FIELDS: FrozenSet[str] = frozenset({
    "amount",
    "currency",
    "order_id",
    "network",
    "to_currency",
    "lifetime",
    "subtract",
    "accuracy_payment_percent",
    "url_callback",
    "url_return",
    "url_success",
    "additional_data",
    "payer_email",
    "theme",
    "is_payment_multiple",
    "is_refresh",
})

# POST /v1/payout — payapi.PayoutRequest
PAYOUT_FIELDS: FrozenSet[str] = frozenset({
    "amount",
    "currency",
    "order_id",
    "address",
    "network",
    "is_subtract",
    "memo",
    "url_callback",
    "from_currency",
    "source",
})

# POST /v1/payout/link — payapi.PayoutLinkItem
PAYOUT_LINK_FIELDS: FrozenSet[str] = frozenset({
    "currency",
    "network",
    "amount",
    "reference",
    "title",
    "note",
    "email",
    "expires_in_hours",
})

# POST /v1/payment/link — payapi.PaymentLinkCreateRequest
PAYMENT_LINK_FIELDS: FrozenSet[str] = frozenset({
    "title",
    "description",
    "amount_mode",
    "currency",
    "amount_fixed",
    "amount_min",
    "amount_max",
    "pinned_currency",
    "pinned_network",
    "expires_in",
})

# POST /v1/split/rule — payapi.SplitRuleRequest
SPLIT_RULE_FIELDS: FrozenSet[str] = frozenset({
    "address",
    "network",
    "merchant_id",
    "percent",
    "note",
})


def _suggest(name: str, allowed: Iterable[str]) -> str:
    """Подсказка «возможно, имелось в виду …» для опечатки в имени поля."""
    close = difflib.get_close_matches(name, sorted(allowed), n=3, cutoff=0.6)
    if not close:
        return ""
    return " Возможно, имелось в виду: " + ", ".join(repr(c) for c in close) + "."


def check_params(
    method: str,
    params: Dict[str, Any],
    allowed: FrozenSet[str],
    *,
    allow_idempotency_key: bool = True,
) -> Dict[str, Any]:
    """Сверяет имена полей со списком; на неизвестное имя кидает ``TypeError``.

    :param method: имя метода для сообщения об ошибке, например ``"payments.create"``.
    :param params: kwargs вызова (возвращаются как есть, если всё в порядке).
    :param allowed: белый список полей тела запроса.
    :param allow_idempotency_key: разрешить SDK-kwarg ``idempotency_key``.
    :raises TypeError: если встретилось хотя бы одно неизвестное имя.
    """
    known = allowed | _SDK_KWARGS if allow_idempotency_key else allowed
    unknown = [k for k in params if k not in known]
    if not unknown:
        return params

    unknown.sort()
    head = ", ".join(repr(k) for k in unknown)
    plural = "неизвестные поля" if len(unknown) > 1 else "неизвестное поле"
    msg = "{}(): {}: {}.".format(method, plural, head)
    if len(unknown) == 1:
        msg += _suggest(unknown[0], known)
    else:
        for k in unknown:
            hint = _suggest(k, known)
            if hint:
                msg += " {} —{}".format(repr(k), hint)
    msg += " Допустимые поля: " + ", ".join(sorted(known)) + "."
    raise TypeError(msg)
