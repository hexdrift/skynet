"""Job lifecycle notifications.

Sends Hebrew messages to the internal comms service when jobs are
submitted or completed.
"""

import logging
import os
from typing import Optional

from .comms import send_message

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3001")


def _job_url(job_id: str) -> str:
    """Build a link to the job detail page."""
    return f"{FRONTEND_URL}/jobs/{job_id}"


def notify_job_started(
    job_id: str,
    username: str,
    job_type: str,
    optimizer_name: str,
    module_name: str,
    model_name: Optional[str] = None,
) -> None:
    """Send a notification when a job is submitted.

    Args:
        job_id: Unique job identifier.
        username: User who submitted the job.
        job_type: "run" or "grid_search".
        optimizer_name: Optimizer being used.
        module_name: DSPy module being optimized.
        model_name: LLM model name (if applicable).
    """
    type_label = "חיפוש רשת" if job_type == "grid_search" else "הרצה"
    model_part = f" | מודל: {model_name}" if model_name else ""
    link = _job_url(job_id)

    text = (
        f"🚀 *אופטימיזציה חדשה*\n"
        f"משתמש: *{username}*\n"
        f"סוג: {type_label} | מודול: {module_name} | אופטימייזר: {optimizer_name}{model_part}\n"
        f"[מעקב אחר המשימה]({link})"
    )

    send_message(text)


def notify_job_completed(
    job_id: str,
    username: str,
    status: str,
    message: Optional[str] = None,
    baseline_score: Optional[float] = None,
    optimized_score: Optional[float] = None,
) -> None:
    """Send a notification when a job finishes.

    Args:
        job_id: Unique job identifier.
        username: User who submitted the job.
        status: Final status ("success", "failed", "cancelled").
        message: Status message from the backend.
        baseline_score: Baseline test metric (if available).
        optimized_score: Optimized test metric (if available).
    """
    link = _job_url(job_id)

    if status == "success":
        scores = ""
        if baseline_score is not None and optimized_score is not None:
            improvement = optimized_score - baseline_score
            scores = f"\nציון: {baseline_score:.1f}% → {optimized_score:.1f}% ({'+' if improvement >= 0 else ''}{improvement:.1f}%)"
        text = (
            f"✅ *אופטימיזציה הושלמה בהצלחה*\n"
            f"משתמש: *{username}*{scores}\n"
            f"[צפייה בתוצאות]({link})"
        )
    elif status == "cancelled":
        text = (
            f"⚠️ *אופטימיזציה בוטלה*\n"
            f"משתמש: *{username}*\n"
            f"[פרטי המשימה]({link})"
        )
    else:
        error_part = f"\nשגיאה: {message[:150]}" if message else ""
        text = (
            f"❌ *אופטימיזציה נכשלה*\n"
            f"משתמש: *{username}*{error_part}\n"
            f"[פרטי המשימה]({link})"
        )

    send_message(text)
