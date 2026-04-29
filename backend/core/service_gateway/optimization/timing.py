"""DSPy callback that records per-call latency for a single LM instance.

Used by :class:`DspyService` to measure the wall-clock time spent inside
the generation LM (excluding the reflection LM that GEPA routes through
the same ``dspy.context``). Identity-filtered so other LMs sharing the
context never contaminate the timing summary.
"""

import threading
import time
from typing import Any

from dspy.utils.callback import BaseCallback


class GenLMTimingCallback(BaseCallback):
    """DSPy callback that records per-call latency for a single LM instance.

    Filters by object identity so only calls on the generation LM are timed;
    reflection-LM calls routed through the same dspy.context are ignored.
    """

    def __init__(self, target_lm: Any) -> None:
        """Store the identity of the LM to time so other LMs routed here are ignored.

        Args:
            target_lm: The DSPy LM whose calls should be timed; identity is
                captured so unrelated LMs sharing the same context are
                excluded from the duration list.
        """
        # ``id()`` is safe here because the optimization driver keeps
        # ``target_lm`` alive for the entire timing window — the callback
        # is registered before the first call and unregistered after the
        # last. No weakref is needed; the LM cannot be garbage-collected
        # and reissued under the same id() during the window.
        self._target_id = id(target_lm)
        self._starts: dict[str, float] = {}
        self.durations_ms: list[float] = []
        self._lock = threading.Lock()

    def on_lm_start(self, call_id: str, instance: Any, inputs: dict[str, Any]) -> None:
        """Record the start time when the tracked LM begins a call; ignore others.

        Args:
            call_id: Unique identifier DSPy assigns to the in-flight call.
            instance: The LM instance issuing the call.
            inputs: The input payload DSPy is about to send (unused).
        """
        if id(instance) != self._target_id:
            return
        self._starts[call_id] = time.monotonic()

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ) -> None:
        """Append the elapsed duration for calls that had a matching start.

        Calls without a matching start (e.g. reflection LM) are silently skipped.

        Args:
            call_id: Unique identifier DSPy assigned at call-start time.
            outputs: The LM's response payload, or ``None`` on error.
            exception: Exception raised by the LM, if any.
        """
        start = self._starts.pop(call_id, None)
        if start is None:
            return
        duration_ms = (time.monotonic() - start) * 1000.0
        with self._lock:
            self.durations_ms.append(duration_ms)

    def summary(self) -> tuple[int, float | None]:
        """Return ``(num_calls, avg_ms)``. ``avg_ms`` is ``None`` if no calls were recorded.

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
