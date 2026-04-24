import threading as _threading
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import Any

import tqdm
import tqdm.auto as tqdm_auto

from ..constants import (
    PROGRESS_OPTIMIZER,
    TQDM_DESC_KEY,
    TQDM_ELAPSED_KEY,
    TQDM_N_KEY,
    TQDM_PERCENT_KEY,
    TQDM_RATE_KEY,
    TQDM_REMAINING_KEY,
    TQDM_TOTAL_KEY,
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
    """Return a tqdm factory that wraps bars in _TqdmProxy for the calling thread's callback."""

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
def capture_tqdm(progress_callback: Callable[[str, dict[str, Any]], None] | None):
    """Patch tqdm globally (ref-counted) and relay updates to this thread's callback.

    The patch is installed on first entry and removed on last exit, making it
    safe for concurrent callers in separate threads.  Each thread stores its own
    callback in thread-local storage so progress events are not cross-wired.

    Args:
        progress_callback: Callable receiving ``(event_name, metrics_dict)`` on
            each tqdm tick.  Passing ``None`` is a no-op.
    """

    if progress_callback is None:
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
    """Proxy that forwards attribute access to the wrapped tqdm instance.

    Wraps a live tqdm bar so that update/close/refresh calls emit structured
    progress events via the supplied callback.  Uses ref-counted global state
    (managed by ``capture_tqdm``) so concurrent pairs each patch tqdm only once
    and restore it when the last active context exits.

    Only GEPA-identified bars (desc starts with 'gepa' or unit='rollouts') emit
    events; inner bars like 'Average Metric' are suppressed to reduce noise.
    """

    def __init__(self, bar: Any, callback: Callable[[str, dict[str, Any]], None]):
        """Wrap a tqdm bar and emit an initial progress event if the bar is a GEPA bar.

        Args:
            bar: The underlying tqdm progress bar instance.
            callback: Callable receiving ``(event_name, metrics_dict)`` on each tick.
        """
        self._bar = bar
        self._callback = callback
        self._last_metrics: dict[str, Any] | None = None
        self._emit_enabled = self._is_gepa_bar(bar, getattr(bar, "desc", None))
        self._emit(PROGRESS_OPTIMIZER, force=True)

    def update(self, n: int = 1) -> Any:
        """Advance the bar by n steps and emit a progress event if metrics changed."""
        result = self._bar.update(n)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def close(self) -> Any:
        """Close the bar and emit a final progress event."""
        result = self._bar.close()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def refresh(self) -> Any:
        """Refresh the bar display and emit a progress event if metrics changed."""
        result = self._bar.refresh()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def __getattr__(self, item: str) -> Any:
        """Delegate unknown attribute access to the wrapped bar."""
        return getattr(self._bar, item)

    def __enter__(self) -> "_TqdmProxy":
        """Enter the context manager, delegating to the wrapped bar."""
        self._bar.__enter__()
        return self

    def __iter__(self):
        """Iterate over the wrapped bar."""
        return iter(self._bar)

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        """Exit the context manager, emit a final event, and delegate to the wrapped bar."""
        result = self._bar.__exit__(exc_type, exc_value, traceback)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def _emit(self, event: str, *, force: bool = False) -> None:
        """Compute current metrics and invoke the callback if they have changed.

        Args:
            event: Event name string passed as the first argument to the callback.
            force: When True, emit even if metrics are identical to the last emission.
        """
        desc = getattr(self._bar, "desc", None)
        if self._is_gepa_bar(self._bar, desc):
            self._emit_enabled = True
        elif self._looks_like_nested_bar(desc) or not self._emit_enabled:
            return

        format_dict = getattr(self._bar, "format_dict", {}) or {}

        total = getattr(self._bar, "total", None)
        current = getattr(self._bar, "n", None)
        rate = format_dict.get("rate")
        percent = None
        if total and current is not None and total > 0:
            percent = 100.0 * (current / total)
        remaining = None
        if total and current is not None and rate and rate > 0:
            remaining = (total - current) / rate
        metrics = {
            TQDM_TOTAL_KEY: total,
            TQDM_N_KEY: current,
            TQDM_ELAPSED_KEY: format_dict.get("elapsed"),
            TQDM_RATE_KEY: rate,
            TQDM_REMAINING_KEY: remaining,
            TQDM_PERCENT_KEY: percent,
            TQDM_DESC_KEY: desc,
        }
        if not force and metrics == self._last_metrics:
            return
        self._last_metrics = dict(metrics)
        self._callback(event, metrics)

    @staticmethod
    def _desc_mentions_gepa(desc: Any) -> bool:
        """Return True when desc starts with 'gepa' (case-insensitive)."""

        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("gepa")

    @staticmethod
    def _is_gepa_bar(bar: Any, desc: Any) -> bool:
        """Return True when the bar is GEPA's top-level bar (desc starts with 'gepa' or unit='rollouts')."""

        if _TqdmProxy._desc_mentions_gepa(desc):
            return True

        unit = getattr(bar, "unit", None)
        return bool(isinstance(unit, str) and unit.strip().lower() == "rollouts")

    @staticmethod
    def _looks_like_nested_bar(desc: Any) -> bool:
        """Return True for inner bars we suppress (e.g., 'Average Metric')."""

        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("average metric")
