"""Compiled DSPy program artifact models (prompts, demos, serialized pickle)."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OptimizedDemo(BaseModel):
    """A single few-shot demonstration example from an optimized predictor.

    Attributes:
        inputs: Dictionary of input field names to their values.
        outputs: Dictionary of output field names to their values.
    """

    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)


class OptimizedPredictor(BaseModel):
    """Extracted prompt and demos from a single predictor in the compiled program.

    Attributes:
        predictor_name: Name or identifier of the predictor within the module.
        signature_name: Class name of the DSPy signature used by this predictor.
        instructions: The optimized instruction/prompt string for this predictor.
        input_fields: List of input field names in the signature.
        output_fields: List of output field names in the signature.
        demos: List of few-shot demonstration examples.
        formatted_prompt: Complete prompt as a single formatted string with instructions and demos.
    """

    predictor_name: str
    signature_name: Optional[str] = None
    instructions: str
    input_fields: List[str] = Field(default_factory=list)
    output_fields: List[str] = Field(default_factory=list)
    demos: List[OptimizedDemo] = Field(default_factory=list)
    formatted_prompt: str = Field(
        default="",
        description="Complete prompt as a single formatted string including instructions and demos.",
    )


class ProgramArtifact(BaseModel):
    """Serializable payload that carries the optimized DSPy program files."""

    path: Optional[str] = Field(
        default=None,
        description="Absolute path on the server where the artifact lives.",
    )
    program_pickle_base64: Optional[str] = Field(
        default=None,
        description="Base64-encoded contents of the saved program.pkl file.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="metadata.json contents already parsed into a dict.",
    )
    optimized_prompt: Optional["OptimizedPredictor"] = Field(
        default=None,
        description="Extracted prompt and demos from the compiled program predictor.",
    )
