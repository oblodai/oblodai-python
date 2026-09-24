"""Waiters for long-running operations (batches, document jobs).

:class:`Job` / :class:`AsyncJob` carry the create call's answer (``.result``) and the job's
``.id``; ``.wait()`` polls until the status is terminal (:data:`oblodai.lro.TERMINAL_STATUSES`)
and returns the last poll answer - a terminal status is returned, not raised, so a ``failed``
job is inspected like a finished one. Which operations become jobs is :mod:`oblodai.lro`.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Generic,
    Mapping,
    Optional,
    TypeVar,
)

from ..lro import LRO, POLLS, TERMINAL_STATUSES
from .errors import ConfigError, ContractError
from .options import RequestOptions
from .route import RouteSpec

if TYPE_CHECKING:
    from ..resources.base import FileResult

__all__ = [
    "AsyncJob",
    "Job",
    "JobPlan",
    "job_id",
    "plan_job",
    "poll_options",
    "status_of",
]

T = TypeVar("T")

#: ``model name -> parser`` for poll answers.
Parsers = Mapping[str, Callable[[Any], Any]]


@dataclass(frozen=True)
class JobPlan:
    """Everything needed to follow a job created by one route."""

    poll_route: RouteSpec
    id_field: str
    #: Parser of the poll answer; ``None`` returns the unwrapped result as is.
    parse: Optional[Callable[[Any], Any]]
    download_route: Optional[RouteSpec]


def _generated(module: str) -> Any:
    name = f"oblodai.generated.{module}"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        # Only the generated package itself may be missing; a broken import inside it is a bug.
        if exc.name not in ("oblodai.generated", name):
            raise
        return None


def _route(operation_id: str, operations: Optional[Mapping[str, RouteSpec]]) -> RouteSpec:
    if operations is None:
        routes = _generated("routes")
        operations = getattr(routes, "ROUTES", {}) if routes is not None else {}
    try:
        return operations[operation_id]
    except KeyError:
        raise ConfigError(
            "sdk.lro_unresolved",
            f"no route for operation {operation_id!r}, needed to follow a long-running call",
        ) from None


def _parser(model: str, parsers: Optional[Parsers]) -> Optional[Callable[[Any], Any]]:
    if parsers is not None:
        return parsers.get(model)
    models = _generated("models")
    cls = getattr(models, model, None) if models is not None else None
    return getattr(cls, "from_dict", None)


def plan_job(
    route: RouteSpec,
    operations: Optional[Mapping[str, RouteSpec]] = None,
    parsers: Optional[Parsers] = None,
) -> Optional[JobPlan]:
    """The plan for a route listed in :data:`~oblodai.lro.LRO`, else ``None``.

    ``operations`` and ``parsers`` default to the generated route table and models.
    """
    poll_id = LRO.get(route.operation_id) if route.operation_id else None
    if poll_id is None:
        return None
    poll = POLLS[poll_id]
    return JobPlan(
        poll_route=_route(poll_id, operations),
        id_field=poll.id_field,
        parse=_parser(poll.model, parsers),
        download_route=_route(poll.download, operations) if poll.download else None,
    )


def job_id(plan: JobPlan, result: Any) -> str:
    """The job's id out of the create call's unwrapped result."""
    value = result.get(plan.id_field) if isinstance(result, Mapping) else None
    if not value:
        raise ContractError(f"long-running call answered without {plan.id_field}", 200, result)
    return str(value)


def poll_options(options: RequestOptions) -> RequestOptions:
    """The create call's options for the polls: same timeout, retries and headers; no
    idempotency key (it belongs to the create) and a fresh request id per poll."""
    return RequestOptions(
        timeout=options.timeout,
        max_retries=options.max_retries,
        extra_headers=options.extra_headers,
    )


def status_of(answer: Any) -> str:
    """The ``status`` of a poll answer, model or mapping."""
    status = answer.get("status") if isinstance(answer, Mapping) else getattr(answer, "status", "")
    return str(status.value if isinstance(status, Enum) else status or "")


def _timeout(job_id: str, timeout: float, status: str) -> TimeoutError:
    return TimeoutError(f"job {job_id} is still {status or 'unfinished'} after {timeout:g}s")


class Job(Generic[T]):
    """A long-running operation: ``.id``, the create answer ``.result``, and ``.wait()``."""

    def __init__(
        self,
        id: str,
        result: Any,
        poll: Callable[[], T],
        download: Optional[Callable[[], FileResult]] = None,
    ) -> None:
        self.id = id
        #: The create call's answer, parsed as the method would return it.
        self.result = result
        self._poll = poll
        self._download = download

    def wait(self, timeout: float = 300, interval: float = 2.0) -> T:
        """Poll every ``interval`` seconds until the job's status is terminal; return that answer.

        Raises :class:`TimeoutError` when ``timeout`` seconds pass first.
        """
        deadline = time.monotonic() + timeout
        while True:
            answer = self._poll()
            status = status_of(answer)
            if status in TERMINAL_STATUSES:
                return answer
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _timeout(self.id, timeout, status)
            time.sleep(min(interval, remaining))

    def download(self) -> FileResult:
        """The finished job's file (document jobs only)."""
        if self._download is None:
            raise TypeError(f"job {self.id} produces no file to download")
        return self._download()

    def __repr__(self) -> str:
        return f"Job(id={self.id!r})"


class AsyncJob(Generic[T]):
    """The async twin of :class:`Job`: ``await job.wait()``, ``await job.download()``."""

    def __init__(
        self,
        id: str,
        result: Any,
        poll: Callable[[], Awaitable[T]],
        download: Optional[Callable[[], Awaitable[FileResult]]] = None,
    ) -> None:
        self.id = id
        #: The create call's answer, parsed as the method would return it.
        self.result = result
        self._poll = poll
        self._download = download

    async def wait(self, timeout: float = 300, interval: float = 2.0) -> T:
        """Poll every ``interval`` seconds until the job's status is terminal; return that answer.

        Raises :class:`TimeoutError` when ``timeout`` seconds pass first.
        """
        deadline = time.monotonic() + timeout
        while True:
            answer = await self._poll()
            status = status_of(answer)
            if status in TERMINAL_STATUSES:
                return answer
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _timeout(self.id, timeout, status)
            await asyncio.sleep(min(interval, remaining))

    async def download(self) -> FileResult:
        """The finished job's file (document jobs only)."""
        if self._download is None:
            raise TypeError(f"job {self.id} produces no file to download")
        return await self._download()

    def __repr__(self) -> str:
        return f"AsyncJob(id={self.id!r})"
