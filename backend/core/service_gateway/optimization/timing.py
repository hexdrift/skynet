"""DSPy callbacks that record per-call latency per LM, bucketed by run stage.

The two callbacks here (:class:`GenLMTimingCallback` and
:class:`ReflectionLMTimingCallback`) both filter calls by object identity
so other LMs sharing the same ``dspy.context`` cannot contaminate the
duration list. Each callback owns its current-stage state (mutated through
:func:`track_stage` under a per-callback lock) so DSPy worker threads see
the stage active on the driver thread. A ``contextvars.ContextVar`` was
deliberately rejected here: ``concurrent.futures.ThreadPoolExecutor``
workers — which DSPy's ``Evaluate`` uses — start with a fresh context, so
ContextVar values set on the driver thread would not reach callback
``on_lm_start`` calls running in workers, and the per-stage buckets would
silently stay empty.
"""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from dspy.utils.callback import BaseCallback

# Stage names used as keys in the ``stage_summary`` output and in the
# wire-level ``LMActivity`` payload. Kept stable — the frontend matches on
# these exact strings.
STAGE_BASELINE = "baseline"
STAGE_TRAINING = "training"
STAGE_EVALUATION = "evaluation"

STAGE_ORDER: tuple[str, ...] = (STAGE_BASELINE, STAGE_TRAINING, STAGE_EVALUATION)


class _LMStageTimingCallback(BaseCallback):
    """Shared base: time only the configured LM and bucket per active stage.

    Subclasses differ only in which LM identity to filter on; the actual
    timing logic, stage state, and bucketing live here.
    """

    def __init__(self, target_lm: Any) -> None:
        """Capture the identity of the LM to time and initialise empty buckets.

        Args:
            target_lm: The DSPy LM whose calls should be timed; identity is
                captured so unrelated LMs sharing the same context are
                excluded from the duration list.
        """
        # ``id()`` is safe because the optimization driver keeps ``target_lm``
        # alive for the entire timing window — the callback is registered
        # before the first call and unregistered after the last, so no
        # weakref is needed.
        self._target_id = id(target_lm)
        self._starts: dict[str, float] = {}
        self._stage_starts: dict[str, str | None] = {}
        self.durations_ms: list[float] = []
        self.stage_durations_ms: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # Stage state lives on the callback (not in a ContextVar) so it is
        # visible from DSPy's worker threads — see module docstring.
        self._current_stage: str | None = None

    def set_stage(self, stage: str | None) -> None:
        """Record the stage that subsequent ``on_lm_start`` calls should attribute to.

        Args:
            stage: Stage name, or ``None`` when no stage is active.
        """
        with self._lock:
            self._current_stage = stage

    def on_lm_start(self, call_id: str, instance: Any, inputs: dict[str, Any]) -> None:
        """Record start time and active stage for matching calls; ignore others.

        Args:
            call_id: Unique identifier DSPy assigns to the in-flight call.
            instance: The LM instance issuing the call.
            inputs: The input payload DSPy is about to send (unused).
        """
        if id(instance) != self._target_id:
            return
        with self._lock:
            stage = self._current_stage
        self._starts[call_id] = time.monotonic()
        # Snapshot the stage at start-time so a stage transition mid-call
        # doesn't misattribute the duration to the next bucket.
        self._stage_starts[call_id] = stage

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ) -> None:
        """Append the elapsed duration to the all-calls and per-stage buckets.

        Calls without a matching start (e.g. wrong LM identity) are silently skipped.

        Args:
            call_id: Unique identifier DSPy assigned at call-start time.
            outputs: The LM's response payload, or ``None`` on error.
            exception: Exception raised by the LM, if any.
        """
        start = self._starts.pop(call_id, None)
        if start is None:
            return
        stage = self._stage_starts.pop(call_id, None)
        duration_ms = (time.monotonic() - start) * 1000.0
        with self._lock:
            self.durations_ms.append(duration_ms)
            if stage is not None:
                self.stage_durations_ms.setdefault(stage, []).append(duration_ms)

    def summary(self) -> tuple[int, float | None]:
        """Return ``(num_calls, avg_ms)`` aggregated across all stages.

        Returns:
            A tuple of ``(num_calls, avg_ms)`` where ``avg_ms`` is the mean
            wall-clock duration in milliseconds rounded to one decimal, or
            ``None`` when no calls have been timed.
        """
        with self._lock:
            n = len(self.durations_ms)
            if n == 0:
                return 0, None
            return n, round(sum(self.durations_ms) / n, 1)

    def stage_summary(self) -> dict[str, tuple[int, float | None]]:
        """Return per-stage ``(num_calls, avg_ms)`` for every stage that recorded a call.

        Returns:
            A mapping from stage name to ``(num_calls, avg_ms)``. Stages
            that recorded zero calls are omitted; callers iterate
            :data:`STAGE_ORDER` to render zero rows.
        """
        out: dict[str, tuple[int, float | None]] = {}
        with self._lock:
            for stage, durations in self.stage_durations_ms.items():
                n = len(durations)
                if n == 0:
                    continue
                out[stage] = (n, round(sum(durations) / n, 1))
        return out


class GenLMTimingCallback(_LMStageTimingCallback):
    """Time calls on the generation LM only; bucket per active stage.

    Filters by object identity so only calls on the generation LM are
    timed — reflection-LM calls routed through the same dspy.context are
    ignored.
    """


class ReflectionLMTimingCallback(_LMStageTimingCallback):
    """Time calls on the reflection LM only; bucket per active stage.

    Mirror of :class:`GenLMTimingCallback` for the reflection LM that
    GEPA routes through the same dspy.context. Identity-filtered so the
    generation LM's calls never reach this callback's buckets.
    """


@contextmanager
def track_stage(
    name: str,
    *callbacks: _LMStageTimingCallback,
) -> Iterator[None]:
    """Set the active stage on each callback for the duration of a ``with`` block.

    Stage state lives on each callback (not in a ContextVar) so DSPy worker
    threads — which start with a fresh context when spawned by
    ``concurrent.futures.ThreadPoolExecutor`` — observe the value set on
    the driver thread. ``set_stage`` is only invoked here (on the driver
    thread); workers only read inside ``on_lm_start``, so there is no
    write-write race.

    Args:
        name: Stage identifier (typically one of :data:`STAGE_ORDER`).
            Callbacks bucket durations under this string.
        *callbacks: Timing callbacks to update. Pass none for a no-op
            (useful in tests that only need the call accounting).

    Yields:
        Control. The previous stage value on each callback is restored on
        exit even if the wrapped block raises.
    """
    previous: list[str | None] = [cb._current_stage for cb in callbacks]
    for cb in callbacks:
        cb.set_stage(name)
    try:
        yield
    finally:
        for cb, prev in zip(callbacks, previous):
            cb.set_stage(prev)
