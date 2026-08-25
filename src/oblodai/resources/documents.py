"""Generated PDF/CSV documents.

Every method returns the bytes (:class:`~oblodai.FileResult`); large ranges go through
asynchronous jobs (:meth:`Documents.create_job` -> :meth:`Documents.job_info` ->
:meth:`Documents.job_file`). Payment key.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, cast

from ..contract.models import DocumentJob
from ..contract.requests import DocumentsJobsBody
from ..core.request import Query
from .base import FileResult, Resource

__all__ = ["Documents"]

#: ``lang`` is a 2-letter code (41 supported); ``format`` is ``pdf`` or ``csv`` where offered;
#: ``from``/``to`` are ``YYYY-MM-DD``.
DocumentQuery = Mapping[str, Any]


class Documents(Resource):
    """Statements, certificates, ledgers and per-object reports."""

    def create_job(self, params: DocumentsJobsBody, **options: Any) -> DocumentJob:
        """``POST /v1/documents/jobs`` - queue a large report; poll :meth:`job_info`."""
        return cast(DocumentJob, self._call("POST /v1/documents/jobs", params, **options))

    def job_info(self, job_id: str, **options: Any) -> DocumentJob:
        """``POST /v1/documents/jobs/info``."""
        return cast(
            DocumentJob,
            self._call("POST /v1/documents/jobs/info", {"job_id": job_id}, **options),
        )

    def job_file(self, job_id: str, **options: Any) -> FileResult:
        """``GET /v1/documents/jobs/file`` - the finished job's bytes."""
        return self._file("GET /v1/documents/jobs/file", query={"job_id": job_id}, **options)

    def statement(self, query: Optional[DocumentQuery] = None, **options: Any) -> FileResult:
        """``GET /v1/documents/statement`` - account statement for a period (PDF or CSV)."""
        return self._file("GET /v1/documents/statement", query=_query(query), **options)

    def balance_certificate(
        self, query: Optional[DocumentQuery] = None, **options: Any
    ) -> FileResult:
        """``GET /v1/documents/balance`` - balance certificate (PDF)."""
        return self._file("GET /v1/documents/balance", query=_query(query), **options)

    def fee_schedule(self, query: Optional[DocumentQuery] = None, **options: Any) -> FileResult:
        """``GET /v1/documents/fees`` - the fee schedule in force for the merchant (PDF)."""
        return self._file("GET /v1/documents/fees", query=_query(query), **options)

    def ledger(self, query: Optional[DocumentQuery] = None, **options: Any) -> FileResult:
        """``GET /v1/documents/ledger`` - full ledger export for a period (PDF or CSV)."""
        return self._file("GET /v1/documents/ledger", query=_query(query), **options)

    def split_report(
        self, payment_uuid: str, query: Optional[DocumentQuery] = None, **options: Any
    ) -> FileResult:
        """``GET /v1/documents/split`` - how one payment was split between partners (PDF)."""
        return self._file(
            "GET /v1/documents/split", query=_query(query, uuid=payment_uuid), **options
        )

    def batch_report(
        self, batch_id: str, query: Optional[DocumentQuery] = None, **options: Any
    ) -> FileResult:
        """``GET /v1/documents/batch`` - per-row report of an asynchronous batch."""
        return self._file("GET /v1/documents/batch", query=_query(query, uuid=batch_id), **options)

    def link_report(
        self, link_id: str, query: Optional[DocumentQuery] = None, **options: Any
    ) -> FileResult:
        """``GET /v1/documents/link`` - payment-link report (its invoices)."""
        return self._file("GET /v1/documents/link", query=_query(query, uuid=link_id), **options)

    def wallet_statement(
        self, wallet_uuid: str, query: Optional[DocumentQuery] = None, **options: Any
    ) -> FileResult:
        """``GET /v1/documents/wallet/statement`` - static-wallet statement."""
        return self._file(
            "GET /v1/documents/wallet/statement", query=_query(query, uuid=wallet_uuid), **options
        )

    def referrals_report(self, query: Optional[DocumentQuery] = None, **options: Any) -> FileResult:
        """``GET /v1/documents/referrals`` - referral earnings report."""
        return self._file("GET /v1/documents/referrals", query=_query(query), **options)

    def download(self, kind: str, id: str, query: DocumentQuery, **options: Any) -> FileResult:
        """``GET /v1/documents/{kind}/{id}`` - a public document by its signed link.

        ``exp`` and ``sig`` come from a ``document_url``; no credentials needed. Prefer fetching
        ``document_url`` directly.
        """
        return self._file(
            "GET /v1/documents/{kind}/{id}",
            path_params={"kind": kind, "id": id},
            query=_query(query),
            **options,
        )


def _query(query: Optional[DocumentQuery], **extra: Any) -> Query:
    """Merge the caller's document query with the id field the route reads."""
    merged: Dict[str, Any] = {k: v for k, v in (query or {}).items() if v is not None}
    merged.update(extra)
    return merged
