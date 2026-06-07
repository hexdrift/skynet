"""Training-ground harness for generic ReAct optimization.

A reusable package that persists and re-hydrates GEPA-optimized ReAct
bundles (program state + tool description/name overlays) and exposes the
registry helpers the runtime needs to serve them against live MCP tools.

Top-level imports are deliberately kept narrow — the runtime only needs the
registry helpers and the bundle model.
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
from .types import Bundle, PairedBootstrapResult

__all__ = [
    "Bundle",
    "BundleIncompatibleError",
    "BundleNotFoundError",
    "PairedBootstrapResult",
    "ToolSchemaDriftError",
    "bundle_path_for",
    "fresh_program_for_bundle",
    "hash_tool_schema",
    "load_bundle",
    "snapshot_tool_schema_hashes",
]
