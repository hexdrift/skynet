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

    @router.post(
        "/run",
        response_model=OptimizationSubmissionResponse,
        status_code=201,
        summary="Submit a single DSPy optimization run",
    )
    def submit_job(payload: RunRequest) -> OptimizationSubmissionResponse:
        """Queue one end-to-end DSPy optimization for background execution.

        This is the primary write endpoint of the service. It takes a fully
        specified optimization request (dataset, column mapping, optimizer,
        model(s), signature, metric), validates it synchronously, and hands
        it to the background worker. The response returns immediately with
        an ``optimization_id`` the caller can poll with
        ``GET /optimizations/{id}/summary`` or stream via
        ``GET /optimizations/{id}/stream``.

        Pipeline on success:
            1. Payload is validated against the registered module/optimizer
               and the user-supplied signature/metric code. A ``ServiceError``
               or ``RegistryError`` here returns HTTP 400 with details.
            2. Per-user quota is enforced. Returns HTTP 409 with a Hebrew
               error message if the user has hit ``MAX_JOBS_PER_USER``.
            3. A UUID is generated. The split seed defaults to a deterministic
               hash of the UUID if the caller didn't supply one, so train/val/test
               splits are reproducible without forcing the user to pick a number.
            4. A job row is created in the store with status ``pending`` and
               its payload overview (a scrubbed, API-key-free copy of the
               request) saved for later display.
            5. The job is pushed onto the worker queue. The worker picks it
               up asynchronously — this call returns before any optimization
               actually runs.
            6. A ``notify_job_started`` event fires (audit log / webhook).

        Security: ``model_settings.api_key`` is stripped before the overview
        is persisted. Keys only exist in memory inside the worker process.

        Returns HTTP 201 with ``OptimizationSubmissionResponse`` on success.
        Errors: 400 (validation), 409 (quota), 422 (malformed body).
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

    @router.post(
        "/grid-search",
        response_model=OptimizationSubmissionResponse,
        status_code=201,
        summary="Submit a grid search over model pairs",
    )
    def submit_grid_search(payload: GridSearchRequest) -> OptimizationSubmissionResponse:
        """Queue a sweep that runs one optimization per ``(generation_model,
        reflection_model)`` pair and then reports the best.

        The Cartesian product of ``generation_models × reflection_models``
        defines the pair count. Every pair reuses the same dataset, split
        fractions, signature, metric, and optimizer kwargs — only the two
        model slots vary. This is the right shape for questions like
        "which base model + reflection model combo works best on my task?".

        Contract with the caller:
            - Both lists must be non-empty; request body validation
              enforces that before this handler runs.
            - ``total_pairs`` is persisted on the overview as
              ``len(generation_models) * len(reflection_models)`` so the UI
              can render a determinate progress bar.
            - Each individual pair is executed serially inside the same
              grid-search job — the worker does not fan them out to
              parallel subprocesses. Cancel the grid to stop all remaining
              pairs.

        Same error handling as ``POST /run``: HTTP 400 on validation
        failure, 409 if the user is at quota, 422 on malformed body.
        Returns 201 with the submission response; poll
        ``/optimizations/{id}/summary`` for per-pair progress.
        """
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
