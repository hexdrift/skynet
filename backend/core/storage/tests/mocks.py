"""Mock/fixture builders for storage tests.

``test_remote_jobstore.py`` uses a real in-memory SQLite engine and has no
MagicMocks — nothing to centralise there.  These helpers provide realistic
job-row dicts seeded from the live-captured fixture files, useful for future
storage tests that need to pre-populate rows without going through the store
interface.
"""

from __future__ import annotations

from tests.fixtures import load_fixture


def real_job_row_dict() -> dict:
    """Return a realistic GEPA-success job row keyed to ``JobModel`` columns."""
    # Keys mirror JobModel columns so a row can be inserted via raw dict without going
    # through the store interface (lets storage tests pre-seed without coupling to writes).
    detail = load_fixture("jobs/success_single_gepa.detail.json")
    return {
        "optimization_id": "fixture-gepa-success",
        "status": "success",
        "created_at": detail["created_at"],
        "started_at": detail["created_at"],
        "completed_at": detail["completed_at"],
        "estimated_remaining_seconds": None,
        "message": None,
        "latest_metrics": detail["latest_metrics"],
        "result": None,
        "payload_overview": {
            "username": "fixture-user",
            "optimization_type": "gepa",
            "dataset_rows": detail["dataset_rows"],
            "column_mapping": detail["column_mapping"],
        },
        "payload": None,
        "username": "fixture-user",
    }


def real_grid_job_row_dict() -> dict:
    """Return a realistic grid-search job row keyed to ``JobModel`` columns."""
    detail = load_fixture("jobs/success_grid.detail.json")
    return {
        "optimization_id": "fixture-grid-success",
        "status": "success",
        "created_at": detail["created_at"],
        "started_at": detail["created_at"],
        "completed_at": detail["completed_at"],
        "estimated_remaining_seconds": None,
        "message": None,
        "latest_metrics": detail["latest_metrics"],
        "result": detail.get("grid_result"),
        "payload_overview": {
            "username": "fixture-user",
            "optimization_type": "grid",
            "dataset_rows": detail["dataset_rows"],
            "column_mapping": detail["column_mapping"],
        },
        "payload": None,
        "username": "fixture-user",
    }


def real_failed_job_row_dict() -> dict:
    """Return a realistic failed-job row keyed to ``JobModel`` columns."""
    detail = load_fixture("jobs/failed_runtime.detail.json")
    return {
        "optimization_id": "fixture-failed-runtime",
        "status": "failed",
        "created_at": detail["created_at"],
        "started_at": detail["created_at"],
        "completed_at": detail["completed_at"],
        "estimated_remaining_seconds": None,
        "message": "LLM call failed — see logs for traceback",
        "latest_metrics": detail["latest_metrics"],
        "result": None,
        "payload_overview": {
            "username": "fixture-user",
            "optimization_type": "gepa",
            "dataset_rows": detail["dataset_rows"],
            "column_mapping": detail["column_mapping"],
        },
        "payload": None,
        "username": "fixture-user",
    }
