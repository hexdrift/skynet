"""Routes for CRUD on reusable job-configuration templates.

Templates let users save and reload submission configurations. This router
also ensures the backing table exists by calling
``StorageBase.metadata.create_all(job_store.engine)`` on construction.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from ...models import TemplateCreateRequest, TemplateResponse
from ...storage.models import TemplateModel, Base as StorageBase


def create_templates_router(*, job_store) -> APIRouter:
    """Build the templates router.

    Args:
        job_store: Job store whose SQLAlchemy engine backs template storage.

    Returns:
        APIRouter: Router with four routes — create, list, get, delete.
    """
    # Ensure the templates table exists before any request hits the router.
    StorageBase.metadata.create_all(job_store.engine)

    router = APIRouter()

    @router.post(
        "/templates",
        response_model=TemplateResponse,
        status_code=201,
        summary="Save a reusable submission template",
    )
    def create_template(req: TemplateCreateRequest) -> TemplateResponse:
        """Persist a full submission config under a user-friendly name so the
        user can re-load it from the dashboard later.

        Use this to snapshot a working run — optimizer, model, signature,
        metric, column mapping, dataset settings — as a starting point for
        future jobs. The saved template is not linked to any specific run:
        it's just a named blob of configuration.

        Request body:
            - ``name``: display name shown in the template picker (trimmed)
            - ``description``: optional longer caption
            - ``username``: owner, used for the delete authorization check
            - ``config``: opaque JSON object with whatever the submit wizard
              stashed. The server does not introspect its shape — it's
              round-tripped verbatim on ``GET /templates/{id}``.

        Returns the saved template including the server-assigned
        ``template_id`` (UUID) and ``created_at`` timestamp. HTTP 201.
        """
        template_id = str(uuid4())
        now = datetime.now(timezone.utc)

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
        response_model=List[TemplateResponse],
        summary="List saved submission templates",
    )
    def list_templates(
        username: Optional[str] = Query(default=None, description="Only return templates created by this user"),
        limit: int = Query(default=100, ge=1, le=500, description="Page size"),
        offset: int = Query(default=0, ge=0, description="Number of templates to skip"),
    ) -> List[TemplateResponse]:
        """Return templates ordered newest-first, with optional owner filter.

        Called by the submit wizard's "Start from template" picker. Omit
        ``username`` to see every template in the system, or pass a
        specific user to see only that user's saved configs.

        Pagination is simple offset/limit. The default page size of 100 is
        plenty for normal use; bump ``limit`` (up to 500) for admin tooling
        that needs to enumerate everything.

        Response is an array of the same shape as
        ``POST /templates`` returns.
        """
        with Session(job_store.engine) as session:
            query = session.query(TemplateModel).order_by(TemplateModel.created_at.desc())
            if username:
                query = query.filter(TemplateModel.username == username)
            rows = query.offset(offset).limit(limit).all()
            return [
                TemplateResponse(
                    template_id=r.template_id,
                    name=r.name,
                    description=r.description,
                    username=r.username,
                    config=r.config,
                    created_at=r.created_at,
                )
                for r in rows
            ]

    @router.get(
        "/templates/{template_id}",
        response_model=TemplateResponse,
        summary="Fetch a single template by ID",
    )
    def get_template(template_id: str) -> TemplateResponse:
        """Retrieve a previously saved template by its UUID.

        Used when the submit wizard needs to load a template into the form,
        including the opaque ``config`` blob that drives the prefill.

        Returns HTTP 404 if no template with that ID exists. The lookup is
        public — anyone who knows the ID can read the template, since the
        ID itself is the security boundary.
        """
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(
                TemplateModel.template_id == template_id
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Template not found.")
            return TemplateResponse(
                template_id=row.template_id,
                name=row.name,
                description=row.description,
                username=row.username,
                config=row.config,
                created_at=row.created_at,
            )

    @router.delete(
        "/templates/{template_id}",
        status_code=200,
        summary="Delete a template (owner only)",
    )
    def delete_template(
        template_id: str,
        username: str = Query(..., description="Username of the requester — must match the template's owner"),
    ) -> dict:
        """Remove a template from the store.

        Authorization: the ``username`` query parameter must exactly match
        the ``username`` that was saved on the template. Otherwise the
        request is rejected with HTTP 403. There is no admin override.

        Returns HTTP 200 with ``{"template_id": ..., "deleted": true}`` on
        success, 404 if the template doesn't exist, 403 if the requester is
        not the owner. The operation is idempotent in the sense that
        deleting an already-missing template 404s rather than silently
        succeeding — this catches bugs where the frontend fails to refresh.
        """
        with Session(job_store.engine) as session:
            row = session.query(TemplateModel).filter(
                TemplateModel.template_id == template_id
            ).first()
            if not row:
                raise HTTPException(status_code=404, detail="Template not found.")
            if row.username != username:
                raise HTTPException(status_code=403, detail="You can only delete your own templates.")
            session.delete(row)
            session.commit()
        return {"template_id": template_id, "deleted": True}

    return router
