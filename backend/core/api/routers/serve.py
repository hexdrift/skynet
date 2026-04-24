"""Routes for inference on optimized programs (single runs and grid-search pairs)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import dspy
from dspy.streaming import StreamListener, StreamResponse
from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ...constants import (
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
)
from ...i18n import t
from ...models import ModelConfig, ServeInfoResponse, ServeRequest, ServeResponse
from ...service_gateway.language_models import build_language_model
from ._helpers import load_pair_program, load_program
from ..response_limits import AGENT_MAX_INSTRUCTIONS, AGENT_MAX_TEXT, truncate_text


def _cap_serve_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    """Truncate string fields in a serve-response ``outputs`` dict.

    LLM predictions can run to many KB; echoing the raw output into the
    agent's context blows the window after one or two calls. Non-string
    values pass through unchanged.
    """
    return {
        key: truncate_text(value, AGENT_MAX_TEXT) if isinstance(value, str) else value
        for key, value in outputs.items()
    }

logger = logging.getLogger(__name__)


def create_serve_router(*, job_store) -> APIRouter:
    """Build the serve router."""
    router = APIRouter()

    @router.get(
        "/serve/{optimization_id}/info",
        response_model=ServeInfoResponse,
        summary="Describe an optimized program without running it",
        tags=["agent"],
    )
    def serve_info(optimization_id: str) -> ServeInfoResponse:
        """Return the compiled program's signature, field names, instructions, and demo count.

        Metadata-only — no LLM calls. 404 if unknown, 409 if job not yet successful.
        """
        _, result, overview = load_program(job_store, optimization_id)
        artifact = result.program_artifact

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []
        instructions = artifact.optimized_prompt.instructions if artifact.optimized_prompt else None
        demo_count = len(artifact.optimized_prompt.demos) if artifact.optimized_prompt else 0

        return ServeInfoResponse(
            optimization_id=optimization_id,
            module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME, ""),
            optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME, ""),
            model_name=overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, ""),
            input_fields=input_fields,
            output_fields=output_fields,
            instructions=truncate_text(instructions, AGENT_MAX_INSTRUCTIONS),
            demo_count=demo_count,
        )

    @router.post(
        "/serve/{optimization_id}",
        response_model=ServeResponse,
        summary="Run a single inference through an optimized program",
        tags=["agent"],
    )
    def serve_program(optimization_id: str, req: ServeRequest) -> ServeResponse:
        """Run a blocking inference call through the compiled program and return outputs.

        Model resolution: ``model_config_override`` → stored job settings → stored model name.
        All ``input_fields`` must be supplied; extras are ignored. Errors: 400/404/409.

        Args:
            optimization_id: ID of the successful optimization job to run inference on.
            req: Serve request with input values and optional model config override.

        Returns:
            ServeResponse with per-field outputs, field lists, and the model used.
        """
        program, result, overview = load_program(job_store, optimization_id)
        artifact = result.program_artifact

        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_settings = overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
            model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
            if model_settings:
                model_config = ModelConfig.model_validate(model_settings)
            elif model_name:
                model_config = ModelConfig(name=model_name)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=t("serve.no_model_config"),
                )

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if not input_fields:
            raise HTTPException(
                status_code=400,
                detail=t("serve.no_declared_inputs"),
            )
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=t("serve.missing_inputs", missing=missing, input_fields=input_fields),
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)

        with dspy.context(lm=lm):
            prediction = program(**filtered_inputs)

        outputs: dict[str, Any] = {}
        if output_fields:
            for field in output_fields:
                outputs[field] = getattr(prediction, field, None)
        else:
            # Prediction fields live in its mapping API, not dir()
            for key, val in prediction.toDict().items():
                if key not in req.inputs:
                    outputs[key] = val

        return ServeResponse(
            optimization_id=optimization_id,
            outputs=_cap_serve_outputs(outputs),
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    @router.post(
        "/serve/{optimization_id}/stream",
        summary="Run inference and stream partial outputs as SSE",
    )
    async def serve_program_stream(optimization_id: str, req: ServeRequest):
        """SSE streaming inference: emits ``token`` events per field, then a ``final`` event.

        Falls back to blocking inference (``streaming_fallback=true``) if ``dspy.streamify``
        can't set up listeners. Same input validation and model resolution as the non-streaming endpoint.

        Args:
            optimization_id: ID of the successful optimization job to stream from.
            req: Serve request with input values and optional model config override.
        """
        program, result, overview = load_program(job_store, optimization_id)
        artifact = result.program_artifact

        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_settings = overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS, {})
            model_name = overview.get(PAYLOAD_OVERVIEW_MODEL_NAME, "")
            if model_settings:
                model_config = ModelConfig.model_validate(model_settings)
            elif model_name:
                model_config = ModelConfig(name=model_name)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=t("serve.no_model_config"),
                )

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if not input_fields:
            raise HTTPException(
                status_code=400,
                detail=t("serve.no_declared_inputs"),
            )
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=t("serve.missing_inputs", missing=missing, input_fields=input_fields),
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]

        async def event_generator():
            """Yield SSE events for the single-run streaming inference."""
            def sse(event: str, payload: dict) -> str:
                """Format a single SSE frame."""
                return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

            try:
                final_outputs: dict[str, Any] = {}
                try:
                    stream_program = dspy.streamify(
                        program,
                        stream_listeners=listeners,
                        async_streaming=True,
                    )
                    with dspy.context(lm=lm):
                        output_stream = stream_program(**filtered_inputs)
                        async for item in output_stream:
                            if isinstance(item, StreamResponse):
                                yield sse("token", {"field": item.signature_field_name, "chunk": item.chunk})
                            elif isinstance(item, dspy.Prediction):
                                if output_fields:
                                    for field in output_fields:
                                        final_outputs[field] = getattr(item, field, None)
                                else:
                                    for key, val in item.toDict().items():
                                        if key not in req.inputs:
                                            final_outputs[key] = val
                    yield sse(
                        "final",
                        {
                            "outputs": final_outputs,
                            "input_fields": input_fields,
                            "output_fields": output_fields,
                            "model_used": model_used,
                        },
                    )
                    return
                except Exception as stream_exc:
                    # Fall back to non-streaming: some modules/fields aren't streamable
                    with dspy.context(lm=lm):
                        prediction = await asyncio.to_thread(lambda: program(**filtered_inputs))
                    if output_fields:
                        for field in output_fields:
                            final_outputs[field] = getattr(prediction, field, None)
                    else:
                        for key, val in prediction.toDict().items():
                            if key not in req.inputs:
                                final_outputs[key] = val
                    yield sse(
                        "final",
                        {
                            "outputs": final_outputs,
                            "input_fields": input_fields,
                            "output_fields": output_fields,
                            "model_used": model_used,
                            "streaming_fallback": True,
                            "fallback_reason": str(stream_exc),
                        },
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield sse("error", {"error": "streaming failed"})
                logger.exception("Serve stream failed for job %s: %s", optimization_id, exc)
                return

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get(
        "/serve/{optimization_id}/pair/{pair_index}/info",
        response_model=ServeInfoResponse,
        summary="Describe the program for one grid-search pair",
        tags=["agent"],
    )
    def serve_pair_info(optimization_id: str, pair_index: int) -> ServeInfoResponse:
        """Like ``GET /serve/{id}/info`` but for a specific grid-search pair (0-based index).

        ``model_name`` is the pair's generation model. 404 if pair missing, 409 if pair failed.
        """
        _program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []
        instructions = artifact.optimized_prompt.instructions if artifact.optimized_prompt else None
        demo_count = len(artifact.optimized_prompt.demos) if artifact.optimized_prompt else 0

        return ServeInfoResponse(
            optimization_id=optimization_id,
            module_name=overview.get(PAYLOAD_OVERVIEW_MODULE_NAME, ""),
            optimizer_name=overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME, ""),
            model_name=pair.generation_model,
            input_fields=input_fields,
            output_fields=output_fields,
            instructions=truncate_text(instructions, AGENT_MAX_INSTRUCTIONS),
            demo_count=demo_count,
        )

    @router.post(
        "/serve/{optimization_id}/pair/{pair_index}",
        response_model=ServeResponse,
        summary="Run inference through one grid-search pair",
    )
    def serve_pair_program(optimization_id: str, pair_index: int, req: ServeRequest) -> ServeResponse:
        """Run inference against a specific grid-search pair's compiled program.

        Default model is the pair's generation model. Override with ``model_config_override``.
        Errors: 400/404/409.

        Args:
            optimization_id: ID of the parent grid-search job.
            pair_index: Zero-based index of the pair to run inference against.
            req: Serve request with input values and optional model config override.

        Returns:
            ServeResponse with per-field outputs, field lists, and the model used.
        """
        program, pair, _overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

        model_config = req.model_config_override or ModelConfig(name=pair.generation_model)

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if not input_fields:
            raise HTTPException(
                status_code=400,
                detail=t("serve.no_declared_inputs"),
            )
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=t("serve.missing_inputs", missing=missing, input_fields=input_fields),
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)

        with dspy.context(lm=lm):
            prediction = program(**filtered_inputs)

        outputs: dict[str, Any] = {}
        if output_fields:
            for field in output_fields:
                outputs[field] = getattr(prediction, field, None)
        else:
            for key, val in prediction.toDict().items():
                if key not in req.inputs:
                    outputs[key] = val

        return ServeResponse(
            optimization_id=optimization_id,
            outputs=outputs,
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    @router.post(
        "/serve/{optimization_id}/pair/{pair_index}/stream",
        summary="Stream inference from one grid-search pair as SSE",
    )
    async def serve_pair_program_stream(optimization_id: str, pair_index: int, req: ServeRequest):
        """SSE streaming inference for a specific grid-search pair.

        Same ``token`` → ``final`` event shape as the single-run stream endpoint, same fallback behavior.

        Args:
            optimization_id: ID of the parent grid-search job.
            pair_index: Zero-based index of the pair to stream from.
            req: Serve request with input values and optional model config override.
        """
        program, pair, _overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

        model_config = req.model_config_override or ModelConfig(name=pair.generation_model)

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if not input_fields:
            raise HTTPException(
                status_code=400,
                detail=t("serve.no_declared_inputs"),
            )
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=t("serve.missing_inputs", missing=missing, input_fields=input_fields),
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]

        async def event_generator():
            """Yield SSE events for the grid-search pair streaming inference."""
            def sse(event: str, payload: dict) -> str:
                """Format a single SSE frame."""
                return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"

            try:
                final_outputs: dict[str, Any] = {}
                try:
                    stream_program = dspy.streamify(
                        program,
                        stream_listeners=listeners,
                        async_streaming=True,
                    )
                    with dspy.context(lm=lm):
                        output_stream = stream_program(**filtered_inputs)
                        async for item in output_stream:
                            if isinstance(item, StreamResponse):
                                yield sse("token", {"field": item.signature_field_name, "chunk": item.chunk})
                            elif isinstance(item, dspy.Prediction):
                                if output_fields:
                                    for field in output_fields:
                                        final_outputs[field] = getattr(item, field, None)
                                else:
                                    for key, val in item.toDict().items():
                                        if key not in req.inputs:
                                            final_outputs[key] = val
                    yield sse(
                        "final",
                        {
                            "outputs": final_outputs,
                            "input_fields": input_fields,
                            "output_fields": output_fields,
                            "model_used": model_used,
                        },
                    )
                    return
                except Exception as stream_exc:
                    with dspy.context(lm=lm):
                        prediction = await asyncio.to_thread(lambda: program(**filtered_inputs))
                    if output_fields:
                        for field in output_fields:
                            final_outputs[field] = getattr(prediction, field, None)
                    else:
                        for key, val in prediction.toDict().items():
                            if key not in req.inputs:
                                final_outputs[key] = val
                    yield sse(
                        "final",
                        {
                            "outputs": final_outputs,
                            "input_fields": input_fields,
                            "output_fields": output_fields,
                            "model_used": model_used,
                            "streaming_fallback": True,
                            "fallback_reason": str(stream_exc),
                        },
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield sse("error", {"error": "streaming failed"})
                logger.exception("Serve pair stream failed for job %s pair %d: %s", optimization_id, pair_index, exc)
                return

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
