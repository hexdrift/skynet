"""Tests for the ECHO grounding GEPA adapter + its 1:1 message capture.

Covers the DSPy-message-shape glue that the pure ``grounding`` reward sits
behind: extracting observation spans from real ReActV2 messages, capturing
the final served call off ``lm.history``, and the parameterized ECHO
adapter's scoring (grounding-only and combined task+grounding presets). The
live template/scorer are faked here — their fidelity is validated against the
real model by the §6 probes, not in CI.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import dspy
import pytest

from core.service_gateway.optimization.training_ground import gepa_adapter, optimize
from core.service_gateway.optimization.training_ground.gepa_adapter import (
    GENERALIST_MODULE_KEY,
    TOOL_MODULE_KEY,
    TrainingGroundDspyAdapter,
    observation_texts_from_messages,
    seed_candidate_from_program,
)
from core.service_gateway.optimization.training_ground.grounding import (
    ScoredPrompt,
    as_unit_interval,
)
from core.service_gateway.optimization.training_ground.metrics import (
    GENERAL_REWARD_SPEC,
    general_vector_reward,
    scalar_with_hard_caps,
    vector_reward,
)
from core.service_gateway.optimization.training_ground.replay import (
    TraceConditionedMCPMock,
    canonical_argument_hash,
)
from core.service_gateway.optimization.training_ground.types import (
    EvaluationExample,
    ReplayStep,
)

_MARKER = "[[ ## tool_call_results ## ]]"


class _Sig(dspy.Signature):
    """Tiny signature so the adapter can instantiate a real ReActV2."""

    user_message: str = dspy.InputField()
    assistant_message: str = dspy.OutputField()


class _CharScorer:
    """One token per char, logprob(i) = -((i % 5) + 1), offsets = indices."""

    def __call__(self, prompt: str) -> ScoredPrompt:
        """Return a deterministic per-char scoring of ``prompt``."""
        return ScoredPrompt(
            tokens=tuple(prompt),
            logprobs=tuple(-((i % 5) + 1) for i in range(len(prompt))),
            offsets=tuple(range(len(prompt))),
        )


class _FixedTemplate:
    """Fake ``ChatTemplate`` returning a preset string regardless of input."""

    def __init__(self, text: str) -> None:
        self._text = text

    def render(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None
    ) -> str:
        """Return the preset rendered string."""
        _ = (messages, tools)
        return self._text


def _expected_mean(text: str, obs: str) -> float:
    """Mean of the fake scorer's logprobs over ``obs``'s char span in ``text``."""
    start = text.index(obs)
    return sum(-((i % 5) + 1) for i in range(start, start + len(obs))) / len(obs)


def _example(*, allowed: frozenset[str] = frozenset(), steps: tuple[ReplayStep, ...] = ()) -> EvaluationExample:
    """Build a minimal EvaluationExample for the adapter tests."""
    return EvaluationExample(
        turn_id="t-1",
        user_message="do it",
        wizard_state_before={},
        wizard_state_after={},
        allowed_tools=allowed,
        tool_schema_hashes={},
        replay_steps=steps,
        chat_history=(),
    )


def _step(tool: str) -> ReplayStep:
    """Build a hit-able ReplayStep."""
    return ReplayStep(
        tool_name=tool,
        arguments={},
        argument_hash=canonical_argument_hash({}),
        status="done",
        result={"ok": True},
        reason=None,
        started_at_ms=None,
        ended_at_ms=None,
    )


def _adapter(
    template: _FixedTemplate,
    scorer: _CharScorer,
    *,
    include_task_reward: bool = False,
    grounding_weight: float = 1.0,
) -> TrainingGroundDspyAdapter:
    """Construct the parameterized adapter over a tiny real seed program.

    Defaults to the grounding-only preset (task off, weight 1.0).
    """
    tool = dspy.Tool(func=lambda x: x, name="alpha", desc="d", args={"x": {"type": "integer"}})
    seed = dspy.ReActV2(_Sig, tools=[tool], max_iters=2)
    return TrainingGroundDspyAdapter(
        seed_program=seed,
        student_lm=SimpleNamespace(history=[]),
        reflection_lm=None,
        include_task_reward=include_task_reward,
        grounding_weight=grounding_weight,
        template=template,
        scorer=scorer,
    )


def test_observation_texts_extracts_results_in_order() -> None:
    """Each tool_call_results user message yields its post-marker text, in order."""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "[[ ## user_message ## ]]\nhi"},
        {"role": "assistant", "content": "[[ ## next_thought ## ]]\nthink"},
        {"role": "user", "content": f"{_MARKER}\nRESULT-A"},
        {"role": "assistant", "content": "more"},
        {"role": "user", "content": f"{_MARKER}\nRESULT-B"},
    ]
    assert observation_texts_from_messages(messages) == ["RESULT-A", "RESULT-B"]


def test_observation_texts_ignores_plain_input_user_messages() -> None:
    """A user message without the tool_call_results marker is not an observation."""
    messages = [{"role": "user", "content": "[[ ## user_message ## ]]\njust input"}]
    assert observation_texts_from_messages(messages) == []


def test_observation_texts_skips_non_string_content() -> None:
    """Multimodal (list) content is skipped, not crashed on."""
    messages = [{"role": "user", "content": [{"type": "image"}]}]
    assert observation_texts_from_messages(messages) == []


def test_observation_texts_empty_for_no_messages() -> None:
    """No messages → no observations."""
    assert observation_texts_from_messages([]) == []


def test_capture_returns_last_calls_messages(monkeypatch) -> None:
    """A new LM call is detected by uuid and its messages + tools are returned."""
    lm = SimpleNamespace(history=[{"messages": [], "kwargs": {}, "uuid": "old"}])
    final_messages = [{"role": "user", "content": f"{_MARKER}\nR"}]

    def _fake_run(*, program, example, lm):
        lm.history.append(
            {"messages": final_messages, "kwargs": {"tools": None}, "uuid": "new"}
        )
        return dspy.Prediction(assistant_message="x")

    monkeypatch.setattr(gepa_adapter, "_run_candidate", _fake_run)
    pred, messages, tools = gepa_adapter._run_candidate_and_capture(
        program=object(), example=_example(), lm=lm
    )
    assert pred is not None
    assert messages == final_messages
    assert tools is None


def test_capture_empty_when_no_new_call(monkeypatch) -> None:
    """When the rollout makes no LM call, the uuid is unchanged → empty capture."""
    lm = SimpleNamespace(
        history=[{"messages": [{"role": "user", "content": "x"}], "kwargs": {}, "uuid": "old"}]
    )
    monkeypatch.setattr(gepa_adapter, "_run_candidate", lambda **_: None)
    pred, messages, tools = gepa_adapter._run_candidate_and_capture(
        program=object(), example=_example(), lm=lm
    )
    assert pred is None
    assert messages == []
    assert tools is None


def test_grounding_evaluate_scores_observation_grounding(monkeypatch) -> None:
    """Grounding-only score is as_unit_interval of the mean logprob over the span."""
    templated = "PREFIX OBS123 SUFFIX"
    adapter = _adapter(_FixedTemplate(templated), _CharScorer())
    canned = [{"role": "user", "content": f"{_MARKER}\nOBS123"}]
    monkeypatch.setattr(
        gepa_adapter,
        "_run_candidate_and_capture",
        lambda **_: (dspy.Prediction(assistant_message="x"), canned, None),
    )
    example = _example(allowed=frozenset({"alpha"}), steps=(_step("alpha"),))
    candidate = seed_candidate_from_program(adapter._seed_program)
    batch = adapter.evaluate([example], candidate, capture_traces=True)
    expected = as_unit_interval(_expected_mean(templated, "OBS123"))
    assert batch.scores[0] == pytest.approx(expected)
    assert batch.objective_scores[0] == {"observation_grounding": pytest.approx(expected)}
    assert batch.trajectories[0]["observation_count"] == 1
    assert batch.trajectories[0]["grounding_mean_logprob"] == pytest.approx(
        _expected_mean(templated, "OBS123")
    )


def test_grounding_evaluate_failure_score_without_observation(monkeypatch) -> None:
    """A rollout that elicits no observation scores the failure floor, not a crash."""
    adapter = _adapter(_FixedTemplate("nothing here"), _CharScorer())
    monkeypatch.setattr(
        gepa_adapter,
        "_run_candidate_and_capture",
        lambda **_: (None, [], None),
    )
    candidate = seed_candidate_from_program(adapter._seed_program)
    batch = adapter.evaluate([_example()], candidate, capture_traces=True)
    assert batch.scores[0] == adapter.failure_score
    assert batch.objective_scores[0] == {"observation_grounding": 0.0}
    assert batch.trajectories[0]["grounding_mean_logprob"] is None
    assert batch.trajectories[0]["observation_count"] == 0


def test_grounding_reflective_dataset_emits_feedback(monkeypatch) -> None:
    """make_reflective_dataset surfaces the grounding score per component."""
    templated = "PREFIX OBS123 SUFFIX"
    adapter = _adapter(_FixedTemplate(templated), _CharScorer())
    canned = [{"role": "user", "content": f"{_MARKER}\nOBS123"}]
    monkeypatch.setattr(
        gepa_adapter,
        "_run_candidate_and_capture",
        lambda **_: (dspy.Prediction(assistant_message="x"), canned, None),
    )
    example = _example(allowed=frozenset({"alpha"}), steps=(_step("alpha"),))
    candidate = seed_candidate_from_program(adapter._seed_program)
    batch = adapter.evaluate([example], candidate, capture_traces=True)
    reflective = adapter.make_reflective_dataset(candidate, batch, [GENERALIST_MODULE_KEY])
    entries = reflective[GENERALIST_MODULE_KEY]
    assert len(entries) == 1
    assert "grounding mean log-likelihood" in entries[0]["Feedback"]
    assert set(entries[0]) == {"Inputs", "Generated Outputs", "Feedback"}


def test_combined_reward_is_task_plus_weighted_grounding(monkeypatch) -> None:
    """Combined score = scalar_with_hard_caps(vector) + λ·as_unit_interval(grounding)."""
    templated = "PREFIX OBS123 SUFFIX"
    weight = 0.05
    adapter = _adapter(
        _FixedTemplate(templated),
        _CharScorer(),
        include_task_reward=True,
        grounding_weight=weight,
    )
    canned = [{"role": "user", "content": f"{_MARKER}\nOBS123"}]
    monkeypatch.setattr(
        gepa_adapter,
        "_run_candidate_and_capture",
        lambda **_: (dspy.Prediction(assistant_message="x"), canned, None),
    )
    example = _example(allowed=frozenset({"alpha"}), steps=(_step("alpha"),))
    candidate = seed_candidate_from_program(adapter._seed_program)
    batch = adapter.evaluate([example], candidate, capture_traces=True)
    # The patched rollout never touches the mock, so the task term is scored on
    # an empty rollout — reproduce it the same way the adapter does.
    empty_rollout = TraceConditionedMCPMock(example).rollout_so_far()
    task_scalar = scalar_with_hard_caps(vector_reward(example, empty_rollout))
    grounding_unit = as_unit_interval(_expected_mean(templated, "OBS123"))
    assert batch.scores[0] == pytest.approx(task_scalar + weight * grounding_unit)
    objectives = batch.objective_scores[0]
    assert objectives["observation_grounding"] == pytest.approx(grounding_unit)
    assert "submit_clean" in objectives  # the 12 task dims are carried alongside


def test_combined_reward_requires_template_and_scorer() -> None:
    """Weighting grounding without a template + scorer is a construction error."""
    seed = dspy.ReActV2(_Sig, tools=[dspy.Tool(func=lambda x: x, name="alpha", desc="d", args={"x": {"type": "integer"}})], max_iters=2)
    with pytest.raises(ValueError):
        TrainingGroundDspyAdapter(
            seed_program=seed,
            student_lm=SimpleNamespace(history=[]),
            reflection_lm=None,
            include_task_reward=True,
            grounding_weight=0.05,
        )


def test_completions_model_strips_litellm_prefix() -> None:
    """The litellm ``fireworks_ai/`` provider prefix is stripped for /completions."""
    args = SimpleNamespace(
        fireworks_model=None,
        model="fireworks_ai/accounts/fireworks/models/minimax-m2p7",
    )
    assert (
        optimize._grounding_completions_model(args)
        == "accounts/fireworks/models/minimax-m2p7"
    )


def test_completions_model_honors_explicit_override() -> None:
    """An explicit --fireworks-model wins over the derived value."""
    args = SimpleNamespace(fireworks_model="accounts/x/models/y", model="fireworks_ai/z")
    assert optimize._grounding_completions_model(args) == "accounts/x/models/y"


def test_completions_model_passthrough_when_no_prefix() -> None:
    """A non-fireworks model id is returned unchanged."""
    args = SimpleNamespace(fireworks_model=None, model="openrouter/minimax/minimax-m2.7")
    assert optimize._grounding_completions_model(args) == "openrouter/minimax/minimax-m2.7"


def test_seed_candidate_uses_neutral_react_key() -> None:
    """The seed candidate is keyed by the neutral ``tool_module:react`` blob."""
    adapter = _adapter(_FixedTemplate("x"), _CharScorer())
    candidate = seed_candidate_from_program(adapter._seed_program)
    assert set(candidate) == {TOOL_MODULE_KEY}
    assert TOOL_MODULE_KEY != GENERALIST_MODULE_KEY


def test_legacy_generalist_keyed_candidate_still_parses() -> None:
    """A candidate seeded under the old ``:generalist`` key loads back-compat.

    Re-keying the seed blob onto the legacy key must surface the same tool
    descriptions through the parser, so old checkpoints still evaluate.
    """
    adapter = _adapter(_FixedTemplate("x"), _CharScorer())
    neutral = seed_candidate_from_program(adapter._seed_program)
    legacy = {GENERALIST_MODULE_KEY: neutral[TOOL_MODULE_KEY]}
    assert gepa_adapter._candidate_blob_key(legacy) == GENERALIST_MODULE_KEY
    assert (
        gepa_adapter._candidate_tool_descriptions(legacy)
        == gepa_adapter._candidate_tool_descriptions(neutral)
        == {"alpha": "d"}
    )


def test_parametrized_vector_fn_scores_general_preset(monkeypatch) -> None:
    """A general-preset adapter scores via ``vector_fn`` + ``reward_spec``.

    The task term must equal ``scalar_with_hard_caps`` over the 8-dim general
    vector (not the 12-dim generalist vector), proving the reward is fully
    parametrized rather than hard-wired to the generalist preset.
    """
    tool = dspy.Tool(func=lambda x: x, name="alpha", desc="d", args={"x": {"type": "integer"}})
    seed = dspy.ReActV2(_Sig, tools=[tool], max_iters=2)
    adapter = TrainingGroundDspyAdapter(
        seed_program=seed,
        student_lm=SimpleNamespace(history=[]),
        reflection_lm=None,
        include_task_reward=True,
        grounding_weight=0.0,
        reward_spec=GENERAL_REWARD_SPEC,
        vector_fn=general_vector_reward,
    )
    monkeypatch.setattr(
        gepa_adapter,
        "_run_candidate",
        lambda **_: dspy.Prediction(assistant_message="x"),
    )
    example = _example(allowed=frozenset({"alpha"}), steps=(_step("alpha"),))
    candidate = seed_candidate_from_program(adapter._seed_program)
    batch = adapter.evaluate([example], candidate, capture_traces=True)
    empty_rollout = TraceConditionedMCPMock(example).rollout_so_far()
    expected = scalar_with_hard_caps(
        general_vector_reward(example, empty_rollout), GENERAL_REWARD_SPEC
    )
    assert batch.scores[0] == pytest.approx(expected)
    objectives = batch.objective_scores[0]
    assert set(objectives) == set(GENERAL_REWARD_SPEC.weights)
    assert "submit_clean" not in objectives  # generalist-only dims are absent
