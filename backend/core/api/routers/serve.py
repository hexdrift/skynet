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

    @router.get(
        "/serve/{optimization_id}/info",
        response_model=ServeInfoResponse,
        summary="Describe an optimized program without running it",
    )
    def serve_info(optimization_id: str) -> ServeInfoResponse:
        """Load the compiled program for a finished optimization and return
        everything the caller needs to build a valid inference request.

        This is a metadata-only probe: no language model is loaded, no
        tokens are generated, no network calls to providers happen. It
        simply reads the stored program artifact and exposes its signature,
        few-shot demo count, and embedded system instructions so the UI
        (or any client) can render a form and validate inputs up front.

        Response fields:
            - ``input_fields``: ordered list of required ``req.inputs`` keys
            - ``output_fields``: ordered list of fields the program produces
            - ``instructions``: the system prompt after optimization (may be
              ``null`` if the optimizer didn't change the base instructions)
            - ``demo_count``: number of few-shot examples baked into the
              program (0 for optimizers that don't use demos)
            - ``module_name`` / ``optimizer_name`` / ``model_name``: echoed
              from the job overview for display

        Errors: 404 if the optimization doesn't exist, 409 if the job
        didn't finish successfully (no artifact to serve).

        Args:
            optimization_id: Identifier of the optimization to inspect.

        Returns:
            ServeInfoResponse describing the compiled program's signature.
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

    @router.post(
        "/serve/{optimization_id}",
        response_model=ServeResponse,
        summary="Run a single inference through an optimized program",
    )
    def serve_program(optimization_id: str, req: ServeRequest) -> ServeResponse:
        """Execute the compiled program end-to-end and return its outputs.

        This is the "playground" endpoint: hand it a dict of inputs keyed by
        the signature's ``input_fields``, and it configures the language
        model, runs the program inside a ``dspy.context``, and returns the
        predicted outputs.

        Model resolution order:
            1. If the request body includes ``model_config_override``, use it
               verbatim. Useful for A/B testing a program against a different
               model than it was optimized with.
            2. Otherwise, reuse the ``model_settings`` stored on the job
               overview from the original submission (including temperature,
               max_tokens, etc., but *excluding* the stripped API key).
            3. If the overview only has ``model_name`` and no settings
               (legacy jobs), construct a minimal ``ModelConfig(name=...)``.
            4. If none of those are available, return HTTP 400 asking the
               caller to supply ``model_config_override``.

        Input validation is strict: every field declared in the signature's
        ``input_fields`` must appear in ``req.inputs`` or the call fails with
        HTTP 400 listing the missing keys. Extra fields are ignored.

        Output extraction: if the signature declares explicit output fields,
        only those are returned. Otherwise (rare) the handler falls back to
        the full prediction dict minus any keys that shadowed inputs.

        Errors: 400 (missing inputs or no model), 404 (job missing), 409
        (job didn't succeed), plus anything the provider raises during
        inference.

        Args:
            optimization_id: Identifier of the optimization to run inference against.
            req: Serve request with inputs and optional model override.

        Returns:
            ServeResponse with the predicted outputs and echoed metadata.

        Raises:
            HTTPException: 400/404/409 depending on the failure mode above.
        """
        import dspy

        from ...service_gateway.language_models import build_language_model

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

        with dspy.context(lm=lm):
            prediction = program(**req.inputs)

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

    @router.post(
        "/serve/{optimization_id}/stream",
        summary="Run inference and stream partial outputs as SSE",
    )
    async def serve_program_stream(optimization_id: str, req: ServeRequest):
        """Token-by-token streaming version of ``POST /serve/{optimization_id}``.

        Wraps the compiled program with ``dspy.streamify`` and a
        ``StreamListener`` per output field, then pipes the resulting
        event stream to the HTTP response as Server-Sent Events so
        interactive UIs can render generations as they arrive.

        SSE event types:
            - ``event: token`` → ``{"field": str, "chunk": str}``
              One event per incremental token on a specific output field.
              Fields may interleave depending on how the module produces them.
            - ``event: final`` → ``{"outputs": {...}, "input_fields": [...],
              "output_fields": [...], "model_used": str}``
              Sent exactly once after the program finishes. Contains the
              complete, concatenated outputs — use this as the source of
              truth instead of reconstructing from tokens.
            - ``event: error`` → ``{"error": "streaming failed"}``
              A generic error envelope. Full details are in server logs.

        Streaming fallback: if the underlying module or any output field
        isn't streamable (DSPy raises during setup), the handler silently
        falls back to a blocking inference call and emits a single
        ``final`` event with ``streaming_fallback=true`` and
        ``fallback_reason`` set. The client sees the same success shape.

        Response headers set ``Cache-Control: no-cache``, keep-alive, and
        ``X-Accel-Buffering: no`` to prevent proxies from collapsing the
        stream. Input validation and model resolution are identical to
        the non-streaming endpoint.

        Args:
            optimization_id: Identifier of the optimization to run inference against.
            req: Serve request with inputs and optional model override.

        Returns:
            StreamingResponse yielding ``text/event-stream`` token and final events.
        """
        import dspy
        from dspy.streaming import StreamListener, StreamResponse

        from ...service_gateway.language_models import build_language_model

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
            """Yield SSE events for streaming single-run inference.

            Yields:
                SSE-formatted strings emitting ``token``, ``final``, or ``error`` events.
            """
            def sse(event: str, payload: dict) -> str:
                """Format an SSE event frame.

                Args:
                    event: Event name placed on the ``event:`` line.
                    payload: JSON-serializable payload for the ``data:`` line.

                Returns:
                    The fully formatted ``event:/data:`` SSE string.
                """
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


    @router.get(
        "/serve/{optimization_id}/pair/{pair_index}/info",
        response_model=ServeInfoResponse,
        summary="Describe the program for one grid-search pair",
    )
    def serve_pair_info(optimization_id: str, pair_index: int) -> ServeInfoResponse:
        """Like ``GET /serve/{id}/info`` but targets a specific pair inside a
        grid-search job instead of a single-run job.

        ``pair_index`` is 0-based and matches the order in
        ``/optimizations/{id}/grid-result``. Each pair has its own compiled
        program (the whole point of a grid search is to compare them), so
        the returned signature, demo count, and instructions can differ
        from the overall "best pair" result the job reports.

        The ``model_name`` returned here is the pair's generation model, not
        the job-level model. Use this endpoint before calling the pair's
        ``/serve`` variant to make sure the UI renders the right fields.

        Errors: 404 if the optimization or pair index doesn't exist, 409 if
        the specific pair failed or hasn't finished yet.

        Args:
            optimization_id: Identifier of the grid-search job.
            pair_index: 0-based index of the pair within the grid sweep.

        Returns:
            ServeInfoResponse describing the pair's compiled program.
        """
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

    @router.post(
        "/serve/{optimization_id}/pair/{pair_index}",
        response_model=ServeResponse,
        summary="Run inference through one grid-search pair",
    )
    def serve_pair_program(optimization_id: str, pair_index: int, req: ServeRequest) -> ServeResponse:
        """Run inference against the compiled program produced by a specific
        ``(generation_model, reflection_model)`` pair inside a grid search.

        Use this when you want to compare predictions from individual pairs
        rather than only the grid's "best pair". The compiled program, its
        signature, and its demo set are all pair-local.

        Model resolution differs slightly from the single-run variant: by
        default the pair's *generation model* is used (the reflection model
        is only relevant at optimization time). Callers can still override
        with ``req.model_config_override`` to test the same program against
        a different model.

        Input validation and output extraction are identical to
        ``POST /serve/{optimization_id}``. Errors: 400 (missing inputs),
        404 (optimization or pair missing), 409 (pair didn't succeed).

        Args:
            optimization_id: Identifier of the grid-search job.
            pair_index: 0-based index of the pair within the grid sweep.
            req: Serve request with inputs and optional model override.

        Returns:
            ServeResponse with the pair's predicted outputs and metadata.

        Raises:
            HTTPException: 400/404/409 as described above.
        """
        import dspy

        from ...service_gateway.language_models import build_language_model

        program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

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

        with dspy.context(lm=lm):
            prediction = program(**req.inputs)

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
        """SSE streaming variant of the per-pair serve endpoint.

        Same event shape as ``POST /serve/{optimization_id}/stream``
        (``token`` → ``final`` → optional ``error``) and the same
        streaming-fallback behavior if ``dspy.streamify`` can't set up
        listeners for one of the output fields. The only difference is
        that the program and default model come from a specific grid
        pair instead of the top-level job.

        Typical client flow:
            1. Call ``GET /optimizations/{id}/grid-result`` to enumerate pairs.
            2. Call ``GET /serve/{id}/pair/{i}/info`` for the pair's signature.
            3. Open an SSE connection to this endpoint with valid ``inputs``.
            4. Render incoming ``token`` events live, then flip to the
               canonical outputs in the ``final`` event.

        Args:
            optimization_id: Identifier of the grid-search job.
            pair_index: 0-based index of the pair within the grid sweep.
            req: Serve request with inputs and optional model override.

        Returns:
            StreamingResponse yielding ``text/event-stream`` token and final events.
        """
        import dspy
        from dspy.streaming import StreamListener, StreamResponse

        from ...service_gateway.language_models import build_language_model

        program, pair, overview = load_pair_program(job_store, optimization_id, pair_index)
        artifact = pair.program_artifact

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
            """Yield SSE events for streaming per-pair inference.

            Yields:
                SSE-formatted strings emitting ``token``, ``final``, or ``error`` events.
            """
            def sse(event: str, payload: dict) -> str:
                """Format an SSE event frame.

                Args:
                    event: Event name placed on the ``event:`` line.
                    payload: JSON-serializable payload for the ``data:`` line.

                Returns:
                    The fully formatted ``event:/data:`` SSE string.
                """
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
