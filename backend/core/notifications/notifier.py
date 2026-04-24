"""Job lifecycle notifications.

Sends Hebrew messages to the internal comms service when jobs are
submitted or completed.
"""

import logging
import os

from ..constants import OPTIMIZATION_TYPE_GRID_SEARCH
from ..i18n import GRID_SEARCH_LABEL, RUN_LABEL, t
from .comms import send_message

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")


def _job_url(optimization_id: str) -> str:
    """Return the full URL for the optimization detail page."""
    return f"{FRONTEND_URL}/optimizations/{optimization_id}"


def notify_job_started(
    optimization_id: str,
    username: str,
    optimization_type: str,
    optimizer_name: str,
    module_name: str,
    model_name: str | None = None,
) -> None:
    """Send a Hebrew notification when a job is submitted."""
    type_label = GRID_SEARCH_LABEL if optimization_type == OPTIMIZATION_TYPE_GRID_SEARCH else RUN_LABEL
    model_part = f" | {t('notifier.label.model')}: {model_name}" if model_name else ""
    link = _job_url(optimization_id)

    text = (
        f"*{t('notifier.title.new')}*\n"
        f"{t('notifier.label.user')}: *{username}*\n"
        f"{t('notifier.label.type')}: {type_label} | "
        f"{t('notifier.label.module')}: {module_name} | "
        f"{t('notifier.label.optimizer')}: {optimizer_name}{model_part}\n"
        f"[{t('notifier.link.follow')}]({link})"
    )

    send_message(text)


def notify_job_completed(
    optimization_id: str,
    username: str,
    status: str,
    message: str | None = None,
    baseline_score: float | None = None,
    optimized_score: float | None = None,
) -> None:
    """Send a Hebrew notification when a job finishes (success, failed, or cancelled)."""
    link = _job_url(optimization_id)
    user_line = f"{t('notifier.label.user')}: *{username}*"

    if status == "success":
        scores = ""
        if baseline_score is not None and optimized_score is not None:
            improvement = optimized_score - baseline_score
            sign = "+" if improvement >= 0 else ""
            scores = (
                f"\n{t('notifier.label.score')}: "
                f"{baseline_score:.1f}% → {optimized_score:.1f}% "
                f"({sign}{improvement:.1f}%)"
            )
        text = (
            f"*{t('notifier.title.completed')}*\n{user_line}{scores}\n"
            f"[{t('notifier.link.results')}]({link})"
        )
    elif status == "cancelled":
        text = (
            f"*{t('notifier.title.cancelled')}*\n{user_line}\n"
            f"[{t('notifier.link.details')}]({link})"
        )
    else:
        error_part = f"\n{t('notifier.label.error')}: {message[:150]}" if message else ""
        text = (
            f"*{t('notifier.title.failed')}*\n{user_line}{error_part}\n"
            f"[{t('notifier.link.details')}]({link})"
        )

    send_message(text)
