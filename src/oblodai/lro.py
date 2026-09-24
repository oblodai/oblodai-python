"""Which operations are long-running, and how to follow them - a decision of this SDK, not of the API.

A create call listed in :data:`LRO` returns a :class:`~oblodai.core.poller.Job` instead of its
bare acknowledgement; ``job.wait()`` polls the operation named here until the status is terminal.
The runtime applies it by the route's ``operationId`` (Ruling 3): the generator knows nothing of
this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

__all__ = ["LRO", "POLLS", "TERMINAL_STATUSES", "Poll"]

#: ``create operationId -> poll operationId``.
LRO: Dict[str, str] = {
    "createPaymentBatch": "getBatchInfo",
    "createPayoutBatch": "getBatchInfo",
    "createRefundBatch": "getBatchInfo",
    "createTransferBatch": "getBatchInfo",
    "createDocumentJob": "getDocumentJob",
}


@dataclass(frozen=True)
class Poll:
    """How to follow one kind of job."""

    #: The job's id in the create answer; sent under the same name to the poll (and download).
    id_field: str
    #: The model the poll answer parses to (from the generated models, when present).
    model: str
    #: The ``operationId`` that returns the finished job's file, if the job makes one.
    download: Optional[str] = None


#: ``poll operationId -> how to follow it``.
POLLS: Dict[str, Poll] = {
    "getBatchInfo": Poll(id_field="batch_id", model="BatchInfoResponse"),
    "getDocumentJob": Poll(
        id_field="job_id", model="DocumentJobView", download="downloadDocumentJobFile"
    ),
}

#: Statuses after which a job no longer changes: a batch ends ``completed`` or ``stopped``
#: (``on_error=stop``), a document job ``done``, ``failed`` or ``expired``.
TERMINAL_STATUSES: FrozenSet[str] = frozenset({"completed", "stopped", "done", "failed", "expired"})
