"""Tests for the parse-failure resampling in :mod:`...optimization.retrying_react`.

Pins the three guarantees the retry contract makes: a transient parse failure
is resampled until it parses, each retry lands on a distinct ``rollout_id`` so
the LM cache is bypassed, and a persistent failure still re-raises (preserving
ReActV2's forced-submit fallback). Also asserts the ``RetryingReActV2`` subclass
keeps a plain ``react`` predictor visible to GEPA's named-predictor walk.
"""

from __future__ import annotations

import dspy
import pytest
from dspy.utils.exceptions import AdapterParseError

from ..optimization.retrying_react import RetryingPredict, RetryingReActV2
from ..react_compat import REACT_CLASS, react_uses_submit


class _Sig(dspy.Signature):
    """Tiny signature so the predictor/program can be built without an LM."""

    question: str = dspy.InputField()
    answer: str = dspy.OutputField()


def _alpha_tool() -> dspy.Tool:
    """Build a trivial integer-arg tool for ReActV2 construction.

    Returns:
        A ``dspy.Tool`` named ``alpha`` taking one integer argument.
    """
    return dspy.Tool(
        func=lambda x: x,
        name="alpha",
        desc="echo",
        args={"x": {"type": "integer"}},
    )


def test_resamples_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parse failure is resampled with a fresh rollout_id until it parses."""
    pred = RetryingPredict(_Sig, parse_retries=2)
    seen_rollout_ids: list[int | None] = []

    def fake_super_forward(self: dspy.Predict, **kwargs: object) -> dspy.Prediction:
        """Fail to parse on the first two attempts, then succeed."""
        config = kwargs.get("config") or {}
        seen_rollout_ids.append(config.get("rollout_id"))
        if len(seen_rollout_ids) < 3:
            raise AdapterParseError("ChatAdapter", _Sig, "garbled")
        return dspy.Prediction(answer="ok")

    monkeypatch.setattr(dspy.Predict, "forward", fake_super_forward)

    out = pred.forward(question="q")

    assert out.answer == "ok"
    assert len(seen_rollout_ids) == 3
    assert seen_rollout_ids[0] is None  # first attempt is untouched
    assert seen_rollout_ids[1] is not None
    assert seen_rollout_ids[2] is not None
    assert seen_rollout_ids[1] != seen_rollout_ids[2]  # cache-busting per retry


def test_reraises_after_exhaustion(monkeypatch: pytest.MonkeyPatch) -> None:
    """A persistent parse failure re-raises so the forced-submit fallback runs."""
    pred = RetryingPredict(_Sig, parse_retries=1)
    attempts = 0

    def always_fail(self: dspy.Predict, **kwargs: object) -> dspy.Prediction:
        """Always raise an adapter parse error."""
        nonlocal attempts
        attempts += 1
        raise AdapterParseError("ChatAdapter", _Sig, "garbled")

    monkeypatch.setattr(dspy.Predict, "forward", always_fail)

    with pytest.raises(AdapterParseError):
        pred.forward(question="q")
    assert attempts == 2  # one initial + one retry


def test_caller_config_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller-supplied config (e.g. forced-submit tool_choice) survives the retry."""
    pred = RetryingPredict(_Sig, parse_retries=1)
    seen_configs: list[dict] = []

    def fake_super_forward(self: dspy.Predict, **kwargs: object) -> dspy.Prediction:
        """Record the merged config, failing once so a retry occurs."""
        seen_configs.append(dict(kwargs.get("config") or {}))
        if len(seen_configs) < 2:
            raise AdapterParseError("ChatAdapter", _Sig, "garbled")
        return dspy.Prediction(answer="ok")

    monkeypatch.setattr(dspy.Predict, "forward", fake_super_forward)

    pred.forward(question="q", config={"tool_choice": "submit"})

    assert seen_configs[0]["tool_choice"] == "submit"
    assert seen_configs[1]["tool_choice"] == "submit"  # preserved on retry
    assert seen_configs[1]["rollout_id"] != seen_configs[0].get("rollout_id")


def test_subclass_swaps_inner_predict_only() -> None:
    """``RetryingReActV2`` re-homes ``react`` onto a retrying Predict, same signature."""
    program = RetryingReActV2(_Sig, tools=[_alpha_tool()], max_iters=2)

    assert isinstance(program, REACT_CLASS)
    assert isinstance(program.react, RetryingPredict)
    predictors = dict(program.named_predictors())
    assert isinstance(predictors["react"], RetryingPredict)
    # The synthetic loop-exit tool (``submit`` on ReActV2, ``finish`` on classic
    # ReAct) and the user roster are untouched by the swap.
    terminal = "submit" if react_uses_submit(program) else "finish"
    assert terminal in program.tools
    assert "alpha" in program.tools
