"""Hard-delete routes: single, grid-pair, and bulk. [MIXED]

Public dev surface (in ``_SCALAR_PUBLIC_PATHS``):
- ``DELETE /optimizations/{id}`` — delete a single optimization.

Internal (dashboard plumbing, hidden from public docs):
- ``DELETE /optimizations/{id}/pair/{idx}`` — per-pair delete inside a grid.
- ``POST /optimizations/bulk-delete`` — multi-select bulk delete.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from ....constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
)
from ....models import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkDeleteSkipped,
    GridSearchResponse,
    JobDeleteResponse,
)
from ...auth import AuthenticatedUser, get_authenticated_user, is_admin
from ...converters import parse_overview, status_to_job_status
from ...errors import DomainError
from .._helpers import _program_cache, job_owner, load_job_for_user
from ..constants import TERMINAL_STATUSES

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


def register_deletion_routes(router: APIRouter, *, job_store) -> None:
    """Register hard-delete routes on ``router``.

    Args:
        router: The router to attach the delete routes to.
        job_store: Job-store the routes read from / mutate.
    """

    @router.delete(
        "/optimizations/{optimization_id}",
        response_model=JobDeleteResponse,
        status_code=200,
        summary="Permanently delete an optimization and all its data",
        tags=["agent"],
    )
    def delete_job(optimization_id: str, current_user: AuthenticatedUserDep) -> JobDeleteResponse:
        """Hard-delete an optimization and all its data (not recoverable).

        Only terminal optimizations can be deleted — cancel first if still
        active. Use ``PATCH /archive`` for a reversible soft-hide.

        Args:
            optimization_id: Optimization id to delete.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``JobDeleteResponse`` confirming the delete.

        Raises:
            DomainError: 404 if unknown or inaccessible to the caller, 409
                if still active.
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise DomainError(
                "optimization.cannot_delete",
                status=409,
                params={"status": status.value},
            )

        job_store.delete_job(optimization_id)
        logger.info("Optimization %s deleted", optimization_id)
        return JobDeleteResponse(optimization_id=optimization_id, deleted=True)

    @router.delete(
        "/optimizations/{optimization_id}/pair/{pair_index}",
        response_model=GridSearchResponse,
        status_code=200,
        summary="Delete a single pair from a grid-search result",
    )
    def delete_grid_pair(
        optimization_id: str, pair_index: int, current_user: AuthenticatedUserDep
    ) -> GridSearchResponse:
        """Remove one pair from a terminal grid search and return the updated result.

        Drops the pair from ``grid_result.pair_results``, clears its cached
        program, and recomputes ``total_pairs`` / ``completed_pairs`` /
        ``failed_pairs`` / ``best_pair``. The stored result JSON is rewritten
        in place.

        Args:
            optimization_id: Grid-search optimization id.
            pair_index: Index of the pair to remove.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            The updated ``GridSearchResponse`` after the pair was dropped.

        Raises:
            DomainError: 404 (unknown id / inaccessible / not a grid / no
                result / missing pair), 409 (not yet terminal), 500
                (corrupt result).
        """
        job_data = load_job_for_user(job_store, optimization_id, current_user)

        overview = parse_overview(job_data)
        if overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE) != OPTIMIZATION_TYPE_GRID_SEARCH:
            raise DomainError("grid_search.not_a_grid_search", status=404)

        status = status_to_job_status(job_data.get("status", "pending"))
        if status not in TERMINAL_STATUSES:
            raise DomainError(
                "grid_search.cannot_delete_pair",
                status=409,
                params={"status": status.value},
            )

        result_data = job_data.get("result")
        if not result_data or not isinstance(result_data, dict):
            raise DomainError("grid_search.no_result_to_modify", status=404)

        try:
            grid_result = GridSearchResponse.model_validate(result_data)
        except ValidationError:
            raise DomainError("grid_search.corrupt_result", status=500) from None

        remaining = [pr for pr in grid_result.pair_results if pr.pair_index != pair_index]
        if len(remaining) == len(grid_result.pair_results):
            raise DomainError(
                "grid_search.pair_position_missing",
                status=404,
                pair_index=pair_index,
            )

        successful = [pr for pr in remaining if not pr.error and pr.optimized_test_metric is not None]
        failed = [pr for pr in remaining if pr.error]
        best = None
        if successful:
            best = max(successful, key=lambda pr: pr.optimized_test_metric or 0.0)

        updated = grid_result.model_copy(
            update={
                "pair_results": remaining,
                "total_pairs": len(remaining),
                "completed_pairs": len(successful),
                "failed_pairs": len(failed),
                "best_pair": best,
            }
        )

        job_store.update_job(optimization_id, result=updated.model_dump(mode="json"))
        _program_cache.pop(f"{optimization_id}_pair_{pair_index}", None)
        # Invalidate the single-program cache entry too (best pair may have changed).
        _program_cache.pop(optimization_id, None)
        logger.info("Optimization %s pair %d deleted", optimization_id, pair_index)
        return updated

    @router.post(
        "/optimizations/bulk-delete",
        response_model=BulkDeleteResponse,
        status_code=200,
        summary="Delete many optimizations in a single request",
        tags=["agent"],
    )
    def bulk_delete_jobs(body: BulkDeleteRequest, current_user: AuthenticatedUserDep) -> BulkDeleteResponse:
        """Delete a batch of terminal optimizations and report per-id outcomes.

        Duplicate ids are deduplicated. Non-terminal, missing, or
        non-owned (for non-admin callers) ids are returned under
        ``skipped``; a bulk database failure reports every requested id as
        skipped rather than raising 500.

        Args:
            body: The bulk-delete request body.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``BulkDeleteResponse`` listing successful and skipped ids.
        """
        deleted: list[str] = []
        skipped: list[BulkDeleteSkipped] = []
        seen: set[str] = set()
        ordered_unique: list[str] = []
        for optimization_id in body.optimization_ids:
            if optimization_id in seen:
                continue
            seen.add(optimization_id)
            ordered_unique.append(optimization_id)

        if not ordered_unique:
            return BulkDeleteResponse(deleted=deleted, skipped=skipped)

        admin = is_admin(current_user)
        if admin:
            allowed = ordered_unique
        else:
            allowed = []
            for optimization_id in ordered_unique:
                try:
                    job_data = job_store.get_job(optimization_id)
                except KeyError:
                    skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason="not_found"))
                    continue
                owner = job_owner(job_data)
                if owner is None or owner != current_user.username:
                    skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason="not_found"))
                    continue
                allowed.append(optimization_id)

        if not allowed:
            return BulkDeleteResponse(deleted=deleted, skipped=skipped)

        status_by_id = job_store.get_jobs_status_by_ids(allowed)

        deletable: list[str] = []
        for optimization_id in allowed:
            raw_status = status_by_id.get(optimization_id)
            if raw_status is None:
                skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason="not_found"))
                continue
            status = status_to_job_status(raw_status)
            if status not in TERMINAL_STATUSES:
                skipped.append(BulkDeleteSkipped(optimization_id=optimization_id, reason=status.value))
                continue
            deletable.append(optimization_id)

        if deletable:
            try:
                job_store.delete_jobs(deletable)
            except Exception as exc:
                # Batch DB failure is reported as per-id skip reason instead of 500.
                logger.exception("Bulk delete failed for %d ids", len(deletable))
                skipped.extend(
                    BulkDeleteSkipped(
                        optimization_id=optimization_id,
                        reason=f"error: {exc}",
                    )
                    for optimization_id in deletable
                )
            else:
                deleted.extend(deletable)

        logger.info(
            "Bulk delete: %d deleted, %d skipped (requested %d)",
            len(deleted),
            len(skipped),
            len(body.optimization_ids),
        )
        return BulkDeleteResponse(deleted=deleted, skipped=skipped)
