"""Tests for core.service_gateway.progress."""

from __future__ import annotations

from typing import Any

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
from core.service_gateway.progress import (
    _TqdmProxy,
    capture_tqdm,
)



class _FakeBar:
    """Minimal stand-in for a tqdm progress bar."""

    def __init__(
        self,
        total: int | None = 10,
        n: int = 0,
        desc: str | None = "GEPA evaluation",
        unit: str = "it",
        format_dict: dict | None = None,
    ) -> None:
        """Configure a fake bar with the given attributes."""
        self.total = total
        self.n = n
        self.desc = desc
        self.unit = unit
        self.format_dict = format_dict or {}

    def update(self, n: int = 1) -> None:
        self.n += n

    def close(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _make_proxy(
    bar: _FakeBar | None = None,
    callback=None,
) -> tuple[_TqdmProxy, list[tuple]]:
    """Return a (_TqdmProxy, events_list) pair; events accumulate on every callback call."""
    events: list[tuple] = []

    def _cb(event: str, metrics: dict) -> None:
        events.append((event, metrics))

    if bar is None:
        bar = _FakeBar()
    proxy = _TqdmProxy(bar, callback or _cb)
    return proxy, events



def test_tqdm_proxy_gepa_bar_construction_emits_one_event() -> None:
    """GEPA bars (desc starts with 'gepa') emit on construction."""
    bar = _FakeBar(desc="GEPA evaluation")
    _, events = _make_proxy(bar)

    assert len(events) == 1


def test_tqdm_proxy_construction_event_name_is_progress_optimizer() -> None:
    """Construction event uses the PROGRESS_OPTIMIZER event name."""
    bar = _FakeBar(desc="GEPA run")
    _, events = _make_proxy(bar)

    assert events[0][0] == PROGRESS_OPTIMIZER


def test_tqdm_proxy_non_gepa_bar_does_not_emit_on_construction() -> None:
    """Non-GEPA bars (e.g. Bootstrap) should NOT emit events — _emit_enabled is False."""
    bar = _FakeBar(desc="Bootstrap", unit="it")
    _, events = _make_proxy(bar)

    assert len(events) == 0


def test_tqdm_proxy_rollouts_unit_bar_emits_on_construction() -> None:
    """A bar with unit='rollouts' is treated as a GEPA bar."""
    bar = _FakeBar(desc="other", unit="rollouts")
    _, events = _make_proxy(bar)

    assert len(events) == 1



def test_tqdm_proxy_percent_computed_correctly() -> None:
    """Percent is computed as 100 * (n / total)."""
    bar = _FakeBar(total=10, n=5, desc="GEPA run")
    _, events = _make_proxy(bar)

    metrics = events[0][1]
    assert metrics[TQDM_PERCENT_KEY] == pytest.approx(50.0)


def test_tqdm_proxy_percent_is_none_when_total_is_none() -> None:
    """Percent is None when total is None."""
    bar = _FakeBar(total=None, n=0, desc="GEPA run")
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_PERCENT_KEY] is None


def test_tqdm_proxy_percent_is_none_when_total_is_zero() -> None:
    """Percent is None when total is zero (avoids division by zero)."""
    bar = _FakeBar(total=0, n=0, desc="GEPA run")
    _, events = _make_proxy(bar)

    # total=0 → falsy, percent stays None
    assert events[0][1][TQDM_PERCENT_KEY] is None



def test_tqdm_proxy_remaining_computed_when_rate_available() -> None:
    """Remaining is computed as (total - n) / rate when rate > 0."""
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={"rate": 2.0})
    _, events = _make_proxy(bar)

    # remaining = (10 - 2) / 2.0 = 4.0
    assert events[0][1][TQDM_REMAINING_KEY] == pytest.approx(4.0)


def test_tqdm_proxy_remaining_is_none_when_rate_is_zero() -> None:
    """Remaining is None when rate is zero (avoids division by zero)."""
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={"rate": 0.0})
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_REMAINING_KEY] is None


def test_tqdm_proxy_remaining_is_none_when_rate_missing() -> None:
    """Remaining is None when rate is absent from format_dict."""
    bar = _FakeBar(total=10, n=2, desc="GEPA run", format_dict={})
    _, events = _make_proxy(bar)

    assert events[0][1][TQDM_REMAINING_KEY] is None



def test_tqdm_proxy_update_emits_event_on_state_change() -> None:
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 3  # advance bar so metrics differ from last emission
    proxy.update(0)  # call update (bar.n already changed above)

    assert len(events) == initial_count + 1


def test_tqdm_proxy_update_deduplicates_identical_metrics() -> None:
    """Calling update when nothing changed should NOT emit a duplicate event."""
    bar = _FakeBar(total=10, n=5, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    # Don't change any bar attributes, so metrics are identical to last emission
    proxy.update(0)

    assert len(events) == initial_count



def test_tqdm_proxy_close_emits_event_on_state_change() -> None:
    """close() emits an event when bar state has changed since last emission."""
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 1  # change state so it's not a duplicate
    proxy.close()

    assert len(events) == initial_count + 1



def test_tqdm_proxy_refresh_emits_event_on_state_change() -> None:
    """refresh() emits an event when bar state has changed since last emission."""
    bar = _FakeBar(total=10, n=0, desc="GEPA run")
    proxy, events = _make_proxy(bar)
    initial_count = len(events)

    bar.n = 2  # change state so it's not a duplicate
    proxy.refresh()

    assert len(events) == initial_count + 1



def test_tqdm_proxy_delegates_unknown_attrs_to_bar() -> None:
    """Unknown attribute access is forwarded to the wrapped bar."""
    bar = _FakeBar()
    bar.custom_attr = "hello"
    proxy, _ = _make_proxy(bar)

    assert proxy.custom_attr == "hello"



def test_tqdm_proxy_context_manager_returns_self() -> None:
    """Using the proxy as a context manager yields itself."""
    bar = _FakeBar()
    proxy, _ = _make_proxy(bar)

    with proxy as p:
        assert p is proxy



def test_tqdm_proxy_metrics_contains_expected_keys() -> None:
    """Emitted metrics dict contains all required tqdm key constants."""
    bar = _FakeBar(total=10, n=3, desc="GEPA run", format_dict={"rate": 1.0, "elapsed": 3.0})
    _, events = _make_proxy(bar)

    metrics = events[0][1]
    for key in (TQDM_TOTAL_KEY, TQDM_N_KEY, TQDM_PERCENT_KEY, TQDM_RATE_KEY, TQDM_REMAINING_KEY, TQDM_DESC_KEY):
        assert key in metrics



@pytest.mark.parametrize(
    "desc, expected",
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
    """Parametrized check that _desc_mentions_gepa detects GEPA descriptions correctly."""
    result = _TqdmProxy._desc_mentions_gepa(desc)

    assert result is expected


def test_is_gepa_bar_true_via_rollouts_unit() -> None:
    """Bar with unit='rollouts' is identified as a GEPA bar."""
    bar = _FakeBar(unit="rollouts", desc="some_other_desc")

    assert _TqdmProxy._is_gepa_bar(bar, bar.desc) is True


def test_is_gepa_bar_false_for_generic_bar() -> None:
    """Generic bar (unit='it', non-GEPA desc) is not identified as a GEPA bar."""
    bar = _FakeBar(unit="it", desc="Bootstrap")

    assert _TqdmProxy._is_gepa_bar(bar, bar.desc) is False



@pytest.mark.parametrize(
    "desc, expected",
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
    """Parametrized check that _looks_like_nested_bar identifies inner bars correctly."""
    result = _TqdmProxy._looks_like_nested_bar(desc)

    assert result is expected



def test_tqdm_proxy_average_metric_bar_does_not_emit_after_init() -> None:
    """Bars with 'Average Metric' desc are suppressed (looks_like_nested_bar is True,
    and _emit_enabled is False for non-GEPA bars)."""
    bar = _FakeBar(desc="Average Metric: bootstrap", unit="it")
    proxy, events = _make_proxy(bar)

    # Non-GEPA bar → _emit_enabled=False → no events even at construction
    assert len(events) == 0
    bar.n = 3
    proxy.update(3)
    assert len(events) == 0



def test_tqdm_proxy_emit_enabled_activates_when_desc_changes_to_gepa() -> None:
    """If a bar's desc is updated to start with 'gepa' after construction,
    subsequent _emit calls should become active."""
    bar = _FakeBar(desc="Bootstrap", unit="it")
    proxy, events = _make_proxy(bar)

    assert len(events) == 0

    bar.desc = "GEPA iteration 1"
    bar.n = 5
    proxy.update(0)  # triggers _emit which checks desc again

    assert len(events) == 1



def test_capture_tqdm_none_callback_is_noop() -> None:
    """capture_tqdm(None) is a no-op and does not raise."""
    with capture_tqdm(None):
        pass  # should not raise



def test_capture_tqdm_patches_and_restores_tqdm() -> None:
    try:
        import tqdm
        import tqdm.auto as tqdm_auto
    except ImportError:
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
    """Two nested capture_tqdm contexts should not double-patch or crash."""
    try:
        import tqdm
        import tqdm.auto as tqdm_auto
    except ImportError:
        pytest.skip("tqdm not installed")

    original_tqdm = tqdm.tqdm

    with capture_tqdm(lambda e, m: None):
        with capture_tqdm(lambda e, m: None):
            pass

    assert tqdm.tqdm is original_tqdm
