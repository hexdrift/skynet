"""Tests for ``core.service_gateway.optimization.timing.GenLMTimingCallback``."""

from __future__ import annotations

from core.service_gateway.optimization.timing import GenLMTimingCallback


class _FakeLM:
    """Empty stand-in for a dspy LM, used purely for identity comparisons."""


def test_records_only_target_lm_calls() -> None:
    """Calls from non-target LMs are filtered out — only the target's durations are recorded."""
    # Non-target LM calls are filtered by id() — only `target`'s timings should be recorded.
    target = _FakeLM()
    other = _FakeLM()
    cb = GenLMTimingCallback(target)

    cb.on_lm_start("call-a", target, {})
    cb.on_lm_end("call-a", outputs={"ok": True})
    cb.on_lm_start("call-b", other, {})
    cb.on_lm_end("call-b", outputs={"ok": True})

    assert len(cb.durations_ms) == 1


def test_summary_none_when_no_calls() -> None:
    """``summary`` returns ``(0, None)`` when no calls have been recorded."""
    cb = GenLMTimingCallback(_FakeLM())
    n, avg = cb.summary()
    assert n == 0
    assert avg is None


def test_summary_averages_durations() -> None:
    """``summary`` returns the count and arithmetic mean of recorded durations."""
    target = _FakeLM()
    cb = GenLMTimingCallback(target)
    cb.durations_ms.extend([100.0, 200.0, 300.0])
    n, avg = cb.summary()
    assert n == 3
    assert avg == 200.0


def test_end_without_start_is_ignored() -> None:
    """``on_lm_end`` without a matching ``on_lm_start`` is a no-op."""
    # on_lm_end without a matching on_lm_start is a no-op (occurs for non-target LM calls
    # that were filtered at on_lm_start time).
    cb = GenLMTimingCallback(_FakeLM())
    cb.on_lm_end("never-started", outputs=None)
    assert cb.durations_ms == []



def test_exception_path_still_records_duration() -> None:
    """A call that ends with an exception still has its duration recorded."""
    target = _FakeLM()
    cb = GenLMTimingCallback(target)
    cb.on_lm_start("call-x", target, {})
    cb.on_lm_end("call-x", outputs=None, exception=RuntimeError("boom"))
    assert len(cb.durations_ms) == 1
