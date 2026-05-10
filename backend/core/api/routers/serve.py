"""Routes for inference on optimized programs (single runs and grid-search pairs). [MIXED]

Public dev surface (in ``_SCALAR_PUBLIC_PATHS``):
- ``POST /serve/{id}`` — invoke the trained program.
- ``GET /serve/{id}/info`` — input/output schema for the program.

Internal (frontend-only, hidden from public docs):
- ``POST /serve/{id}/stream`` and per-pair variants under
  ``/serve/{id}/pair/{idx}/...`` — too granular for dev integration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

import dspy
from dspy.streaming import StreamListener, StreamResponse
from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from ...constants import (
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
)
from ...models import ModelConfig, ServeInfoResponse, ServeRequest, ServeResponse
from ...service_gateway.language_models import build_language_model
from ..auth import AuthenticatedUser, get_authenticated_user
from ..errors import DomainError
from ..response_limits import AGENT_MAX_INSTRUCTIONS, AGENT_MAX_TEXT, truncate_text
from ._helpers import load_pair_program, load_program, sse_from_events

logger = logging.getLogger(__name__)

AuthenticatedUserDep = Annotated[AuthenticatedUser, Depends(get_authenticated_user)]


def _cap_serve_outputs(outputs: dict[str, Any]) -> dict[str, Any]:
    """Truncate string fields in a serve-response ``outputs`` dict.

    LLM predictions can run to many KB; echoing the raw output into the
    agent's context blows the window after one or two calls. Non-string
    values pass through unchanged.

    Args:
        outputs: Mapping of output-field name to predicted value.

    Returns:
        A new dict with long string values truncated.
    """
    return {
        key: truncate_text(value, AGENT_MAX_TEXT) if isinstance(value, str) else value for key, value in outputs.items()
    }


def _artifact_prompt_fields(artifact: Any) -> tuple[list[str], list[str], str | None, int]:
    """Read prompt metadata from a ``ProgramArtifact`` with ``None``-safe fallbacks.

    ``artifact.optimized_prompt`` may be unset for legacy results, so this
    helper centralises the empty-default behaviour the routes rely on.

    Args:
        artifact: A ``ProgramArtifact`` (or grid-pair equivalent).

    Returns:
        ``(input_fields, output_fields, instructions, demo_count)``.
    """
    prompt = artifact.optimized_prompt
    if prompt is None:
        return [], [], None, 0
    return (
        list(prompt.input_fields),
        list(prompt.output_fields),
        prompt.instructions,
        len(prompt.demos),
    )


async def _stream_program_inference(
    *,
    program: Any,
    lm: Any,
    filtered_inputs: dict[str, Any],
    input_fields: list[str],
    output_fields: list[str],
    listeners: list[StreamListener],
    model_used: str,
    error_log_context: str,
) -> Any:
    """Yield ``{event, data}`` dicts for streaming a DSPy program's inference.

    Tries ``dspy.streamify`` first and falls back to a synchronous call when
    the program / output fields aren't streamable. Emits ``token`` events
    per chunk and a terminal ``final`` event, or a single ``error`` event on
    failure. Re-raises ``asyncio.CancelledError`` so the caller can tear
    the generator down cleanly.

    Args:
        program: Compiled DSPy program to invoke.
        lm: DSPy language model context to bind during inference.
        filtered_inputs: Caller-provided inputs filtered to declared fields.
        input_fields: Declared input field names from the optimized prompt.
        output_fields: Declared output field names from the optimized prompt.
        listeners: Stream listeners (one per output field) for token fan-out.
        model_used: Identifier for the LM, surfaced in the ``final`` event.
        error_log_context: Tag included in the failure log for debuggability.

    Yields:
        ``{"event": "token"|"final"|"error", "data": ...}`` dicts.

    Raises:
        asyncio.CancelledError: Re-raised so the caller can tear the
            generator down cleanly.
    """
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
                        yield {
                            "event": "token",
                            "data": {"field": item.signature_field_name, "chunk": item.chunk},
                        }
                    elif isinstance(item, dspy.Prediction):
                        if output_fields:
                            for field in output_fields:
                                final_outputs[field] = getattr(item, field, None)
                        else:
                            final_outputs |= {
                                key: val for key, val in item.toDict().items() if key not in filtered_inputs
                            }
            yield {
                "event": "final",
                "data": {
                    "outputs": final_outputs,
                    "input_fields": input_fields,
                    "output_fields": output_fields,
                    "model_used": model_used,
                },
            }
            return
        except Exception as stream_exc:
            with dspy.context(lm=lm):
                prediction = await asyncio.to_thread(lambda: program(**filtered_inputs))
            if output_fields:
                for field in output_fields:
                    final_outputs[field] = getattr(prediction, field, None)
            else:
                final_outputs |= {key: val for key, val in prediction.toDict().items() if key not in filtered_inputs}
            yield {
                "event": "final",
                "data": {
                    "outputs": final_outputs,
                    "input_fields": input_fields,
                    "output_fields": output_fields,
                    "model_used": model_used,
                    "streaming_fallback": True,
                    "fallback_reason": str(stream_exc),
                },
            }
            return
    except asyncio.CancelledError:
        raise
    except Exception:
        yield {"event": "error", "data": {"error": "streaming failed"}}
        logger.exception("Serve stream failed for %s", error_log_context)
        return


def create_serve_router(*, job_store) -> APIRouter:
    """Build the serve router.

    Args:
        job_store: Job-store instance backing the load/inference helpers.

    Returns:
        A FastAPI ``APIRouter`` exposing single-run and grid-pair serve routes.
    """
    router = APIRouter()

    @router.get(
        "/serve/{optimization_id}/info",
        response_model=ServeInfoResponse,
        summary="Describe an optimized program without running it",
        tags=["agent"],
    )
    def serve_info(optimization_id: str, current_user: AuthenticatedUserDep) -> ServeInfoResponse:
        """Describe a compiled optimized program without running it.

        Metadata-only — no LLM calls. 404 if unknown or inaccessible to the
        caller, 409 if not finished.

        Args:
            optimization_id: Optimization id whose artifact should be described.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``ServeInfoResponse`` listing the program's I/O fields,
            instructions, and demo count.

        Raises:
            DomainError: 404 if unknown or inaccessible, 409 if the
                optimization is not in a serveable state.
        """
        _, result, overview = load_program(job_store, optimization_id, current_user)
        artifact = result.program_artifact
        input_fields, output_fields, instructions, demo_count = _artifact_prompt_fields(artifact)

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
    def serve_program(
        optimization_id: str, req: ServeRequest, current_user: AuthenticatedUserDep
    ) -> ServeResponse:
        """Run a blocking inference call through the compiled program.

        Model resolution: ``model_config_override`` → stored job settings →
        stored model name. All ``input_fields`` must be supplied; extras are
        ignored.

        Args:
            optimization_id: Optimization id whose program should run.
            req: Inference request carrying inputs and optional model override.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``ServeResponse`` with the predicted outputs and resolved model.

        Raises:
            DomainError: 400 (bad inputs / no model), 404 (unknown or
                inaccessible), 409 (not in a serveable state).
        """
        program, result, overview = load_program(job_store, optimization_id, current_user)
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
                raise DomainError("serve.no_model_config", status=400)

        input_fields, output_fields, _instructions, _demo_count = _artifact_prompt_fields(artifact)

        if not input_fields:
            raise DomainError("serve.no_declared_inputs", status=400)
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise DomainError(
                "serve.missing_inputs",
                status=400,
                missing=missing,
                input_fields=input_fields,
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
            outputs = {key: val for key, val in prediction.toDict().items() if key not in req.inputs}

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
    async def serve_program_stream(
        optimization_id: str, req: ServeRequest, current_user: AuthenticatedUserDep
    ):
        """Run inference and stream partial outputs as Server-Sent Events.

        Emits one ``token`` event per chunk, keyed by output field, then a
        terminal ``final`` event. Falls back to blocking inference with
        ``streaming_fallback=true`` if ``dspy.streamify`` can't set up
        listeners. Same input validation and model resolution as the
        non-streaming endpoint.

        Args:
            optimization_id: Optimization id whose program should run.
            req: Inference request carrying inputs and optional model override.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.

        Raises:
            DomainError: 400, 404 (including inaccessible to caller), or
                409 mirroring the non-streaming route.
        """
        program, result, overview = load_program(job_store, optimization_id, current_user)
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
                raise DomainError("serve.no_model_config", status=400)

        input_fields, output_fields, _instructions, _demo_count = _artifact_prompt_fields(artifact)

        if not input_fields:
            raise DomainError("serve.no_declared_inputs", status=400)
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise DomainError(
                "serve.missing_inputs",
                status=400,
                missing=missing,
                input_fields=input_fields,
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]
        source = _stream_program_inference(
            program=program,
            lm=lm,
            filtered_inputs=filtered_inputs,
            input_fields=input_fields,
            output_fields=output_fields,
            listeners=listeners,
            model_used=model_used,
            error_log_context=f"job {optimization_id}",
        )
        return StreamingResponse(
            sse_from_events(source),
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
    def serve_pair_info(
        optimization_id: str, pair_index: int, current_user: AuthenticatedUserDep
    ) -> ServeInfoResponse:
        """Describe the program for one grid-search pair without running it.

        Same shape as ``GET /serve/{id}/info`` but scoped to a specific
        grid-search pair; ``model_name`` is the pair's generation model.

        Args:
            optimization_id: Grid-search optimization id.
            pair_index: Index of the pair in the grid-search result.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``ServeInfoResponse`` describing the pair's compiled program.

        Raises:
            DomainError: 404 (unknown / inaccessible), 409 (not finished or
                pair failed).
        """
        _program, pair, overview = load_pair_program(job_store, optimization_id, pair_index, current_user)
        artifact = pair.program_artifact
        input_fields, output_fields, instructions, demo_count = _artifact_prompt_fields(artifact)

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
    def serve_pair_program(
        optimization_id: str,
        pair_index: int,
        req: ServeRequest,
        current_user: AuthenticatedUserDep,
    ) -> ServeResponse:
        """Run inference through one grid-search pair's compiled program.

        Default model is the pair's generation model; override with
        ``model_config_override``. All ``input_fields`` must be supplied;
        extras are ignored.

        Args:
            optimization_id: Grid-search optimization id.
            pair_index: Index of the pair in the grid-search result.
            req: Inference request carrying inputs and optional model override.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A ``ServeResponse`` with the predicted outputs and resolved model.

        Raises:
            DomainError: 400 (bad inputs), 404 (unknown / inaccessible),
                409 (not finished or pair failed).
        """
        program, pair, _overview = load_pair_program(job_store, optimization_id, pair_index, current_user)
        artifact = pair.program_artifact

        model_config = req.model_config_override or ModelConfig(name=pair.generation_model)

        input_fields, output_fields, _instructions, _demo_count = _artifact_prompt_fields(artifact)

        if not input_fields:
            raise DomainError("serve.no_declared_inputs", status=400)
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise DomainError(
                "serve.missing_inputs",
                status=400,
                missing=missing,
                input_fields=input_fields,
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
            outputs = {key: val for key, val in prediction.toDict().items() if key not in req.inputs}

        return ServeResponse(
            optimization_id=optimization_id,
            outputs=_cap_serve_outputs(outputs),
            input_fields=input_fields,
            output_fields=output_fields,
            model_used=model_config.normalized_identifier(),
        )

    @router.post(
        "/serve/{optimization_id}/pair/{pair_index}/stream",
        summary="Stream inference from one grid-search pair as SSE",
    )
    async def serve_pair_program_stream(
        optimization_id: str,
        pair_index: int,
        req: ServeRequest,
        current_user: AuthenticatedUserDep,
    ):
        """Stream inference from one grid-search pair as Server-Sent Events.

        Same ``token`` -> ``final`` event shape as the single-run stream
        endpoint, same blocking fallback behavior when ``dspy.streamify``
        can't set up listeners.

        Args:
            optimization_id: Grid-search optimization id.
            pair_index: Index of the pair in the grid-search result.
            req: Inference request carrying inputs and optional model override.
            current_user: Authenticated caller resolved from the bearer token.

        Returns:
            A streaming ``StreamingResponse`` with ``text/event-stream`` body.

        Raises:
            DomainError: 400 (bad inputs), 404 (unknown / inaccessible),
                409 (not finished or pair failed).
        """
        program, pair, _overview = load_pair_program(job_store, optimization_id, pair_index, current_user)
        artifact = pair.program_artifact

        model_config = req.model_config_override or ModelConfig(name=pair.generation_model)

        input_fields, output_fields, _instructions, _demo_count = _artifact_prompt_fields(artifact)

        if not input_fields:
            raise DomainError("serve.no_declared_inputs", status=400)
        missing = [f for f in input_fields if f not in req.inputs]
        if missing:
            raise DomainError(
                "serve.missing_inputs",
                status=400,
                missing=missing,
                input_fields=input_fields,
            )
        filtered_inputs = {f: req.inputs[f] for f in input_fields}

        lm = build_language_model(model_config)
        model_used = model_config.normalized_identifier()
        listeners = [StreamListener(signature_field_name=f) for f in output_fields]
        source = _stream_program_inference(
            program=program,
            lm=lm,
            filtered_inputs=filtered_inputs,
            input_fields=input_fields,
            output_fields=output_fields,
            listeners=listeners,
            model_used=model_used,
            error_log_context=f"job {optimization_id} pair {pair_index}",
        )
        return StreamingResponse(
            sse_from_events(source),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return router
