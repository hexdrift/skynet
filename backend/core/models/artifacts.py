"""Compiled DSPy program artifact models (prompts, demos, serialized pickle)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OptimizedDemo(BaseModel):
    """A single few-shot demonstration example from an optimized predictor."""

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)


class OptimizedPredictor(BaseModel):
    """Extracted prompt and demos from a single predictor in the compiled program."""

    predictor_name: str
    signature_name: str | None = None
    instructions: str
    input_fields: list[str] = Field(default_factory=list)
    output_fields: list[str] = Field(default_factory=list)
    demos: list[OptimizedDemo] = Field(default_factory=list)
    formatted_prompt: str = Field(
        default="",
        description="Complete prompt as a single formatted string including instructions and demos.",
    )


class ProgramArtifact(BaseModel):
    """Serializable payload that carries the optimized DSPy program files."""

    path: str | None = Field(
        default=None,
        description="Absolute path on the server where the artifact lives.",
    )
    program_state_json: dict[str, Any] | None = Field(
        default=None,
        description=(
            "State-only JSON dump from ``module.save(path.json)``. Loaded by "
            "reconstructing the module from signature_code + module_name and "
            "calling ``program.load(json_path)``."
        ),
    )
    program_pickle_base64: str | None = Field(
        default=None,
        description=(
            "Deprecated. Base64-encoded ``program.pkl`` retained only so jobs "
            "saved before the JSON migration can still be served. New jobs "
            "leave this field unset."
        ),
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="metadata.json contents already parsed into a dict.",
    )
    optimized_prompt: OptimizedPredictor | None = Field(
        default=None,
        description="Extracted prompt and demos from the compiled program predictor.",
    )
