"""Google-Drive-style sharing for optimizations. [MIXED]

Owner/editor-gated management endpoints plus the access-gated public surface:

* ``GET    /optimizations/{id}/sharing`` — current sharing config (owner/editor).
* ``PUT    /optimizations/{id}/sharing`` — set the general-access policy.
* ``POST   /optimizations/{id}/sharing/members`` — add/replace a member grant.
* ``PATCH  /optimizations/{id}/sharing/members/{username}`` — change a role.
* ``DELETE /optimizations/{id}/sharing/members/{username}`` — remove a grant.
* ``GET    /users/search`` — username autocomplete for the invite picker.
* ``GET    /share/{token}`` — **access-gated** composite read of one
  optimization (anonymous view-only under an ``anyone`` link, full data for
  invited members), no auth required.
* ``POST   /share/{token}/serve`` — one inference through the owner's stored
  model (requires an effective role of viewer or higher).

Two sharing modes coexist per :mod:`core.api.sharing_access`: ``general_access``
on the active link selects the anonymous policy (``restricted`` vs ``anyone``)
and member grants invite specific users at a tier role. Effective access is
resolved by :func:`resolve_share_access`. Secrets (API keys, base URLs) never
cross the public boundary; for the anonymous ``view`` role the real owner is
hidden and inference is forbidden.
"""

from __future__ import annotations

import logging
import random
import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

import dspy
from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
)
from ...models import (
    ColumnMapping,
    GridSearchResponse,
    JobLogEntry,
    ModelConfig,
    OptimizationStatus,
    OptimizationStatusResponse,
    RunResponse,
    ServeInfoResponse,
    ServeRequest,
    ServeResponse,
    SplitFractions,
)
from ...service_gateway.language_models import build_language_model
from ...storage.models import (
    AgentConversationModel,
    ApiTokenModel,
    JobModel,
    OptimizationShareGrantModel,
    OptimizationShareLinkModel,
)
from ..auth import AuthenticatedUser, get_authenticated_user, is_admin
from ..converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)
from ..errors import DomainError
from ..sharing_access import (
    GENERAL_ACCESS_ANYONE,
    GENERAL_ACCESS_RESTRICTED,
    MEMBER_ROLES,
    ShareRole,
    get_active_link,
    get_grant,
    get_link_by_token,
    list_grants,
    resolve_share_access,
)
from ._helpers import (
    _artifact_has_payload,
    compute_compare_fingerprint,
    job_owner,
    load_program,
    stable_seed,
)
from .constants import TERMINAL_STATUSES
from .optimizations._local import remap_test_indices

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


def get_optional_user(
    request: Request, authorization: str | None = Header(default=None)
) -> AuthenticatedUser | None:
    """Resolve the caller when a valid credential is present, else ``None``.

    The public share routes accept anonymous visitors, so an absent or invalid
    bearer credential must not 401 — it yields ``None`` and the access resolver
    falls through to the ``anyone`` policy. Exposed at module scope (not as a
    route-local closure) so it participates in FastAPI's dependency-override
    mechanism for tests.

    Args:
        request: Incoming request (used to reach the store for PAT lookup).
        authorization: HTTP Authorization header, if any.

    Returns:
        The authenticated user, or ``None`` for an anonymous visitor.
    """
    if not authorization:
        return None
    try:
        return get_authenticated_user(request, authorization)
    except DomainError:
        return None


OptionalUserDep = Annotated[AuthenticatedUser | None, Depends(get_optional_user)]

# Roles that may read/manage the sharing config or run inference on a share.
_MANAGE_ROLES: frozenset[ShareRole] = frozenset({ShareRole.editor, ShareRole.owner})
_INFER_ROLES: frozenset[ShareRole] = frozenset({ShareRole.viewer, ShareRole.editor, ShareRole.owner})
_GENERAL_ACCESS_VALUES = (GENERAL_ACCESS_RESTRICTED, GENERAL_ACCESS_ANYONE)
# Cap for the username-autocomplete result set (contract: at most 10).
_USER_SEARCH_LIMIT = 10
# Model-config sub-keys that must never cross the public boundary.
_SECRET_MODEL_FIELDS = ("model_config", "reflection_model_config", "task_model_config")


class SharingMember(BaseModel):
    """One invited member of an optimization (username + tier role)."""

    username: str
    role: str


class SharingState(BaseModel):
    """Owner/editor-facing sharing config for one optimization."""

    general_access: str
    token: str | None = None
    share_path: str | None = None
    owner: str | None = None
    members: list[SharingMember] = Field(default_factory=list)


class PutSharingRequest(BaseModel):
    """Request body for ``PUT /optimizations/{id}/sharing``."""

    general_access: str


class AddMemberRequest(BaseModel):
    """Request body for ``POST /optimizations/{id}/sharing/members``."""

    username: str
    role: str


class UpdateMemberRequest(BaseModel):
    """Request body for ``PATCH /optimizations/{id}/sharing/members/{username}``."""

    role: str


class UserSearchResponse(BaseModel):
    """Envelope for ``GET /users/search`` — matching distinct usernames."""

    usernames: list[str]


def _strip_model_secrets(cfg: Any) -> Any:
    """Return a copy of a model-config dict without its secret fields.

    Args:
        cfg: A model-config mapping (or anything else, returned unchanged).

    Returns:
        A shallow copy with ``base_url`` removed and ``extra.api_key`` stripped,
        or the input unchanged when it is not a dict.
    """
    if not isinstance(cfg, dict):
        return cfg
    cleaned = {k: v for k, v in cfg.items() if k != "base_url"}
    extra = cleaned.get("extra")
    if isinstance(extra, dict):
        cleaned["extra"] = {k: v for k, v in extra.items() if k != "api_key"}
    return cleaned


def _scrub_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project the stored payload onto the public, secret-free share view.

    Drops the owner ``username`` and the raw ``dataset`` rows (the full split is
    served separately) and strips API keys / base URLs from every model config,
    including the grid-search model lists.

    Args:
        payload: The optimization's stored request payload.

    Returns:
        A new dict safe to expose through a share link.
    """
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if key in ("username", "dataset"):
            continue
        if key in _SECRET_MODEL_FIELDS:
            out[key] = _strip_model_secrets(value)
        elif key in ("generation_models", "reflection_models") and isinstance(value, list):
            out[key] = [_strip_model_secrets(m) for m in value]
        else:
            out[key] = value
    return out


def _test_split_indices(payload: dict[str, Any], optimization_id: str, total: int) -> list[int]:
    """Recompute the deterministic test-split global indices for a job.

    Mirrors the seed/shuffle/fraction algorithm in ``get_job_dataset`` and
    ``get_test_results`` so the remapped test scores line up with the rows the
    full-dataset split returns.

    Args:
        payload: The optimization's stored request payload.
        optimization_id: Owning optimization id (used to derive the seed fallback).
        total: Total dataset row count.

    Returns:
        Global dataset indices belonging to the test split.
    """
    try:
        fractions = SplitFractions.model_validate(payload.get("split_fractions", {}))
    except ValidationError:
        fractions = SplitFractions()
    shuffle = payload.get("shuffle", True)
    seed = payload.get("seed")
    effective_seed = seed if seed is not None else stable_seed(optimization_id)
    ordered = list(range(total))
    if shuffle:
        random.Random(effective_seed).shuffle(ordered)
    train_end = int(total * fractions.train)
    val_end = train_end + int(total * fractions.val)
    return ordered[val_end:]


def _full_dataset(job_data: dict[str, Any], optimization_id: str) -> dict[str, Any] | None:
    """Build the FULL train/val/test split for the share view (uncapped).

    Reuses the deterministic split of ``get_job_dataset`` without the per-split
    preview cap, so an invited member sees the same rows the owner does.

    Args:
        job_data: Raw job row.
        optimization_id: Owning optimization id (used to derive the seed fallback).

    Returns:
        A dict with ``total_rows``, full ``splits``, ``column_mapping``, and
        ``split_counts``, or ``None`` when no dataset is stored.
    """
    payload = job_data.get("payload")
    if not isinstance(payload, dict):
        return None
    dataset = payload.get("dataset")
    if not isinstance(dataset, list) or not dataset:
        return None
    try:
        column_mapping = ColumnMapping.model_validate(payload.get("column_mapping", {}))
    except ValidationError:
        return None
    try:
        fractions = SplitFractions.model_validate(payload.get("split_fractions", {}))
    except ValidationError:
        fractions = SplitFractions()

    shuffle = payload.get("shuffle", True)
    seed = payload.get("seed")
    effective_seed = seed if seed is not None else stable_seed(optimization_id)
    total = len(dataset)
    indices = list(range(total))
    if shuffle:
        random.Random(effective_seed).shuffle(indices)
    train_end = int(total * fractions.train)
    val_end = train_end + int(total * fractions.val)
    train_idx = indices[:train_end]
    val_idx = indices[train_end:val_end]
    test_idx = indices[val_end:]

    def _rows(idx: list[int]) -> list[dict[str, Any]]:
        return [{"index": i, "row": dataset[i]} for i in idx]

    return {
        "total_rows": total,
        "splits": {"train": _rows(train_idx), "val": _rows(val_idx), "test": _rows(test_idx)},
        "column_mapping": {"inputs": column_mapping.inputs, "outputs": column_mapping.outputs},
        "split_counts": {"train": len(train_idx), "val": len(val_idx), "test": len(test_idx)},
    }


def _test_results(job_data: dict[str, Any], optimization_id: str) -> dict[str, list[dict[str, Any]]] | None:
    """Return stored per-example test scores remapped to global indices, if any.

    Reuses the ``get_test_results`` loader: validates the stored single-run
    ``RunResponse`` and remaps the sequential test-split indices back to global
    dataset positions. Returns ``None`` for grid searches, missing results, or
    corrupt result envelopes (the share view simply omits the column).

    Args:
        job_data: Raw job row.
        optimization_id: Owning optimization id (used to derive the seed fallback).

    Returns:
        ``{"baseline": [...], "optimized": [...]}`` with global indices, or
        ``None`` when no per-example single-run results are available.
    """
    result_data = job_data.get("result")
    if not isinstance(result_data, dict):
        return None
    overview = parse_overview(job_data)
    if overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN) == OPTIMIZATION_TYPE_GRID_SEARCH:
        return None
    try:
        result = RunResponse.model_validate(result_data)
    except ValidationError:
        return None
    payload = job_data.get("payload") or {}
    dataset = payload.get("dataset") or []
    if not isinstance(dataset, list) or not dataset:
        return None
    test_indices = _test_split_indices(payload, optimization_id, len(dataset))
    return {
        "baseline": remap_test_indices(result.baseline_test_results, test_indices),
        "optimized": remap_test_indices(result.optimized_test_results, test_indices),
    }


def _build_status_response(
    job_store, optimization_id: str, job_data: dict[str, Any], *, owner_visible: bool
) -> OptimizationStatusResponse:
    """Assemble the read-only status response for a shared optimization.

    Mirrors the ``OptimizationStatusResponse`` that ``GET /optimizations/{id}``
    returns (minus its ETag/caching concerns) so the share page can reuse the
    same frontend detail components.

    Args:
        job_store: Job-store the logs/progress are read from.
        optimization_id: Optimization id being rendered.
        job_data: Raw job row.
        owner_visible: When ``False`` (anonymous ``view``), the ``username``
            field is anonymised; when ``True`` (member) the real owner is shown.

    Returns:
        A populated :class:`OptimizationStatusResponse`.
    """
    status = status_to_job_status(job_data.get("status", "pending"))
    overview = parse_overview(job_data)
    optimization_type = overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN)

    result = None
    grid_result = None
    result_data = job_data.get("result")
    if isinstance(result_data, dict):
        try:
            if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
                grid_result = GridSearchResponse.model_validate(result_data)
            elif status == OptimizationStatus.success:
                result = RunResponse.model_validate(result_data)
        except ValidationError:
            logger.warning("Shared optimization %s has corrupted result data", optimization_id)

    created_at = parse_timestamp(job_data.get("created_at")) or datetime.now(UTC)
    started_at = parse_timestamp(job_data.get("started_at"))
    completed_at = parse_timestamp(job_data.get("completed_at"))
    est_remaining = None if status in TERMINAL_STATUSES else extract_estimated_remaining(job_data)

    latest_metrics = job_data.get("latest_metrics", {})
    completed_pairs = failed_pairs = None
    if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
        if grid_result:
            completed_pairs = grid_result.completed_pairs
            failed_pairs = grid_result.failed_pairs
        else:
            completed_pairs = latest_metrics.get("completed_so_far") or 0
            failed_pairs = latest_metrics.get("failed_so_far") or 0

    elapsed_str, elapsed_secs = compute_elapsed(created_at, started_at, completed_at)
    logs = job_store.get_logs(optimization_id)
    progress_events = job_store.get_progress_events(optimization_id)

    base_fields = overview_to_base_fields(overview)
    if not owner_visible:
        base_fields["username"] = None

    return OptimizationStatusResponse(
        optimization_id=optimization_id,
        status=status,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        elapsed=elapsed_str,
        elapsed_seconds=elapsed_secs,
        estimated_remaining=est_remaining,
        **base_fields,
        compare_fingerprint=compute_compare_fingerprint(optimization_id, overview),
        message=job_data.get("message"),
        latest_metrics=latest_metrics,
        completed_pairs=completed_pairs,
        failed_pairs=failed_pairs,
        progress_events=progress_events,
        logs=[JobLogEntry(**log) for log in logs],
        result=result,
        grid_result=grid_result,
    )


def _serve_info(job_store, optimization_id: str, owner: str) -> ServeInfoResponse | None:
    """Build the program ``ServeInfoResponse`` for a shared optimization.

    Loads the program under the OWNER's identity (the resolver already proved
    the caller is a viewer+), returning ``None`` when the job is not in a
    serveable state — the share view simply omits ``serve_info`` then.

    Args:
        job_store: Job-store backing :func:`load_program`.
        optimization_id: Optimization whose program is described.
        owner: Job owner username, used to satisfy the ownership check inside
            :func:`load_program` without exposing the real model secrets.

    Returns:
        A :class:`ServeInfoResponse`, or ``None`` when the program is not
        serveable (not finished, no artifact, etc.).
    """
    owner_user = AuthenticatedUser(username=owner, role="user", groups=())
    try:
        _program, result, overview = load_program(job_store, optimization_id, owner_user)
    except DomainError:
        return None
    artifact = result.program_artifact
    prompt = artifact.optimized_prompt
    if prompt is None:
        input_fields: list[str] = []
        output_fields: list[str] = []
        instructions = None
        demo_count = 0
    else:
        input_fields = list(prompt.input_fields)
        output_fields = list(prompt.output_fields)
        instructions = prompt.instructions
        demo_count = len(prompt.demos)
    return ServeInfoResponse(
        optimization_id=optimization_id,
        module_name=overview.get("module_name", ""),
        optimizer_name=overview.get("optimizer_name", ""),
        model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, ""),
        input_fields=input_fields,
        output_fields=output_fields,
        instructions=instructions,
        demo_count=demo_count,
    )


def _owner_model_config(job_data: dict[str, Any], overview: dict[str, Any]) -> ModelConfig:
    """Resolve the OWNER's stored model config (with the owner key) for inference.

    Prefers the unscrubbed ``payload['model_config']`` (carries the owner's API
    key and base_url, server-side only), falling back to the stripped overview
    settings or the bare model name. The resolved config is never returned to
    the caller — only used to build the language model.

    Args:
        job_data: Raw job row whose ``payload`` carries the owner's model config.
        overview: Parsed payload-overview dict (fallback model settings/name).

    Returns:
        The owner's :class:`ModelConfig`.

    Raises:
        DomainError: 400 when no model config can be resolved.
    """
    payload = job_data.get("payload") or {}
    stored = payload.get("model_config") or overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
    model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
    if stored:
        return ModelConfig.model_validate(stored)
    if model_name:
        return ModelConfig(name=model_name)
    raise DomainError("serve.no_model_config", status=400)


def create_share_router(*, job_store) -> APIRouter:
    """Build the Google-Drive-style optimization sharing router.

    Args:
        job_store: Job-store whose ORM engine backs the share tables and whose
            job rows feed the public composite read and inference path.

    Returns:
        A FastAPI ``APIRouter`` with the owner/editor-gated management routes,
        the user-search autocomplete, and the access-gated public surface.
    """
    router = APIRouter()

    def _require_manage(session: Session, optimization_id: str, user: AuthenticatedUser) -> str | None:
        """Ensure ``user`` may manage sharing for ``optimization_id``.

        The optimization must exist (404 otherwise, never 403 — existence is not
        leaked to strangers). The job owner and admins manage; a member with an
        editor/owner grant also manages. A non-owner, non-admin, non-editor
        caller cannot even confirm the optimization exists, so they 404 too.

        Args:
            session: Open DB session.
            optimization_id: Optimization being managed.
            user: Authenticated caller.

        Returns:
            The job owner username (lowercased), or ``None`` when the job
            carries no owner.

        Raises:
            DomainError: 404 when the optimization is unknown or the caller has
                no management access at all (owner existence is not leaked).
        """
        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id) from None
        owner = job_owner(job_data)
        if (owner is not None and owner == user.username) or is_admin(user):
            return owner
        grant = get_grant(session, optimization_id, user.username)
        if grant is not None and ShareRole(grant.role) in _MANAGE_ROLES:
            return owner
        raise DomainError("optimization.not_found", status=404, optimization_id=optimization_id)

    def _sharing_state(session: Session, optimization_id: str, owner: str | None) -> SharingState:
        """Assemble the current :class:`SharingState` for an optimization.

        Args:
            session: Open DB session.
            optimization_id: Optimization to describe.
            owner: The job owner username (shown to managers).

        Returns:
            The populated :class:`SharingState`.
        """
        link = get_active_link(session, optimization_id)
        general_access = link.general_access if link is not None else GENERAL_ACCESS_RESTRICTED
        token = link.token if link is not None else None
        members = [
            SharingMember(username=g.grantee_username, role=g.role)
            for g in list_grants(session, optimization_id)
        ]
        return SharingState(
            general_access=general_access,
            token=token,
            share_path=f"/share/{token}" if token else None,
            owner=owner,
            members=members,
        )

    def _ensure_link(session: Session, optimization_id: str, created_by: str) -> OptimizationShareLinkModel:
        """Return the active link, minting one if none exists.

        Args:
            session: Open DB session (caller commits).
            optimization_id: Optimization the link belongs to.
            created_by: Username recorded as the link creator.

        Returns:
            The active :class:`OptimizationShareLinkModel`.
        """
        link = get_active_link(session, optimization_id)
        if link is None:
            link = OptimizationShareLinkModel(
                token=secrets.token_urlsafe(24),
                optimization_id=optimization_id,
                created_by=created_by,
                created_at=datetime.now(UTC),
                general_access=GENERAL_ACCESS_RESTRICTED,
            )
            session.add(link)
        return link

    @router.get(
        "/optimizations/{optimization_id}/sharing",
        response_model=SharingState,
        summary="Get the sharing config (general access + members) for an optimization",
    )
    def get_sharing(optimization_id: str, current_user: AuthenticatedUserDep) -> SharingState:
        """Return the optimization's sharing config for an owner/editor.

        Args:
            optimization_id: Optimization to inspect.
            current_user: Authenticated owner/editor.

        Returns:
            The current :class:`SharingState`.

        Raises:
            DomainError: 404 when the optimization is unknown/inaccessible;
                403 when the caller may not manage sharing.
        """
        with Session(job_store.engine) as session:
            owner = _require_manage(session, optimization_id, current_user)
            return _sharing_state(session, optimization_id, owner)

    @router.put(
        "/optimizations/{optimization_id}/sharing",
        response_model=SharingState,
        summary="Set the general-access policy (restricted vs anyone-with-link)",
    )
    def put_sharing(
        optimization_id: str, req: PutSharingRequest, current_user: AuthenticatedUserDep
    ) -> SharingState:
        """Set the optimization's general-access policy, minting a link if needed.

        Args:
            optimization_id: Optimization to update.
            req: Body carrying the new ``general_access`` policy.
            current_user: Authenticated owner/editor.

        Returns:
            The updated :class:`SharingState`.

        Raises:
            DomainError: 404 when unknown/inaccessible; 403 when the caller may
                not manage sharing; 400 when ``general_access`` is invalid.
        """
        if req.general_access not in _GENERAL_ACCESS_VALUES:
            raise DomainError(
                "share.invalid_general_access", status=400, allowed=", ".join(_GENERAL_ACCESS_VALUES)
            )
        with Session(job_store.engine) as session:
            owner = _require_manage(session, optimization_id, current_user)
            link = _ensure_link(session, optimization_id, current_user.username)
            link.general_access = req.general_access
            session.commit()
            return _sharing_state(session, optimization_id, owner)

    @router.post(
        "/optimizations/{optimization_id}/sharing/members",
        response_model=SharingState,
        summary="Invite a user (add or replace a member grant)",
    )
    def add_member(
        optimization_id: str, req: AddMemberRequest, current_user: AuthenticatedUserDep
    ) -> SharingState:
        """Add or replace a member grant on the optimization.

        Args:
            optimization_id: Optimization to share.
            req: Body carrying the grantee ``username`` and tier ``role``.
            current_user: Authenticated owner/editor.

        Returns:
            The updated :class:`SharingState`.

        Raises:
            DomainError: 404 when unknown/inaccessible; 403 when the caller may
                not manage sharing; 400 when the role is invalid or the caller
                tries to grant themselves.
        """
        if req.role not in MEMBER_ROLES:
            raise DomainError(
                "share.invalid_role", status=400, role=req.role, allowed=", ".join(sorted(MEMBER_ROLES))
            )
        grantee = req.username.strip().lower()
        with Session(job_store.engine) as session:
            owner = _require_manage(session, optimization_id, current_user)
            if owner is not None and grantee == owner:
                raise DomainError("share.cannot_grant_self", status=400)
            existing = get_grant(session, optimization_id, grantee)
            if existing is not None:
                existing.role = req.role
            else:
                session.add(
                    OptimizationShareGrantModel(
                        optimization_id=optimization_id,
                        grantee_username=grantee,
                        role=req.role,
                        created_by=current_user.username,
                        created_at=datetime.now(UTC),
                    )
                )
            session.commit()
            return _sharing_state(session, optimization_id, owner)

    @router.patch(
        "/optimizations/{optimization_id}/sharing/members/{username}",
        response_model=SharingState,
        summary="Change an existing member's role",
    )
    def update_member(
        optimization_id: str,
        username: str,
        req: UpdateMemberRequest,
        current_user: AuthenticatedUserDep,
    ) -> SharingState:
        """Change an existing member's tier role.

        Args:
            optimization_id: Optimization to update.
            username: Grantee whose role changes.
            req: Body carrying the new ``role``.
            current_user: Authenticated owner/editor.

        Returns:
            The updated :class:`SharingState`.

        Raises:
            DomainError: 404 when the optimization is unknown/inaccessible or
                the member grant does not exist; 403 when the caller may not
                manage sharing; 400 when the role is invalid.
        """
        if req.role not in MEMBER_ROLES:
            raise DomainError(
                "share.invalid_role", status=400, role=req.role, allowed=", ".join(sorted(MEMBER_ROLES))
            )
        grantee = username.strip().lower()
        with Session(job_store.engine) as session:
            owner = _require_manage(session, optimization_id, current_user)
            grant = get_grant(session, optimization_id, grantee)
            if grant is None:
                raise DomainError("share.member_not_found", status=404, username=grantee)
            grant.role = req.role
            session.commit()
            return _sharing_state(session, optimization_id, owner)

    @router.delete(
        "/optimizations/{optimization_id}/sharing/members/{username}",
        response_model=SharingState,
        summary="Remove a member's grant",
    )
    def remove_member(
        optimization_id: str, username: str, current_user: AuthenticatedUserDep
    ) -> SharingState:
        """Remove a member's grant from the optimization.

        Args:
            optimization_id: Optimization to update.
            username: Grantee whose grant is removed.
            current_user: Authenticated owner/editor.

        Returns:
            The updated :class:`SharingState`.

        Raises:
            DomainError: 404 when the optimization is unknown/inaccessible or
                the member grant does not exist; 403 when the caller may not
                manage sharing.
        """
        grantee = username.strip().lower()
        with Session(job_store.engine) as session:
            owner = _require_manage(session, optimization_id, current_user)
            grant = get_grant(session, optimization_id, grantee)
            if grant is None:
                raise DomainError("share.member_not_found", status=404, username=grantee)
            session.delete(grant)
            session.commit()
            return _sharing_state(session, optimization_id, owner)

    @router.get(
        "/users/search",
        response_model=UserSearchResponse,
        summary="Autocomplete distinct known usernames by prefix",
    )
    def search_users(q: str, current_user: AuthenticatedUserDep) -> UserSearchResponse:
        """Return up to 10 distinct known usernames matching a prefix.

        Backs the invite autocomplete. Searches the union of known username
        sources (``jobs.username``, ``agent_conversations.username``,
        ``api_tokens.username``); a blank query returns nothing.

        Args:
            q: Case-insensitive username prefix.
            current_user: Any authenticated caller.

        Returns:
            A :class:`UserSearchResponse` with the matching usernames.
        """
        prefix = q.strip().lower()
        if not prefix:
            return UserSearchResponse(usernames=[])
        pattern = f"{prefix}%"
        found: set[str] = set()
        with Session(job_store.engine) as session:
            for column in (
                JobModel.username,
                AgentConversationModel.username,
                ApiTokenModel.username,
            ):
                rows = session.scalars(
                    select(column).where(column.isnot(None)).where(column.ilike(pattern)).distinct()
                )
                for value in rows:
                    if value:
                        found.add(str(value).strip().lower())
        return UserSearchResponse(usernames=sorted(found)[:_USER_SEARCH_LIMIT])

    @router.get(
        "/share/{token}",
        summary="Access-gated composite snapshot of a shared optimization (no auth required)",
    )
    def get_shared_optimization(token: str, viewer: OptionalUserDep) -> dict[str, Any]:
        """Return the access-gated composite view of a shared optimization.

        Anonymous visitors under an ``anyone`` link resolve to the ``view``
        role: the owner is hidden and ``serve_info`` is ``null``. Invited
        members (viewer+) see the real owner and ``serve_info``. Secrets (API
        keys, base URLs) are stripped from the payload in every case, and the
        full train/val/test split plus per-example test results are returned
        uncapped for the read-only detail view.

        Args:
            token: The public share token from the URL.
            viewer: Resolved caller (or ``None`` for an anonymous visitor).

        Returns:
            ``{optimization_id, role, owner, status, payload, dataset,
            test_results, serve_info}``.

        Raises:
            DomainError: 404 when the token is unknown/revoked, the caller has
                no access, or the underlying optimization no longer exists.
        """
        with Session(job_store.engine) as session:
            role = resolve_share_access(session, token, viewer)
            if role is None:
                raise DomainError("share.not_found", status=404)
            link = get_link_by_token(session, token)
            optimization_id = link.optimization_id

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("share.not_found", status=404) from None

        owner_visible = role != ShareRole.view
        owner = job_owner(job_data) if owner_visible else None

        status = _build_status_response(job_store, optimization_id, job_data, owner_visible=owner_visible)
        raw_payload = job_data.get("payload")
        payload = _scrub_payload(raw_payload) if isinstance(raw_payload, dict) else {}
        serve_info = None
        if owner_visible and owner is not None:
            info = _serve_info(job_store, optimization_id, owner)
            serve_info = info.model_dump(mode="json") if info is not None else None

        return {
            "optimization_id": optimization_id,
            "role": role.value,
            "owner": owner,
            "status": status.model_dump(mode="json"),
            "payload": payload,
            "dataset": _full_dataset(job_data, optimization_id),
            "test_results": _test_results(job_data, optimization_id),
            "serve_info": serve_info,
        }

    @router.post(
        "/share/{token}/serve",
        response_model=ServeResponse,
        summary="Run one inference on a shared optimization (viewer+ only)",
    )
    def serve_shared_optimization(token: str, req: ServeRequest, viewer: OptionalUserDep) -> ServeResponse:
        """Run a single blocking inference using the OWNER's stored model config.

        Requires an effective role of viewer or higher — anonymous ``view``
        callers (and unknown tokens) get 403/404. The owner's model config
        (including the owner's API key) is loaded server-side and never
        returned. Extra inputs beyond the program signature are ignored.

        Args:
            token: The public share token from the URL.
            req: Inference request carrying the inputs.
            viewer: Resolved caller (or ``None`` for an anonymous visitor).

        Returns:
            A :class:`ServeResponse` with the predicted outputs and resolved
            model identifier.

        Raises:
            DomainError: 404 when the token is unknown/revoked; 403 when the
                caller's role is view/anonymous; 400 (bad inputs / no model);
                409 when the optimization is not in a serveable state.
        """
        with Session(job_store.engine) as session:
            role = resolve_share_access(session, token, viewer)
            if role is None:
                raise DomainError("share.not_found", status=404)
            if role not in _INFER_ROLES:
                raise DomainError("share.inference_forbidden", status=403)
            link = get_link_by_token(session, token)
            optimization_id = link.optimization_id

        try:
            job_data = job_store.get_job(optimization_id)
        except KeyError:
            raise DomainError("share.not_found", status=404) from None
        owner = job_owner(job_data)
        if owner is None:
            raise DomainError("share.not_found", status=404)

        owner_user = AuthenticatedUser(username=owner, role="user", groups=())
        program, result, overview = load_program(job_store, optimization_id, owner_user)
        artifact = result.program_artifact
        if not _artifact_has_payload(artifact):
            raise DomainError("optimization.no_program_artifact_scoped", status=409)

        model_config = _owner_model_config(job_data, overview)

        prompt = artifact.optimized_prompt
        input_fields = list(prompt.input_fields) if prompt is not None else []
        output_fields = list(prompt.output_fields) if prompt is not None else []
        if not input_fields:
            raise DomainError("serve.no_declared_inputs", status=400)
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise DomainError(
                "serve.missing_inputs", status=400, missing=missing, input_fields=input_fields
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)
        with dspy.context(lm=lm):
            prediction = program(**filtered_inputs)

        if output_fields:
            outputs = {field: getattr(prediction, field, None) for field in output_fields}
        else:
            outputs = {key: val for key, val in prediction.toDict().items() if key not in req.inputs}

        return ServeResponse(
            optimization_id=optimization_id,
            outputs=outputs,
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    return router
