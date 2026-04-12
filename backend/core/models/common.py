"""Foundational Pydantic models used across every domain.

Split out of the old ``backend/core/models.py`` per AGENTS.md. Contains
the primitive building blocks (mappings, model configs, split specs,
status enum, and the health status constant) that every other model
file depends on.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

HEALTH_STATUS_OK = "ok"


class ColumnMapping(BaseModel):
    """Describe how dataframe columns map onto DSPy signature fields."""

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_non_empty(self) -> "ColumnMapping":
        """Validate that mappings include inputs and no shared columns.

        Args:
            self: The ``ColumnMapping`` instance being validated.

        Returns:
            ColumnMapping: Validated mapping.

        Raises:
            ValueError: If inputs are missing or columns overlap.
        """
        if not self.inputs:
            raise ValueError("At least one input column must be specified.")
        shared = set(self.inputs.values()) & set(self.outputs.values())
        if shared:
            raise ValueError(f"Input and output column mappings must not reuse the same columns: {sorted(shared)}")
        return self


class ModelConfig(BaseModel):
    """Configuration block for language-model/backbone selection."""

    name: str
    base_url: str | None = None
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    extra: dict[str, Any] = Field(default_factory=dict)

    def normalized_identifier(self) -> str:
        """Return the Litellm identifier (deprecated: identical to ``name``).

        Args:
            None.

        Returns:
            str: Normalized model identifier preferred by LiteLLM.
        """

        return self.name.strip("/")


class SplitFractions(BaseModel):
    """Train/val/test fraction spec."""

    train: float = 0.7
    val: float = 0.15
    test: float = 0.15

    @model_validator(mode="after")
    def _validate(self) -> "SplitFractions":
        """Verify that split fractions are non-negative and sum to one.

        Args:
            self: The ``SplitFractions`` instance being validated.

        Returns:
            SplitFractions: Validated fraction set.

        Raises:
            ValueError: If constraints are violated.
        """
        parts = [self.train, self.val, self.test]
        if any(part < 0 for part in parts):
            raise ValueError("Split fractions must be non-negative.")
        total = sum(parts)
        if abs(total - 1.0) > 1e-6:
            raise ValueError("Split fractions must sum to 1.0.")
        return self


class SplitCounts(BaseModel):
    """Container for the number of examples in each dataset split.

    Attributes:
        train: Number of training examples.
        val: Number of validation examples.
        test: Number of test examples.
    """

    train: int
    val: int
    test: int


class OptimizationStatus(str, Enum):
    """Enumerate background job states."""

    pending = "pending"
    validating = "validating"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"
