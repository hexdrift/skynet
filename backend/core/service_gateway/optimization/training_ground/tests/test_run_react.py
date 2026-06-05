"""Unit tests for the pure pieces of the react /run core.

Covers the two building blocks that need no live model or ``gepa.optimize``:
``build_replay_examples`` (row → :class:`EvaluationExample` conversion) and the
``dataset_snapshot`` branch of ``resolve_react_tools`` (roster rebuild from the
reserved sidecar), plus the ``gepa.optimize`` call contract of
``run_react_optimization`` verified with that call stubbed (no live model). The
full model-driven path is exercised by the gateway integration suite.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import dspy
import pytest

from core.config import settings
from core.models.submissions import ReplayMapping, ToolSource
from core.service_gateway.optimization.timing import (
    STAGE_BASELINE,
    STAGE_EVALUATION,
    STAGE_TRAINING,
    GenLMTimingCallback,
)
from core.service_gateway.optimization.training_ground import run_react as run_react_mod
from core.service_gateway.optimization.training_ground.registry import hash_tool_schema
from core.service_gateway.optimization.core import _tool_to_snapshot_spec
from core.service_gateway.optimization.training_ground.optimize import (
    _severity_from_annotations,
    set_tool_severity,
    tool_severity,
)
from core.service_gateway.optimization.training_ground.run_react import (
    _JobLogGepaLogger,
    build_replay_examples,
    resolve_react_tools,
    run_react_optimization,
)


def _example_with_columns(**columns: object) -> dspy.Example:
    """Build a ``dspy.Example`` with one signature input plus replay columns.

    The replay-role columns are attached as plain attributes (mirroring
    ``rows_to_examples(..., extra_columns=...)``) so they stay out of
    ``example.inputs()``.
    """
    example = dspy.Example(question="what is the weather?").with_inputs("question")
    for name, value in columns.items():
        setattr(example, name, value)
    return example


def test_build_replay_examples_converts_v1_steps() -> None:
    """A synthetic v1 row becomes an EvaluationExample with replay fields set."""
    steps = [
        {
            "tool": "search",
            "status": "done",
            "payload": {"arguments": {"q": "weather"}, "result": {"hits": 3}},
        },
        {"tool": "submit", "status": "done", "payload": {}},
        {"tool": "pending", "status": "running", "payload": {}},
    ]
    example = _example_with_columns(
        turn_id="turn-7",
        steps_col=steps,
        allowed_col=["search", "submit", "lookup"],
        hashes_col={"search": "abc123", "lookup": "def456"},
        before_col={"phase": "start"},
        after_col={"phase": "done"},
        chat_col=[{"role": "user", "content": "hi"}, "not-a-mapping"],
    )
    mapping = ReplayMapping(
        steps="steps_col",
        allowed_tools="allowed_col",
        tool_schema_hashes="hashes_col",
        state_before="before_col",
        state_after="after_col",
        chat_history="chat_col",
    )

    result = build_replay_examples([example], mapping)

    assert len(result) == 1
    ev = result[0]
    assert ev.turn_id == "turn-7"
    assert ev.signature_inputs == {"question": "what is the weather?"}
    assert ev.user_message == ""
    assert [step.tool_name for step in ev.replay_steps] == ["search"]
    assert ev.replay_steps[0].result == {"hits": 3}
    assert isinstance(ev.allowed_tools, frozenset)
    assert ev.allowed_tools == frozenset({"search", "lookup"})
    assert "submit" not in ev.allowed_tools
    assert ev.tool_schema_hashes == {"search": "abc123", "lookup": "def456"}
    assert ev.wizard_state_before == {"phase": "start"}
    assert ev.wizard_state_after == {"phase": "done"}
    assert ev.chat_history == ({"role": "user", "content": "hi"},)


def test_build_replay_examples_tolerates_json_string_cells() -> None:
    """CSV-style JSON-string cells parse the same as native objects."""
    example = _example_with_columns(
        steps_col='[{"tool": "search", "status": "done", "payload": {"arguments": {}, "result": 1}}]',
        allowed_col='["search"]',
        hashes_col='{"search": "h"}',
    )
    mapping = ReplayMapping(
        steps="steps_col",
        allowed_tools="allowed_col",
        tool_schema_hashes="hashes_col",
        state_before="before_col",
        state_after="after_col",
    )

    ev = build_replay_examples([example], mapping)[0]

    assert [step.tool_name for step in ev.replay_steps] == ["search"]
    assert ev.allowed_tools == frozenset({"search"})
    assert ev.tool_schema_hashes == {"search": "h"}
    assert ev.wizard_state_before == {}
    assert ev.chat_history == ()


def test_build_replay_examples_drops_errored_steps() -> None:
    """Errored recorded calls are bad ground truth, so they are dropped here."""
    steps = [
        {
            "tool": "search",
            "status": "done",
            "payload": {"arguments": {"q": "x"}, "result": {"hits": 1}},
        },
        {
            "tool": "lookup",
            "status": "error",
            "payload": {"arguments": {"id": 9}, "result": "boom"},
        },
    ]
    example = _example_with_columns(
        steps_col=steps,
        allowed_col=["search", "lookup"],
        hashes_col={"search": "h"},
    )
    mapping = ReplayMapping(
        steps="steps_col",
        allowed_tools="allowed_col",
        tool_schema_hashes="hashes_col",
        state_before="before_col",
        state_after="after_col",
    )

    ev = build_replay_examples([example], mapping)[0]

    assert [step.tool_name for step in ev.replay_steps] == ["search"]
    assert all(step.status == "done" for step in ev.replay_steps)


def test_resolve_react_tools_dataset_snapshot_rebuilds_roster() -> None:
    """A dataset snapshot sidecar rebuilds a dspy.Tool roster + schema hashes."""
    snapshot = [
        {
            "name": "search",
            "description": "Search the web.",
            "args": {"q": {"type": "string", "description": "query"}},
        },
        {"name": "lookup", "description": "Look up an id.", "args": {}},
        {"name": "submit", "description": "reserved", "args": {}},
    ]
    dataset = [
        {"question": "x", "__tool_snapshot__": snapshot},
        {"question": "y"},
    ]
    tool_source = ToolSource(kind="dataset_snapshot")

    tools, hashes = resolve_react_tools(
        tool_source, signature_cls=object, settings=settings, dataset=dataset
    )

    names = [tool.name for tool in tools]
    assert names == ["search", "lookup"]
    assert "submit" not in names
    search_tool = next(tool for tool in tools if tool.name == "search")
    assert search_tool.desc == "Search the web."
    assert set(hashes) == {"search", "lookup"}
    assert hashes["search"] == hash_tool_schema(search_tool)


def test_severity_from_annotations_maps_mcp_hints() -> None:
    """MCP annotation hints map to the three approval tiers, else ``None``."""
    read_only = SimpleNamespace(readOnlyHint=True, destructiveHint=None)
    destructive = SimpleNamespace(readOnlyHint=False, destructiveHint=True)
    mutating = SimpleNamespace(readOnlyHint=False, destructiveHint=False)
    open_world = SimpleNamespace(readOnlyHint=None, destructiveHint=None)

    assert _severity_from_annotations(read_only) == "info"
    assert _severity_from_annotations(destructive) == "destructive"
    assert _severity_from_annotations(mutating) == "warning"
    assert _severity_from_annotations(open_world) is None
    assert _severity_from_annotations(None) is None


def test_tool_to_snapshot_spec_serializes_severity() -> None:
    """A tool's stashed severity is serialized into its spec; omitted when unset."""

    def _noop(**_kwargs: object) -> None:
        """Placeholder body for a snapshot tool."""

    _noop.__name__ = "wipe"
    marked = dspy.Tool(_noop, name="wipe", desc="Delete it.", args=None)
    set_tool_severity(marked, "destructive")
    unmarked = dspy.Tool(_noop, name="peek", desc="Read it.", args=None)

    assert _tool_to_snapshot_spec(marked)["severity"] == "destructive"
    assert "severity" not in _tool_to_snapshot_spec(unmarked)


def test_resolve_react_tools_dataset_snapshot_carries_severity() -> None:
    """A snapshot spec's ``severity`` round-trips onto the rebuilt tool."""
    snapshot = [
        {"name": "wipe", "description": "Delete it.", "args": {}, "severity": "destructive"},
        {"name": "peek", "description": "Read it.", "args": {}},
    ]
    dataset = [{"__tool_snapshot__": snapshot}]
    tool_source = ToolSource(kind="dataset_snapshot")

    tools, _ = resolve_react_tools(
        tool_source, signature_cls=object, settings=settings, dataset=dataset
    )

    by_name = {tool.name: tool for tool in tools}
    assert tool_severity(by_name["wipe"]) == "destructive"
    assert tool_severity(by_name["peek"]) is None


def test_resolve_react_tools_dataset_snapshot_honours_tool_filter() -> None:
    """``tool_filter`` keeps and reorders the snapshot roster."""
    snapshot = [
        {"name": "alpha", "description": "a", "args": {}},
        {"name": "beta", "description": "b", "args": {}},
        {"name": "gamma", "description": "c", "args": {}},
    ]
    dataset = [{"__tool_snapshot__": snapshot}]
    tool_source = ToolSource(kind="dataset_snapshot", tool_filter=["gamma", "alpha"])

    tools, _ = resolve_react_tools(
        tool_source, signature_cls=object, settings=settings, dataset=dataset
    )

    assert [tool.name for tool in tools] == ["gamma", "alpha"]


def test_resolve_react_tools_dataset_snapshot_without_sidecar_raises() -> None:
    """A dataset_snapshot source with no sidecar is a hard error."""
    tool_source = ToolSource(kind="dataset_snapshot")
    with pytest.raises(ValueError, match="carried no tools"):
        resolve_react_tools(
            tool_source, signature_cls=object, settings=settings, dataset=[{"q": "x"}]
        )


def test_resolve_react_tools_unknown_kind_raises() -> None:
    """An unrecognised tool_source kind fails fast."""
    bad_source = SimpleNamespace(kind="carrier_pigeon", tool_filter=None)
    with pytest.raises(ValueError, match=r"Unknown tool_source\.kind"):
        resolve_react_tools(bad_source, signature_cls=object, settings=settings)


def test_resolve_react_tools_accepts_persisted_dict_snapshot() -> None:
    """A persisted dict tool_source (serve path) rebuilds the roster without a dataset."""
    persisted = {
        "kind": "dataset_snapshot",
        "tool_filter": ["search"],
        "tool_snapshot": [
            {
                "name": "search",
                "description": "Search the web.",
                "args": {"q": {"type": "string"}},
            },
            {"name": "lookup", "description": "Look up an id.", "args": {}},
        ],
    }

    tools, hashes = resolve_react_tools(
        persisted, signature_cls=object, settings=settings, dataset=None
    )

    assert [tool.name for tool in tools] == ["search"]
    assert set(hashes) == {"search"}
    assert hashes["search"] == hash_tool_schema(tools[0])


class _StopAfterOptimize(Exception):
    """Sentinel raised by the gepa.optimize spy to halt before the scoring tail."""


@contextmanager
def _noop_cm(*_args: object, **_kwargs: object):
    """Stand in for the react trajectory recorders as a do-nothing context manager.

    Yields:
        Control, so the ``with`` block runs without touching a real adapter.
    """
    yield


def test_job_log_gepa_logger_routes_to_logging(caplog: pytest.LogCaptureFixture) -> None:
    """``_JobLogGepaLogger.log`` forwards a GEPA line to its sink at INFO level."""
    sink = logging.getLogger("test.gepa.sink")
    line = "Iteration 3: Valset score for new program: 0.42"
    with caplog.at_level(logging.INFO, logger="test.gepa.sink"):
        _JobLogGepaLogger(sink).log(line)
    assert line in caplog.text


def test_run_react_optimization_passes_progress_bar_and_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``run_react_optimization`` wires ``display_progress_bar`` + a logging bridge into gepa.optimize.

    Guards the regression where react runs emitted no ``optimizer_progress`` (so
    the tqdm bar stayed empty) and no GEPA ``Iteration N`` lines into job_logs
    (so the score chart stayed empty) because both ``gepa.optimize`` arguments
    were omitted. The optimize call is stubbed, so no live model runs.
    """
    captured: dict[str, object] = {}

    def _spy_optimize(**kwargs: object) -> None:
        """Record the optimize kwargs, then abort before the scoring tail."""
        captured.update(kwargs)
        raise _StopAfterOptimize

    monkeypatch.setattr(run_react_mod.dspy, "ReActV2", lambda *a, **k: MagicMock())
    monkeypatch.setattr(run_react_mod, "seed_candidate_from_program", lambda program: {"seed": True})
    monkeypatch.setattr(run_react_mod, "TrainingGroundDspyAdapter", lambda **k: MagicMock())
    monkeypatch.setattr(
        run_react_mod, "_evaluate_candidate_on_examples", lambda **k: ([1.0], [{}], 1.0, [None])
    )
    monkeypatch.setattr(run_react_mod, "react_valset_outputs", _noop_cm)
    monkeypatch.setattr(run_react_mod, "react_minibatch_feedback", _noop_cm)
    monkeypatch.setattr(run_react_mod.gepa, "optimize", _spy_optimize)

    with pytest.raises(_StopAfterOptimize):
        run_react_optimization(
            signature_cls=object,
            tools=[],
            schema_hashes={},
            reward_spec=MagicMock(),
            vector_fn=MagicMock(),
            grounding_weight=0.0,
            train=[],
            val=[],
            test=[],
            student_lm=MagicMock(),
            reflection_lm=MagicMock(),
        )

    assert captured["display_progress_bar"] is True
    wired_logger = captured["logger"]
    assert isinstance(wired_logger, _JobLogGepaLogger)
    # The sink must sit under core.service_gateway.optimization so the worker's
    # JobLogHandler (attached to that parent) captures GEPA's iteration lines.
    assert wired_logger._sink.name.startswith("core.service_gateway.optimization")


def test_run_react_optimization_buckets_lm_activity_per_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Student rollouts are attributed to the baseline/training/evaluation stages.

    Guards the regression where react runs left the LM-activity panel empty:
    ``run_react_optimization`` ran its three model-call regions without a
    ``track_stage`` wrapper, so the per-stage buckets the panel reads stayed
    empty and the tab rendered "no activity". A real
    :class:`GenLMTimingCallback` is threaded in here and each stubbed region
    simulates one matched student call; the callback must then report exactly
    one call bucketed under each of the three stages.
    """
    student_lm = MagicMock()
    gen_timing = GenLMTimingCallback(student_lm)
    call_ids = iter(range(100))

    def _simulate_student_call() -> None:
        """Record one matched student-LM call against whichever stage is active."""
        call_id = f"call-{next(call_ids)}"
        gen_timing.on_lm_start(call_id, student_lm, {})
        gen_timing.on_lm_end(call_id, {})

    def _fake_eval(**_kwargs: object) -> tuple[list[float], list[dict], float, list[object]]:
        """Stand in for ``_evaluate_candidate_on_examples`` with one simulated call."""
        _simulate_student_call()
        return [1.0], [{}], 1.0, [None]

    def _fake_optimize(**_kwargs: object) -> MagicMock:
        """Stand in for ``gepa.optimize`` with one simulated training call."""
        _simulate_student_call()
        return MagicMock()

    monkeypatch.setattr(run_react_mod.dspy, "ReActV2", lambda *a, **k: MagicMock())
    monkeypatch.setattr(run_react_mod, "seed_candidate_from_program", lambda program: {"seed": True})
    monkeypatch.setattr(run_react_mod, "TrainingGroundDspyAdapter", lambda **k: MagicMock())
    monkeypatch.setattr(run_react_mod, "_evaluate_candidate_on_examples", _fake_eval)
    monkeypatch.setattr(run_react_mod, "react_valset_outputs", _noop_cm)
    monkeypatch.setattr(run_react_mod, "react_minibatch_feedback", _noop_cm)
    monkeypatch.setattr(run_react_mod.gepa, "optimize", _fake_optimize)
    monkeypatch.setattr(run_react_mod, "_best_candidate", lambda result: {"opt": True})
    monkeypatch.setattr(run_react_mod, "_program_state_from", lambda **k: {})
    monkeypatch.setattr(run_react_mod, "_bootstrap_or_empty", lambda **k: MagicMock())
    monkeypatch.setattr(
        run_react_mod,
        "_resolve_promotion",
        lambda **k: SimpleNamespace(promotable=True, reasons=[]),
    )
    monkeypatch.setattr(run_react_mod, "_candidate_tool_descriptions", lambda c: {})
    monkeypatch.setattr(run_react_mod, "_candidate_tool_arg_descriptions", lambda c: {})
    monkeypatch.setattr(run_react_mod, "_candidate_tool_names", lambda c: [])

    run_react_optimization(
        signature_cls=object,
        tools=[],
        schema_hashes={},
        reward_spec=MagicMock(),
        vector_fn=MagicMock(),
        grounding_weight=0.0,
        train=[],
        val=[],
        test=[],
        student_lm=student_lm,
        reflection_lm=MagicMock(),
        timing_callbacks=(gen_timing,),
    )

    stages = gen_timing.stage_summary()
    assert set(stages) == {STAGE_BASELINE, STAGE_TRAINING, STAGE_EVALUATION}
    assert all(calls == 1 for calls, _avg in stages.values())
