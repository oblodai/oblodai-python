"""Which operations are long-running, and how to follow them - declared by the API itself.

A create call listed in :data:`LRO` returns a :class:`~oblodai.core.poller.Job` instead of its
bare acknowledgement; ``job.wait()`` polls the operation named here until the status is one of
that poll's ``terminal`` statuses. The tables are generated from the contract's ``x-sdk-poll``
(:mod:`oblodai.generated.lro`); this module only gives them their public home.
"""

from __future__ import annotations

from .core.route import Poll
from .generated.lro import LRO, POLLS, TERMINAL_STATUSES

__all__ = ["LRO", "POLLS", "TERMINAL_STATUSES", "Poll"]
