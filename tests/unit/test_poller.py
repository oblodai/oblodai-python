"""Long-running operations: a batch or document job comes back as a :class:`Job` to ``wait()`` on.

Per Ruling 4 the calls go through test-local ``Resource`` subclasses whose routes (keyed by
``operationId``, as the generated table keys them) and poll-answer parsers are built here.
Per Ruling 3 the wrapping itself is the runtime's: ``_request`` looks the route up in
``oblodai.lro``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping

import httpx
import pytest

from oblodai import RequestOptions, RouteSpec
from oblodai.aio.base import AsyncResource
from oblodai.core.errors import ConfigError
from oblodai.core.poller import AsyncJob, Job
from oblodai.lro import LRO
from oblodai.resources.base import FileResult, Resource
from tests.support.clients import make_async_client, make_client

CREATE_BATCH = RouteSpec(
    method="POST",
    path="/v1/payout/batch",
    auth="key",
    idempotent=True,
    safe=False,
    bare=False,
    operation_id="createPayoutBatch",
)
BATCH_INFO = RouteSpec(
    method="POST",
    path="/v1/batch/info",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    operation_id="getBatchInfo",
)
CREATE_DOC = RouteSpec(
    method="POST",
    path="/v1/documents/jobs",
    auth="key",
    idempotent=True,
    safe=False,
    bare=False,
    operation_id="createDocumentJob",
)
DOC_INFO = RouteSpec(
    method="POST",
    path="/v1/documents/jobs/info",
    auth="key",
    idempotent=False,
    safe=True,
    bare=False,
    operation_id="getDocumentJob",
)
DOC_FILE = RouteSpec(
    method="GET",
    path="/v1/documents/jobs/file",
    auth="key",
    idempotent=False,
    safe=True,
    bare=True,
    operation_id="downloadDocumentJobFile",
)
OPERATIONS = {r.operation_id: r for r in (CREATE_BATCH, BATCH_INFO, CREATE_DOC, DOC_INFO, DOC_FILE)}

NO_OPTIONS = RequestOptions()


class Submitted:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.batch_id = data["batch_id"]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Submitted:
        return cls(data)


class Info:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.status = data["status"]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Info:
        return cls(data)


MODELS = {"BatchInfoResponse": Info.from_dict, "DocumentJobView": Info.from_dict}


class Batches(Resource):
    _operations = OPERATIONS
    _models = MODELS

    def create(self, body: Dict[str, Any], options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(CREATE_BATCH, body, options, parse=Submitted.from_dict)


class Documents(Resource):
    _operations = OPERATIONS
    _models: Mapping[str, Any] = {}

    def create_job(self, body: Dict[str, Any], options: RequestOptions = NO_OPTIONS) -> Any:
        return self._request(CREATE_DOC, body, options)


class AsyncBatches(AsyncResource):
    _operations = OPERATIONS
    _models = MODELS

    async def create(self, body: Dict[str, Any], options: RequestOptions = NO_OPTIONS) -> Any:
        return await self._request(CREATE_BATCH, body, options, parse=Submitted.from_dict)


class AsyncDocuments(AsyncResource):
    _operations = OPERATIONS

    async def create_job(self, body: Dict[str, Any], options: RequestOptions = NO_OPTIONS) -> Any:
        return await self._request(CREATE_DOC, body, options)


def ok(result: Any) -> httpx.Response:
    return httpx.Response(200, json={"state": 0, "result": result})


class Server:
    """Answers the create call, then the given poll statuses in turn (the last one repeats)."""

    def __init__(self, id_field: str, *statuses: str) -> None:
        self.id_field = id_field
        self.statuses = list(statuses)
        self.requests: List[httpx.Request] = []

    @property
    def polls(self) -> List[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("/info")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/info"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return ok({self.id_field: "id-1", "status": status})
        if path == DOC_FILE.path:
            return httpx.Response(
                200,
                content=b"%PDF-1",
                headers={
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="ledger.pdf"',
                },
            )
        return ok({self.id_field: "id-1", "status": "pending", "count": 2})


def test_the_lro_table_is_the_sdks_decision() -> None:
    assert LRO == {
        "createPaymentBatch": "getBatchInfo",
        "createPayoutBatch": "getBatchInfo",
        "createRefundBatch": "getBatchInfo",
        "createTransferBatch": "getBatchInfo",
        "createDocumentJob": "getDocumentJob",
    }


def test_batch_wait_polls_until_completed() -> None:
    server = Server("batch_id", "pending", "processing", "completed")
    job = Batches(make_client(server).transport).create({"items": [1, 2]})
    assert isinstance(job, Job)
    assert job.id == "id-1"
    assert isinstance(job.result, Submitted)
    done = job.wait(interval=0)
    assert isinstance(done, Info)
    assert done.status == "completed"
    assert len(server.polls) == 3
    assert all(json.loads(r.content) == {"batch_id": "id-1"} for r in server.polls)


def test_stopped_is_terminal_too() -> None:
    server = Server("batch_id", "processing", "stopped")
    job = Batches(make_client(server).transport).create({})
    assert job.wait(interval=0).status == "stopped"
    assert len(server.polls) == 2


def test_wait_times_out_with_timeout_error() -> None:
    server = Server("batch_id", "pending")
    job = Batches(make_client(server).transport).create({})
    with pytest.raises(TimeoutError, match="id-1"):
        job.wait(timeout=0.01)


def test_raw_mode_parses_to_a_job() -> None:
    server = Server("batch_id", "completed")
    raw = Batches(make_client(server).transport).with_raw_response.create({})
    job = raw.parse()
    assert isinstance(job, Job)
    assert job.wait(interval=0).status == "completed"


def test_polls_keep_the_calls_headers_but_not_its_idempotency_key() -> None:
    server = Server("batch_id", "completed")
    options = RequestOptions(idempotency_key="k-1", extra_headers={"X-Tenant": "t"})
    Batches(make_client(server).transport).create({}, options).wait(interval=0)
    create, poll = server.requests
    assert create.headers["idempotency-key"] == "k-1"
    assert "idempotency-key" not in poll.headers
    assert poll.headers["x-tenant"] == "t"


def test_document_job_waits_and_downloads() -> None:
    server = Server("job_id", "queued", "processing", "done")
    job = Documents(make_client(server).transport).create_job({"kind": "ledger"})
    assert job.result == {"job_id": "id-1", "status": "pending", "count": 2}
    # no parser for the poll answer: the unwrapped result comes back as is
    assert job.wait(interval=0) == {"job_id": "id-1", "status": "done"}
    file = job.download()
    assert isinstance(file, FileResult)
    assert file.content == b"%PDF-1"
    assert file.filename == "ledger.pdf"
    request = server.requests[-1]
    assert request.method == "GET"
    assert request.url.params["job_id"] == "id-1"


def test_failed_document_job_is_returned_not_polled_forever() -> None:
    server = Server("job_id", "failed")
    job = Documents(make_client(server).transport).create_job({})
    assert job.wait(interval=0)["status"] == "failed"


def test_a_batch_job_has_nothing_to_download() -> None:
    server = Server("batch_id", "completed")
    job = Batches(make_client(server).transport).create({})
    with pytest.raises(TypeError):
        job.download()


def test_unresolvable_poll_route_is_a_config_error() -> None:
    class Bare(Resource):
        _operations: Mapping[str, RouteSpec] = {}

    server = Server("batch_id", "completed")
    with pytest.raises(ConfigError):
        Bare(make_client(server).transport)._request(CREATE_BATCH, {}, NO_OPTIONS)


async def test_async_batch_wait() -> None:
    server = Server("batch_id", "pending", "processing", "completed")
    job = await AsyncBatches(make_async_client(server).transport).create({})
    assert isinstance(job, AsyncJob)
    assert job.id == "id-1"
    done = await job.wait(interval=0)
    assert done.status == "completed"
    assert len(server.polls) == 3


async def test_async_wait_times_out() -> None:
    server = Server("batch_id", "pending")
    job = await AsyncBatches(make_async_client(server).transport).create({})
    with pytest.raises(TimeoutError):
        await job.wait(timeout=0.01)


async def test_async_document_download() -> None:
    server = Server("job_id", "done")
    job = await AsyncDocuments(make_async_client(server).transport).create_job({})
    assert (await job.wait(interval=0))["status"] == "done"
    assert (await job.download()).content == b"%PDF-1"
