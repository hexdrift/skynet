"""Persistence and prompt-extraction helpers for compiled DSPy programs.

Encapsulates two concerns: turning a compiled :class:`dspy.Program` into a
JSON-friendly :class:`ProgramArtifact` (state JSON alongside its metadata)
and extracting a human-readable :class:`OptimizedPredictor` view from the
program's first named predictor for the UI.
"""

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from ...exceptions import ServiceError
from ...models import OptimizedDemo, OptimizedPredictor, ProgramArtifact

logger = logging.getLogger(__name__)


def _format_prompt_string(
    instructions: str,
    input_fields: list[str],
    output_fields: list[str],
    demos: list[OptimizedDemo],
    signature: Any,
) -> str:
    """Build a human-readable prompt string from instructions, fields, and demos.

    Args:
        instructions: Top-level signature instruction text.
        input_fields: Ordered names of input fields.
        output_fields: Ordered names of output fields.
        demos: Few-shot demo pairs to render.
        signature: The signature object used to look up field descriptions.

    Returns:
        A multi-line string ready to display in the UI.
    """
    parts: list[str] = []

    if instructions:
        parts.append(instructions)
        parts.append("")

    if input_fields or output_fields:
        field_lines: list[str] = []
        for field_name in input_fields:
            desc = ""
            try:
                field_obj = signature.input_fields.get(field_name)
                if field_obj and hasattr(field_obj, "json_schema_extra"):
                    desc = field_obj.json_schema_extra.get("desc", "")
            except (AttributeError, TypeError):
                logger.debug("Could not extract description for input field '%s'", field_name)
            if desc:
                field_lines.append(f"[Input] {field_name}: {desc}")
            else:
                field_lines.append(f"[Input] {field_name}")

        for field_name in output_fields:
            desc = ""
            try:
                field_obj = signature.output_fields.get(field_name)
                if field_obj and hasattr(field_obj, "json_schema_extra"):
                    desc = field_obj.json_schema_extra.get("desc", "")
            except (AttributeError, TypeError):
                logger.debug("Could not extract description for output field '%s'", field_name)
            if desc:
                field_lines.append(f"[Output] {field_name}: {desc}")
            else:
                field_lines.append(f"[Output] {field_name}")

        if field_lines:
            parts.append("Fields:")
            parts.extend(field_lines)
            parts.append("")

    if demos:
        parts.append("---")
        parts.append("Examples:")
        parts.append("")
        for i, demo in enumerate(demos, 1):
            parts.append(f"Example {i}:")
            for field_name, value in demo.inputs.items():
                parts.append(f"  {field_name}: {value}")
            for field_name, value in demo.outputs.items():
                parts.append(f"  {field_name}: {value}")
            parts.append("")

    return "\n".join(parts).strip()


def extract_optimized_prompt(program: Any) -> OptimizedPredictor | None:
    """Extract instructions, fields, and demos from the first named predictor.

    Args:
        program: A compiled DSPy program.

    Returns:
        An :class:`OptimizedPredictor` describing the predictor's prompt
        surface, or ``None`` when introspection fails.
    """
    try:
        named_predictors = list(program.named_predictors())
    except Exception as exc:
        logger.warning("Could not enumerate predictors: %s", exc)
        return None

    if not named_predictors:
        return None

    name, predictor = named_predictors[0]

    try:
        signature = getattr(predictor, "signature", None)
        if signature is None:
            return None

        instructions = getattr(signature, "instructions", "") or ""
        signature_name = signature.__class__.__name__

        input_fields: list[str] = []
        output_fields: list[str] = []
        try:
            input_fields = list(signature.input_fields.keys())
            output_fields = list(signature.output_fields.keys())
        except (AttributeError, TypeError):
            logger.debug("Could not extract field names from signature")

        demos: list[OptimizedDemo] = []
        raw_demos = getattr(predictor, "demos", []) or []
        for demo in raw_demos:
            try:
                demo_inputs = {field: getattr(demo, field, None) for field in input_fields if hasattr(demo, field)}
                demo_outputs = {field: getattr(demo, field, None) for field in output_fields if hasattr(demo, field)}
                demos.append(OptimizedDemo(inputs=demo_inputs, outputs=demo_outputs))
            except (AttributeError, TypeError, ValueError) as demo_exc:
                logger.debug("Could not extract demo: %s", demo_exc)

        formatted_prompt = _format_prompt_string(instructions, input_fields, output_fields, demos, signature)

        return OptimizedPredictor(
            predictor_name=name,
            signature_name=signature_name,
            instructions=instructions,
            input_fields=input_fields,
            output_fields=output_fields,
            demos=demos,
            formatted_prompt=formatted_prompt,
        )
    except Exception as exc:
        logger.warning("Failed to extract predictor '%s': %s", name, exc)
        return None


def persist_program(
    program: Any,
    artifact_id: str | None,
) -> ProgramArtifact | None:
    """Save the compiled program as JSON state and return the artifact.

    Uses DSPy's state-only ``module.save(path.json)`` path: only the
    optimizer-tuned state (instructions, demos, predictor settings) is
    written, never a pickle. Reconstruction at load time rebuilds the
    module shell from ``signature_code`` + ``module_name`` and then
    overlays this state.

    Args:
        program: The compiled DSPy program to serialize.
        artifact_id: Optional identifier baked into the temp directory name.

    Returns:
        A :class:`ProgramArtifact` containing the program state JSON,
        DSPy metadata, and the extracted prompt — or ``None`` when no
        artifact is produced.

    Raises:
        ServiceError: When ``program.save`` fails or the serialized JSON
            cannot be read back from the scratch directory.
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"dspy_artifact_{artifact_id or uuid4()}_")
        destination = Path(temp_dir)
        state_path = destination / "program.json"

        try:
            program.save(str(state_path), save_program=False)
        except Exception as exc:
            logger.exception("Failed to save DSPy program artifact")
            raise ServiceError(f"Failed to save program artifact: {exc}") from exc

        try:
            state = json.loads(state_path.read_text())
        except Exception as exc:
            logger.exception("Failed to read DSPy artifact contents")
            raise ServiceError(f"Failed to load program artifact contents: {exc}") from exc

        # DSPy bundles dependency_versions into ``state["metadata"]``;
        # surface it separately so the artifact shape mirrors the old
        # (metadata, payload) split the UI/API was built around.
        metadata = state.get("metadata")

        optimized_prompt = extract_optimized_prompt(program)
        if optimized_prompt:
            logger.debug("Extracted optimized prompt from program")

        return ProgramArtifact(
            path=None,
            metadata=metadata,
            program_state_json=state,
            optimized_prompt=optimized_prompt,
        )

    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug("Cleaned up temp artifact directory: %s", temp_dir)
