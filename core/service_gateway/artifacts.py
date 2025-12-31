import base64
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, List, Optional
from uuid import uuid4
from ..exceptions import ServiceError
from ..models import OptimizedDemo, OptimizedPredictor, ProgramArtifact

logger = logging.getLogger(__name__)


def _format_prompt_string(
    instructions: str,
    input_fields: List[str],
    output_fields: List[str],
    demos: List[OptimizedDemo],
    signature: Any,
) -> str:
    """Build a complete formatted prompt string from predictor components.

    Args:
        instructions: The instruction text for the predictor.
        input_fields: List of input field names.
        output_fields: List of output field names.
        demos: List of few-shot demonstration examples.
        signature: The DSPy signature object for field descriptions.

    Returns:
        str: Complete formatted prompt as a single string.
    """
    parts: List[str] = []

    if instructions:
        parts.append(instructions)
        parts.append("")

    if input_fields or output_fields:
        field_lines: List[str] = []
        for field_name in input_fields:
            desc = ""
            try:
                field_obj = signature.input_fields.get(field_name)
                if field_obj and hasattr(field_obj, "json_schema_extra"):
                    desc = field_obj.json_schema_extra.get("desc", "")
            except Exception:
                pass
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
                pass
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


def extract_optimized_prompt(program: Any) -> Optional[OptimizedPredictor]:
    """Extract optimized prompt and demos from a compiled DSPy program.

    Extracts the instructions, signature fields, and few-shot demonstration
    examples from the program's predictor.

    Args:
        program: Compiled DSPy module produced by an optimizer.

    Returns:
        Optional[OptimizedPredictor]: Extracted prompt data, or None if extraction fails.
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

        input_fields: List[str] = []
        output_fields: List[str] = []
        try:
            input_fields = list(signature.input_fields.keys())
            output_fields = list(signature.output_fields.keys())
        except Exception:
            pass

        demos: List[OptimizedDemo] = []
        raw_demos = getattr(predictor, "demos", []) or []
        for demo in raw_demos:
            try:
                demo_inputs = {
                    field: getattr(demo, field, None)
                    for field in input_fields
                    if hasattr(demo, field)
                }
                demo_outputs = {
                    field: getattr(demo, field, None)
                    for field in output_fields
                    if hasattr(demo, field)
                }
                demos.append(OptimizedDemo(inputs=demo_inputs, outputs=demo_outputs))
            except Exception as demo_exc:
                logger.debug("Could not extract demo: %s", demo_exc)

        formatted_prompt = _format_prompt_string(
            instructions, input_fields, output_fields, demos, signature
        )

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
    artifact_id: Optional[str],
    artifacts_root: Path = None,
) -> Optional[ProgramArtifact]:
    """Save the compiled DSPy program to temp, encode to base64, then cleanup.

    All artifact data is returned in the ProgramArtifact for storage.
    No files are left on disk.

    Args:
        program: Compiled DSPy module produced by an optimizer.
        artifact_id: Optional identifier for the artifact.
        artifacts_root: Ignored - kept for backward compatibility.

    Returns:
        Optional[ProgramArtifact]: Serialized metadata bundle with base64 program.

    Raises:
        ServiceError: When saving or reading the artifact fails.
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
        # Always cleanup temp directory
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug("Cleaned up temp artifact directory: %s", temp_dir)
