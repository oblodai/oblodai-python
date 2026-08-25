"""Revenue splits: a percentage of every payment forwarded to a partner. Payout key."""

from __future__ import annotations

from typing import Any, Optional, cast

from ..contract.models import OkResult, SplitConfig, SplitOptIn, SplitRule
from ..contract.requests import SplitConfigSetBody, SplitRuleBody, SplitRuleListBody
from ..core.pagination import Page
from .base import Resource

__all__ = ["Splits"]


class Splits(Resource):
    """Split rules, hold configuration and the recipient opt-in."""

    def create_rule(self, params: SplitRuleBody, **options: Any) -> SplitRule:
        """``POST /v1/split/rule`` - to an external address or to a platform merchant."""
        return cast(SplitRule, self._call("POST /v1/split/rule", params, **options))

    def list_rules(
        self, params: Optional[SplitRuleListBody] = None, **options: Any
    ) -> Page[SplitRule]:
        """``POST /v1/split/rule/list``."""
        return self._page("POST /v1/split/rule/list", params, **options)

    def delete_rule(self, rule_id: str, **options: Any) -> OkResult:
        """``POST /v1/split/rule/delete``."""
        return cast(
            OkResult, self._call("POST /v1/split/rule/delete", {"rule_id": rule_id}, **options)
        )

    def get_config(self, **options: Any) -> SplitConfig:
        """``POST /v1/split/config/get``."""
        return cast(SplitConfig, self._call("POST /v1/split/config/get", **options))

    def set_config(self, params: SplitConfigSetBody, **options: Any) -> SplitConfig:
        """``POST /v1/split/config/set`` - how long split shares are held back for refunds."""
        return cast(SplitConfig, self._call("POST /v1/split/config/set", params, **options))

    def get_opt_in(self, **options: Any) -> SplitOptIn:
        """``POST /v1/split/recipient/optin/get`` - does this merchant accept being a recipient."""
        return cast(SplitOptIn, self._call("POST /v1/split/recipient/optin/get", **options))

    def set_opt_in(self, enabled: bool, **options: Any) -> SplitOptIn:
        """``POST /v1/split/recipient/optin``."""
        return cast(
            SplitOptIn,
            self._call("POST /v1/split/recipient/optin", {"enabled": enabled}, **options),
        )
