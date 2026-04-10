"""Routes for inference on optimized programs (single runs and grid-search pairs)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import StreamingResponse

from ...constants import (
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
)
from ...models import ModelConfig, ServeInfoResponse, ServeRequest, ServeResponse
from ._helpers import load_pair_program, load_program

logger = logging.getLogger(__name__)


def create_serve_router(*, job_store) -> APIRouter:
    """Build the serve router.

    Args:
        job_store: Active job store instance used to locate artifacts.

    Returns:
        APIRouter: Router with the six ``/serve/*`` routes.
    """
    router = APIRouter()

    @router.get("/serve/{optimization_id}/info", response_model=ServeInfoResponse)
    def serve_info(optimization_id: str) -> ServeInfoResponse:
        """Return metadata about a servable program without running inference.

        Args:
            optimization_id: Identifier of a successful optimization job.

        Returns:
            ServeInfoResponse: Program signature and metadata.
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
            instructions=instructions,
            demo_count=demo_count,
        )

    @router.post("/serve/{optimization_id}", response_model=ServeResponse)
    def serve_program(optimization_id: str, req: ServeRequest) -> ServeResponse:
        """Run inference on an optimized program.

        Deserializes the program artifact, configures the LM, and calls
        the program with the provided inputs.

        Args:
            optimization_id: Identifier of a successful optimization job.
            req: Input fields and optional model config override.

        Returns:
            ServeResponse: Program outputs.
        """
        import dspy

        from ...service_gateway.language_models import build_language_model

        program, result, overview = load_program(job_store, optimization_id)
        artifact = result.program_artifact

        # Determine model config
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
                    detail="No model config found for this job. Provide model_config_override.",
                )

        # Validate input fields
        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        # Build LM and run inference
        lm = build_language_model(model_config)

        with dspy.context(lm=lm):
            prediction = program(**req.inputs)

        # Extract outputs
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
            outputs=outputs,
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    @router.post("/serve/{optimization_id}/stream")
    async def serve_program_stream(optimization_id: str, req: ServeRequest):
        """Stream inference outputs token-by-token via Server-Sent Events.

        Uses ``dspy.streamify`` to wrap the loaded program with stream listeners
        for each output field, then emits SSE events:

        - ``event: token`` — ``{"field": str, "chunk": str}`` per partial token
        - ``event: final`` — ``{"outputs": {...}, "model_used": str}`` at the end
        - ``event: error`` — ``{"error": str}`` on failure

        Args:
            optimization_id: Identifier of a successful optimization job.
            req: Input fields and optional model config override.

        Returns:
            StreamingResponse: SSE stream of streaming events.
        """
        import dspy
        from dspy.streaming import StreamListener, StreamResponse

        from ...service_gateway.language_models import build_language_model

        program, result, overview = load_program(job_store, optimization_id)
        artifact = result.program_artifact

        # Determine model config (same logic as /serve/{optimization_id})
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
                    detail="No model config found for this job. Provide model_config_override.",
                )

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]

        async def event_generator():
            def sse(event: str, payload: dict) -> str:
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
                        output_stream = stream_program(**req.inputs)
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
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                    })
                    return
                except Exception as stream_exc:  # noqa: BLE001
                    # Fall back to non-streaming: some modules/fields aren't streamable
                    with dspy.context(lm=lm):
                        prediction = await asyncio.to_thread(lambda: program(**req.inputs))
                    if output_fields:
                        for field in output_fields:
                            final_outputs[field] = getattr(prediction, field, None)
                    else:
                        for key, val in prediction.toDict().items():
                            if key not in req.inputs:
                                final_outputs[key] = val
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                        "streaming_fallback": True,
                        "fallback_reason": str(stream_exc),
                    })
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
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

    # ── Per-pair serving (grid search) ──

    @router.get("/serve/{optimization_id}/pair/{pair_index}/info", response_model=ServeInfoResponse)
    def serve_pair_info(optimization_id: str, pair_index: int) -> ServeInfoResponse:
        """Return metadata about a servable pair program without running inference."""
        program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
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
            instructions=instructions,
            demo_count=demo_count,
        )

    @router.post("/serve/{optimization_id}/pair/{pair_index}", response_model=ServeResponse)
    def serve_pair_program(optimization_id: str, pair_index: int, req: ServeRequest) -> ServeResponse:
        """Run inference on an optimized program from a specific grid search pair."""
        import dspy

        from ...service_gateway.language_models import build_language_model

        program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

        # Determine model config
        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_config = ModelConfig(name=pair.generation_model)

        # Validate input fields
        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        # Build LM and run inference
        lm = build_language_model(model_config)

        with dspy.context(lm=lm):
            prediction = program(**req.inputs)

        # Extract outputs
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

    @router.post("/serve/{optimization_id}/pair/{pair_index}/stream")
    async def serve_pair_program_stream(optimization_id: str, pair_index: int, req: ServeRequest):
        """Stream inference outputs from a specific grid search pair's program."""
        import dspy
        from dspy.streaming import StreamListener, StreamResponse

        from ...service_gateway.language_models import build_language_model

        program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

        # Determine model config
        if req.model_config_override:
            model_config = req.model_config_override
        else:
            model_config = ModelConfig(name=pair.generation_model)

        input_fields = artifact.optimized_prompt.input_fields if artifact.optimized_prompt else []
        output_fields = artifact.optimized_prompt.output_fields if artifact.optimized_prompt else []

        if input_fields:
            missing = [f for f in input_fields if f not in req.inputs]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required input fields: {missing}. Expected: {input_fields}",
                )

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]

        async def event_generator():
            def sse(event: str, payload: dict) -> str:
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
                        output_stream = stream_program(**req.inputs)
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
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                    })
                    return
                except Exception as stream_exc:  # noqa: BLE001
                    with dspy.context(lm=lm):
                        prediction = await asyncio.to_thread(lambda: program(**req.inputs))
                    if output_fields:
                        for field in output_fields:
                            final_outputs[field] = getattr(prediction, field, None)
                    else:
                        for key, val in prediction.toDict().items():
                            if key not in req.inputs:
                                final_outputs[key] = val
                    yield sse("final", {
                        "outputs": final_outputs,
                        "input_fields": input_fields,
                        "output_fields": output_fields,
                        "model_used": model_used,
                        "streaming_fallback": True,
                        "fallback_reason": str(stream_exc),
                    })
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
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
