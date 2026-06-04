"""Unit tests for the react reflective-feedback recorder.

Covers :class:`ReactReflectiveFeedbackRecorder` and the
:func:`react_minibatch_feedback` context manager — the wrapper that surfaces a
react ``POST /run`` optimization's per-example GEPA reflection feedback as
``PROGRESS_MINIBATCH`` events. The metric-callable path emits these for
predict/cot runs, but the react adapter produces feedback inside
``make_reflective_dataset`` instead, so without this wrapper the minibatch
panel stays empty for agent runs. No live model or ``gepa.optimize`` is needed:
the tests drive a stub ``make_reflective_dataset`` and assert on emitted events.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from core.constants import PROGRESS_MINIBATCH
from core.service_gateway.optimization.trajectory import (
    _current_proposal_iteration,
    react_minibatch_feedback,
)


def _eval_batch(n: int) -> SimpleNamespace:
    """Build an EvaluationBatch-shaped namespace with ``n`` index-aligned examples."""
    return SimpleNamespace(
        trajectories=[{"example": SimpleNamespace(turn_id=f"t{i}")} for i in range(n)],
        scores=[float(i) for i in range(n)],
        outputs=[SimpleNamespace(answer=f"a{i}") for i in range(n)],
    )


def _make_reflective(n: int) -> Any:
    """Return a stub ``make_reflective_dataset`` with one feedback entry per example.

    Args:
        n: Number of per-example entries to emit per requested component.

    Returns:
        A callable matching the adapter's ``make_reflective_dataset`` signature.
    """

    def _fn(candidate: Any, eval_batch: Any, components: list[str], *a: Any, **k: Any):
        entries = [
            {"Inputs": {}, "Generated Outputs": f"o{i}", "Feedback": f"fix {i}"}
            for i in range(n)
        ]
        return {component: list(entries) for component in components}

    return _fn


def test_emits_one_minibatch_event_per_reflected_example() -> None:
    """Each reflected example with feedback becomes a PROGRESS_MINIBATCH event."""
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(make_reflective_dataset=_make_reflective(2))

    with react_minibatch_feedback(adapter, [], lambda ev, p: events.append((ev, p))):
        adapter.make_reflective_dataset(
            {"react": "c"}, _eval_batch(2), ["tool_module:react"]
        )

    assert [e for e, _ in events] == [PROGRESS_MINIBATCH, PROGRESS_MINIBATCH]
    payloads = [p for _, p in events]
    assert [p["feedback"] for p in payloads] == ["fix 0", "fix 1"]
    assert [p["score"] for p in payloads] == [0.0, 1.0]
    assert [p["example_id"] for p in payloads] == ["t0", "t1"]


def test_example_id_prefers_valset_membership() -> None:
    """A reflected example that is a valset member resolves to its row index."""
    events: list[tuple[str, dict[str, Any]]] = []
    val_ex = SimpleNamespace(turn_id="t5")
    batch = SimpleNamespace(
        trajectories=[{"example": val_ex}],
        scores=[1.0],
        outputs=[SimpleNamespace(answer="x")],
    )

    def _fn(candidate: Any, eval_batch: Any, components: list[str], *a: Any, **k: Any):
        return {component: [{"Feedback": "fb"}] for component in components}

    adapter = SimpleNamespace(make_reflective_dataset=_fn)
    with react_minibatch_feedback(adapter, [val_ex], lambda ev, p: events.append((ev, p))):
        adapter.make_reflective_dataset({}, batch, ["c"])

    assert events[0][1]["example_id"] == "0"


def test_skips_examples_without_feedback() -> None:
    """Examples whose reflective entry carries empty feedback emit nothing."""
    events: list[tuple[str, dict[str, Any]]] = []

    def _fn(candidate: Any, eval_batch: Any, components: list[str], *a: Any, **k: Any):
        return {component: [{"Feedback": ""}] for component in components}

    batch = SimpleNamespace(
        trajectories=[{"example": SimpleNamespace(turn_id="t0")}],
        scores=[0.0],
        outputs=[None],
    )
    adapter = SimpleNamespace(make_reflective_dataset=_fn)
    with react_minibatch_feedback(adapter, [], lambda ev, p: events.append((ev, p))):
        adapter.make_reflective_dataset({}, batch, ["c"])

    assert events == []


def test_iteration_is_read_from_contextvar() -> None:
    """The current proposal iteration is stamped onto each event."""
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(make_reflective_dataset=_make_reflective(1))
    token = _current_proposal_iteration.set(4)
    try:
        with react_minibatch_feedback(adapter, [], lambda ev, p: events.append((ev, p))):
            adapter.make_reflective_dataset({}, _eval_batch(1), ["c"])
    finally:
        _current_proposal_iteration.reset(token)

    assert events[0][1]["iteration"] == 4


def test_iteration_defaults_to_none_outside_propose() -> None:
    """With no propose() iteration set, events carry ``iteration=None``."""
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(make_reflective_dataset=_make_reflective(1))
    with react_minibatch_feedback(adapter, [], lambda ev, p: events.append((ev, p))):
        adapter.make_reflective_dataset({}, _eval_batch(1), ["c"])

    assert events[0][1]["iteration"] is None


def test_restores_original_on_exit() -> None:
    """The adapter's make_reflective_dataset is unwrapped after the context closes."""
    fn = _make_reflective(1)
    adapter = SimpleNamespace(make_reflective_dataset=fn)
    with react_minibatch_feedback(adapter, [], lambda _ev, _p: None):
        assert adapter.make_reflective_dataset is not fn
    assert adapter.make_reflective_dataset is fn


def test_noop_without_progress_callback() -> None:
    """A missing callback leaves make_reflective_dataset untouched."""
    fn = _make_reflective(1)
    adapter = SimpleNamespace(make_reflective_dataset=fn)
    with react_minibatch_feedback(adapter, [], None):
        assert adapter.make_reflective_dataset is fn
