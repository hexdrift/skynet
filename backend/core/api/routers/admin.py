"""Admin-only operational routes. [INTERNAL]

All endpoints are hidden from the public Scalar reference (none are in
``_SCALAR_PUBLIC_PATHS``). Used by the in-app admin console only.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ...config import settings
from ..auth import AuthenticatedUser, get_authenticated_user, require_admin_user
from ..directory_client import DirectoryClient, NullDirectoryClient
from ..errors import DomainError

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


class UserQuotaOverrideResponse(BaseModel):
    """Live per-user quota override returned to admin UI."""

    username: str
    quota: int | None = None
    updated_at: str | None = None
    updated_by: str | None = None
    effective_quota: int | None = None
    job_count: int = 0
    last_action: str | None = None


class UserQuotaOverrideRequest(BaseModel):
    """Request body for setting a user's live quota override."""

    username: str = Field(min_length=1)
    quota: int | None = Field(default=None, ge=1)


class UserQuotaAuditResponse(BaseModel):
    """Audit event for a live quota override change."""

    id: int
    actor: str
    target_username: str
    action: str
    old_quota: int | None = None
    new_quota: int | None = None
    created_at: str | None = None


class UserQuotaOverrideListResponse(BaseModel):
    """Envelope for admin quota override listing."""

    default_quota: int
    overrides: list[UserQuotaOverrideResponse]
    audit_events: list[UserQuotaAuditResponse]


class DirectoryUserMatch(BaseModel):
    """Single autocomplete suggestion for the admin user search."""

    username: str
    display_name: str | None = None
    email: str | None = None
    source: str


class DirectoryUserSearchResponse(BaseModel):
    """Envelope for the admin user-search endpoint."""

    matches: list[DirectoryUserMatch]


def _build_quota_response(row: dict[str, Any], *, job_store) -> UserQuotaOverrideResponse:
    """Build one admin quota response row.

    Args:
        row: Raw quota override mapping from storage.
        job_store: Backing job store used to resolve counts and effective quota.

    Returns:
        A populated response model.
    """
    username = str(row["username"])
    return UserQuotaOverrideResponse(
        username=username,
        quota=row.get("quota"),
        updated_at=row.get("updated_at"),
        updated_by=row.get("updated_by"),
        effective_quota=job_store.get_effective_user_quota(username),
        job_count=job_store.count_jobs(username=username),
        last_action=row.get("last_action"),
    )


def _build_audit_response(row: dict[str, Any]) -> UserQuotaAuditResponse:
    """Build one admin quota audit response row.

    Args:
        row: Raw quota audit mapping from storage.

    Returns:
        A populated response model.
    """
    return UserQuotaAuditResponse(
        id=int(row["id"]),
        actor=str(row["actor"]),
        target_username=str(row["target_username"]),
        action=str(row["action"]),
        old_quota=row.get("old_quota"),
        new_quota=row.get("new_quota"),
        created_at=row.get("created_at"),
    )


def _require_admin_dependency(user: AuthenticatedUserDep) -> AuthenticatedUser:
    """FastAPI dependency that returns an authorized admin user.

    Args:
        user: Authenticated user from the signed bearer token.

    Returns:
        The same user when admin authorization passes.
    """
    return require_admin_user(user)


AdminUserDep = Annotated[AuthenticatedUser, Depends(_require_admin_dependency)]


def create_admin_router(
    *,
    job_store,
    directory_client: DirectoryClient | None = None,
) -> APIRouter:
    """Build admin operational routes.

    Args:
        job_store: Backing job store used for live quota override operations.
        directory_client: Optional directory provider for network-wide user
            search; defaults to :class:`NullDirectoryClient` when omitted.

    Returns:
        A configured :class:`APIRouter` exposing admin-only endpoints.
    """
    router = APIRouter(prefix="/admin")
    resolved_directory_client: DirectoryClient = directory_client or NullDirectoryClient()

    @router.get(
        "/quotas",
        response_model=UserQuotaOverrideListResponse,
        status_code=200,
        summary="List live user quota overrides",
    )
    def list_user_quota_overrides(
        admin_user: AdminUserDep,
    ) -> UserQuotaOverrideListResponse:
        """List live per-user quota overrides.

        Args:
            admin_user: Authenticated admin user from the signed bearer token.

        Returns:
            The default quota plus every live override.
        """
        rows = job_store.list_user_quota_overrides()
        audit_rows = job_store.list_user_quota_audit_events()
        return UserQuotaOverrideListResponse(
            default_quota=settings.max_jobs_per_user,
            overrides=[_build_quota_response(row, job_store=job_store) for row in rows],
            audit_events=[_build_audit_response(row) for row in audit_rows],
        )

    @router.put(
        "/quotas",
        response_model=UserQuotaOverrideResponse,
        status_code=200,
        summary="Set a live user quota override",
    )
    def set_user_quota_override(
        payload: UserQuotaOverrideRequest,
        admin_user: AdminUserDep,
    ) -> UserQuotaOverrideResponse:
        """Create or update a live per-user quota override.

        Args:
            payload: Username and quota. A ``null`` quota means unlimited.
            admin_user: Authenticated admin user from the signed bearer token.

        Returns:
            The saved override with current job count.
        """
        normalized_username = payload.username.strip().lower()
        if not normalized_username:
            raise DomainError("admin.invalid_username", status=400)
        has_old_override, old_quota = job_store.get_user_quota_override(normalized_username)
        old_value = old_quota if has_old_override else job_store.get_effective_user_quota(normalized_username)
        job_store.set_user_quota_override(normalized_username, payload.quota, updated_by=admin_user.username)
        job_store.record_user_quota_audit(
            actor=admin_user.username,
            target_username=normalized_username,
            action="set",
            old_quota=old_value,
            new_quota=payload.quota,
        )
        has_override, quota = job_store.get_user_quota_override(normalized_username)
        if not has_override:
            raise DomainError("admin.quota_save_failed", status=500)
        return _build_quota_response(
            {
                "username": normalized_username,
                "quota": quota,
                "updated_at": None,
                "updated_by": admin_user.username,
                "last_action": "set",
            },
            job_store=job_store,
        )

    @router.delete(
        "/quotas/{username}",
        response_model=UserQuotaOverrideResponse,
        status_code=200,
        summary="Delete a live user quota override",
    )
    def delete_user_quota_override(
        username: str,
        admin_user: AdminUserDep,
    ) -> UserQuotaOverrideResponse:
        """Delete a live quota override so config fallback applies.

        Args:
            username: User whose live quota override should be removed.
            admin_user: Authenticated admin user from the signed bearer token.

        Returns:
            The user's current effective quota after deletion.
        """
        normalized_username = username.strip().lower()
        if not normalized_username:
            raise DomainError("admin.invalid_username", status=400)
        has_old_override, old_quota = job_store.get_user_quota_override(normalized_username)
        job_store.delete_user_quota_override(normalized_username)
        if has_old_override:
            job_store.record_user_quota_audit(
                actor=admin_user.username,
                target_username=normalized_username,
                action="delete",
                old_quota=old_quota,
                new_quota=job_store.get_effective_user_quota(normalized_username),
            )
        return UserQuotaOverrideResponse(
            username=normalized_username,
            quota=None,
            updated_at=None,
            updated_by=None,
            effective_quota=job_store.get_effective_user_quota(normalized_username),
            job_count=job_store.count_jobs(username=normalized_username),
            last_action="delete",
        )

    @router.get(
        "/users/search",
        response_model=DirectoryUserSearchResponse,
        status_code=200,
        summary="Autocomplete users by username, display name, or email",
    )
    def search_users(
        admin_user: AdminUserDep,
        q: Annotated[str, Query(description="Free-text fragment to match.")] = "",
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> DirectoryUserSearchResponse:
        """Return merged autocomplete matches from DB-known users + the directory.

        Args:
            admin_user: Authenticated admin user from the signed bearer token.
            q: Free-text fragment.
            limit: Maximum number of matches to return.

        Returns:
            Distinct matches with the source channel attached to each row.
        """
        del admin_user
        query = q.strip()
        if not query:
            return DirectoryUserSearchResponse(matches=[])

        matches: list[DirectoryUserMatch] = []
        seen: set[str] = set()

        for username in job_store.search_usernames(query, limit=limit):
            normalized = (username or "").strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            matches.append(DirectoryUserMatch(username=normalized, source="db"))

        for entry in resolved_directory_client.search_users(query, limit=limit):
            normalized = entry.username.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            matches.append(
                DirectoryUserMatch(
                    username=normalized,
                    display_name=entry.display_name,
                    email=entry.email,
                    source="directory",
                )
            )

        return DirectoryUserSearchResponse(matches=matches[:limit])

    return router
