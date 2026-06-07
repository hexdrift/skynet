"""Pydantic models for the training-ground bundle on-disk format.

The bundle model mirrors the on-disk schema in ``training_ground_SPEC.md`` §8
verbatim so a bundle round-trip survives a `pydantic` validate-dump cycle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PairedBootstrapResult(BaseModel):
    """Acceptance statistics produced by ``persistence.paired_bootstrap_ci``."""

    resamples: int
    mean_delta: float
    ci95_lower: float
    ci95_upper: float


class Bundle(BaseModel):
    """On-disk bundle format mounted from the prod ConfigMap.

    Schema is the source of truth for the file the runtime loads at
    ``/etc/skynet/bundles/<model_id>/current.json``. Any field rename here
    is a breaking change — bump ``bundle_format_version`` before shipping.
    """

    bundle_format_version: int = Field(default=1)
    model_id: str
    version: str
    dspy_version: str
    gepa_version: str
    gate_logic_version: str
    tool_schema_hashes: dict[str, str]
    max_iters: int = Field(default=8, ge=1)
    program_state: dict[str, Any]
    # GEPA-mutated overlays applied on top of the live MCP tools at
    # runtime. ``program.save(save_program=False)`` discards the program's
    # tool dict, so these are persisted separately and re-applied in
    # ``registry.fresh_program_for_bundle``. Default-empty for backwards
    # compatibility with bundles produced before this field existed.
    tool_descriptions: dict[str, str] = Field(default_factory=dict)
    tool_arg_descriptions: dict[str, dict[str, str]] = Field(default_factory=dict)
    # GEPA-proposed agent-facing display names ``{canonical: proposed}``, applied
    # after drift-check + desc/arg overlays in ``fresh_program_for_bundle``. None
    # (default) preserves pre-rename behavior for bundles produced before this field.
    tool_names: dict[str, str] | None = Field(default=None)
    scalar_score: float
    objective_scores: dict[str, float]
    window_days: int = Field(ge=1)
    trajectories_trained_on: int = Field(ge=0)
    trajectories_held_out: int = Field(ge=0)
    paired_bootstrap: PairedBootstrapResult
    # Optional debug metadata (provenance — not enforced on load).
    optimizer_kwargs: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "Bundle",
    "PairedBootstrapResult",
]
