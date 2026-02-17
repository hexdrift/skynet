"""Convert raw job store dicts to API response model fields."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..constants import (
    PAYLOAD_OVERVIEW_COLUMN_MAPPING,
    PAYLOAD_OVERVIEW_DATASET_ROWS,
    PAYLOAD_OVERVIEW_MODEL_NAME,
    PAYLOAD_OVERVIEW_MODEL_SETTINGS,
    PAYLOAD_OVERVIEW_MODULE_KWARGS,
    PAYLOAD_OVERVIEW_MODULE_NAME,
    PAYLOAD_OVERVIEW_OPTIMIZER_NAME,
    PAYLOAD_OVERVIEW_PROMPT_MODEL,
    PAYLOAD_OVERVIEW_REFLECTION_MODEL,
    PAYLOAD_OVERVIEW_TASK_MODEL,
    PAYLOAD_OVERVIEW_USERNAME,
)
from ..models import JobStatus

logger = logging.getLogger(__name__)


def status_to_job_status(status: str) -> JobStatus:
    """Map status string to JobStatus enum.

    Args:
        status: Status string from job store.

    Returns:
        JobStatus: Corresponding enum value.
    """
    try:
        return JobStatus(status)
    except ValueError:
        return JobStatus.pending


def parse_timestamp(val: Any) -> Optional[datetime]:
    """Convert value to datetime, handling None and ISO strings.

    Args:
        val: Raw value from job store (None, str, or datetime).

    Returns:
        Optional[datetime]: Parsed datetime or None.
    """
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return None


def compute_elapsed(
    created_at: datetime,
    started_at: Optional[datetime],
    completed_at: Optional[datetime],
) -> Optional[float]:
    """Compute elapsed seconds for a job.

    Args:
        created_at: Job creation time.
        started_at: Job start time (may be None).
        completed_at: Job completion time (may be None).

    Returns:
        Optional[float]: Elapsed seconds, or None if not started.
    """
    if completed_at is not None:
        return max(0.0, (completed_at - created_at).total_seconds())
    if started_at is not None:
        return max(0.0, (datetime.now(started_at.tzinfo) - started_at).total_seconds())
    return None


def parse_overview(job_data: dict) -> dict:
    """Extract and parse the payload_overview from job data.

    Args:
        job_data: Raw job dictionary from the store.

    Returns:
        dict: Parsed overview dictionary.
    """
    overview = job_data.get("payload_overview", {})
    if isinstance(overview, str):
        try:
            overview = json.loads(overview)
        except json.JSONDecodeError:
            logger.debug("Failed to parse payload_overview as JSON, using empty dict")
            overview = {}
    return overview


def overview_to_base_fields(overview: dict) -> dict:
    """Map overview keys to the shared _JobResponseBase field names.

    Args:
        overview: Parsed overview dictionary.

    Returns:
        dict: Keyword arguments for _JobResponseBase fields.
    """
    return {
        "username": overview.get(PAYLOAD_OVERVIEW_USERNAME),
        "module_name": overview.get(PAYLOAD_OVERVIEW_MODULE_NAME),
        "module_kwargs": overview.get(PAYLOAD_OVERVIEW_MODULE_KWARGS, {}),
        "optimizer_name": overview.get(PAYLOAD_OVERVIEW_OPTIMIZER_NAME),
        "model_name": overview.get(PAYLOAD_OVERVIEW_MODEL_NAME),
        "model_settings": overview.get(PAYLOAD_OVERVIEW_MODEL_SETTINGS),
        "reflection_model_name": overview.get(PAYLOAD_OVERVIEW_REFLECTION_MODEL),
        "prompt_model_name": overview.get(PAYLOAD_OVERVIEW_PROMPT_MODEL),
        "task_model_name": overview.get(PAYLOAD_OVERVIEW_TASK_MODEL),
        "column_mapping": overview.get(PAYLOAD_OVERVIEW_COLUMN_MAPPING),
        "dataset_rows": overview.get(PAYLOAD_OVERVIEW_DATASET_ROWS),
    }
