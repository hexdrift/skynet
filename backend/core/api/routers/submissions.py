"""Routes for submitting optimization jobs.

``POST /run`` — single optimization run.
``POST /grid-search`` — sweep over (generation, reflection) model pairs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_COLUMN_MAPPING,
    PAYLOAD_OVERVIEW_COMPILE_KWARGS,
    PAYLOAD_OVERVIEW_DATASET_FILENAME,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_DESCRIPTION,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_JOB_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_PROMPT_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_SEED,
    PAYLOAD_OVERVIEW_SHUFFLE,
    PAYLOAD_OVERVIEW_SPLIT_FRACTIONS,
    PAYLOAD_OVERVIEW_TASK_MODEL,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...models import (
    GridSearchRequest,
    OptimizationStatus,
    OptimizationSubmissionResponse,
    RunRequest,
)
from ...notifications import notify_job_started
from ...registry import RegistryError
from ...service_gateway import ServiceError
from ...worker import get_worker
from ._helpers import enforce_user_quota, strip_api_key

logger = logging.getLogger(__name__)


def create_submissions_router(*, service, job_store) -> APIRouter:
    """Build the submissions router.

    Args:
        service: DspyService used for payload validation.
        job_store: Job store used to persist new jobs and their overviews.

    Returns:
        APIRouter: Router with ``POST /run`` and ``POST /grid-search``.
    """
    router = APIRouter()

    @router.post("/run", response_model=OptimizationSubmissionResponse, status_code=201)
    def submit_job(payload: RunRequest) -> OptimizationSubmissionResponse:
        """Validate and queue a DSPy optimization request.

        Args:
            payload: Parsed request containing dataset and optimizer settings.

        Returns:
            OptimizationSubmissionResponse: Optimization identifier and scheduling metadata.

        Raises:
            HTTPException: If validation fails.
        """

        try:
            service.validate_payload(payload)
        except (ServiceError, RegistryError) as exc:
            logger.warning("Payload validation failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))

        enforce_user_quota(job_store, payload.username)

        optimization_id = str(uuid4())
        # Ensure a deterministic seed so dataset splits are reproducible
        if payload.seed is None:
            payload.seed = hash(optimization_id) % (2**31)

        job_store.create_job(optimization_id)
        job_store.set_payload_overview(
            optimization_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: OPTIMIZATION_TYPE_RUN,
                PAYLOAD_OVERVIEW_NAME: payload.name,
                PAYLOAD_OVERVIEW_DESCRIPTION: payload.description,
                PAYLOAD_OVERVIEW_USERNAME: payload.username,
                PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
                PAYLOAD_OVERVIEW_MODULE_KWARGS: dict(payload.module_kwargs),
                PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
                PAYLOAD_OVERVIEW_MODEL_NAME: payload.model_settings.normalized_identifier(),
                PAYLOAD_OVERVIEW_MODEL_SETTINGS: strip_api_key(payload.model_settings.model_dump()),
                PAYLOAD_OVERVIEW_REFLECTION_MODEL: (
                    payload.reflection_model_settings.normalized_identifier()
                    if payload.reflection_model_settings else None
                ),
                PAYLOAD_OVERVIEW_PROMPT_MODEL: (
                    payload.prompt_model_settings.normalized_identifier()
                    if payload.prompt_model_settings else None
                ),
                PAYLOAD_OVERVIEW_TASK_MODEL: (
                    payload.task_model_settings.normalized_identifier()
                    if payload.task_model_settings else None
                ),
                PAYLOAD_OVERVIEW_COLUMN_MAPPING: payload.column_mapping.model_dump(),
                PAYLOAD_OVERVIEW_DATASET_ROWS: len(payload.dataset),
                PAYLOAD_OVERVIEW_DATASET_FILENAME: payload.dataset_filename,
                PAYLOAD_OVERVIEW_SPLIT_FRACTIONS: payload.split_fractions.model_dump(),
                PAYLOAD_OVERVIEW_SHUFFLE: payload.shuffle,
                PAYLOAD_OVERVIEW_SEED: payload.seed,
                PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS: dict(payload.optimizer_kwargs),
                PAYLOAD_OVERVIEW_COMPILE_KWARGS: dict(payload.compile_kwargs),
            },
        )

        current_worker = get_worker(job_store, service=service)
        current_worker.submit_job(optimization_id, payload)

        logger.info(
            "Enqueued job %s for module=%s optimizer=%s",
            optimization_id,
            payload.module_name,
            payload.optimizer_name,
        )

        notify_job_started(
            optimization_id=optimization_id,
            username=payload.username,
            optimization_type=OPTIMIZATION_TYPE_RUN,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=payload.model_settings.normalized_identifier(),
        )

        return OptimizationSubmissionResponse(
            optimization_id=optimization_id,
            optimization_type=OPTIMIZATION_TYPE_RUN,
            status=OptimizationStatus.pending,
            created_at=datetime.now(timezone.utc),
            name=payload.name,
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    @router.post("/grid-search", response_model=OptimizationSubmissionResponse, status_code=201)
    def submit_grid_search(payload: GridSearchRequest) -> OptimizationSubmissionResponse:
        """Submit a grid search over (generation, reflection) model pairs."""
        if hasattr(service, "validate_grid_search_payload"):
            try:
                service.validate_grid_search_payload(payload)
            except (ServiceError, RegistryError) as exc:
                logger.warning("Grid search validation failed: %s", exc)
                raise HTTPException(status_code=400, detail=str(exc))

        enforce_user_quota(job_store, payload.username)

        optimization_id = str(uuid4())
        if payload.seed is None:
            payload.seed = hash(optimization_id) % (2**31)
        total_pairs = len(payload.generation_models) * len(payload.reflection_models)

        job_store.create_job(optimization_id)
        job_store.set_payload_overview(
            optimization_id,
            {
                PAYLOAD_OVERVIEW_JOB_TYPE: OPTIMIZATION_TYPE_GRID_SEARCH,
                PAYLOAD_OVERVIEW_NAME: payload.name,
                PAYLOAD_OVERVIEW_DESCRIPTION: payload.description,
                PAYLOAD_OVERVIEW_USERNAME: payload.username,
                PAYLOAD_OVERVIEW_MODULE_NAME: payload.module_name,
                PAYLOAD_OVERVIEW_MODULE_KWARGS: dict(payload.module_kwargs),
                PAYLOAD_OVERVIEW_OPTIMIZER_NAME: payload.optimizer_name,
                PAYLOAD_OVERVIEW_COLUMN_MAPPING: payload.column_mapping.model_dump(),
                PAYLOAD_OVERVIEW_DATASET_ROWS: len(payload.dataset),
                PAYLOAD_OVERVIEW_DATASET_FILENAME: payload.dataset_filename,
                PAYLOAD_OVERVIEW_SPLIT_FRACTIONS: payload.split_fractions.model_dump(),
                PAYLOAD_OVERVIEW_SHUFFLE: payload.shuffle,
                PAYLOAD_OVERVIEW_SEED: payload.seed,
                PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS: dict(payload.optimizer_kwargs),
                PAYLOAD_OVERVIEW_COMPILE_KWARGS: dict(payload.compile_kwargs),
                PAYLOAD_OVERVIEW_TOTAL_PAIRS: total_pairs,
                PAYLOAD_OVERVIEW_GENERATION_MODELS: [m.model_dump() for m in payload.generation_models],
                PAYLOAD_OVERVIEW_REFLECTION_MODELS: [m.model_dump() for m in payload.reflection_models],
            },
        )

        current_worker = get_worker(job_store, service=service)
        current_worker.submit_job(optimization_id, payload)

        logger.info(
            "Enqueued grid search %s: %d pairs, module=%s optimizer=%s",
            optimization_id, total_pairs, payload.module_name, payload.optimizer_name,
        )

        notify_job_started(
            optimization_id=optimization_id,
            username=payload.username,
            optimization_type=OPTIMIZATION_TYPE_GRID_SEARCH,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=f"{total_pairs} זוגות",
        )

        return OptimizationSubmissionResponse(
            optimization_id=optimization_id,
            optimization_type=OPTIMIZATION_TYPE_GRID_SEARCH,
            status=OptimizationStatus.pending,
            created_at=datetime.now(timezone.utc),
            name=payload.name,
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    return router
