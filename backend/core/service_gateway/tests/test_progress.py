"""Tests for ``core.service_gateway.optimization.progress`` (tqdm capture proxy)."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from core.constants import (
    PROGRESS_OPTIMIZER,
    TQDM_DESC_KEY,
    TQDM_N_KEY,
    TQDM_PERCENT_KEY,
    TQDM_RATE_KEY,
    TQDM_REMAINING_KEY,
    TQDM_TOTAL_KEY,
)
from core.service_gateway.optimization.progress import (
    _TqdmProxy,
    capture_tqdm,
)

# tqdm is a transitive dep of dspy and effectively always installed; the guards
# below are kept so the test still runs in stripped-down envs.
try:
    import tqdm
    import tqdm.auto as tqdm_auto
except ImportError:
    tqdm = None  # type: ignore[assignment]
    tqdm_auto = None  # type: ignore[assignment]


class _FakeBar:
    """Stand-in for a ``tqdm`` progress bar with a stable, observable shape."""

    def __init__(
        self,
        total: int | None = 10,
        n: int = 0,
        desc: str | None = "GEPA evaluation",
        unit: str = "it",
        format_dict: dict | None = None,
    ) -> None:
        """Store standard tqdm-like fields for direct mutation by tests."""
        self.total = total
        self.n = n
        self.desc = desc
        self.unit = unit
        self.format_dict = format_dict or {}

    def update(self, n: int = 1) -> None:
        """Advance the running count by ``n``."""
        self.n += n

    def close(self) -> None:
        """No-op close to match the tqdm API."""

    def refresh(self) -> None:
        """No-op refresh to match the tqdm API."""

    def __enter__(self) -> _FakeBar:
        """Return self for ``with`` semantics."""
        return self

    def __exit__(self, *args: Any) -> Literal[False]:
        """Suppress no exceptions (always False)."""
        return False


def _make_proxy(
    bar: _FakeBar | None = None,
    callback: Any = None,
) -> tuple[_TqdmProxy, list[tuple]]:
    """Build a ``_TqdmProxy`` plus a list that captures every emitted event."""
    events: list[tuple] = []

    def _cb(event: str, metrics: dict) -> None:
        events.append((event, metrics))

    if bar is None:
        bar = _FakeBar()
    proxy = _TqdmProxy(bar, callback or _cb)
    return proxy, events


def test_tqdm_proxy_gepa_bar_construction_emits_one_event() -> None:
    """GEPA bars (desc starts with 'gepa') emit a single event on construction."""
    bar = _FakeBar(desc="GEPA evaluation")
    _, events = _make_proxy(bar)

    assert len(events) == 1


def test_tqdm_proxy_construction_event_name_is_progress_optimizer() -> None:
    """The construction event for GEPA bars is named ``PROGRESS_OPTIMIZER``."""
    bar = _FakeBar(desc="GEPA run")
    _, events = _make_proxy(bar)

    assert events[0][0] == PROGRESS_OPTIMIZER


def test_tqdm_proxy_non_gepa_bar_does_not_emit_on_construction() -> None:
    """Non-GEPA bars (e.g. Bootstrap) stay silent on construction."""
    # _emit_enabled is False for non-GEPA bars (e.g. Bootstrap), so no event fires.
    bar = _FakeBar(desc="Bootstrap", unit="it")
    _, events = _make_proxy(bar)

    assert len(events) == 0


def test_tqdm_proxy_rollouts_unit_bar_emits_on_construction() -> None:
    """A bar with unit='rollouts' is treated as GEPA even when desc isn't."""
    # unit='rollouts' is the GEPA classifier's secondary signal — treated as GEPA even when desc isn't.
    bar = _FakeBar(desc="other", unit="rollouts")
    _, events = _make_proxy(bar)

    assert len(events) == 1


def test_tqdm_proxy_percent_computed_correctly() -> None:
    """``percent`` is computed as ``n / total * 100``."""
    bar = _FakeBar(total=10, n=5, desc="GEPA run")
    _, events = _make_proxy(bar)

    metrics = events[0][1]
    assert metrics[TQDM_PERCENT_KEY] == pytest.approx(50.0)


def test_tqdm_proxy_percent_is_none_when_total_is_none() -> None:
    """``percent`` is ``None`` when total is unknown."""
    bar = _FakeBar(total=None, n=0, desc="GEPA run")
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_PERCENT_KEY] is None


def test_tqdm_proxy_percent_is_none_when_total_is_zero() -> None:
    """``percent`` is ``None`` when total is zero (avoids division by zero)."""
    # total=0 is falsy, so percent stays None — guards against division by zero.
    bar = _FakeBar(total=0, n=0, desc="GEPA run")
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_PERCENT_KEY] is None


def test_tqdm_proxy_remaining_computed_when_rate_available() -> None:
    """``remaining`` is ``(total - n) / rate`` when both are available."""
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={"rate": 2.0})
    _, events = _make_proxy(bar)

    # remaining = (10 - 2) / 2.0 = 4.0
    assert events[0][1][TQDM_REMAINING_KEY] == pytest.approx(4.0)


def test_tqdm_proxy_remaining_is_none_when_rate_is_zero() -> None:
    """``remaining`` is ``None`` when rate is zero (avoids division by zero)."""
    # rate=0 must not produce ZeroDivisionError; guard returns None instead.
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={"rate": 0.0})
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_REMAINING_KEY] is None


def test_tqdm_proxy_remaining_is_none_when_rate_missing() -> None:
    """``remaining`` is ``None`` when no rate is available."""
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={})
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_REMAINING_KEY] is None


def test_tqdm_proxy_update_emits_event_on_state_change() -> None:
    """``update`` emits a new event when the bar state has changed."""
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 3  # advance bar so metrics differ from last emission
    proxy.update(0)  # call update (bar.n already changed above)

    assert len(events) == initial_count + 1


def test_tqdm_proxy_update_deduplicates_identical_metrics() -> None:
    """``update`` does not emit a duplicate event when metrics are unchanged."""
    # Dedup contract: identical-state update must NOT emit a duplicate event.
    bar = _FakeBar(total=10, n=5, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    proxy.update(0)

    assert len(events) == initial_count


def test_tqdm_proxy_close_emits_event_on_state_change() -> None:
    """``close`` emits a new event when the bar state has changed."""
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 1  # change state so it's not a duplicate
    proxy.close()

    assert len(events) == initial_count + 1


def test_tqdm_proxy_refresh_emits_event_on_state_change() -> None:
    """``refresh`` emits a new event when the bar state has changed."""
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 2  # change state so it's not a duplicate
    proxy.refresh()

    assert len(events) == initial_count + 1


def test_tqdm_proxy_delegates_unknown_attrs_to_bar() -> None:
    """Unknown attribute access is delegated to the underlying bar."""
    bar = _FakeBar()
    bar.custom_attr = "hello"  # type: ignore[attr-defined]
    proxy, _ = _make_proxy(bar)

    assert proxy.custom_attr == "hello"


def test_tqdm_proxy_context_manager_returns_self() -> None:
    """``__enter__`` returns the proxy itself for ``with`` semantics."""
    bar = _FakeBar()
    proxy, _ = _make_proxy(bar)

    with proxy as p:
        assert p is proxy


def test_tqdm_proxy_metrics_contains_expected_keys() -> None:
    """Emitted metrics include all canonical tqdm fields."""
    bar = _FakeBar(total=10, n=3, desc="GEPA run", format_dict={"rate": 1.0, "elapsed": 3.0})
    _, events = _make_proxy(bar)

    metrics = events[0][1]
    for key in (TQDM_TOTAL_KEY, TQDM_N_KEY, TQDM_PERCENT_KEY, TQDM_RATE_KEY, TQDM_REMAINING_KEY, TQDM_DESC_KEY):
        assert key in metrics


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("GEPA run", True),
        ("gepa", True),
        ("  Gepa evaluation  ", True),
        ("Bootstrap", False),
        ("Average Metric", False),
        (None, False),
        (42, False),
    ],
)
def test_desc_mentions_gepa_parametrized(desc: Any, expected: bool) -> None:
    """``_desc_mentions_gepa`` recognises GEPA descs case-insensitively."""
    result = _TqdmProxy._desc_mentions_gepa(desc)

    assert result is expected


def test_is_gepa_bar_true_via_rollouts_unit() -> None:
    """A bar with unit='rollouts' classifies as a GEPA bar."""
    bar = _FakeBar(unit="rollouts", desc="some_other_desc")

    assert _TqdmProxy._is_gepa_bar(bar, bar.desc) is True


def test_is_gepa_bar_false_for_generic_bar() -> None:
    """A generic Bootstrap bar does not classify as a GEPA bar."""
    bar = _FakeBar(unit="it", desc="Bootstrap")

    assert _TqdmProxy._is_gepa_bar(bar, bar.desc) is False


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("Average Metric", True),
        ("average metric: 0.7", True),
        ("AVERAGE METRIC", True),
        ("Bootstrap", False),
        ("GEPA run", False),
        (None, False),
    ],
)
def test_looks_like_nested_bar_parametrized(desc: Any, expected: bool) -> None:
    """``_looks_like_nested_bar`` recognises Average Metric descs case-insensitively."""
    result = _TqdmProxy._looks_like_nested_bar(desc)

    assert result is expected


def test_tqdm_proxy_average_metric_bar_does_not_emit_after_init() -> None:
    """An 'Average Metric' bar never emits, even after updates."""
    # 'Average Metric' bars classify as nested AND non-GEPA → _emit_enabled=False, never emits.
    bar = _FakeBar(desc="Average Metric: bootstrap", unit="it")
    proxy, events = _make_proxy(bar)

    assert len(events) == 0
    bar.n = 3
    proxy.update(3)
    assert len(events) == 0


def test_tqdm_proxy_emit_enabled_activates_when_desc_changes_to_gepa() -> None:
    """Late activation: a desc rewrite to 'gepa' mid-life re-enables emission."""
    # Late activation: a desc rewrite to "gepa" mid-life must re-enable emission
    # (regression — previously _emit_enabled was latched at construction).
    bar = _FakeBar(desc="Bootstrap", unit="it")
    proxy, events = _make_proxy(bar)

    assert len(events) == 0

    bar.desc = "GEPA iteration 1"
    bar.n = 5
    proxy.update(0)

    assert len(events) == 1


def test_capture_tqdm_none_callback_is_noop() -> None:
    """``capture_tqdm(None)`` is a no-op context manager."""
    with capture_tqdm(None):
        pass  # should not raise


def test_capture_tqdm_patches_and_restores_tqdm() -> None:
    """``capture_tqdm`` swaps tqdm.tqdm in and back out."""
    if tqdm is None or tqdm_auto is None:
        pytest.skip("tqdm not installed")

    original_tqdm = tqdm.tqdm
    original_auto = tqdm_auto.tqdm

    with capture_tqdm(lambda ev, m: None):
        patched_tqdm = tqdm.tqdm
        patched_auto = tqdm_auto.tqdm
        assert patched_tqdm is not original_tqdm
        assert patched_auto is not original_auto

    # After context exit the originals are restored
    assert tqdm.tqdm is original_tqdm
    assert tqdm_auto.tqdm is original_auto


def test_capture_tqdm_reference_count_nests_correctly() -> None:
    """Nested ``capture_tqdm`` contexts share a refcount and restore correctly."""
    # Refcount invariant: nested contexts must not double-patch (would corrupt restore order).
    if tqdm is None:
        pytest.skip("tqdm not installed")

    original_tqdm = tqdm.tqdm

    with capture_tqdm(lambda e, m: None), capture_tqdm(lambda e, m: None):
        pass

    assert tqdm.tqdm is original_tqdm
