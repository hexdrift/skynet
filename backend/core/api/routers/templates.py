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

    @router.post("/templates", response_model=TemplateResponse, status_code=201)
    def create_template(req: TemplateCreateRequest) -> TemplateResponse:
        """Save a reusable job configuration template."""
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

    @router.get("/templates", response_model=List[TemplateResponse])
    def list_templates(
        username: Optional[str] = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> List[TemplateResponse]:
        """List templates with optional filtering and pagination."""
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

    @router.get("/templates/{template_id}", response_model=TemplateResponse)
    def get_template(template_id: str) -> TemplateResponse:
        """Retrieve a single template."""
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

    @router.delete("/templates/{template_id}", status_code=200)
    def delete_template(
        template_id: str,
        username: str = Query(..., description="Owner username for authorization"),
    ) -> dict:
        """Delete a template (only the owner can delete)."""
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
