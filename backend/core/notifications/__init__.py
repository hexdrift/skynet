"""Job lifecycle notification public surface.

Re-exports the two top-level helpers used by the worker and API layers when
a job is submitted or finishes; the underlying transport (Slack / Teams /
Rocket.Chat / etc.) is encapsulated in ``core.notifications.comms``.
"""

from .notifier import notify_job_completed, notify_job_started

__all__ = ["notify_job_completed", "notify_job_started"]
