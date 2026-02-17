import threading as _threading
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional

from ..constants import (
    PROGRESS_OPTIMIZER,
    TQDM_DESC_KEY,
    TQDM_ELAPSED_KEY,
    TQDM_N_KEY,
    TQDM_PERCENT_KEY,
    TQDM_RATE_KEY,
    TQDM_REMAINING_KEY,
    TQDM_TOTAL_KEY
)

# Module-level state for concurrency-safe tqdm patching.
# Only the first concurrent caller installs the patch; the last removes it.
# Each thread stores its own callback in _tqdm_thread_local.
_tqdm_capture_lock = _threading.Lock()
_tqdm_capture_refs: int = 0
_tqdm_original: Any = None
_tqdm_auto_original: Any = None
_tqdm_thread_local = _threading.local()


def _thread_aware_wrap(original_factory: Callable[..., Any]) -> Callable[..., Any]:
    """Return a tqdm factory that dispatches to the calling thread's callback.

    Args:
        original_factory: The real tqdm class/factory to wrap.

    Returns:
        Callable[..., Any]: Wrapper that routes to the per-thread callback.
    """

    @wraps(original_factory)
    def _create(*args: Any, **kwargs: Any) -> Any:
        callback = getattr(_tqdm_thread_local, "progress_callback", None)
        bar = original_factory(*args, **kwargs)
        if callback is None:
            return bar
        return _TqdmProxy(bar, callback)

    for attr in ("_instances", "monitor_interval", "monitor", "status_printer"):
        if hasattr(original_factory, attr):
            setattr(_create, attr, getattr(original_factory, attr))

    return _create


@contextmanager
def capture_tqdm(progress_callback: Optional[Callable[[str, dict[str, Any]], None]]):
    """Relay tqdm progress updates to the provided callback, concurrency-safe.

    Uses a reference count so the global tqdm patch is installed once (by the
    first concurrent caller) and removed once (by the last). Each thread
    registers its own callback via threading.local, so concurrent jobs never
    receive each other's progress events.

    Args:
        progress_callback: Callable invoked with progress events.

    Returns:
        Context manager that cleans up per-thread state on exit.
    """

    if progress_callback is None:
        yield
        return

    try:
        import tqdm
        from tqdm import auto as tqdm_auto
    except ImportError:
        yield
        return

    global _tqdm_capture_refs, _tqdm_original, _tqdm_auto_original

    _tqdm_thread_local.progress_callback = progress_callback

    with _tqdm_capture_lock:
        _tqdm_capture_refs += 1
        if _tqdm_capture_refs == 1:
            _tqdm_original = tqdm.tqdm
            _tqdm_auto_original = tqdm_auto.tqdm
            tqdm.tqdm = _thread_aware_wrap(_tqdm_original)
            tqdm_auto.tqdm = _thread_aware_wrap(_tqdm_auto_original)

    try:
        yield
    finally:
        _tqdm_thread_local.progress_callback = None
        with _tqdm_capture_lock:
            _tqdm_capture_refs -= 1
            if _tqdm_capture_refs == 0:
                tqdm.tqdm = _tqdm_original
                tqdm_auto.tqdm = _tqdm_auto_original


class _TqdmProxy:
    """Proxy that forwards attribute access to the wrapped tqdm instance."""

    def __init__(self, bar: Any, callback: Callable[[str, dict[str, Any]], None]):
        """Create a proxy that emits optimizer progress events.

        Args:
            bar: tqdm progress bar being wrapped.
            callback: Callable receiving progress updates.

        Returns:
            None
        """

        self._bar = bar
        self._callback = callback
        self._last_metrics: dict[str, Any] | None = None
        self._emit_enabled = self._is_gepa_bar(
            bar, getattr(bar, "desc", None)
        )
        self._emit(PROGRESS_OPTIMIZER, force=True)

    def update(self, n: int = 1) -> Any:
        """Advance the progress bar and emit a telemetry event.

        Args:
            n: Step size passed through to tqdm.update.

        Returns:
            Any: Result returned by the wrapped update call.
        """

        result = self._bar.update(n)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def close(self) -> Any:
        """Close the progress bar and emit a telemetry event.

        Args:
            None.

        Returns:
            Any: Result returned by tqdm.close.
        """

        result = self._bar.close()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def refresh(self) -> Any:
        """Refresh the progress bar display and emit a telemetry event.

        Args:
            None.

        Returns:
            Any: Result returned by tqdm.refresh.
        """

        result = self._bar.refresh()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def __getattr__(self, item: str) -> Any:
        """Fallback attribute access to the underlying tqdm instance.

        Args:
            item: Attribute name.

        Returns:
            Any: Attribute retrieved from the wrapped tqdm bar.
        """

        return getattr(self._bar, item)

    def __enter__(self) -> "_TqdmProxy":
        """Support context-manager entry by delegating to tqdm.

        Args:
            None.

        Returns:
            _TqdmProxy: Self reference for context manager compatibility.
        """

        self._bar.__enter__()
        return self

    def __iter__(self):
        """Allow iteration so tqdm proxies work inside for-loops.

        Args:
            None.

        Returns:
            Iterator[Any]: Iterator yielded by the wrapped tqdm object.
        """

        return iter(self._bar)

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        """Support context-manager exit while emitting telemetry.

        Args:
            exc_type: Exception type if one occurred.
            exc_value: Exception instance if raised.
            traceback: Traceback object for the exception.

        Returns:
            Any: Result from the wrapped __exit__ call.
        """

        result = self._bar.__exit__(exc_type, exc_value, traceback)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def _emit(self, event: str, *, force: bool = False) -> None:
        """Emit a progress update using the stored callback.

        Args:
            event: Event name describing the update.
            force: When True, bypass duplicate-metric suppression.

        Returns:
            None
        """

        desc = getattr(self._bar, "desc", None)
        if self._is_gepa_bar(self._bar, desc):
            self._emit_enabled = True
        elif self._looks_like_nested_bar(desc):
            return
        elif not self._emit_enabled:
            return

        format_dict = getattr(self._bar, "format_dict", {}) or {}

        total = getattr(self._bar, "total", None)
        current = getattr(self._bar, "n", None)
        percent = None
        if total and current is not None and total > 0:
            percent = 100.0 * (current / total)
        metrics = {
            TQDM_TOTAL_KEY: total,
            TQDM_N_KEY: current,
            TQDM_ELAPSED_KEY: format_dict.get("elapsed"),
            TQDM_RATE_KEY: format_dict.get("rate"),
            TQDM_REMAINING_KEY: format_dict.get("remaining"),
            TQDM_PERCENT_KEY: percent,
            TQDM_DESC_KEY: desc,
        }
        if not force and metrics == self._last_metrics:
            return
        self._last_metrics = dict(metrics)
        self._callback(event, metrics)

    @staticmethod
    def _desc_mentions_gepa(desc: Any) -> bool:
        """Return True when desc looks like GEPA's top-level progress bar.

        Args:
            desc: tqdm ``desc`` attribute to inspect.

        Returns:
            bool: True when the description references GEPA.
        """

        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("gepa")

    @staticmethod
    def _is_gepa_bar(bar: Any, desc: Any) -> bool:
        """Heuristically determine whether this tqdm bar is GEPA's top-level bar.

        Args:
            bar: tqdm instance currently being proxied.
            desc: tqdm description string (may be ``None``).

        Returns:
            bool: True when the bar appears to represent GEPA's main progress.
        """

        if _TqdmProxy._desc_mentions_gepa(desc):
            return True

        unit = getattr(bar, "unit", None)
        if isinstance(unit, str) and unit.strip().lower() == "rollouts":
            return True
        return False

    @staticmethod
    def _looks_like_nested_bar(desc: Any) -> bool:
        """Identify inner tqdm bars we intentionally suppress (e.g., Average Metric).

        Args:
            desc: tqdm description string to inspect.

        Returns:
            bool: True when the bar should be suppressed to avoid noise.
        """

        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("average metric")
