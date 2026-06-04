"""Unit tests for the react valset-outputs recorder.

Covers :class:`ReactValsetOutputsRecorder` and the :func:`react_valset_outputs`
context manager — the wrapper that gives react ``POST /run`` optimizations the
per-candidate Pareto-cell predictions the standard (metric-callable) path emits
via :class:`MinibatchRecorder`. No live model or ``gepa.optimize`` is needed:
the tests drive a stub ``evaluate`` and assert on the emitted progress events.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from core.constants import PROGRESS_VALSET_OUTPUTS
from core.service_gateway.optimization.trajectory import react_valset_outputs


def _stub_evaluate(batch: list[Any], _candidate: Any, **_kwargs: Any) -> SimpleNamespace:
    """Return an EvaluationBatch-shaped result scoring each example by its ``i``.

    Args:
        batch: Examples to score.
        _candidate: Unused candidate map (signature parity with the adapter).
        **_kwargs: Unused forwarded kwargs (e.g. ``capture_traces``).

    Returns:
        A namespace with ``outputs`` and ``scores`` aligned to ``batch`` order.
    """
    return SimpleNamespace(
        outputs=[SimpleNamespace(answer=f"a{ex.i}") for ex in batch],
        scores=[float(ex.i) for ex in batch],
    )


def _valset(n: int) -> list[SimpleNamespace]:
    """Build ``n`` identity-distinct example objects tagged with index ``i``."""
    return [SimpleNamespace(i=idx) for idx in range(n)]


def test_full_sweep_emits_event_keyed_by_candidate_index() -> None:
    """A full-valset evaluate emits one event with all example ids and scores."""
    val = _valset(3)
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(evaluate=_stub_evaluate)

    with react_valset_outputs(adapter, val, lambda ev, p: events.append((ev, p))):
        adapter.evaluate(val, {"react": "seed"})

    assert len(events) == 1
    name, payload = events[0]
    assert name == PROGRESS_VALSET_OUTPUTS
    assert payload["candidate_index"] == 0
    assert [p["example_id"] for p in payload["predictions"]] == ["0", "1", "2"]
    assert [p["score"] for p in payload["predictions"]] == [0.0, 1.0, 2.0]


def test_minibatch_subset_does_not_emit() -> None:
    """Evaluations that don't cover the full valset (proposals) stay silent."""
    val = _valset(3)
    train = [SimpleNamespace(i=10 + k) for k in range(2)]
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(evaluate=_stub_evaluate)

    with react_valset_outputs(adapter, val, lambda ev, p: events.append((ev, p))):
        adapter.evaluate(train, {"react": "proposal"})
        adapter.evaluate(val[:2], {"react": "proposal"})

    assert events == []


def test_candidate_index_increments_across_sweeps() -> None:
    """Sequential full sweeps map to program_candidates indices (seed = 0)."""
    val = _valset(2)
    events: list[tuple[str, dict[str, Any]]] = []
    adapter = SimpleNamespace(evaluate=_stub_evaluate)

    with react_valset_outputs(adapter, val, lambda ev, p: events.append((ev, p))):
        adapter.evaluate(val, {"react": "seed"})
        adapter.evaluate(list(reversed(val)), {"react": "c1"})

    assert [p["candidate_index"] for _, p in events] == [0, 1]
    # Reordered batch keeps example_id ↔ score alignment by identity.
    second = events[1][1]["predictions"]
    assert {p["example_id"]: p["score"] for p in second} == {"0": 0.0, "1": 1.0}


def test_restores_original_evaluate_on_exit() -> None:
    """The adapter's evaluate is unwrapped after the context closes."""
    val = _valset(2)
    adapter = SimpleNamespace(evaluate=_stub_evaluate)

    with react_valset_outputs(adapter, val, lambda _ev, _p: None):
        assert adapter.evaluate is not _stub_evaluate
    assert adapter.evaluate is _stub_evaluate


def test_noop_without_progress_callback() -> None:
    """A missing callback leaves evaluate untouched and emits nothing."""
    val = _valset(2)
    adapter = SimpleNamespace(evaluate=_stub_evaluate)

    with react_valset_outputs(adapter, val, None):
        assert adapter.evaluate is _stub_evaluate
        adapter.evaluate(val, {"react": "seed"})
