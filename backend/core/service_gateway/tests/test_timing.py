"""Tests for ``core.service_gateway.optimization.timing`` callbacks and stage bucketing."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from core.service_gateway.optimization.timing import (
    STAGE_BASELINE,
    STAGE_EVALUATION,
    STAGE_TRAINING,
    GenLMTimingCallback,
    ReflectionLMTimingCallback,
    track_stage,
)


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


def test_stage_summary_empty_when_no_calls() -> None:
    """``stage_summary`` returns an empty dict when no calls were recorded."""
    cb = GenLMTimingCallback(_FakeLM())
    assert cb.stage_summary() == {}


def test_stage_summary_buckets_calls_by_active_stage() -> None:
    """Calls are attributed to the stage active at ``on_lm_start`` time."""
    target = _FakeLM()
    cb = GenLMTimingCallback(target)

    with track_stage(STAGE_BASELINE, cb):
        cb.on_lm_start("call-a", target, {})
        cb.on_lm_end("call-a", outputs={"ok": True})
    with track_stage(STAGE_TRAINING, cb):
        cb.on_lm_start("call-b", target, {})
        cb.on_lm_end("call-b", outputs={"ok": True})
        cb.on_lm_start("call-c", target, {})
        cb.on_lm_end("call-c", outputs={"ok": True})

    summary = cb.stage_summary()
    assert STAGE_BASELINE in summary
    assert STAGE_TRAINING in summary
    assert STAGE_EVALUATION not in summary
    assert summary[STAGE_BASELINE][0] == 1
    assert summary[STAGE_TRAINING][0] == 2


def test_stage_snapshot_at_start_survives_mid_call_transition() -> None:
    """A stage transition mid-call doesn't reattribute the duration to the next bucket."""
    # Snapshotting current_stage at on_lm_start prevents misattribution when
    # track_stage exits while a call is still in flight.
    target = _FakeLM()
    cb = GenLMTimingCallback(target)

    with track_stage(STAGE_BASELINE, cb):
        cb.on_lm_start("call-a", target, {})
    with track_stage(STAGE_TRAINING, cb):
        cb.on_lm_end("call-a", outputs={"ok": True})

    summary = cb.stage_summary()
    assert STAGE_BASELINE in summary
    assert STAGE_TRAINING not in summary
    assert summary[STAGE_BASELINE][0] == 1


def test_stage_summary_counts_match_all_call_total() -> None:
    """The sum of per-stage call counts equals the all-calls count."""
    target = _FakeLM()
    cb = GenLMTimingCallback(target)

    for stage, count in ((STAGE_BASELINE, 1), (STAGE_TRAINING, 3), (STAGE_EVALUATION, 2)):
        with track_stage(stage, cb):
            for i in range(count):
                cid = f"{stage}-{i}"
                cb.on_lm_start(cid, target, {})
                cb.on_lm_end(cid, outputs={})

    n_total, _ = cb.summary()
    per_stage_total = sum(s[0] for s in cb.stage_summary().values())
    assert per_stage_total == n_total == 6


def test_reflection_callback_filters_by_identity() -> None:
    """``ReflectionLMTimingCallback`` records only its own LM's calls."""
    gen_lm = _FakeLM()
    refl_lm = _FakeLM()
    refl_cb = ReflectionLMTimingCallback(refl_lm)

    refl_cb.on_lm_start("call-gen", gen_lm, {})
    refl_cb.on_lm_end("call-gen", outputs={})
    refl_cb.on_lm_start("call-refl", refl_lm, {})
    refl_cb.on_lm_end("call-refl", outputs={})

    assert len(refl_cb.durations_ms) == 1


def test_gen_and_reflection_callbacks_dont_cross_contaminate() -> None:
    """A shared dspy.context with both callbacks routes each call to the right bucket."""
    gen_lm = _FakeLM()
    refl_lm = _FakeLM()
    gen_cb = GenLMTimingCallback(gen_lm)
    refl_cb = ReflectionLMTimingCallback(refl_lm)

    with track_stage(STAGE_TRAINING, gen_cb, refl_cb):
        for cb in (gen_cb, refl_cb):
            cb.on_lm_start("call-1", gen_lm, {})
            cb.on_lm_end("call-1", outputs={})
            cb.on_lm_start("call-2", refl_lm, {})
            cb.on_lm_end("call-2", outputs={})

    assert gen_cb.summary()[0] == 1
    assert refl_cb.summary()[0] == 1


def test_track_stage_restores_previous_value_on_exit() -> None:
    """Nested ``track_stage`` blocks restore the outer stage on exit."""
    target = _FakeLM()
    cb = GenLMTimingCallback(target)
    with track_stage(STAGE_BASELINE, cb):
        with track_stage(STAGE_TRAINING, cb):
            cb.on_lm_start("call-inner", target, {})
            cb.on_lm_end("call-inner", outputs={})
        cb.on_lm_start("call-outer", target, {})
        cb.on_lm_end("call-outer", outputs={})
    summary = cb.stage_summary()
    assert summary[STAGE_BASELINE][0] == 1
    assert summary[STAGE_TRAINING][0] == 1


def test_stage_visible_from_worker_thread() -> None:
    """Stage set on driver thread is visible from a ThreadPoolExecutor worker.

    Regression: an earlier implementation used a ``ContextVar`` here, but
    ``concurrent.futures.ThreadPoolExecutor`` does NOT propagate the
    driver's context to workers — so ``current_stage.get()`` returned the
    default ``None`` and the per-stage buckets stayed silently empty.
    DSPy's ``Evaluate`` uses such an executor under the hood.
    """
    target = _FakeLM()
    cb = GenLMTimingCallback(target)

    def worker(call_id: str) -> None:
        cb.on_lm_start(call_id, target, {})
        cb.on_lm_end(call_id, outputs={"ok": True})

    with track_stage(STAGE_TRAINING, cb):
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(worker, [f"call-{i}" for i in range(8)]))

    summary = cb.stage_summary()
    assert STAGE_TRAINING in summary
    assert summary[STAGE_TRAINING][0] == 8
