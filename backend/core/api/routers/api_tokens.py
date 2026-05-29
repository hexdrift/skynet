"""Personal Access Token (PAT) management for the authenticated user. [INTERNAL]

Backs the Settings → API panel. Each user owns exactly one active token;
generating a new one rotates (replaces) the previous. The plaintext token is
returned only once — at creation — and only its SHA-256 hash is persisted, so
a leaked database never yields a usable credential. Authentication for these
routes accepts either the session JWT (web app) or an existing PAT, via the
shared :func:`get_authenticated_user` dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...storage.models import ApiTokenModel
from ..auth import (
    AuthenticatedUser,
    generate_api_token,
    get_authenticated_user,
    hash_api_token,
    token_last4,
)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


# Metadata about the caller's active token. Never includes the secret itself.
class ApiTokenInfo(BaseModel):
    last4: str = Field(description="Last four characters of the active token, for display.")
    created_at: datetime = Field(description="When the active token was generated.")
    last_used_at: datetime | None = Field(
        default=None, description="When the token was last presented to the API."
    )


# Returned exactly once, at creation — carries the full plaintext token.
class ApiTokenCreated(BaseModel):
    token: str = Field(description="The full plaintext token — shown only once; store it now.")
    last4: str = Field(description="Last four characters, for later display.")
    created_at: datetime = Field(description="When the token was generated.")


def create_api_tokens_router(*, job_store) -> APIRouter:
    """Build the personal-access-token management router.

    Args:
        job_store: Job-store instance whose ORM engine backs the routes.

    Returns:
        A FastAPI ``APIRouter`` exposing get / generate / revoke for the
        caller's single API token.
    """
    router = APIRouter()

    @router.get(
        "/settings/api-token",
        response_model=ApiTokenInfo | None,
        summary="Get metadata for the caller's API token",
    )
    def get_api_token(user: AuthenticatedUserDep) -> ApiTokenInfo | None:
        """Return the caller's active token metadata, or ``null`` if none exists.

        Args:
            user: Authenticated caller; only their own token is returned.

        Returns:
            The token metadata (never the secret), or ``None`` when the caller
            has no active token.
        """
        with Session(job_store.engine) as session:
            row = session.get(ApiTokenModel, user.username)
            if row is None:
                return None
            return ApiTokenInfo(
                last4=row.last4, created_at=row.created_at, last_used_at=row.last_used_at
            )

    @router.post(
        "/settings/api-token",
        response_model=ApiTokenCreated,
        status_code=201,
        summary="Generate (or rotate) the caller's API token",
    )
    def create_api_token(user: AuthenticatedUserDep) -> ApiTokenCreated:
        """Generate a fresh token for the caller, replacing any existing one.

        The previous token (if any) is deleted in the same transaction, so at
        most one token is ever valid per user. The plaintext is returned here
        and nowhere else — only its hash is stored.

        Args:
            user: Authenticated caller who will own the new token.

        Returns:
            The newly created token, including its one-time plaintext value.
        """
        token = generate_api_token()
        now = datetime.now(UTC)
        with Session(job_store.engine) as session:
            existing = session.get(ApiTokenModel, user.username)
            if existing is not None:
                session.delete(existing)
                session.flush()
            session.add(
                ApiTokenModel(
                    username=user.username,
                    token_hash=hash_api_token(token),
                    last4=token_last4(token),
                    created_at=now,
                )
            )
            session.commit()
        return ApiTokenCreated(token=token, last4=token_last4(token), created_at=now)

    @router.delete(
        "/settings/api-token",
        status_code=204,
        summary="Revoke the caller's API token",
    )
    def delete_api_token(user: AuthenticatedUserDep) -> None:
        """Revoke the caller's active token, if any.

        Idempotent: revoking when no token exists still succeeds with 204.

        Args:
            user: Authenticated caller whose token is revoked.
        """
        with Session(job_store.engine) as session:
            existing = session.get(ApiTokenModel, user.username)
            if existing is not None:
                session.delete(existing)
                session.commit()

    return router
