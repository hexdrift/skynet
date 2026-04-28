"""Event-type discriminators for the subprocess → parent worker queue.

These four strings tag every dict the subprocess runner pushes onto the
shared :class:`multiprocessing.Queue`. :class:`BackgroundWorker` dispatches
on them in its event-consume loop. They are an internal contract between
:mod:`subprocess_runner` and :mod:`engine` — not a wire-level value seen
outside the worker package.
"""

from __future__ import annotations

EVENT_PROGRESS = "progress"
EVENT_LOG = "log"
EVENT_RESULT = "result"
EVENT_ERROR = "error"
