"""Access-control foundation for Google-Drive-style optimization sharing.

Defines the effective-role vocabulary, the helpers that read and write the
per-optimization sharing config (the active share-link row plus its member
grants), and :func:`resolve_share_access` — the single resolver every
share-scoped route consults to turn a ``(token, user)`` pair into an effective
role (or ``None`` for no access).

Two sharing modes coexist on one optimization:

* ``general_access`` on the active link selects the anonymous policy:
  ``restricted`` (owner + invited members only) or ``anyone`` (anyone holding
  the link gets a view-only, inference-free snapshot).
* Member grants invite specific users at a tier role (``viewer`` / ``editor``
  / ``owner``) regardless of the anonymous policy.

The resolver is intentionally pure to ``(session, token, user)``: it reads the
job owner straight from the ``jobs`` row on the same session so no router or
job-store wiring leaks into the access layer.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..storage.models import JobModel, OptimizationShareGrantModel, OptimizationShareLinkModel
from .auth import AuthenticatedUser, is_admin
from .routers._helpers import job_owner


class ShareRole(StrEnum):
    """Effective access a caller resolves to on a shared optimization.

    Ordered loosest-to-tightest privilege:

    * ``view`` — anonymous, read-only composite (owner hidden, no inference).
    * ``viewer`` — read (real owner shown) + run inference + clone.
    * ``editor`` — viewer + rename + manage sharing + cancel/retry.
    * ``owner`` — editor + delete; the actual creator and admins are owners.
    """

    view = "view"
    viewer = "viewer"
    editor = "editor"
    owner = "owner"


# General-access policy stored on the active share-link row.
GENERAL_ACCESS_RESTRICTED = "restricted"
GENERAL_ACCESS_ANYONE = "anyone"

# Roles a member grant may carry. ``view`` is never a stored grant role — it is
# only the anonymous effective role derived from an ``anyone`` link.
MEMBER_ROLES: frozenset[str] = frozenset({ShareRole.viewer, ShareRole.editor, ShareRole.owner})


def _normalize_username(username: str) -> str:
    """Return the canonical lowercased form used for owner/member comparison.

    Args:
        username: Raw username from a token claim or invite request.

    Returns:
        The stripped, lowercased username.
    """
    return username.strip().lower()


def get_active_link(session: Session, optimization_id: str) -> OptimizationShareLinkModel | None:
    """Return the optimization's live (non-revoked) sharing row, if any.

    Args:
        session: Open DB session.
        optimization_id: Optimization to look up.

    Returns:
        The active :class:`OptimizationShareLinkModel`, or ``None`` when no
        live row exists.
    """
    return session.scalars(
        select(OptimizationShareLinkModel).where(
            OptimizationShareLinkModel.optimization_id == optimization_id,
            OptimizationShareLinkModel.revoked_at.is_(None),
        )
    ).first()


def get_link_by_token(session: Session, token: str) -> OptimizationShareLinkModel | None:
    """Return the active sharing row for a public ``token``, if any.

    Args:
        session: Open DB session.
        token: The public share token from a ``/share/<token>`` URL.

    Returns:
        The active :class:`OptimizationShareLinkModel`, or ``None`` when the
        token is unknown or its row was revoked.
    """
    return session.scalars(
        select(OptimizationShareLinkModel).where(
            OptimizationShareLinkModel.token == token,
            OptimizationShareLinkModel.revoked_at.is_(None),
        )
    ).first()


def list_grants(session: Session, optimization_id: str) -> list[OptimizationShareGrantModel]:
    """Return all member grants for an optimization, ordered by username.

    Args:
        session: Open DB session.
        optimization_id: Optimization whose member grants are listed.

    Returns:
        The optimization's :class:`OptimizationShareGrantModel` rows (possibly
        empty), ordered by ``grantee_username`` for stable rendering.
    """
    return list(
        session.scalars(
            select(OptimizationShareGrantModel)
            .where(OptimizationShareGrantModel.optimization_id == optimization_id)
            .order_by(OptimizationShareGrantModel.grantee_username)
        )
    )


def get_grant(
    session: Session, optimization_id: str, username: str
) -> OptimizationShareGrantModel | None:
    """Return a specific user's grant on an optimization, if one exists.

    Args:
        session: Open DB session.
        optimization_id: Optimization to look up.
        username: Grantee username (compared case-insensitively).

    Returns:
        The matching :class:`OptimizationShareGrantModel`, or ``None``.
    """
    return session.get(
        OptimizationShareGrantModel,
        {"optimization_id": optimization_id, "grantee_username": _normalize_username(username)},
    )


def _job_owner_for(session: Session, optimization_id: str) -> str | None:
    """Return the normalized owner username for a job, read on ``session``.

    Loads only the owner-bearing columns from the ``jobs`` row and reuses
    :func:`core.api.routers._helpers.job_owner` for identical normalization to
    the rest of the API (payload ``username`` first, then ``payload_overview``).

    Args:
        session: Open DB session.
        optimization_id: Optimization whose owner is resolved.

    Returns:
        The job owner's lowercased username, or ``None`` when the job is
        unknown or carries no owner.
    """
    row = session.execute(
        select(JobModel.payload, JobModel.payload_overview).where(
            JobModel.optimization_id == optimization_id
        )
    ).first()
    if row is None:
        return None
    payload, payload_overview = row
    return job_owner({"payload": payload, "payload_overview": payload_overview})


def resolve_share_access(
    session: Session, token: str, user: AuthenticatedUser | None
) -> ShareRole | None:
    """Resolve the effective role a caller has on a shared optimization.

    Resolution order (first match wins):

    1. Resolve the active (non-revoked) link by ``token`` to its optimization
       and ``general_access`` policy; an unknown/revoked token grants nothing.
    2. The job owner or any admin -> :attr:`ShareRole.owner`.
    3. A user holding a member grant -> that grant's role.
    4. ``general_access == 'anyone'`` -> :attr:`ShareRole.view` (anonymous,
       view-only).
    5. Otherwise -> ``None`` (no access; caller 404s).

    Args:
        session: Open DB session backing the jobs and share tables.
        token: The public share token from the ``/share/<token>`` URL.
        user: Authenticated caller, or ``None`` for an anonymous visitor.

    Returns:
        The caller's effective :class:`ShareRole`, or ``None`` when the token is
        invalid or the caller has no access under either sharing mode.
    """
    link = get_link_by_token(session, token)
    if link is None:
        return None
    optimization_id = link.optimization_id

    if user is not None:
        username = _normalize_username(user.username)
        owner = _job_owner_for(session, optimization_id)
        if (owner is not None and owner == username) or is_admin(user):
            return ShareRole.owner
        grant = get_grant(session, optimization_id, username)
        if grant is not None and grant.role in MEMBER_ROLES:
            return ShareRole(grant.role)

    if link.general_access == GENERAL_ACCESS_ANYONE:
        return ShareRole.view

    return None
