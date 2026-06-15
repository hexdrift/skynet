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

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...models import (
    BulkDeleteByIdsRequest,
    BulkDeleteByIdsResponse,
    BulkDeleteByIdsSkipped,
)
from ...storage.usage import STORAGE_CATEGORIES
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


class StorageItemResponse(BaseModel):
    """One ranked item in ``GET /usage/storage/items``.

    ``type`` is ``"optimization"``, ``"dataset"`` or ``"chat"`` and ``id`` is that
    object's primary key so the cleanup list can deep-link to it; ``bytes`` is the
    same per-row figure the meter attributes to it.
    """

    id: str
    type: str
    name: str
    bytes: int


class StorageItemsResponse(BaseModel):
    """Envelope for ``GET /usage/storage/items`` — the caller's biggest items."""

    items: list[StorageItemResponse]


class StorageDeleteResponse(BaseModel):
    """Result of a storage-cleanup delete — ``deleted`` is ``False`` when no row matched."""

    deleted: bool


def create_usage_router(*, job_store) -> APIRouter:
    """Build the unified storage-usage router.

    Args:
        job_store: Storage backend exposing ``compute_user_storage``,
            ``compute_user_storage_items`` and ``get_effective_user_storage_quota``
            for the authenticated caller.

    Returns:
        A configured :class:`APIRouter` exposing the ``/usage/storage`` reads.
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

    @router.get(
        "/usage/storage/items",
        response_model=StorageItemsResponse,
        summary="Rank the caller's largest individual items for cleanup",
    )
    def get_storage_items(
        current_user: AuthenticatedUserDep,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> StorageItemsResponse:
        """Return the caller's largest optimizations, datasets and chats by size.

        Args:
            current_user: Authenticated caller whose items are ranked.
            limit: Maximum number of items to return, clamped to ``1..100``.

        Returns:
            A :class:`StorageItemsResponse` whose ``items`` are ordered by
            descending size, for the storage page's "free up space" list.
        """
        items = job_store.compute_user_storage_items(current_user.username, limit)
        return StorageItemsResponse(
            items=[
                StorageItemResponse(id=item.id, type=item.type, name=item.name, bytes=item.bytes)
                for item in items
            ]
        )

    @router.get(
        "/usage/storage/categories/{category}",
        response_model=StorageItemsResponse,
        summary="List every deletable item in one storage category",
    )
    def get_storage_category_items(
        category: str, current_user: AuthenticatedUserDep
    ) -> StorageItemsResponse:
        """Return all of the caller's deletable items in one storage category.

        Args:
            category: One of :data:`~core.storage.usage.STORAGE_CATEGORIES`
                (``optimizations``, ``datasets``, ``agent_chats``,
                ``staged_uploads``), backing that category's cleanup drawer.
            current_user: Authenticated caller whose items are listed.

        Returns:
            A :class:`StorageItemsResponse` with every item in the category,
            ordered by descending size.

        Raises:
            HTTPException: 404 when ``category`` is not a known storage category
                (e.g. a folded-away byproduct name such as ``embeddings``).
        """
        if category not in STORAGE_CATEGORIES:
            raise HTTPException(status_code=404, detail="unknown_category")
        items = job_store.compute_user_storage_category_items(current_user.username, category)
        return StorageItemsResponse(
            items=[
                StorageItemResponse(id=item.id, type=item.type, name=item.name, bytes=item.bytes)
                for item in items
            ]
        )

    @router.delete(
        "/usage/storage/staged/{staged_id}",
        response_model=StorageDeleteResponse,
        summary="Delete one of the caller's pending uploads",
    )
    def delete_staged_upload(
        staged_id: str, current_user: AuthenticatedUserDep
    ) -> StorageDeleteResponse:
        """Delete one staged (pending) upload owned by the caller.

        Args:
            staged_id: Id of the staged dataset to delete.
            current_user: Authenticated caller; the delete is scoped to their rows.

        Returns:
            A :class:`StorageDeleteResponse` whose ``deleted`` flag is ``False``
            when no matching row was found.
        """
        deleted = job_store.delete_staged_dataset(staged_id, current_user.username)
        return StorageDeleteResponse(deleted=deleted)

    @router.post(
        "/usage/storage/staged/bulk-delete",
        response_model=BulkDeleteByIdsResponse,
        summary="Delete many of the caller's pending uploads in one request",
    )
    def bulk_delete_staged_uploads(
        body: BulkDeleteByIdsRequest, current_user: AuthenticatedUserDep
    ) -> BulkDeleteByIdsResponse:
        """Delete a batch of the caller's staged (pending) uploads, per-id outcomes.

        Duplicate ids are deduplicated. The delete is scoped to the caller's rows,
        so an id matching no owned row is reported under ``skipped`` as
        ``not_found``; a per-id store failure is likewise skipped, not raised.

        Args:
            body: The bulk-delete request body carrying the staged-upload ids.
            current_user: Authenticated caller; deletes are scoped to their rows.

        Returns:
            A :class:`BulkDeleteByIdsResponse` listing deleted and skipped ids.
        """
        deleted: list[str] = []
        skipped: list[BulkDeleteByIdsSkipped] = []
        seen: set[str] = set()
        for staged_id in body.ids:
            if staged_id in seen:
                continue
            seen.add(staged_id)
            try:
                removed = job_store.delete_staged_dataset(staged_id, current_user.username)
            except Exception as exc:
                skipped.append(BulkDeleteByIdsSkipped(id=staged_id, reason=f"error: {exc}"))
                continue
            if removed:
                deleted.append(staged_id)
            else:
                skipped.append(BulkDeleteByIdsSkipped(id=staged_id, reason="not_found"))
        return BulkDeleteByIdsResponse(deleted=deleted, skipped=skipped)

    return router
