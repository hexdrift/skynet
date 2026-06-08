"""Route for the caller's unified storage usage.

Exposes a single read endpoint backing the account-wide "X of Y used" meter and
the quota modal. The number reported here is the same total the save/run gate
enforces (see :func:`core.api.routers._helpers.enforce_storage_quota`), so the
meter and the 409 can never disagree: both read
:meth:`core.storage.remote.RemoteJobStore.compute_user_storage` and the caller's
effective budget from
:meth:`core.storage.remote.RemoteJobStore.get_effective_user_storage_quota`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import AuthenticatedUser, get_authenticated_user

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


class StorageUsageResponse(BaseModel):
    """Envelope for ``GET /usage/storage`` — the caller's account-wide usage.

    ``breakdown`` maps each storage category (the keys of
    ``core.storage.usage.STORAGE_CATEGORIES``) to its byte contribution so the
    quota modal can show where the space went.
    """

    used_bytes: int
    quota_bytes: int
    breakdown: dict[str, int]


def create_usage_router(*, job_store) -> APIRouter:
    """Build the unified storage-usage router.

    Args:
        job_store: Storage backend exposing ``compute_user_storage`` and
            ``get_effective_user_storage_quota`` for the authenticated caller.

    Returns:
        A configured :class:`APIRouter` exposing ``GET /usage/storage``.
    """
    router = APIRouter()

    @router.get(
        "/usage/storage",
        response_model=StorageUsageResponse,
        summary="Report the caller's unified storage usage against their budget",
    )
    def get_storage_usage(current_user: AuthenticatedUserDep) -> StorageUsageResponse:
        """Return the caller's total stored bytes, per-category breakdown, and budget.

        Args:
            current_user: Authenticated caller whose storage is summed.

        Returns:
            A :class:`StorageUsageResponse` with the total, the effective budget,
            and the per-category breakdown for the "X of Y used" display.
        """
        usage = job_store.compute_user_storage(current_user.username)
        quota = job_store.get_effective_user_storage_quota(current_user.username)
        return StorageUsageResponse(
            used_bytes=usage.total,
            quota_bytes=quota,
            breakdown=usage.breakdown,
        )

    return router
