"""Routes for submitting optimization jobs.

``POST /run`` — single optimization run.
``POST /grid-search`` — sweep over (generation, reflection) model pairs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from fastapi import APIRouter

from ...constants import (
    OPTIMIZATION_TYPE_GRID_SEARCH,
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_COLUMN_MAPPING,
    PAYLOAD_OVERVIEW_COMPILE_KWARGS,
    PAYLOAD_OVERVIEW_DATASET_FILENAME,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_DESCRIPTION,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_REFLECTION_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_SEED,
    PAYLOAD_OVERVIEW_SHUFFLE,
    PAYLOAD_OVERVIEW_SPLIT_FRACTIONS,
    PAYLOAD_OVERVIEW_TASK_FINGERPRINT,
    PAYLOAD_OVERVIEW_TASK_MODEL,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ...i18n import t
from ...i18n_keys import I18nKey
from ...models import (
    GridSearchRequest,
    OptimizationStatus,
    OptimizationSubmissionResponse,
    RunRequest,
)
from ...models.common import ModelConfig, OptimizationType
from ...notifications import notify_job_started
from ...registry import RegistryError
from ...service_gateway import ServiceError
from ...service_gateway.safe_exec import validate_signature_code
from ...worker import get_worker
from ..errors import DomainError
from ..model_catalog import get_catalog_cached
from ._helpers import compute_task_fingerprint, enforce_user_quota, strip_api_key

logger = logging.getLogger(__name__)


def _catalog_models_as_configs() -> list[ModelConfig]:
    """Return every available catalog model wrapped as a ``ModelConfig``.

    Used by the grid-search route to expand ``use_all_available_*`` flags
    into concrete model lists.

    Returns:
        A list of ``ModelConfig`` instances, one per available catalog model.

    Raises:
        DomainError: 400 ``submit.no_models_available`` when the catalog
            reports no available models (usually no provider API keys configured).
    """
    catalog = get_catalog_cached()
    configs = [ModelConfig(name=entry.value) for entry in catalog.models]
    if not configs:
        raise DomainError("submit.no_models_available", status=400)
    return configs


def _enforce_vision_capability(
    *,
    signature_code: str,
    candidate_models: list[ModelConfig],
) -> None:
    """Reject submissions whose signature has dspy.Image inputs but a non-vision model.

    Parses ``signature_code`` once via the safe-exec subprocess, then — only when
    ``dspy.Image`` typed inputs are present — looks up every candidate model in
    the catalog and requires ``supports_vision`` for each one.

    Args:
        signature_code: User-provided DSPy Signature source.
        candidate_models: Models that would receive image-bearing inputs.

    Raises:
        DomainError: 400 ``submission.vision_required`` listing offending
            models when any candidate lacks vision support.
    """
    intro = validate_signature_code(signature_code)
    image_fields = list(intro.image_input_fields)
    if not image_fields:
        return

    catalog = get_catalog_cached()
    vision_supported: dict[str, bool] = {entry.value: entry.supports_vision for entry in catalog.models}

    offenders = sorted(
        {
            cfg.normalized_identifier()
            for cfg in candidate_models
            if not vision_supported.get(cfg.normalized_identifier(), False)
        }
    )
    if offenders:
        raise DomainError(
            I18nKey.SUBMISSION_VISION_REQUIRED,
            status=400,
            fields=", ".join(image_fields),
            model=", ".join(offenders),
        )


def _expand_catalog_grid_payload(payload: GridSearchRequest) -> None:
    """Populate generation/reflection model lists from the catalog when flagged.

    Replaces ``payload.generation_models`` and/or ``payload.reflection_models``
    with every available catalog model when the matching
    ``use_all_available_*`` flag is set. When neither flag is set this is a
    no-op.

    Args:
        payload: The grid-search request to mutate in place.

    Raises:
        DomainError: 400 when expansion is requested but no models are
            available.
    """
    if not (payload.use_all_available_generation_models or payload.use_all_available_reflection_models):
        return
    expanded = _catalog_models_as_configs()
    if payload.use_all_available_generation_models:
        payload.generation_models = expanded
    if payload.use_all_available_reflection_models:
        payload.reflection_models = expanded


def create_submissions_router(*, service, job_store) -> APIRouter:
    """Build the submissions router.

    Args:
        service: Optimization service used for synchronous validation.
        job_store: Job-store instance used to persist new submissions.

    Returns:
        A FastAPI ``APIRouter`` exposing the ``/run`` and ``/grid-search``
        endpoints.
    """
    router = APIRouter()

    @router.post(
        "/run",
        response_model=OptimizationSubmissionResponse,
        status_code=201,
        summary="Submit a single DSPy optimization run",
        tags=["agent"],
    )
    def submit_job(payload: RunRequest) -> OptimizationSubmissionResponse:
        """Queue one end-to-end DSPy optimization for background execution.

        Validates synchronously, persists a job row, and enqueues the
        payload. Returns HTTP 201 immediately; poll
        ``/optimizations/{id}/summary`` or stream via
        ``/optimizations/{id}/stream`` for progress. Security:
        ``model_settings.api_key`` is stripped from the persisted overview.

        Args:
            payload: The run-request body validated by FastAPI.

        Returns:
            An ``OptimizationSubmissionResponse`` carrying the assigned id
            and ``pending`` status.

        Raises:
            DomainError: 400 (validation), 409 (quota), 422 (malformed body).
        """

        try:
            service.validate_payload(payload)
        except (ServiceError, RegistryError) as exc:
            logger.warning("Payload validation failed: %s", exc)
            raise DomainError("submission.validation_failed", status=400, error=str(exc)) from exc

        _enforce_vision_capability(
            signature_code=payload.signature_code,
            candidate_models=[payload.model_settings],
        )

        enforce_user_quota(job_store, payload.username)

        optimization_id = str(uuid4())
        # Ensure a deterministic seed so dataset splits are reproducible
        if payload.seed is None:
            payload.seed = hash(optimization_id) % (2**31)

        task_fingerprint = compute_task_fingerprint(payload.signature_code, payload.metric_code, payload.dataset)

        job_store.create_job(optimization_id)
        job_store.set_payload_overview(
            optimization_id,
            {
                PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE: OPTIMIZATION_TYPE_RUN,
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
                    if payload.reflection_model_settings
                    else None
                ),
                PAYLOAD_OVERVIEW_TASK_MODEL: (
                    payload.task_model_settings.normalized_identifier() if payload.task_model_settings else None
                ),
                PAYLOAD_OVERVIEW_COLUMN_MAPPING: payload.column_mapping.model_dump(),
                PAYLOAD_OVERVIEW_DATASET_ROWS: len(payload.dataset),
                PAYLOAD_OVERVIEW_DATASET_FILENAME: payload.dataset_filename,
                PAYLOAD_OVERVIEW_SPLIT_FRACTIONS: payload.split_fractions.model_dump(),
                PAYLOAD_OVERVIEW_SHUFFLE: payload.shuffle,
                PAYLOAD_OVERVIEW_SEED: payload.seed,
                PAYLOAD_OVERVIEW_OPTIMIZER_KWARGS: dict(payload.optimizer_kwargs),
                PAYLOAD_OVERVIEW_COMPILE_KWARGS: dict(payload.compile_kwargs),
                PAYLOAD_OVERVIEW_TASK_FINGERPRINT: task_fingerprint,
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
            optimization_type=cast(OptimizationType, OPTIMIZATION_TYPE_RUN),
            status=OptimizationStatus.pending,
            created_at=datetime.now(UTC),
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
        tags=["agent"],
    )
    def submit_grid_search(payload: GridSearchRequest) -> OptimizationSubmissionResponse:
        """Queue a sweep over ``(generation_model, reflection_model)`` pairs.

        Runs one optimization per Cartesian pair serially inside a single
        job. When ``use_all_available_generation_models`` or
        ``use_all_available_reflection_models`` is set, the server replaces
        the matching list with every model currently available in the
        catalog before validation or enqueue. Poll
        ``/optimizations/{id}/summary`` for per-pair progress.

        Args:
            payload: The grid-search request body validated by FastAPI.

        Returns:
            An ``OptimizationSubmissionResponse`` carrying the assigned id
            and ``pending`` status.

        Raises:
            DomainError: 400 (validation/empty catalog), 409 (quota), 422
                (malformed).
        """
        _expand_catalog_grid_payload(payload)

        if hasattr(service, "validate_grid_search_payload"):
            try:
                service.validate_grid_search_payload(payload)
            except (ServiceError, RegistryError) as exc:
                logger.warning("Grid search validation failed: %s", exc)
                raise DomainError("submission.validation_failed", status=400, error=str(exc)) from exc

        _enforce_vision_capability(
            signature_code=payload.signature_code,
            candidate_models=list(payload.generation_models),
        )

        enforce_user_quota(job_store, payload.username)

        optimization_id = str(uuid4())
        if payload.seed is None:
            payload.seed = hash(optimization_id) % (2**31)
        total_pairs = len(payload.generation_models) * len(payload.reflection_models)

        task_fingerprint = compute_task_fingerprint(payload.signature_code, payload.metric_code, payload.dataset)

        job_store.create_job(optimization_id)
        job_store.set_payload_overview(
            optimization_id,
            {
                PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE: OPTIMIZATION_TYPE_GRID_SEARCH,
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
                PAYLOAD_OVERVIEW_TASK_FINGERPRINT: task_fingerprint,
            },
        )

        current_worker = get_worker(job_store, service=service)
        current_worker.submit_job(optimization_id, payload)

        logger.info(
            "Enqueued grid search %s: %d pairs, module=%s optimizer=%s",
            optimization_id,
            total_pairs,
            payload.module_name,
            payload.optimizer_name,
        )

        notify_job_started(
            optimization_id=optimization_id,
            username=payload.username,
            optimization_type=OPTIMIZATION_TYPE_GRID_SEARCH,
            optimizer_name=payload.optimizer_name,
            module_name=payload.module_name,
            model_name=t("optimization.pairs_label", count=total_pairs),
        )

        return OptimizationSubmissionResponse(
            optimization_id=optimization_id,
            optimization_type=cast(OptimizationType, OPTIMIZATION_TYPE_GRID_SEARCH),
            status=OptimizationStatus.pending,
            created_at=datetime.now(UTC),
            name=payload.name,
            username=payload.username,
            module_name=payload.module_name,
            optimizer_name=payload.optimizer_name,
        )

    return router
