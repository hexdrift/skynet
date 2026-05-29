"""Training-ground harness for the generalist agent.

A reusable package that optimizes the production generalist's prompts +
tool descriptions via GEPA, scored on a hybrid trace-conditioned replay of
recorded ``agent_messages`` trajectories.

Design contract lives in ``backend/training_ground_SPEC.md``. Top-level
imports are deliberately kept narrow — the CLI uses the submodules
directly, and the runtime only needs the registry helpers.
"""

from .registry import (
    BundleIncompatibleError,
    BundleNotFoundError,
    ToolSchemaDriftError,
    bundle_path_for,
    fresh_program_for_bundle,
    hash_tool_schema,
    load_bundle,
    snapshot_tool_schema_hashes,
)
from .types import Bundle, EvaluationExample, PairedBootstrapResult, ReplayStep

__all__ = [
    "Bundle",
    "BundleIncompatibleError",
    "BundleNotFoundError",
    "EvaluationExample",
    "PairedBootstrapResult",
    "ReplayStep",
    "ToolSchemaDriftError",
    "bundle_path_for",
    "fresh_program_for_bundle",
    "hash_tool_schema",
    "load_bundle",
    "snapshot_tool_schema_hashes",
]
