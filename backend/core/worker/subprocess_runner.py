"""Subprocess-side entry point for DSPy optimization jobs.

Houses the code that runs inside the child process forked/spawned by
``BackgroundWorker`` — the log handler, the event-queue helpers, and
the ``_run_service_in_subprocess`` function itself. Kept in its own
module so ``engine.py`` can stay focused on the parent-side worker
lifecycle.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..constants import OPTIMIZATION_TYPE_GRID_SEARCH, OPTIMIZATION_TYPE_RUN
from ..models import GridSearchRequest, RunRequest
from ..registry import ServiceRegistry
from ..service_gateway import DspyService

EVENT_PROGRESS = "progress"
EVENT_LOG = "log"
EVENT_RESULT = "result"
EVENT_ERROR = "error"

# Populated by the parent via ``set_fork_service`` before forking so
# child processes can reuse the same registry-backed service.
_FORK_SERVICE: Optional[DspyService] = None


def set_fork_service(service: Optional[DspyService]) -> None:
    """Store a service instance that child processes may reuse after fork.

    Args:
        service: The DspyService instance to share, or ``None`` to clear.

    Returns:
        None.
    """
    global _FORK_SERVICE
    _FORK_SERVICE = service


def safe_queue_put(event_queue: Any, event: Dict[str, Any]) -> None:
    """Put an event onto a multiprocessing queue, suppressing errors.

    Args:
        event_queue: Multiprocessing queue to write to.
        event: Event dictionary to enqueue.

    Returns:
        None.
    """
    try:
        event_queue.put(event)
    except Exception:
        # Parent may have already torn down the queue during cancellation/shutdown.
        pass


class SubprocessLogHandler(logging.Handler):
    """Forward DSPy logs from the subprocess to the parent worker."""

    def __init__(self, event_queue: Any) -> None:
        """Initialize the subprocess log handler.

        Args:
            event_queue: Multiprocessing queue for forwarding log events.
        """
        super().__init__()
        self._event_queue = event_queue

    def emit(self, record: logging.LogRecord) -> None:
        """Format and forward a log record to the parent process via the event queue.

        Args:
            record: Log record to forward.

        Returns:
            None.
        """
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
            },
        )


def run_service_in_subprocess(
    payload_dict: Dict[str, Any],
    artifact_id: str,
    event_queue: Any,
    start_method: str,
) -> None:
    """Execute a DSPy run in a child process and stream events to parent.

    Args:
        payload_dict: Serialized request payload including a ``_optimization_type`` key.
        artifact_id: Identifier used for storing optimization artifacts.
        event_queue: Multiprocessing queue for streaming progress, log, and
            result events back to the parent process.
        start_method: Multiprocessing start method (e.g. "fork", "spawn").

    Returns:
        None.
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
        optimization_type = payload_dict.pop("_optimization_type", OPTIMIZATION_TYPE_RUN)

        def progress_callback(message: str, metrics: Dict[str, Any]) -> None:
            """Forward a progress event from the optimizer to the parent queue.

            Args:
                message: Short event name describing the progress step.
                metrics: Structured metrics payload accompanying the event.

            Returns:
                None.
            """
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
