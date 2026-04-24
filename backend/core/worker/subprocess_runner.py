"""Subprocess-side entry point for DSPy optimization jobs.

Houses the code that runs inside the child process forked/spawned by
``BackgroundWorker`` — the log handler, the event-queue helpers, and
the ``_run_service_in_subprocess`` function itself. Kept in its own
module so ``engine.py`` can stay focused on the parent-side worker
lifecycle.
"""

import contextlib
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from ..constants import OPTIMIZATION_TYPE_GRID_SEARCH, OPTIMIZATION_TYPE_RUN
from ..models import GridSearchRequest, RunRequest
from ..registry import ServiceRegistry
from ..service_gateway import DspyService
from .log_handler import get_current_pair_index

EVENT_PROGRESS = "progress"
EVENT_LOG = "log"
EVENT_RESULT = "result"
EVENT_ERROR = "error"

# Populated by the parent via ``set_fork_service`` before forking so
# child processes can reuse the same registry-backed service.
_FORK_SERVICE: DspyService | None = None


def set_fork_service(service: DspyService | None) -> None:
    """Store a service instance that child processes may reuse after fork."""
    global _FORK_SERVICE
    _FORK_SERVICE = service


def safe_queue_put(event_queue: Any, event: dict[str, Any]) -> None:
    """Put an event onto a multiprocessing queue, suppressing any errors."""
    with contextlib.suppress(Exception):
        event_queue.put(event)


class SubprocessLogHandler(logging.Handler):
    """Forward DSPy log records from the child process to the parent via the event queue.

    Attached to the ``dspy`` logger inside ``run_service_in_subprocess`` and removed
    in the ``finally`` block so it does not persist across calls.  Each record is
    serialised into an ``EVENT_LOG`` dict and placed on the shared queue; errors
    from the queue are suppressed via ``safe_queue_put``.
    """

    def __init__(self, event_queue: Any) -> None:
        """Initialize the handler with the shared multiprocessing queue.

        Args:
            event_queue: Queue used to send ``EVENT_LOG`` events to the parent.
        """
        super().__init__()
        self._event_queue = event_queue

    def emit(self, record: logging.LogRecord) -> None:
        """Format and forward a log record to the parent process via the event queue."""
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        safe_queue_put(
            self._event_queue,
            {
                "type": EVENT_LOG,
                "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                "pair_index": get_current_pair_index(),
            },
        )


def run_service_in_subprocess(
    payload_dict: dict[str, Any],
    artifact_id: str,
    event_queue: Any,
    start_method: str,
) -> None:
    """Execute a DSPy optimization in the child process, streaming events back to the parent.

    This is the ``target`` function passed to ``mp.Process``.  It emits four event
    types onto ``event_queue``:

    - ``EVENT_LOG`` — every record from the ``dspy`` logger at INFO or above,
      forwarded via ``SubprocessLogHandler``.
    - ``EVENT_PROGRESS`` — one event per ``progress_callback`` invocation from the
      optimizer, carrying ``event`` (phase name) and ``metrics`` (dict).
    - ``EVENT_RESULT`` — emitted once on success, containing the serialised
      ``RunResponse`` or ``GridSearchResponse``.
    - ``EVENT_ERROR`` — emitted on any ``BaseException``, containing the error
      string and formatted traceback.

    When ``start_method == "fork"`` and ``_FORK_SERVICE`` is set, the pre-built
    service from the parent is reused directly; otherwise a fresh ``DspyService``
    is constructed.

    Args:
        payload_dict: Serialised job payload; ``_optimization_type`` key is popped
            before model validation.
        artifact_id: Passed through to ``service.run`` / ``service.run_grid_search``
            as the artifact storage identifier.
        event_queue: Multiprocessing queue used to stream events to the parent.
        start_method: The context start method (``"fork"`` or ``"spawn"``); controls
            whether ``_FORK_SERVICE`` is reused.
    """
    service = _FORK_SERVICE if start_method == "fork" and _FORK_SERVICE is not None else DspyService(ServiceRegistry())
    dspy_logger = logging.getLogger("dspy")
    saved_level = dspy_logger.level
    log_handler = SubprocessLogHandler(event_queue)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(message)s"))

    if dspy_logger.level == 0 or dspy_logger.level > logging.INFO:
        dspy_logger.setLevel(logging.INFO)
    dspy_logger.addHandler(log_handler)

    try:
        payload_dict = dict(payload_dict)
        optimization_type = payload_dict.pop("_optimization_type", OPTIMIZATION_TYPE_RUN)

        def progress_callback(message: str, metrics: dict[str, Any]) -> None:
            """Forward an optimizer progress event to the parent via the queue."""
            safe_queue_put(
                event_queue,
                {
                    "type": EVENT_PROGRESS,
                    "event": message,
                    "metrics": metrics or {},
                },
            )

        if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH:
            if not hasattr(service, "run_grid_search"):
                service = DspyService(ServiceRegistry())
            payload = GridSearchRequest.model_validate(payload_dict)
            result = service.run_grid_search(
                payload,
                artifact_id=artifact_id,
                progress_callback=progress_callback,
            )
        else:
            payload = RunRequest.model_validate(payload_dict)
            result = service.run(
                payload,
                artifact_id=artifact_id,
                progress_callback=progress_callback,
            )
        safe_queue_put(
            event_queue,
            {
                "type": EVENT_RESULT,
                "result": result.model_dump(mode="json"),
            },
        )
    except BaseException as exc:
        safe_queue_put(
            event_queue,
            {
                "type": EVENT_ERROR,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        dspy_logger.removeHandler(log_handler)
        dspy_logger.setLevel(saved_level)
