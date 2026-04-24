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
        self._target_id = id(target_lm)
        self._starts: dict[str, float] = {}
        self.durations_ms: list[float] = []
        self._lock = threading.Lock()

    def on_lm_start(self, call_id: str, instance: Any, inputs: dict[str, Any]) -> None:
        if id(instance) != self._target_id:
            return
        self._starts[call_id] = time.monotonic()

    def on_lm_end(
        self,
        call_id: str,
        outputs: dict[str, Any] | None,
        exception: Exception | None = None,
    ) -> None:
        start = self._starts.pop(call_id, None)
        if start is None:
            return
        duration_ms = (time.monotonic() - start) * 1000.0
        with self._lock:
            self.durations_ms.append(duration_ms)

    def summary(self) -> tuple[int, float | None]:
        """Return (num_calls, avg_ms). avg_ms is None if no calls were recorded."""
        with self._lock:
            n = len(self.durations_ms)
            if n == 0:
                return 0, None
            return n, round(sum(self.durations_ms) / n, 1)
