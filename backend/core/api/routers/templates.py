"""Routes for CRUD on reusable job-configuration templates.

Templates let users save and reload submission configurations. This router
also ensures the backing table exists by calling
``StorageBase.metadata.create_all(job_store.engine)`` on construction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...models import TemplateCreateRequest, TemplateResponse
from ...storage.models import Base as StorageBase
from ...storage.models import TemplateModel
from ..errors import DomainError
from ..response_limits import (
    AGENT_DEFAULT_LIST,
    AGENT_MAX_CODE_PREVIEW,
    AGENT_MAX_LIST,
    clamp_limit,
    truncate_text,
)


def _compact_template_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of ``config`` with large code blocks replaced by size previews.

    ``signature_code`` and ``metric_code`` can each be a few KB of Python;
    echoing them inside a list response blows the agent context. This keeps
    a truncated preview so the agent can tell "what kind of template is this"
    without pulling the full source. The REST UI calls ``GET /templates/{id}``
    with ``view=full`` to get the unabridged config.

    Args:
        config: Stored template config dict, or ``None``.

    Returns:
        A new dict with ``signature_code`` and ``metric_code`` truncated.
    """
    if not config:
        return config or {}
    out = dict(config)
    for key in ("signature_code", "metric_code"):
        value = out.get(key)
        if isinstance(value, str) and value:
            out[key] = truncate_text(value, AGENT_MAX_CODE_PREVIEW)
    return out


def _row_to_template_response(
    row: TemplateModel,
    *,
    compact: bool,
) -> TemplateResponse:
    """Materialise an ORM row into a ``TemplateResponse``.

    ``Column[T]`` descriptors on the ``TemplateModel`` class read as the
    underlying Python ``T`` at instance level; this helper centralises the
    cast so each route doesn't repeat the boilerplate.

    Args:
        row: A ``TemplateModel`` instance loaded via SQLAlchemy.
        compact: When ``True``, code blocks inside ``config`` are truncated.

    Returns:
        The response model the route returns to clients.
    """
    config = cast(dict[str, Any] | None, row.config)
    return TemplateResponse(
        template_id=cast(str, row.template_id),
        name=cast(str, row.name),
        description=cast("str | None", row.description),
        username=cast(str, row.username),
        config=_compact_template_config(config) if compact else (config or {}),
        created_at=cast(datetime, row.created_at),
    )


class TemplateUpdateRequest(BaseModel):
    """Partial update for a saved template (owner-only, at least one field required)."""

    username: str = Field(description="Username of the requester — must match the template's owner.")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    config: dict[str, Any] | None = Field(
        default=None,
        description="Replacement template configuration. Supply the full config, not a patch.",
    )


class ApplyTemplateResponse(BaseModel):
    """Envelope returned by ``POST /templates/{id}/apply`` that carries a wizard_state patch."""

    template_id: str
    name: str
    wizard_state: dict[str, Any]


def create_templates_router(*, job_store) -> APIRouter:
    """Build the templates' router.

    Also triggers ``StorageBase.metadata.create_all`` so the backing
    ``templates`` table is guaranteed to exist before any request hits
    the router — safe on repeat calls because ``create_all`` is a no-op
    when the table is already present.

    Args:
        job_store: Job-store instance whose ``engine`` backs the templates
            table.

    Returns:
        A FastAPI ``APIRouter`` exposing the template CRUD routes.
    """
    StorageBase.metadata.create_all(job_store.engine)

    router = APIRouter()

    @router.post(
        "/templates",
        response_model=TemplateResponse,
        status_code=201,
        summary="Save a reusable submission template",
        tags=["agent"],
    )
    def create_template(req: TemplateCreateRequest) -> TemplateResponse:
        """Save a submission config as a named template for re-use.

        Args:
            req: New-template body validated by FastAPI.

        Returns:
            The persisted template echoed back to the caller.
        """
        template_id = str(uuid4())
        now = datetime.now(UTC)

        with Session(job_store.engine) as session:
            model = TemplateModel(
                template_id=template_id,
                name=req.name.strip(),
                description=req.description,
                username=req.username,
                config=req.config,
                created_at=now,
            )
            session.add(model)
            session.commit()

        return TemplateResponse(
            template_id=template_id,
            name=req.name.strip(),
            description=req.description,
            username=req.username,
            config=req.config,
            created_at=now,
        )

    @router.get(
        "/templates",
        response_model=list[TemplateResponse],
        summary="List saved submission templates",
        tags=["agent"],
    )
    def list_templates(
        username: str | None = Query(default=None, description="Only return templates created by this user"),
        limit: int = Query(
            default=AGENT_DEFAULT_LIST,
            ge=1,
            le=AGENT_MAX_LIST,
            description=f"Page size (default {AGENT_DEFAULT_LIST}, ceiling {AGENT_MAX_LIST}).",
        ),
        offset: int = Query(default=0, ge=0, description="Number of templates to skip"),
        view: str = Query(
            default="compact",
            description=(
                "'compact' (default) truncates template config code blocks for agent calls; "
                "'full' returns the raw config including full signature/metric code."
            ),
        ),
    ) -> list[TemplateResponse]:
        """Return saved templates ordered newest-first.

        By default (``view=compact``) embedded ``signature_code`` /
        ``metric_code`` in each template's ``config`` is truncated to a
        short preview so long snippets don't fill the agent context. UI
        callers that need the full Python source pass ``view=full``.

        Args:
            username: Optional owner filter.
            limit: Page size, clamped to ``AGENT_MAX_LIST``.
            offset: Number of templates to skip.
            view: ``compact`` or ``full`` projection.

        Returns:
            A list of ``TemplateResponse`` rows ordered ``created_at`` desc.
        """
        resolved_limit = clamp_limit(limit)
        compact = view != "full"
        with Session(job_store.engine) as session:
            query = session.query(TemplateModel).order_by(TemplateModel.created_at.desc())
            if username:
                query = query.filter(TemplateModel.username == username)
            rows = query.offset(offset).limit(resolved_limit).all()
            return [_row_to_template_response(r, compact=compact) for r in rows]

    @router.get(
        "/templates/{template_id}",
        response_model=TemplateResponse,
        summary="Fetch a single template by ID",
        tags=["agent"],
    )
    def get_template(
        template_id: str,
        view: str = Query(
            default="compact",
            description=(
                "'compact' (default) truncates code blocks inside config; "
                "'full' returns the raw config — UI callers should pass 'full'."
            ),
        ),
    ) -> TemplateResponse:
        """Fetch a single template by UUID.

        Defaults to a compact projection that truncates large code fields
        so the agent can introspect a template without burning context.
        Pass ``view=full`` to retrieve the complete signature/metric source.

        Args:
            template_id: Template UUID to fetch.
            view: ``compact`` or ``full`` projection.

        Returns:
            The matching ``TemplateResponse``.

        Raises:
            DomainError: 404 when the template ID is unknown.
        """
        compact = view != "full"
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(TemplateModel.template_id == template_id).first()
            if not row:
                raise DomainError("template.not_found", status=404)
            return _row_to_template_response(row, compact=compact)

    @router.delete(
        "/templates/{template_id}",
        status_code=200,
        summary="Delete a template (owner only)",
        tags=["agent"],
    )
    def delete_template(
        template_id: str,
        username: str = Query(..., description="Username of the requester — must match the template's owner"),
    ) -> dict:
        """Delete a template owned by the requester.

        Args:
            template_id: Template UUID to delete.
            username: Caller's username — must match the template's owner.

        Returns:
            ``{"template_id": id, "deleted": True}`` on success.

        Raises:
            DomainError: 404 when unknown, 403 when ``username`` doesn't
                own the template.
        """
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(TemplateModel.template_id == template_id).first()
            if not row:
                raise DomainError("template.not_found", status=404)
            if row.username != username:
                raise DomainError("template.cannot_delete_others", status=403)
            session.delete(row)
            session.commit()
        return {"template_id": template_id, "deleted": True}

    @router.put(
        "/templates/{template_id}",
        response_model=TemplateResponse,
        status_code=200,
        summary="Update a template in place (owner only)",
        tags=["agent"],
    )
    def update_template(template_id: str, req: TemplateUpdateRequest) -> TemplateResponse:
        """Patch a template's name, description, and/or config.

        At least one of ``name``, ``description``, or ``config`` must be
        supplied; missing fields are left untouched.

        Args:
            template_id: Template UUID to update.
            req: Partial update body.

        Returns:
            The updated ``TemplateResponse``.

        Raises:
            DomainError: 422 when no updatable field is supplied, 404 if
                unknown, 403 if the requester is not the owner.
        """
        if req.name is None and req.description is None and req.config is None:
            raise DomainError("template.update_requires_field", status=422)
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(TemplateModel.template_id == template_id).first()
            if not row:
                raise DomainError("template.not_found", status=404)
            if row.username != req.username:
                raise DomainError("template.cannot_update_others", status=403)
            if req.name is not None:
                row.name = cast(Any, req.name.strip())
            if req.description is not None:
                row.description = cast(Any, req.description)
            if req.config is not None:
                row.config = cast(Any, req.config)
            session.commit()
            session.refresh(row)
            return _row_to_template_response(row, compact=False)

    @router.post(
        "/templates/{template_id}/apply",
        response_model=ApplyTemplateResponse,
        status_code=200,
        summary="Load a saved template into the wizard",
        tags=["agent"],
    )
    def apply_template(template_id: str) -> ApplyTemplateResponse:
        """Return a ``wizard_state`` patch that prefills the submit wizard.

        The template's stored config may include signature_code,
        metric_code, column_mapping, model config, optimizer, and an
        optional job name. Only keys the wizard knows about are projected.

        Args:
            template_id: Template UUID to load.

        Returns:
            An ``ApplyTemplateResponse`` carrying the wizard-state patch.

        Raises:
            DomainError: 404 when the template is unknown.
        """
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(TemplateModel.template_id == template_id).first()
            if not row:
                raise DomainError("template.not_found", status=404)
            cfg: dict[str, Any] = dict(cast(dict[str, Any] | None, row.config) or {})
            template_name = cast(str, row.name)

        wizard_state: dict[str, Any] = {}

        signature_code = cfg.get("signature_code")
        if isinstance(signature_code, str) and signature_code.strip():
            wizard_state["signature_code"] = signature_code

        metric_code = cfg.get("metric_code")
        if isinstance(metric_code, str) and metric_code.strip():
            wizard_state["metric_code"] = metric_code

        job_name = cfg.get("name") or cfg.get("job_name")
        if isinstance(job_name, str) and job_name.strip():
            wizard_state["job_name"] = job_name

        column_mapping = cfg.get("column_mapping")
        if isinstance(column_mapping, dict):
            roles: dict[str, str] = {}
            inputs = column_mapping.get("inputs", {})
            outputs = column_mapping.get("outputs", {})
            if isinstance(inputs, dict):
                for col in inputs.values():
                    if isinstance(col, str) and col:
                        roles[col] = "input"
            if isinstance(outputs, dict):
                for col in outputs.values():
                    if isinstance(col, str) and col:
                        roles[col] = "output"
            if roles:
                wizard_state["column_roles"] = roles
                wizard_state["columns_configured"] = True

        model_config = cfg.get("model_config") or cfg.get("model_settings")
        if isinstance(model_config, dict) and model_config.get("name"):
            wizard_state["model_config"] = model_config
            wizard_state["model_configured"] = True

        return ApplyTemplateResponse(
            template_id=template_id,
            name=template_name,
            wizard_state=wizard_state,
        )

    return router
