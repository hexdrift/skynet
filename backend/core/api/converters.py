"""Convert raw job store dicts to API response model fields."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..constants import (
    OPTIMIZATION_TYPE_RUN,
    PAYLOAD_OVERVIEW_COLUMN_MAPPING,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_DESCRIPTION,
    PAYLOAD_OVERVIEW_GENERATION_MODELS,
    PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_REFLECTION_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODELS,
    PAYLOAD_OVERVIEW_TASK_MODEL,
    PAYLOAD_OVERVIEW_TOTAL_PAIRS,
    PAYLOAD_OVERVIEW_USERNAME,
    TQDM_REMAINING_KEY,
)
from ..models import OptimizationStatus

logger = logging.getLogger(__name__)


def status_to_job_status(status: str) -> OptimizationStatus:
    """Convert a raw status string to an OptimizationStatus enum, defaulting to pending.

    Args:
        status: Raw status string from the job store.

    Returns:
        The matching OptimizationStatus, or ``pending`` if the value is unrecognised.
    """
    try:
        return OptimizationStatus(status)
    except ValueError:
        return OptimizationStatus.pending


def parse_timestamp(val: Any) -> datetime | None:
    """Parse a timestamp value into a timezone-aware datetime.

    Args:
        val: A datetime instance, an ISO-8601 string (with optional ``Z`` suffix),
            or ``None``/empty string.

    Returns:
        A datetime object, or ``None`` if the input is absent or unparseable.
    """
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _seconds_to_hhmmss(seconds: float) -> str:
    """Format a duration in seconds as ``HH:MM:SS``.

    Args:
        seconds: Non-negative duration in seconds.

    Returns:
        Zero-padded ``HH:MM:SS`` string.
    """
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _compute_elapsed_raw(
    created_at: datetime,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> float | None:
    """Return elapsed seconds between the job reference point and now or completion.

    Uses ``started_at`` as the reference if available; falls back to ``created_at``.
    Returns ``None`` when the job has not started yet.

    Args:
        created_at: Job creation timestamp.
        started_at: Timestamp when the job began execution, if any.
        completed_at: Timestamp when the job finished, if any.

    Returns:
        Elapsed seconds (clamped to 0), or ``None`` if the job hasn't started.
    """
    ref = started_at or created_at
    if completed_at is not None:
        return max(0.0, (completed_at - ref).total_seconds())
    if started_at is not None:
        now = datetime.now(timezone.utc)
        ref_utc = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ref_utc).total_seconds())
    return None


def compute_elapsed(
    created_at: datetime,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> tuple[str | None, float | None]:
    """Return a formatted elapsed string and raw seconds for a job.

    Args:
        created_at: Job creation timestamp.
        started_at: Timestamp when the job began execution, if any.
        completed_at: Timestamp when the job finished, if any.

    Returns:
        A ``(HH:MM:SS string, float seconds)`` pair, or ``(None, None)`` if the
        job has not started.
    """
    seconds = _compute_elapsed_raw(created_at, started_at, completed_at)
    if seconds is None:
        return None, None
    return _seconds_to_hhmmss(seconds), round(seconds, 2)


def parse_overview(job_data: dict) -> dict:
    """Extract and deserialize the ``payload_overview`` field from a job dict.

    Handles both pre-parsed dicts and JSON strings stored by older job rows.

    Args:
        job_data: Raw job dict from the job store.

    Returns:
        The overview as a plain dict, or an empty dict on any parse failure.
    """
    overview = job_data.get("payload_overview", {})
    if isinstance(overview, str):
        try:
            overview = json.loads(overview)
        except json.JSONDecodeError:
            logger.debug("Failed to parse payload_overview as JSON, using empty dict")
            overview = {}
    return overview


def extract_estimated_remaining(job_data: dict) -> str | None:
    """Read the tqdm-derived remaining-time metric and format it as ``HH:MM:SS``.

    Args:
        job_data: Raw job dict that may contain ``latest_metrics``.

    Returns:
        A formatted time string, or ``None`` if the metric is absent or negative.
    """
    metrics = job_data.get("latest_metrics") or {}
    val = metrics.get(TQDM_REMAINING_KEY)
    if isinstance(val, (int, float)) and val >= 0:
        return _seconds_to_hhmmss(val)
    return None


def overview_to_base_fields(overview: dict) -> dict:
    """Map payload-overview keys to the flat field names expected by response models.

    Args:
        overview: Deserialised payload overview dict.

    Returns:
        Dict of field names suitable for unpacking into response model constructors.
    """
    return {
        "optimization_type": overview.get(PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE, OPTIMIZATION_TYPE_RUN),
        "name": overview.get(PAYLOAD_OVERVIEW_NAME),
        "description": overview.get(PAYLOAD_OVERVIEW_DESCRIPTION),
        "pinned": overview.get("pinned", False),
        "archived": overview.get("archived", False),
        "username": overview.get(PAYLOAD_OVERVIEW_USERNAME),
        "module_name": overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
        "module_kwargs": overview.get(PAYLOAD_OVERVIEW_MODULE_KWARGS, {}),
        "optimizer_name": overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
        "column_mapping": overview.get(PAYLOAD_OVERVIEW_COLUMN_MAPPING),
        "dataset_rows": overview.get(PAYLOAD_OVERVIEW_DATASET_ROWS),
        "model_name": overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
        "model_settings": overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS),
        "reflection_model_name": overview.get(PAYLOAD_OVERVIEW_REFLECTION_MODEL),
        "task_model_name": overview.get(PAYLOAD_OVERVIEW_TASK_MODEL),
        "total_pairs": overview.get(PAYLOAD_OVERVIEW_TOTAL_PAIRS),
        "generation_models": overview.get(PAYLOAD_OVERVIEW_GENERATION_MODELS),
        "reflection_models": overview.get(PAYLOAD_OVERVIEW_REFLECTION_MODELS),
    }
