"""tqdm patcher that relays optimizer progress to a structured callback.

DSPy's optimizers print progress with tqdm bars; this module wraps the
process-wide ``tqdm.tqdm`` factory so each bar feeds a thread-local
callback while the surrounding optimization runs. Reference-counted so
concurrent grid-search pairs share the patch and only the GEPA top-level
bar emits — inner ``Average Metric`` bars are suppressed.
"""

from __future__ import annotations

import threading as _threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

import tqdm
import tqdm.auto as tqdm_auto

from ...constants import (
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


def _thread_aware_tqdm_create(original_factory: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Instantiate ``original_factory`` and wrap it in _TqdmProxy when a thread-local callback is set.

    The first positional argument is the underlying tqdm factory so this
    function can be bound with ``functools.partial`` in
    ``_thread_aware_wrap``; the rest are forwarded to the real factory
    unchanged.

    Args:
        original_factory: The real tqdm factory being wrapped.
        *args: Positional arguments forwarded to ``original_factory``.
        **kwargs: Keyword arguments forwarded to ``original_factory``.

    Returns:
        The created tqdm bar (wrapped in :class:`_TqdmProxy` when a
        thread-local callback is set, otherwise returned unchanged).
    """
    callback = getattr(_tqdm_thread_local, "progress_callback", None)
    bar = original_factory(*args, **kwargs)
    if callback is None:
        return bar
    return _TqdmProxy(bar, callback)


def _thread_aware_wrap(original_factory: Callable[..., Any]) -> Callable[..., Any]:
    """Return a tqdm factory that wraps bars in _TqdmProxy for the calling thread's callback.

    Built as a ``functools.partial`` bound to ``_thread_aware_tqdm_create``
    so no closure is created. Class-level attributes tqdm consumers expect
    (``_instances``, ``monitor_interval``, ``monitor``, ``status_printer``)
    are copied onto the partial so callers that poke at the factory (e.g.
    tqdm's own monitor thread) keep working.

    Args:
        original_factory: The real tqdm factory to wrap.

    Returns:
        A drop-in factory that emits structured progress events when the
        calling thread has a callback installed.
    """
    wrapper = partial(_thread_aware_tqdm_create, original_factory)
    for attr in ("_instances", "monitor_interval", "monitor", "status_printer"):
        if hasattr(original_factory, attr):
            setattr(wrapper, attr, getattr(original_factory, attr))
    return wrapper


@contextmanager
def capture_tqdm(progress_callback: Callable[[str, dict[str, Any]], None] | None):
    """Patch tqdm globally (ref-counted) and relay updates to this thread's callback.

    The patch is installed on first entry and removed on last exit, making it
    safe for concurrent callers in separate threads.  Each thread stores its own
    callback in thread-local storage so progress events are not cross-wired.
    Passing ``None`` is a no-op.

    Args:
        progress_callback: Callback receiving ``(event, metrics)`` tuples,
            or ``None`` to disable patching for this scope.

    Yields:
        Control while the patch is active.
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

    Proxy pattern: ``__getattr__`` is defined so every tqdm attribute not
    explicitly overridden here (``write``, ``set_description``, ``n``, ``total``,
    ``format_dict``, ...) is forwarded unchanged to the wrapped bar. DSPy and
    tqdm internals poke at many attributes we don't statically know about, so
    dynamic delegation is required — a fixed whitelist of methods would silently
    break whenever tqdm or a caller reaches for a new attribute.
    """

    def __init__(self, bar: Any, callback: Callable[[str, dict[str, Any]], None]):
        """Wrap a tqdm bar and emit an initial progress event if the bar is a GEPA bar.

        Args:
            bar: The wrapped tqdm bar instance.
            callback: Callback invoked with ``(event, metrics)`` per emission.
        """
        self._bar = bar
        self._callback = callback
        self._last_metrics: dict[str, Any] | None = None
        self._emit_enabled = self._is_gepa_bar(bar, getattr(bar, "desc", None))
        self._emit(PROGRESS_OPTIMIZER, force=True)

    def update(self, n: int = 1) -> Any:
        """Advance the bar by n steps and emit a progress event if metrics changed.

        Args:
            n: Step count to advance the bar.

        Returns:
            Whatever the wrapped bar's ``update`` returns.
        """
        result = self._bar.update(n)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def close(self) -> Any:
        """Close the bar and emit a final progress event.

        Returns:
            Whatever the wrapped bar's ``close`` returns.
        """
        result = self._bar.close()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def refresh(self) -> Any:
        """Refresh the bar display and emit a progress event if metrics changed.

        Returns:
            Whatever the wrapped bar's ``refresh`` returns.
        """
        result = self._bar.refresh()
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def __getattr__(self, item: str) -> Any:
        """Delegate unknown attribute access to the wrapped bar.

        Args:
            item: Attribute name being looked up.

        Returns:
            The corresponding attribute on the wrapped bar.
        """
        return getattr(self._bar, item)

    def __enter__(self) -> _TqdmProxy:
        """Enter the context manager, delegating to the wrapped bar.

        Returns:
            This proxy instance for use in ``with`` blocks.
        """
        self._bar.__enter__()
        return self

    def __iter__(self) -> Iterator[Any]:
        """Iterate over the wrapped bar.

        Returns:
            An iterator over the wrapped bar's items.
        """
        return iter(self._bar)

    def __exit__(self, exc_type, exc_value, traceback) -> Any:
        """Exit the context manager, emit a final event, and delegate to the wrapped bar.

        Args:
            exc_type: Exception class if the block raised, else ``None``.
            exc_value: Exception instance if the block raised, else ``None``.
            traceback: Traceback if the block raised, else ``None``.

        Returns:
            Whatever the wrapped bar's ``__exit__`` returns.
        """
        result = self._bar.__exit__(exc_type, exc_value, traceback)
        self._emit(PROGRESS_OPTIMIZER)
        return result

    def _emit(self, event: str, *, force: bool = False) -> None:
        """Compute current metrics and invoke the callback if they have changed.

        ``force=True`` emits even if metrics are identical to the last emission.

        Args:
            event: Event name forwarded to the callback.
            force: Emit even when metrics are unchanged from the last call.
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
        """Return True when desc starts with 'gepa' (case-insensitive).

        Args:
            desc: The bar's description string.

        Returns:
            True when the description begins with ``"gepa"``.
        """
        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("gepa")

    @staticmethod
    def _is_gepa_bar(bar: Any, desc: Any) -> bool:
        """Return True when the bar is GEPA's top-level bar.

        Args:
            bar: The wrapped tqdm bar.
            desc: The bar's description string.

        Returns:
            True when the bar identifies as GEPA's top-level progress bar
            (desc starts with ``"gepa"`` or the bar's unit is ``"rollouts"``).
        """
        if _TqdmProxy._desc_mentions_gepa(desc):
            return True

        unit = getattr(bar, "unit", None)
        return bool(isinstance(unit, str) and unit.strip().lower() == "rollouts")

    @staticmethod
    def _looks_like_nested_bar(desc: Any) -> bool:
        """Return True for inner bars we suppress (e.g., 'Average Metric').

        Args:
            desc: The bar's description string.

        Returns:
            True when the description marks the bar as an inner aggregate
            (such as ``"Average Metric"``) we want to suppress.
        """
        if not isinstance(desc, str):
            return False
        normalized = desc.strip().lower()
        return normalized.startswith("average metric")
