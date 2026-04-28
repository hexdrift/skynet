"""Persistence and prompt-extraction helpers for compiled DSPy programs.

Encapsulates two concerns: turning a compiled :class:`dspy.Program` into a
JSON-friendly :class:`ProgramArtifact` (pickle base64-encoded alongside its
metadata) and extracting a human-readable :class:`OptimizedPredictor` view
from the program's first named predictor for the UI.
"""

import base64
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
            except Exception:
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
            except Exception:
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
        except Exception:
            logger.debug("Could not extract field names from signature")

        demos: list[OptimizedDemo] = []
        raw_demos = getattr(predictor, "demos", []) or []
        for demo in raw_demos:
            try:
                demo_inputs = {field: getattr(demo, field, None) for field in input_fields if hasattr(demo, field)}
                demo_outputs = {field: getattr(demo, field, None) for field in output_fields if hasattr(demo, field)}
                demos.append(OptimizedDemo(inputs=demo_inputs, outputs=demo_outputs))
            except Exception as demo_exc:
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
    """Save the compiled program to a temp dir, encode to base64, clean up, and return the artifact.

    DSPy's serializer writes two files (``metadata.json`` and
    ``program.pkl``) into a directory; we read both back, pack the
    pickle into base64 so the artifact can live inside a JSON payload,
    and delete the scratch dir before returning.

    Args:
        program: The compiled DSPy program to serialize.
        artifact_id: Optional identifier baked into the temp directory name.

    Returns:
        A :class:`ProgramArtifact` containing metadata and the base64-encoded
        pickle, or ``None`` when no artifact is produced.

    Raises:
        ServiceError: When ``program.save`` fails or the serialized files
            cannot be read back from the scratch directory.
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"dspy_artifact_{artifact_id or uuid4()}_")
        destination = Path(temp_dir)

        try:
            program.save(str(destination), save_program=True)
        except Exception as exc:
            logger.exception("Failed to save DSPy program artifact")
            raise ServiceError(f"Failed to save program artifact: {exc}") from exc

        try:
            metadata_path = destination / "metadata.json"
            program_path = destination / "program.pkl"
            metadata = json.loads(metadata_path.read_text())
            program_bytes = program_path.read_bytes()
            program_b64 = base64.b64encode(program_bytes).decode("ascii")
        except Exception as exc:
            logger.exception("Failed to read DSPy artifact contents")
            raise ServiceError(f"Failed to load program artifact contents: {exc}") from exc

        optimized_prompt = extract_optimized_prompt(program)
        if optimized_prompt:
            logger.debug("Extracted optimized prompt from program")

        return ProgramArtifact(
            path=None,
            metadata=metadata,
            program_pickle_base64=program_b64,
            optimized_prompt=optimized_prompt,
        )

    finally:
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug("Cleaned up temp artifact directory: %s", temp_dir)
