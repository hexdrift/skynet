"""Tests for RunRequest, GridSearchRequest, and OptimizationSubmissionResponse models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from core.models.common import OptimizationStatus
from core.models.submissions import GridSearchRequest, OptimizationSubmissionResponse, RunRequest


def _base_payload(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid RunRequest payload with optional overrides.

    Args:
        **overrides: Keys that replace defaults in the returned dict.

    Returns:
        Dict suitable for ``RunRequest.model_validate``.
    """
    base: dict[str, Any] = {
        "username": "alice",
        "module_name": "predict",
        "signature_code": "class S: pass",
        "metric_code": "def m(e, p): return 1.0",
        "optimizer_name": "gepa",
        "dataset": [{"q": "1+1", "a": "2"}],
        "column_mapping": {"inputs": {"q": "q"}, "outputs": {"a": "a"}},
        "model_config": {"name": "gpt-4o-mini"},
    }
    base.update(overrides)
    return base


def test_run_request_accepts_minimal_payload() -> None:
    """Verify RunRequest validates the minimal payload and exposes nested fields."""
    req = RunRequest.model_validate(_base_payload())

    assert req.model_settings.name == "gpt-4o-mini"
    assert req.dataset == [{"q": "1+1", "a": "2"}]


def test_run_request_model_settings_via_alias() -> None:
    """Verify the ``model_config`` alias maps to ``model_settings`` on the model."""
    req = RunRequest.model_validate(_base_payload())

    assert req.model_settings.name == "gpt-4o-mini"


def test_run_request_rejects_empty_dataset() -> None:
    """Verify RunRequest rejects an empty dataset list."""
    with pytest.raises(ValidationError, match="at least one row"):
        RunRequest.model_validate(_base_payload(dataset=[]))


@pytest.mark.parametrize(
    ("length", "valid"),
    [
        (0, True),
        (280, True),
        (281, False),
    ],
    ids=["empty_description", "max", "over_max"],
)
def test_run_request_description_length_boundary(length: int, valid: bool) -> None:
    """Verify description length boundaries: empty/<=280 accepted, >280 rejected."""
    kwargs = _base_payload()
    if length == 0:
        kwargs.pop("description", None)
    else:
        kwargs["description"] = "x" * length

    if valid:
        req = RunRequest.model_validate(kwargs)
        if length > 0:
            assert req.description is not None
            assert len(req.description) == length
    else:
        with pytest.raises(ValidationError):
            RunRequest.model_validate(kwargs)


def test_run_request_split_fractions_default() -> None:
    """Verify default split fractions sum to 1.0."""
    req = RunRequest.model_validate(_base_payload())

    assert abs(req.split_fractions.train + req.split_fractions.val + req.split_fractions.test - 1.0) < 1e-6


def test_run_request_shuffle_default_true() -> None:
    """Verify shuffle defaults to True when not specified."""
    req = RunRequest.model_validate(_base_payload())

    assert req.shuffle is True


def test_run_request_optional_reflection_model_absent() -> None:
    """Verify reflection and task model settings default to None."""
    req = RunRequest.model_validate(_base_payload())

    assert req.reflection_model_settings is None
    assert req.task_model_settings is None


def test_run_request_optional_reflection_model_present() -> None:
    """Verify ``reflection_model_config`` alias populates ``reflection_model_settings``."""
    payload = _base_payload(reflection_model_config={"name": "ref-model"})
    req = RunRequest.model_validate(payload)

    assert req.reflection_model_settings is not None
    assert req.reflection_model_settings.name == "ref-model"


def test_run_request_module_kwargs_default_empty() -> None:
    """Verify module_kwargs defaults to an empty dict."""
    req = RunRequest.model_validate(_base_payload())

    assert req.module_kwargs == {}


def test_run_request_react_without_metric_code_errors_even_with_preset() -> None:
    """Verify react requires metric_code even when a reward preset is present.

    React scoring moved from built-in presets to an authored metric over the
    ``(example, rollout)`` pair, so metric_code is mandatory for every run.
    """
    payload = _base_payload(module_name="react", reward={"preset": "general"})
    payload.pop("metric_code")
    with pytest.raises(ValidationError, match="metric_code is required"):
        RunRequest.model_validate(payload)


def test_run_request_non_react_without_metric_code_errors() -> None:
    """Verify a non-react run without metric_code is still rejected."""
    payload = _base_payload()
    payload.pop("metric_code")
    with pytest.raises(ValidationError, match="metric_code is required"):
        RunRequest.model_validate(payload)


def test_run_request_react_without_metric_code_and_no_preset_errors() -> None:
    """Verify a react run without metric_code and without a reward preset is rejected."""
    payload = _base_payload(module_name="react")
    payload.pop("metric_code")
    with pytest.raises(ValidationError, match="metric_code is required"):
        RunRequest.model_validate(payload)


def test_run_request_react_with_metric_code_and_no_preset_ok() -> None:
    """Verify a react run that supplies metric_code validates without a reward preset."""
    payload = _base_payload(module_name="react")
    req = RunRequest.model_validate(payload)

    assert req.metric_code == "def m(e, p): return 1.0"
    assert req.reward is None


def test_run_request_parses_tool_source() -> None:
    """Verify tool_source parses into a ToolSource with its optional fields."""
    payload = _base_payload(
        module_name="react",
        tool_source={
            "kind": "live_mcp",
            "mcp_url": "http://mcp.local",
            "mcp_auth_header": "Bearer x",
            "tool_filter": ["search", "fetch"],
        },
    )
    req = RunRequest.model_validate(payload)

    assert req.tool_source is not None
    assert req.tool_source.kind == "live_mcp"
    assert req.tool_source.mcp_url == "http://mcp.local"
    assert req.tool_source.mcp_auth_header == "Bearer x"
    assert req.tool_source.tool_filter == ["search", "fetch"]


def test_run_request_parses_replay_mapping() -> None:
    """Verify replay_mapping parses its required roles, including the state snapshots."""
    payload = _base_payload(
        module_name="react",
        replay_mapping={
            "steps": "trajectory",
            "allowed_tools": "tools",
            "tool_schema_hashes": "hashes",
            "state_before": "before",
            "state_after": "after",
        },
    )
    req = RunRequest.model_validate(payload)

    assert req.replay_mapping is not None
    assert req.replay_mapping.steps == "trajectory"
    assert req.replay_mapping.allowed_tools == "tools"
    assert req.replay_mapping.tool_schema_hashes == "hashes"
    assert req.replay_mapping.state_before == "before"
    assert req.replay_mapping.state_after == "after"
    assert req.replay_mapping.chat_history is None


def test_run_request_replay_mapping_requires_state_snapshots() -> None:
    """Verify replay_mapping rejects a payload missing the state_before/after roles.

    The gate-progress signal a metric scores against is the before/after delta,
    so an unmapped snapshot must be a hard error rather than silently empty.
    """
    payload = _base_payload(
        module_name="react",
        replay_mapping={
            "steps": "trajectory",
            "allowed_tools": "tools",
            "tool_schema_hashes": "hashes",
        },
    )
    with pytest.raises(ValidationError):
        RunRequest.model_validate(payload)


def test_run_request_reward_defaults() -> None:
    """Verify reward defaults preset to ``general`` and grounding_weight to 0.05."""
    payload = _base_payload(module_name="react", reward={})
    req = RunRequest.model_validate(payload)

    assert req.reward is not None
    assert req.reward.preset == "general"
    assert req.reward.grounding_weight == 0.05


def test_run_request_reward_generalist_preset() -> None:
    """Verify reward accepts the ``generalist`` preset and a custom grounding_weight."""
    payload = _base_payload(
        module_name="react",
        reward={"preset": "generalist", "grounding_weight": 0.2},
    )
    req = RunRequest.model_validate(payload)

    assert req.reward is not None
    assert req.reward.preset == "generalist"
    assert req.reward.grounding_weight == 0.2


def test_run_request_reward_replay_match_preset() -> None:
    """Verify reward accepts the ``replay_match`` preset without metric_code."""
    payload = _base_payload(
        module_name="react",
        reward={"preset": "replay_match", "match_mode": "tool_name"},
    )
    req = RunRequest.model_validate(payload)

    assert req.reward is not None
    assert req.reward.preset == "replay_match"
    assert req.reward.match_mode == "tool_name"


def test_run_request_reward_match_mode_defaults_exact() -> None:
    """Verify reward defaults ``match_mode`` to ``exact`` when omitted."""
    payload = _base_payload(module_name="react", reward={})
    req = RunRequest.model_validate(payload)

    assert req.reward is not None
    assert req.reward.match_mode == "exact"


def test_run_request_reward_match_mode_tool_name() -> None:
    """Verify reward accepts the opt-in ``tool_name`` match mode."""
    payload = _base_payload(
        module_name="react",
        reward={"preset": "general", "match_mode": "tool_name"},
    )
    req = RunRequest.model_validate(payload)

    assert req.reward is not None
    assert req.reward.match_mode == "tool_name"


def test_run_request_react_fields_default_none() -> None:
    """Verify the new react fields default to None on a standard payload."""
    req = RunRequest.model_validate(_base_payload())

    assert req.tool_source is None
    assert req.replay_mapping is None
    assert req.reward is None


def _grid_base(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid GridSearchRequest payload with optional overrides.

    Args:
        **overrides: Keys that replace defaults in the returned dict.

    Returns:
        Dict suitable for ``GridSearchRequest.model_validate``.
    """
    base = _base_payload()
    base.pop("model_config")
    base["generation_models"] = [{"name": "g"}]
    base["reflection_models"] = [{"name": "r"}]
    base.update(overrides)
    return base


def test_grid_search_accepts_both_model_lists() -> None:
    """Verify GridSearchRequest validates with non-empty generation and reflection lists."""
    req = GridSearchRequest.model_validate(_grid_base())

    assert len(req.generation_models) == 1
    assert len(req.reflection_models) == 1


def test_grid_search_rejects_empty_generation_models() -> None:
    """Verify GridSearchRequest rejects an empty generation_models list."""
    with pytest.raises(ValidationError, match="generation model"):
        GridSearchRequest.model_validate(_grid_base(generation_models=[]))


def test_grid_search_rejects_empty_reflection_models() -> None:
    """Verify GridSearchRequest rejects an empty reflection_models list."""
    with pytest.raises(ValidationError, match="reflection model"):
        GridSearchRequest.model_validate(_grid_base(reflection_models=[]))


def test_grid_search_multiple_pairs_accepted() -> None:
    """Verify GridSearchRequest accepts multiple generation and reflection model entries."""
    req = GridSearchRequest.model_validate(
        _grid_base(
            generation_models=[{"name": "g1"}, {"name": "g2"}],
            reflection_models=[{"name": "r1"}, {"name": "r2"}],
        )
    )

    assert len(req.generation_models) == 2
    assert len(req.reflection_models) == 2


def test_grid_search_rejects_empty_dataset() -> None:
    """Verify GridSearchRequest rejects an empty dataset list."""
    with pytest.raises(ValidationError, match="at least one row"):
        GridSearchRequest.model_validate(_grid_base(dataset=[]))


def test_optimization_submission_response_defaults() -> None:
    """Verify OptimizationSubmissionResponse defaults name and description to None."""
    resp = OptimizationSubmissionResponse(
        optimization_id="abc123",
        optimization_type="run",
        status=OptimizationStatus.pending,
        created_at=datetime.now(tz=UTC),
        username="alice",
        module_name="predict",
        optimizer_name="gepa",
    )

    assert resp.name is None
    assert resp.description is None
