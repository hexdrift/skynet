"""Lifecycle mutations: clone, retry, cancel, bulk-cancel, bulk-pin, bulk-archive."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter

from ....constants import (
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ....i18n import CANCELLATION_REASON, CLONE_NAME_PREFIX, RETRY_NAME_PREFIX
from ....models import (
    BulkCancelRequest,
    BulkCancelResponse,
    BulkCancelSkipped,
    JobCancelResponse,
    OptimizationStatus,
    OptimizationSubmissionResponse,
)
from ...converters import parse_overview, status_to_job_status
from ...errors import DomainError
from .._helpers import enforce_user_quota
from ..constants import TERMINAL_STATUSES
from ._local import bulk_set_flag, clone_payload, persist_and_enqueue
from .schemas import (
    BulkMetadataRequest,
    BulkMetadataResponse,
    CloneJobRequest,
    CloneJobResponse,
)

logger = logging.getLogger(__name__)


def register_lifecycle_routes(
    router: APIRouter,
    *,
    job_store,
    get_worker_ref: Callable[[], Any],
) -> None:
    """Register mutation routes that change state or queue new work.

    Args:
        router: The router to attach the lifecycle routes to.
        job_store: Job-store the routes read from / mutate.
        get_worker_ref: Zero-arg callable returning the active worker (or
            ``None`` when no worker is bound) — wrapped so tests can inject.
    """

    @router.post(
        "/optimizations/{optimization_id}/cancel",
        response_model=JobCancelResponse,
        status_code=200,
        summary="Cancel a pending or running optimization",
        tags=["agent"],
    )
    def cancel_job(optimization_id: str) -> JobCancelResponse:
        """Cooperatively cancel an active optimization.

        Flips status to ``cancelled`` immediately; the worker stops between
        DSPy calls. One-way — no uncancel.

        Args:
            optimization_id: Optimization id to cancel.

        Returns:
            A ``JobCancelResponse`` confirming the cancellation.

        Raises:
            DomainError: 404 if unknown, 409 if already terminal.
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status in TERMINAL_STATUSES:
            raise DomainError(
                "optimization.already_terminal",
                status=409,
                params={"status": status.value},
            )

        worker = get_worker_ref()
        if worker:
            worker.cancel_job(optimization_id)

        now = datetime.now(UTC).isoformat()
        job_store.update_job(optimization_id, status="cancelled", message=CANCELLATION_REASON, completed_at=now)
        logger.info("Optimization %s (%s) cancelled", optimization_id, status.value)
        return JobCancelResponse(optimization_id=optimization_id, status="cancelled")

    @router.post(
        "/optimizations/bulk-cancel",
        response_model=BulkCancelResponse,
        status_code=200,
        summary="Cancel many running or pending optimizations in a single request",
        tags=["agent"],
    )
    def bulk_cancel_jobs(body: BulkCancelRequest) -> BulkCancelResponse:
        """Cancel a batch of non-terminal optimizations and report per-id outcomes.

        Same semantics as single-ID ``POST /optimizations/{id}/cancel``: flips
        status to ``cancelled`` immediately, worker stops between DSPy calls,
        one-way. Duplicate ids in the request are deduplicated. IDs that don't
        exist or are already terminal are reported in ``skipped`` with the reason.

        Args:
            body: The bulk-cancel request body.

        Returns:
            A ``BulkCancelResponse`` listing cancelled and skipped ids.
        """
        cancelled: list[str] = []
        skipped: list[BulkCancelSkipped] = []
        seen: set[str] = set()
        ordered_unique: list[str] = []
        for optimization_id in body.optimization_ids:
            if optimization_id in seen:
                continue
            seen.add(optimization_id)
            ordered_unique.append(optimization_id)

        if not ordered_unique:
            return BulkCancelResponse(cancelled=cancelled, skipped=skipped)

        status_by_id = job_store.get_jobs_status_by_ids(ordered_unique)

        cancellable: list[str] = []
        for optimization_id in ordered_unique:
            raw_status = status_by_id.get(optimization_id)
            if raw_status is None:
                skipped.append(BulkCancelSkipped(optimization_id=optimization_id, reason="not_found"))
                continue
            status = status_to_job_status(raw_status)
            if status in TERMINAL_STATUSES:
                skipped.append(BulkCancelSkipped(optimization_id=optimization_id, reason=status.value))
                continue
            cancellable.append(optimization_id)

        if cancellable:
            worker = get_worker_ref()
            now = datetime.now(UTC).isoformat()
            for optimization_id in cancellable:
                try:
                    if worker:
                        worker.cancel_job(optimization_id)
                    job_store.update_job(
                        optimization_id,
                        status="cancelled",
                        message=CANCELLATION_REASON,
                        completed_at=now,
                    )
                except Exception as exc:
                    logger.exception("Bulk cancel failed for %s", optimization_id)
                    skipped.append(
                        BulkCancelSkipped(
                            optimization_id=optimization_id,
                            reason=f"error: {exc}",
                        )
                    )
                else:
                    cancelled.append(optimization_id)

        logger.info(
            "Bulk cancel: %d cancelled, %d skipped (requested %d)",
            len(cancelled),
            len(skipped),
            len(body.optimization_ids),
        )
        return BulkCancelResponse(cancelled=cancelled, skipped=skipped)

    @router.post(
        "/optimizations/{optimization_id}/clone",
        response_model=CloneJobResponse,
        status_code=201,
        summary="Duplicate an optimization and queue N copies",
        tags=["agent"],
    )
    def clone_job(optimization_id: str, req: CloneJobRequest) -> CloneJobResponse:
        """Clone a finished or active optimization into ``count`` fresh runs.

        Reads the stored payload, assigns new ids and seeds, and enqueues each
        copy. Each clone's display name is prefixed with ``req.name_prefix`` or
        ``CLONE_NAME_PREFIX``. Respects the per-user quota.

        Args:
            optimization_id: Source optimization id.
            req: Clone request with ``count`` and optional ``name_prefix``.

        Returns:
            A ``CloneJobResponse`` listing every newly enqueued copy.

        Raises:
            DomainError: 404 (unknown source), 409 (no payload / quota),
                500 (corrupt payload).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None

        source_payload = job_data.get("payload")
        if not source_payload or not isinstance(source_payload, dict):
            raise DomainError("optimization.clone_no_payload", status=409)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
        prefix = (req.name_prefix or CLONE_NAME_PREFIX).strip()
        source_name = overview.get(PAYLOAD_OVERVIEW_NAME) or optimization_id[:8]
        username = source_payload.get("username") or overview.get(PAYLOAD_OVERVIEW_USERNAME)

        enforce_user_quota(job_store, cast(str, username))

        created: list[OptimizationSubmissionResponse] = []
        for i in range(req.count):
            suffix = f" ({i + 1})" if req.count > 1 else ""
            cloned_name = f"{prefix} {source_name}{suffix}".strip()
            new_id, payload = clone_payload(
                source_payload,
                optimization_type=optimization_type,
                new_name=cloned_name,
            )
            created.append(persist_and_enqueue(job_store, new_id, payload, optimization_type=optimization_type))

        logger.info("Cloned optimization %s into %d copies", optimization_id, len(created))
        return CloneJobResponse(source_optimization_id=optimization_id, created=created)

    @router.post(
        "/optimizations/{optimization_id}/retry",
        response_model=OptimizationSubmissionResponse,
        status_code=201,
        summary="Re-run a failed or cancelled optimization with the same configuration",
        tags=["agent"],
    )
    def retry_job(optimization_id: str) -> OptimizationSubmissionResponse:
        """Re-run a failed or cancelled optimization using the original payload.

        Only valid when the source optimization is in a terminal non-success
        state. The new run's name is prefixed with ``RETRY_NAME_PREFIX``.
        Respects the per-user quota.

        Args:
            optimization_id: Source optimization id to retry.

        Returns:
            An ``OptimizationSubmissionResponse`` for the new run.

        Raises:
            DomainError: 404 (unknown source), 409 (wrong status / no
                payload — use clone instead), 500 (corrupt payload).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in {OptimizationStatus.failed, OptimizationStatus.cancelled}:
            raise DomainError(
                "optimization.retry_wrong_status",
                status=409,
                params={"status": status.value},
            )

        source_payload = job_data.get("payload")
        if not source_payload or not isinstance(source_payload, dict):
            raise DomainError("optimization.retry_no_payload", status=409)

        overview = parse_overview(job_data)
        optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)
        username = source_payload.get("username") or overview.get(PAYLOAD_OVERVIEW_USERNAME)
        enforce_user_quota(job_store, cast(str, username))

        source_name = overview.get(PAYLOAD_OVERVIEW_NAME) or optimization_id[:8]
        retry_name = f"{RETRY_NAME_PREFIX} {source_name}".strip()
        new_id, payload = clone_payload(source_payload, optimization_type=optimization_type, new_name=retry_name)
        response = persist_and_enqueue(job_store, new_id, payload, optimization_type=optimization_type)
        logger.info("Retried optimization %s as %s", optimization_id, new_id)
        return response

    @router.post(
        "/optimizations/bulk-pin",
        response_model=BulkMetadataResponse,
        summary="Pin or unpin many optimizations in one call",
        tags=["agent"],
    )
    def bulk_pin_jobs(req: BulkMetadataRequest) -> BulkMetadataResponse:
        """Pin or unpin up to 100 optimizations in a single call.

        Args:
            req: Bulk-metadata request with ``optimization_ids`` and ``value``.

        Returns:
            A ``BulkMetadataResponse`` listing successful and skipped ids.
        """
        return bulk_set_flag(job_store, req, flag="pinned")

    @router.post(
        "/optimizations/bulk-archive",
        response_model=BulkMetadataResponse,
        summary="Archive or unarchive many optimizations in one call",
        tags=["agent"],
    )
    def bulk_archive_jobs(req: BulkMetadataRequest) -> BulkMetadataResponse:
        """Archive or unarchive up to 100 optimizations in a single call.

        Args:
            req: Bulk-metadata request with ``optimization_ids`` and ``value``.

        Returns:
            A ``BulkMetadataResponse`` listing successful and skipped ids.
        """
        return bulk_set_flag(job_store, req, flag="archived")
