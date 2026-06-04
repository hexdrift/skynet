"""End-to-end integration + parity for the react on-ramp (§14).

Exercises the whole generalist loop in-process, starting from the exporter's
canonical row schema and ending at a served ``dspy.ReActV2``:

  exporter rows → ``DspyService.validate_payload`` → ``DspyService.run`` →
  ``ProgramArtifact`` (react overlay) → ``_materialize_react_program``.

DETERMINISM — REAL vs STUBBED
=============================

No network or live model is touched. Two complementary paths cover the loop:

- **Full ``DspyService.run`` wiring (stubbed optimizer).** A real
  ``gepa.optimize`` run is impractical as a unit test: GEPA's reflective
  proposer expects instruction-proposal output fields that a tool-call
  ``DummyLM`` cannot satisfy, and its valset/reflection call interleaving
  makes a flat ``DummyLM`` answer list non-deterministic. So the
  ``test_full_loop_*`` tests MONKEYPATCH ``run_react.run_react_optimization``
  to return a realistic envelope and ``run_react.resolve_react_tools`` to a
  canned roster (no live MCP). Everything else on the ``run`` path is REAL:
  payload validation, the exporter rows, ``rows_to_examples`` +
  ``build_replay_examples``, reward-preset resolution, artifact persistence
  (``program.save``), and the typed ``RunResponse`` assembly.

- **Adapter scoring + §14 parity (REAL).** ``test_adapter_evaluate_*`` and
  ``test_parity_*`` run ``TrainingGroundDspyAdapter.evaluate`` for real over a
  seed ``ReActV2``, driven by a deterministic tool-call ``DummyLM`` that emits
  the recorded ``alpha(x=1)`` call so the trace-conditioned mock scores a hit
  exactly as production would. The parity test then re-scores the SAME
  captured rollout via the CLI scalarizer
  (``scalar_with_hard_caps(vector_reward(example, rollout))``) and asserts it
  equals the adapter's score — guarding the refactor end to end.

The serve step (``test_serve_*``) is fully REAL apart from re-sourcing the
tool roster (no live MCP): it persists a real program, attaches the overlay,
and round-trips it through ``_materialize_react_program``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import dspy
import pytest
from dspy.utils import DummyLM

from core.api.errors import DomainError
from core.api.routers import _helpers
from core.constants import PAYLOAD_OVERVIEW_SIGNATURE_CODE
from core.models import ColumnMapping, ModelConfig, RunRequest, SplitFractions
from core.models.artifacts import ProgramArtifact, ReactOverlay
from core.models.results import RunResponse
from core.models.submissions import ReplayMapping, Reward, ToolSource
from core.registry import ServiceRegistry
from core.service_gateway.optimization.artifacts import persist_program
from core.service_gateway.optimization.core import DspyService
from core.service_gateway.optimization.training_ground import exporter, run_react
from core.service_gateway.optimization.training_ground.gepa_adapter import (
    TrainingGroundDspyAdapter,
    seed_candidate_from_program,
)
from core.service_gateway.optimization.training_ground.metrics import (
    GENERALIST_REWARD_SPEC,
    scalar_with_hard_caps,
    vector_reward,
)
from core.service_gateway.optimization.training_ground.registry import hash_tool_schema
from core.service_gateway.optimization.training_ground.types import (
    EvaluationExample,
    PairedBootstrapResult,
    ReplayStep,
)

# Generalist three-key input + assistant output, matching
# ``GENERALIST_COLUMN_MAPPING`` so the exporter rows feed the signature 1:1.
_SIGNATURE_CODE = """\
import dspy


class GeneralistTurn(dspy.Signature):
    user_message: str = dspy.InputField()
    wizard_state: str = dspy.InputField()
    chat_history: str = dspy.InputField()
    assistant_message: str = dspy.OutputField()
"""

_RECORDED_ARGS = {"x": 1}
"""The single recorded tool-call argument all synthetic turns share, so a
``DummyLM`` that always emits ``alpha(x=1)`` deterministically hits the mock."""


class _Sig(dspy.Signature):
    """In-process twin of ``_SIGNATURE_CODE`` for the adapter/parity tests."""

    user_message: str = dspy.InputField()
    wizard_state: str = dspy.InputField()
    chat_history: str = dspy.InputField()
    assistant_message: str = dspy.OutputField()


def _alpha(x: int) -> dict[str, Any]:
    """Canned tool body — never invoked (rollouts route through the mock)."""
    return {"ok": x}


def _alpha_tool(*, arg_type: str = "integer") -> dspy.Tool:
    """Build the canned ``alpha`` tool the recorded roster references.

    Args:
        arg_type: JSON-schema type for ``x``; ``"string"`` forges a schema
            different from the recorded snapshot to drive the drift path.

    Returns:
        A ``dspy.Tool`` named ``alpha`` with a single typed ``x`` argument.
    """
    return dspy.Tool(_alpha, name="alpha", desc="alpha tool", args={"x": {"type": arg_type}})


def _recorded_step() -> ReplayStep:
    """Build the single recorded ``alpha`` step the synthetic turns replay."""
    return ReplayStep(
        tool_name="alpha",
        arguments=dict(_RECORDED_ARGS),
        argument_hash=run_react.adapt_agent_tool_calls_v1_to_replay(
            [{"tool": "alpha", "status": "done", "payload": {"arguments": _RECORDED_ARGS}}],
            turn_id="seed",
        )[0].argument_hash,
        status="done",
        result={"ok": 1},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def _raw_agent_row(row_id: int, schema_hashes: dict[str, str]) -> SimpleNamespace:
    """Build one synthetic raw ``agent_messages`` row for the exporter.

    Mirrors the columns ``_fetch_assistant_rows`` selects, carrying a single
    recorded ``alpha`` tool call plus the per-turn wizard-state snapshots.

    Args:
        row_id: Stable id used as the turn identifier.
        schema_hashes: ``{tool: hash}`` snapshot recorded for the turn.

    Returns:
        A ``SimpleNamespace`` shaped like a ``_fetch_assistant_rows`` result.
    """
    return SimpleNamespace(
        id=row_id,
        conversation_id=f"conv-{row_id}",
        content="ok",
        tool_calls=[
            {
                "tool": "alpha",
                "reason": "first",
                "status": "done",
                "startedAt": 100,
                "endedAt": 200,
                "payload": {"arguments": dict(_RECORDED_ARGS), "result": {"ok": 1}},
            }
        ],
        model="gpt-x",
        wizard_state_before={"dataset_ready": True},
        wizard_state_after={"dataset_ready": True, "submitted": True},
        allowed_tools=["alpha"],
        tool_schema_hashes=dict(schema_hashes),
        chat_history=[{"role": "user", "content": "hi"}],
        user_message="do it",
    )


def _exporter_dataset(schema_hashes: dict[str, str], *, turns: int = 4) -> list[dict[str, Any]]:
    """Produce a small trajectory dataset via the REAL exporter on-ramp.

    Patches ``_fetch_assistant_rows`` so ``export_agent_messages_to_rows``
    transforms synthetic raw rows into the canonical §5 replay-row schema
    without touching Postgres — the same rows a caller would POST to
    ``/datasets/stage-for-agent`` then run with ``module_name="react"``.

    Args:
        schema_hashes: ``{tool: hash}`` snapshot stamped onto each turn.
        turns: Number of recorded turns to synthesize.

    Returns:
        Canonical export rows, one per turn.
    """
    raw_rows = [_raw_agent_row(i, schema_hashes) for i in range(turns)]
    with patch.object(exporter, "_fetch_assistant_rows", lambda *a, **k: raw_rows):
        return exporter.export_agent_messages_to_rows(object(), window="14d")


def _react_payload(dataset: list[dict[str, Any]]) -> RunRequest:
    """Assemble a react ``RunRequest`` over exporter rows + generalist mappings."""
    return RunRequest(
        username="tester",
        module_name="react",
        signature_code=_SIGNATURE_CODE,
        metric_code="def metric(example, rollout):\n    return 1.0\n",
        optimizer_name="gepa",
        dataset=dataset,
        column_mapping=ColumnMapping(**exporter.GENERALIST_COLUMN_MAPPING),
        split_fractions=SplitFractions(train=0.5, val=0.25, test=0.25),
        model_config=ModelConfig(name="openai/gpt-4o-mini"),
        tool_source=ToolSource(kind="live_mcp", mcp_url="http://localhost:9000/mcp"),
        replay_mapping=ReplayMapping(**exporter.GENERALIST_REPLAY_MAPPING),
        reward=Reward(match_mode="tool_name"),
        shuffle=False,
        seed=0,
    )


def _example(turn_id: str) -> EvaluationExample:
    """Build a replay example with one recorded ``alpha`` step (adapter tests)."""
    return EvaluationExample(
        turn_id=turn_id,
        user_message="do it",
        wizard_state_before={"dataset_ready": True},
        wizard_state_after={"dataset_ready": True, "submitted": True},
        allowed_tools=frozenset({"alpha"}),
        tool_schema_hashes={"alpha": "h"},
        replay_steps=(_recorded_step(),),
        chat_history=(),
        signature_inputs={"user_message": "do it"},
    )


def _replaying_dummy_lm() -> DummyLM:
    """Build a ``DummyLM`` that drives ReActV2 to call ``alpha(x=1)`` then submit.

    The answer list is sized for many turns (each rollout consumes two
    entries: one tool-call step, one submit step), so a batch of examples
    replays deterministically.
    """
    return DummyLM(
        [
            {
                "next_thought": "call alpha",
                "tool_calls": '{"tool_calls": [{"name": "alpha", "args": {"x": 1}}]}',
            },
            {
                "next_thought": "submit",
                "tool_calls": '{"tool_calls": [{"name": "submit", "args": {"assistant_message": "done"}}]}',
            },
        ]
        * 50
    )


def _realistic_envelope(schema_hashes: dict[str, str], tools: list[dspy.Tool]):
    """Return a ``run_react_optimization`` stand-in that emits a real envelope.

    Builds a genuine ``ReActV2`` state dict (so ``persist_program`` writes real
    state JSON) and fills the typed §11 acceptance fields, mirroring the shape
    ``run_react_optimization`` returns. Used to keep the full-loop test
    deterministic without a live ``gepa.optimize`` run.

    Args:
        schema_hashes: Snapshot carried onto the overlay (kept 1:1 with tools).
        tools: The canned roster the seed program is built over.

    Returns:
        A callable matching ``run_react_optimization``'s keyword signature.
    """

    def _fake(*, signature_cls, tools, schema_hashes, max_iters=run_react.DEFAULT_MAX_ITERS, **_kwargs):
        seed = dspy.ReActV2(signature_cls, tools=tools, max_iters=max_iters)
        return {
            "program_state": seed.dump_state(),
            "baseline_objective_scores": {"tool_selection": 0.4},
            "optimized_objective_scores": {"tool_selection": 0.8},
            "baseline_objective_per_example": [{"tool_selection": 0.4}],
            "optimized_objective_per_example": [{"tool_selection": 0.8}],
            "baseline_scalar": 0.4,
            "optimized_scalar": 0.8,
            "baseline_scalars_per_example": [0.4],
            "optimized_scalars_per_example": [0.8],
            "paired_bootstrap": PairedBootstrapResult(
                resamples=10, mean_delta=0.4, ci95_lower=0.2, ci95_upper=0.6
            ),
            "promotion": {
                "promotable": False,
                "reasons": ["held-out scale: 1 < 200 required by §11"],
            },
            "tool_overlay": {
                "tool_descriptions": {"alpha": "optimized alpha"},
                "tool_arg_descriptions": {"alpha": {"x": "the x argument"}},
                "tool_schema_hashes": schema_hashes,
                "max_iters": max_iters,
            },
        }

    return _fake


def test_full_loop_validate_then_run_returns_typed_envelope() -> None:
    """The exporter→validate→run loop yields a typed ``RunResponse`` + overlay.

    REAL: exporter rows, ``validate_payload``, dataset→examples conversion,
    artifact persistence, and the typed-envelope assembly. STUBBED:
    ``resolve_react_tools`` (canned roster, no MCP) and
    ``run_react_optimization`` (realistic envelope, no ``gepa.optimize``).
    """
    tool = _alpha_tool()
    hashes = {"alpha": hash_tool_schema(tool)}
    dataset = _exporter_dataset(hashes)
    payload = _react_payload(dataset)
    service = DspyService(registry=ServiceRegistry())

    service.validate_payload(payload)

    with (
        patch(
            "core.service_gateway.optimization.core.build_language_model",
            return_value=DummyLM([{"assistant_message": "x"}]),
        ),
        patch.object(run_react, "resolve_react_tools", return_value=([tool], dict(hashes))),
        patch.object(
            run_react,
            "run_react_optimization",
            side_effect=_realistic_envelope(hashes, [tool]),
        ),
    ):
        result = service.run(payload)

    assert isinstance(result, RunResponse)
    assert result.module_name == "react"
    assert result.objective_scores == {"tool_selection": 0.8}
    assert result.paired_bootstrap is not None
    assert result.paired_bootstrap.mean_delta == pytest.approx(0.4)
    assert result.promotion is not None
    assert result.promotion.promotable is False
    assert result.promotion.reasons == ["held-out scale: 1 < 200 required by §11"]
    assert result.baseline_test_metric == pytest.approx(0.4)
    assert result.optimized_test_metric == pytest.approx(0.8)


def test_full_loop_artifact_carries_react_overlay_and_state() -> None:
    """The persisted ``ProgramArtifact`` carries real state JSON + the overlay.

    The overlay's schema-hash snapshot stays 1:1 with the resolved roster, and
    ``program_state_json`` holds the genuine ``ReActV2`` state dump.
    """
    tool = _alpha_tool()
    hashes = {"alpha": hash_tool_schema(tool)}
    dataset = _exporter_dataset(hashes)
    payload = _react_payload(dataset)
    service = DspyService(registry=ServiceRegistry())
    service.validate_payload(payload)

    with (
        patch(
            "core.service_gateway.optimization.core.build_language_model",
            return_value=DummyLM([{"assistant_message": "x"}]),
        ),
        patch.object(run_react, "resolve_react_tools", return_value=([tool], dict(hashes))),
        patch.object(
            run_react,
            "run_react_optimization",
            side_effect=_realistic_envelope(hashes, [tool]),
        ),
    ):
        result = service.run(payload)

    artifact = result.program_artifact
    assert artifact is not None
    overlay = artifact.react_overlay
    assert isinstance(overlay, ReactOverlay)
    assert overlay.tool_schema_hashes == hashes
    assert overlay.tool_descriptions == {"alpha": "optimized alpha"}
    assert overlay.max_iters == run_react.DEFAULT_MAX_ITERS
    assert "react" in artifact.program_state_json


def test_serve_materializes_react_program_with_overlay() -> None:
    """``_materialize_react_program`` rebuilds a ``ReActV2`` from artifact + overlay.

    REAL apart from re-sourcing the roster: persists a genuine program, attaches
    the overlay, then round-trips it through serve to assert a live ``ReActV2``
    is reconstructed with the recorded ``max_iters``.
    """
    tool = _alpha_tool()
    hashes = {"alpha": hash_tool_schema(tool)}
    artifact = _persisted_react_artifact(hashes)
    overview = {PAYLOAD_OVERVIEW_SIGNATURE_CODE: _SIGNATURE_CODE}

    with patch.object(_helpers, "resolve_react_tools", return_value=([tool], dict(hashes))):
        program = _helpers._materialize_react_program(artifact, overview)

    assert isinstance(program, dspy.ReActV2)
    assert program.max_iters == run_react.DEFAULT_MAX_ITERS


def test_serve_tool_schema_drift_raises() -> None:
    """A live tool whose schema drifts from the snapshot raises a 409 ``DomainError``.

    Re-sourcing ``alpha`` with a ``string`` ``x`` (vs the recorded ``integer``)
    changes its schema hash, so ``_assert_tool_set_matches`` trips
    ``ToolSchemaDriftError``, surfaced as ``optimization.tool_schema_drift``.
    """
    recorded_hashes = {"alpha": hash_tool_schema(_alpha_tool())}
    artifact = _persisted_react_artifact(recorded_hashes)
    overview = {PAYLOAD_OVERVIEW_SIGNATURE_CODE: _SIGNATURE_CODE}
    drift_tool = _alpha_tool(arg_type="string")

    with (
        patch.object(
            _helpers,
            "resolve_react_tools",
            return_value=([drift_tool], {"alpha": hash_tool_schema(drift_tool)}),
        ),
        pytest.raises(DomainError) as excinfo,
    ):
        _helpers._materialize_react_program(artifact, overview)

    assert excinfo.value.code == "optimization.tool_schema_drift"
    assert excinfo.value.status_code == 409


def _persisted_react_artifact(schema_hashes: dict[str, str]) -> ProgramArtifact:
    """Persist a real ``ReActV2`` and attach a ``live_mcp`` react overlay.

    Args:
        schema_hashes: ``{tool: hash}`` snapshot recorded onto the overlay.

    Returns:
        A ``ProgramArtifact`` with real ``program_state_json`` and a
        ``react_overlay`` whose ``tool_source`` re-sources via ``live_mcp``.
    """
    program = dspy.ReActV2(_Sig, tools=[_alpha_tool()], max_iters=run_react.DEFAULT_MAX_ITERS)
    artifact = persist_program(program, "react-e2e")
    assert artifact is not None
    artifact.react_overlay = ReactOverlay(
        tool_descriptions={"alpha": "optimized alpha"},
        tool_arg_descriptions={"alpha": {"x": "the x argument"}},
        tool_schema_hashes=dict(schema_hashes),
        max_iters=run_react.DEFAULT_MAX_ITERS,
        tool_source={
            "kind": "live_mcp",
            "grounding_weight": 0.0,
            "reward_preset": "general",
        },
    )
    return artifact


def test_adapter_evaluate_scores_real_seed_rollout() -> None:
    """The adapter scores a REAL ReActV2 rollout driven by the replay ``DummyLM``.

    Each example's recorded ``alpha(x=1)`` is reproduced by the stub LM, so the
    trace-conditioned mock records a hit and the generalist vector reward scores
    for real — no network, no monkeypatch of the rollout.
    """
    seed = dspy.ReActV2(_Sig, tools=[_alpha_tool()], max_iters=4)
    dummy = _replaying_dummy_lm()
    adapter = TrainingGroundDspyAdapter(
        seed_program=seed,
        student_lm=dummy,
        reflection_lm=dummy,
        include_task_reward=True,
        grounding_weight=0.0,
        template=None,
        scorer=None,
        reward_spec=GENERALIST_REWARD_SPEC,
        vector_fn=vector_reward,
    )
    candidate = seed_candidate_from_program(seed)
    examples = [_example("t1"), _example("t2")]

    with dspy.context(lm=dummy):
        batch = adapter.evaluate(examples, candidate, capture_traces=True)

    assert len(batch.scores) == 2
    for objectives in batch.objective_scores:
        # A real hit on the recorded ``alpha`` step lands tool-success at 1.0.
        assert objectives["tool_success_rate"] == pytest.approx(1.0)
        assert "submit_clean" in objectives


def test_parity_adapter_score_equals_cli_scalarizer() -> None:
    """§14 parity: the adapter score equals the CLI scalarizer on the SAME rollout.

    Re-scoring the adapter's captured rollout with
    ``scalar_with_hard_caps(vector_reward(example, rollout))`` (the generalist
    preset, the CLI path) must reproduce the adapter's score bit-for-bit —
    proving the harness refactor preserves the CLI scalars.
    """
    seed = dspy.ReActV2(_Sig, tools=[_alpha_tool()], max_iters=4)
    dummy = _replaying_dummy_lm()
    adapter = TrainingGroundDspyAdapter(
        seed_program=seed,
        student_lm=dummy,
        reflection_lm=dummy,
        include_task_reward=True,
        grounding_weight=0.0,
        template=None,
        scorer=None,
        reward_spec=GENERALIST_REWARD_SPEC,
        vector_fn=vector_reward,
    )
    candidate = seed_candidate_from_program(seed)
    examples = [_example("t1"), _example("t2")]

    with dspy.context(lm=dummy):
        batch = adapter.evaluate(examples, candidate, capture_traces=True)

    assert batch.trajectories is not None
    for idx, trajectory in enumerate(batch.trajectories):
        assert trajectory is not None
        cli_scalar = scalar_with_hard_caps(
            vector_reward(trajectory["example"], trajectory["rollout"]),
            GENERALIST_REWARD_SPEC,
        )
        assert batch.scores[idx] == pytest.approx(cli_scalar)
