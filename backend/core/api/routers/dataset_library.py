"""Routes for the personal dataset library — save, list, read, rename, delete.

A library dataset is a single saved file: lean metadata plus the row bytes
behind the :class:`DatasetBlobStore` seam (see
:mod:`core.storage.dataset_library`). These endpoints are the CRUD surface the
three producer doorways (tagger, upload page, optimization Data tab) and the
submit-wizard consumer call.

PR1 scopes every dataset to its owner: a caller sees and mutates only the
datasets whose ``owner_username`` matches their lowercased username (admins may
reach any). Cross-user sharing arrives in a later change and slots in behind the
same access helper without reshaping these routes.

Saving gates on three limits, in order: the per-file compressed cap
(``settings.dataset_max_file_bytes`` → 413), content-hash dedupe (a byte-
identical re-save returns the existing entry, charged nothing), and the
per-user compressed quota (``settings.dataset_user_quota_bytes`` → 409). All
accounting is on the compressed ``stored_bytes``; the uncompressed ``byte_size``
is what the UI shows.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...config import settings
from ...storage.dataset_library import (
    DatasetLibraryStore,
    DatasetRecord,
    PostgresDatasetBlobStore,
)
from ..auth import AuthenticatedUser, get_authenticated_user, is_admin
from ..errors import DomainError

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


class SaveDatasetRequest(BaseModel):
    """Request body for ``POST /datasets/library`` — rows plus saved schema."""

    name: str = Field(min_length=1, max_length=255)
    source: str = Field(default="upload", max_length=32)
    dataset: list[dict[str, Any]] = Field(min_length=1, max_length=200_000)
    column_schema: dict[str, Any] = Field(default_factory=dict)


class RenameDatasetRequest(BaseModel):
    """Request body for ``PATCH /datasets/library/{id}`` — the new display name."""

    name: str = Field(min_length=1, max_length=255)


class DatasetSummary(BaseModel):
    """One library dataset's metadata, as returned to the client."""

    id: str
    name: str
    source: str
    row_count: int
    column_count: int
    byte_size: int
    content_hash: str
    created_at: str
    updated_at: str


class UsageMeter(BaseModel):
    """Aggregate library storage used by the caller against their quota."""

    used_bytes: int
    quota_bytes: int


class SaveDatasetResponse(BaseModel):
    """Envelope for ``POST /datasets/library`` — the entry and whether it deduped."""

    dataset: DatasetSummary
    deduplicated: bool


class DatasetListResponse(BaseModel):
    """Envelope for ``GET /datasets/library`` — the caller's entries and usage."""

    datasets: list[DatasetSummary]
    usage: UsageMeter


class DatasetRowsResponse(BaseModel):
    """Envelope for ``GET /datasets/library/{id}/rows`` — columns and rows."""

    id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class DeleteDatasetResponse(BaseModel):
    """Envelope for ``DELETE /datasets/library/{id}`` — definitive delete flag."""

    deleted: bool


def _summary(record: DatasetRecord) -> DatasetSummary:
    """Project a :class:`DatasetRecord` onto the client-facing summary.

    Args:
        record: The stored dataset metadata.

    Returns:
        The :class:`DatasetSummary` for the API response.
    """
    return DatasetSummary(
        id=record.id,
        name=record.name,
        source=record.source,
        row_count=record.row_count,
        column_count=record.column_count,
        byte_size=record.byte_size,
        content_hash=record.content_hash,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _columns_of(record: DatasetRecord, rows: list[dict[str, Any]]) -> list[str]:
    """Resolve a dataset's column order for the rows response.

    Args:
        record: The dataset metadata; its saved ``column_order`` wins when set.
        rows: The decompressed rows, used as the fallback column source.

    Returns:
        The ordered column names.
    """
    order = record.column_schema.get("column_order")
    if isinstance(order, list) and order:
        return [str(col) for col in order]
    return list(rows[0].keys()) if rows else []


def create_dataset_library_router(*, job_store) -> APIRouter:
    """Build the personal dataset-library CRUD router.

    Args:
        job_store: Storage backend whose ``engine`` carries the ``datasets`` and
            ``dataset_blobs`` tables; used to construct the library store.

    Returns:
        A configured :class:`APIRouter` exposing the owner-scoped library
        endpoints under ``/datasets/library``.
    """
    store = DatasetLibraryStore(job_store.engine, PostgresDatasetBlobStore(job_store.engine))

    def _require_owned(dataset_id: str, caller: AuthenticatedUser) -> DatasetRecord:
        """Return a dataset the caller may access, or raise 404 otherwise.

        A non-owner who is not an admin gets the same 404 as a missing dataset
        so the endpoint never leaks the existence of another user's entry.

        Args:
            dataset_id: Id of the requested dataset.
            caller: Authenticated caller.

        Returns:
            The owned :class:`DatasetRecord`.

        Raises:
            DomainError: 404 when the dataset is unknown or not the caller's.
        """
        record = store.get_dataset(dataset_id)
        if record is None or (record.owner_username != caller.username and not is_admin(caller)):
            raise DomainError("dataset.library.not_found", status=404)
        return record

    router = APIRouter()

    @router.post(
        "/datasets/library",
        response_model=SaveDatasetResponse,
        summary="Save a dataset to the caller's personal library",
    )
    def save_dataset(
        payload: SaveDatasetRequest,
        current_user: AuthenticatedUserDep,
    ) -> SaveDatasetResponse:
        """Save rows as a new library entry, gating on size, dedupe, and quota.

        The rows are serialized and compressed once, then checked against the
        per-file cap, the owner's existing entries (byte-identical re-saves
        return the existing entry without storing a second copy), and the
        per-user quota — in that order.

        Args:
            payload: The dataset name, source, rows, and saved column schema.
            current_user: Authenticated owner of the new entry.

        Returns:
            A :class:`SaveDatasetResponse` carrying the stored summary and
            whether an existing byte-identical entry was returned instead.

        Raises:
            DomainError: 413 when the compressed file exceeds the per-file cap;
                409 when storing it would exceed the per-user quota.
        """
        staged = store.stage(payload.dataset, payload.column_schema)
        if staged.stored_bytes > settings.dataset_max_file_bytes:
            raise DomainError(
                "dataset.library.too_large",
                status=413,
                max_mb=round(settings.dataset_max_file_bytes / (1024 * 1024), 1),
            )
        existing = store.find_by_hash(current_user.username, staged.digest)
        if existing is not None:
            return SaveDatasetResponse(dataset=_summary(existing), deduplicated=True)
        used = store.used_bytes(current_user.username)
        if used + staged.stored_bytes > settings.dataset_user_quota_bytes:
            raise DomainError(
                "dataset.library.quota_exceeded",
                status=409,
                used_mb=round(used / (1024 * 1024), 1),
                quota_mb=round(settings.dataset_user_quota_bytes / (1024 * 1024), 1),
            )
        record = store.commit_staged(
            owner_username=current_user.username,
            name=payload.name,
            source=payload.source,
            staged=staged,
        )
        return SaveDatasetResponse(dataset=_summary(record), deduplicated=False)

    @router.get(
        "/datasets/library",
        response_model=DatasetListResponse,
        summary="List the caller's saved datasets with a usage meter",
    )
    def list_datasets(current_user: AuthenticatedUserDep) -> DatasetListResponse:
        """Return the caller's datasets (newest first) and their storage usage.

        Args:
            current_user: Authenticated owner whose library is listed.

        Returns:
            A :class:`DatasetListResponse` with one summary per entry and the
            compressed-bytes usage meter for the "X of Y used" display.
        """
        records = store.list_datasets(current_user.username)
        usage = UsageMeter(
            used_bytes=store.used_bytes(current_user.username),
            quota_bytes=settings.dataset_user_quota_bytes,
        )
        return DatasetListResponse(datasets=[_summary(r) for r in records], usage=usage)

    @router.get(
        "/datasets/library/{dataset_id}",
        response_model=DatasetSummary,
        summary="Fetch one saved dataset's metadata",
    )
    def get_dataset(
        dataset_id: str,
        current_user: AuthenticatedUserDep,
    ) -> DatasetSummary:
        """Return one library dataset's metadata, scoped to the caller.

        Args:
            dataset_id: Id of the requested dataset.
            current_user: Authenticated caller.

        Returns:
            The :class:`DatasetSummary` for the entry.

        Raises:
            DomainError: 404 when the dataset is unknown or not the caller's.
        """
        return _summary(_require_owned(dataset_id, current_user))

    @router.get(
        "/datasets/library/{dataset_id}/rows",
        response_model=DatasetRowsResponse,
        summary="Fetch a saved dataset's rows for preview or wizard pre-fill",
    )
    def get_dataset_rows(
        dataset_id: str,
        current_user: AuthenticatedUserDep,
    ) -> DatasetRowsResponse:
        """Return a dataset's decompressed rows plus its column order.

        Args:
            dataset_id: Id of the requested dataset.
            current_user: Authenticated caller.

        Returns:
            A :class:`DatasetRowsResponse` with the ordered columns and rows.

        Raises:
            DomainError: 404 when the dataset is unknown, not the caller's, or
                its row bytes are missing.
        """
        record = _require_owned(dataset_id, current_user)
        rows = store.get_rows(dataset_id)
        if rows is None:
            raise DomainError("dataset.library.not_found", status=404)
        return DatasetRowsResponse(
            id=dataset_id,
            columns=_columns_of(record, rows),
            rows=rows,
            row_count=len(rows),
        )

    @router.patch(
        "/datasets/library/{dataset_id}",
        response_model=DatasetSummary,
        summary="Rename a saved dataset",
    )
    def rename_dataset(
        dataset_id: str,
        payload: RenameDatasetRequest,
        current_user: AuthenticatedUserDep,
    ) -> DatasetSummary:
        """Rename one library dataset, scoped to the caller.

        Args:
            dataset_id: Id of the dataset to rename.
            payload: The new display name.
            current_user: Authenticated caller.

        Returns:
            The updated :class:`DatasetSummary`.

        Raises:
            DomainError: 404 when the dataset is unknown or not the caller's.
        """
        _require_owned(dataset_id, current_user)
        record = store.rename_dataset(dataset_id, payload.name)
        if record is None:
            raise DomainError("dataset.library.not_found", status=404)
        return _summary(record)

    @router.delete(
        "/datasets/library/{dataset_id}",
        response_model=DeleteDatasetResponse,
        summary="Delete a saved dataset and its bytes",
    )
    def delete_dataset(
        dataset_id: str,
        current_user: AuthenticatedUserDep,
    ) -> DeleteDatasetResponse:
        """Delete one library dataset and its stored bytes, scoped to the caller.

        Args:
            dataset_id: Id of the dataset to delete.
            current_user: Authenticated caller.

        Returns:
            A :class:`DeleteDatasetResponse` with ``deleted`` set to ``True``.

        Raises:
            DomainError: 404 when the dataset is unknown or not the caller's.
        """
        _require_owned(dataset_id, current_user)
        store.delete_dataset(dataset_id)
        return DeleteDatasetResponse(deleted=True)

    return router
