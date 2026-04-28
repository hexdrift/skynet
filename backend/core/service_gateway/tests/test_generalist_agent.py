"""Tests for the generalist-agent tool gating and approval registry."""

from __future__ import annotations

import asyncio
from typing import cast

import dspy
import pytest

from core.service_gateway.agents.generalist import (
    ApprovalRegistry,
    WizardState,
    _needs_approval,
    _wrap_tool_with_approval,
    tools_for,
)


def test_empty_state_hides_dataset_and_submit_tools() -> None:
    """An empty wizard state hides dataset/code/submit tools, exposing only discovery."""
    allowed = tools_for(WizardState())
    assert "edit_code_optimizations_edit_code_post" not in allowed
    assert "validate_code_validate_code_post" not in allowed
    assert "submit_job_run_post" not in allowed
    assert "submit_grid_search_grid_search_post" not in allowed
    assert "list_models_models_get" in allowed


def test_dataset_ready_unlocks_code_tools_but_not_submit() -> None:
    """``dataset_ready`` exposes code/profile tools but submit stays hidden."""
    allowed = tools_for(WizardState(dataset_ready=True, columns_configured=True))
    assert "edit_code_optimizations_edit_code_post" in allowed
    assert "validate_code_validate_code_post" in allowed
    assert "profile_datasets_profile_post" in allowed
    assert "submit_job_run_post" not in allowed


def test_full_readiness_unlocks_submit() -> None:
    """Full readiness exposes the submit and grid-search tools."""
    allowed = tools_for(
        WizardState(
            dataset_ready=True,
            columns_configured=True,
            signature_code="class S(dspy.Signature): ...",
            metric_code="def metric(): return 1.0",
            model_configured=True,
        )
    )
    assert "submit_job_run_post" in allowed
    assert "submit_grid_search_grid_search_post" in allowed


def test_missing_any_submit_precondition_keeps_submit_hidden() -> None:
    """Submit tools stay hidden when any single readiness key is missing."""
    base: dict[str, object] = {
        "dataset_ready": True,
        "columns_configured": True,
        "signature_code": "x",
        "metric_code": "y",
        "model_configured": True,
    }
    for key in ("dataset_ready", "columns_configured", "signature_code", "metric_code", "model_configured"):
        state = {**base, key: False if isinstance(base[key], bool) else ""}
        assert "submit_job_run_post" not in tools_for(cast(WizardState, state)), (
            f"submit_job leaked with {key} missing"
        )


def test_always_tools_include_discovery_and_post_submit() -> None:
    """The always-on toolset includes discovery and post-submit lifecycle tools."""
    allowed = tools_for(WizardState())
    assert "list_models_models_get" in allowed
    assert "get_registry_snapshot_registry_get" in allowed
    assert "list_jobs_optimizations_get" in allowed
    assert "cancel_job_optimizations" in allowed
    assert "rename_job_optimizations" in allowed


def test_yolo_never_gates() -> None:
    """Yolo trust-mode never gates any tool."""
    for name in ("delete_job_optimizations", "submit_job_run_post", "rename_job_optimizations"):
        assert _needs_approval(name, "yolo") is False


def test_ask_gates_every_mutation() -> None:
    """Ask trust-mode gates every mutating tool."""
    assert _needs_approval("delete_job_optimizations", "ask") is True
    assert _needs_approval("rename_job_optimizations", "ask") is True
    assert _needs_approval("submit_job_run_post", "ask") is True


def test_auto_safe_gates_only_destructive() -> None:
    """Auto-safe gates only destructive operations."""
    assert _needs_approval("rename_job_optimizations", "auto_safe") is False
    assert _needs_approval("create_template_templates_post", "auto_safe") is False
    assert _needs_approval("delete_job_optimizations", "auto_safe") is True
    assert _needs_approval("submit_job_run_post", "auto_safe") is True


def _make_fake_tool(name: str, return_value: str = "ok") -> dspy.Tool:
    """Build a ``dspy.Tool`` whose async ``func`` returns the given value."""
    async def func(**kwargs):
        return return_value

    return dspy.Tool(func=func, name=name, desc="test tool", args={}, arg_types={}, arg_desc={})


@pytest.mark.asyncio
async def test_wrap_bypasses_when_no_approval_needed() -> None:
    """Wrapped tool runs straight through when no approval is needed."""
    events: list[dict] = []
    registry = ApprovalRegistry()
    tool = _wrap_tool_with_approval(
        _make_fake_tool("rename_job_optimizations", return_value="renamed"),
        trust_mode="auto_safe",
        registry=registry,
        emit=events.append,
    )
    result = await tool.func()
    assert result == "renamed"
    event_names = [e["event"] for e in events]
    assert "pending_approval" not in event_names
    assert event_names == ["tool_start", "tool_end"]


@pytest.mark.asyncio
async def test_wrap_emits_pending_and_runs_on_approve() -> None:
    """Wrapped tool emits ``pending_approval`` and runs once approved."""
    events: list[dict] = []
    registry = ApprovalRegistry()
    tool = _wrap_tool_with_approval(
        _make_fake_tool("delete_job_optimizations", return_value="deleted"),
        trust_mode="ask",
        registry=registry,
        emit=events.append,
    )
    call_task = asyncio.create_task(tool.func())
    for _ in range(20):
        await asyncio.sleep(0)
        if any(e["event"] == "pending_approval" for e in events):
            break
    pending = next((e for e in events if e["event"] == "pending_approval"), None)
    assert pending is not None
    call_id = pending["data"]["id"]
    assert registry.resolve(call_id, True) is True
    result = await call_task
    assert result == "deleted"
    resolved = next((e for e in events if e["event"] == "approval_resolved"), None)
    assert resolved is not None
    assert resolved["data"]["approved"] is True


@pytest.mark.asyncio
async def test_denial_returns_observation_not_exception() -> None:
    """A denied approval surfaces a string observation instead of raising."""
    events: list[dict] = []
    registry = ApprovalRegistry()
    tool = _wrap_tool_with_approval(
        _make_fake_tool("submit_job_run_post", return_value="should not run"),
        trust_mode="ask",
        registry=registry,
        emit=events.append,
    )
    call_task = asyncio.create_task(tool.func())
    for _ in range(20):
        await asyncio.sleep(0)
        if events:
            break
    call_id = events[0]["data"]["id"]
    registry.resolve(call_id, False)
    result = await call_task
    assert result == "User declined"


def test_registry_resolve_unknown_returns_false() -> None:
    """Resolving an unknown call id returns ``False``."""
    registry = ApprovalRegistry()
    assert registry.resolve("does-not-exist", True) is False
