from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ..converters import (
    compute_elapsed,
    extract_estimated_remaining,
    overview_to_base_fields,
    parse_overview,
    parse_timestamp,
    status_to_job_status,
)
from ...models import OptimizationStatus


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pending", OptimizationStatus.pending),
        ("validating", OptimizationStatus.validating),
        ("running", OptimizationStatus.running),
        ("success", OptimizationStatus.success),
        ("failed", OptimizationStatus.failed),
        ("cancelled", OptimizationStatus.cancelled),
    ],
    ids=["pending", "validating", "running", "success", "failed", "cancelled"],
)
def test_status_to_job_status_maps_valid_values(raw: str, expected: OptimizationStatus) -> None:
    """Each valid status string maps to the corresponding OptimizationStatus enum."""
    assert status_to_job_status(raw) == expected


def test_status_to_job_status_unknown_falls_back_to_pending() -> None:
    """Unrecognised status strings fall back to OptimizationStatus.pending."""
    assert status_to_job_status("nonsense") == OptimizationStatus.pending


def test_status_to_job_status_empty_string_falls_back_to_pending() -> None:
    """Empty string status falls back to OptimizationStatus.pending."""
    assert status_to_job_status("") == OptimizationStatus.pending



def test_parse_timestamp_returns_none_for_none() -> None:
    """None input returns None."""
    assert parse_timestamp(None) is None


def test_parse_timestamp_returns_none_for_empty_string() -> None:
    """Empty string returns None."""
    assert parse_timestamp("") is None


def test_parse_timestamp_passthrough_for_datetime() -> None:
    """An existing datetime is returned as-is (identity)."""
    dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    assert parse_timestamp(dt) is dt


def test_parse_timestamp_parses_iso_string_with_offset() -> None:
    """ISO-8601 string with explicit UTC offset is parsed to the correct datetime."""
    result = parse_timestamp("2024-01-15T12:00:00+00:00")
    assert isinstance(result, datetime)
    assert result.year == 2024 and result.month == 1 and result.day == 15


def test_parse_timestamp_parses_z_suffix() -> None:
    """ISO-8601 string ending in ``Z`` is treated as UTC."""
    result = parse_timestamp("2024-06-01T08:30:00Z")
    assert isinstance(result, datetime)
    assert result.hour == 8 and result.minute == 30


def test_parse_timestamp_returns_none_for_invalid_string() -> None:
    """A non-date string returns None."""
    assert parse_timestamp("not-a-date") is None


def test_parse_timestamp_returns_none_for_non_string_non_datetime() -> None:
    """An integer or other non-string/non-datetime type returns None."""
    assert parse_timestamp(42) is None



def _ts(y: int, m: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, m, d, h, mi, s, tzinfo=timezone.utc)


def test_compute_elapsed_not_started_returns_none_pair() -> None:
    """Job that has not started returns (None, None) for elapsed."""
    created = _ts(2024, 1, 1, 10, 0, 0)
    elapsed_str, elapsed_secs = compute_elapsed(created, started_at=None, completed_at=None)
    assert elapsed_str is None
    assert elapsed_secs is None


def test_compute_elapsed_completed_job_is_exact() -> None:
    """Completed job with known timestamps returns exact elapsed string and seconds."""
    created = _ts(2024, 1, 1, 10, 0, 0)
    started = _ts(2024, 1, 1, 10, 0, 0)
    completed = _ts(2024, 1, 1, 10, 1, 5)  # 65 seconds

    elapsed_str, elapsed_secs = compute_elapsed(created, started, completed)

    assert elapsed_str == "00:01:05"
    assert elapsed_secs == 65.0


def test_compute_elapsed_formats_hours_minutes_seconds() -> None:
    """Elapsed formats correctly as HH:MM:SS for multi-hour durations."""
    created = _ts(2024, 1, 1, 0, 0, 0)
    started = _ts(2024, 1, 1, 0, 0, 0)
    completed = _ts(2024, 1, 1, 2, 3, 7)  # 2h 3m 7s = 7387s

    elapsed_str, _ = compute_elapsed(created, started, completed)

    assert elapsed_str == "02:03:07"


def test_compute_elapsed_clamps_to_zero_for_completed_before_started() -> None:
    """Clock-skew where completed < started is clamped to 0.0 elapsed seconds."""
    # completed < started — edge case where clock skew could produce negatives
    created = _ts(2024, 1, 1, 10, 0, 0)
    started = _ts(2024, 1, 1, 10, 0, 5)
    completed = _ts(2024, 1, 1, 10, 0, 0)  # before started

    elapsed_str, elapsed_secs = compute_elapsed(created, started, completed)

    assert elapsed_secs == 0.0
    assert elapsed_str == "00:00:00"


def test_compute_elapsed_running_job_uses_wall_clock_and_is_positive() -> None:
    """Running job (no completed_at) uses current wall clock and returns a non-negative elapsed."""
    created = _ts(2024, 1, 1, 10, 0, 0)
    started = datetime.now(timezone.utc)  # just started
    elapsed_str, elapsed_secs = compute_elapsed(created, started, completed_at=None)

    assert elapsed_str is not None
    assert elapsed_secs is not None
    assert elapsed_secs >= 0.0



def test_parse_overview_returns_dict_when_already_dict() -> None:
    """payload_overview already a dict is returned unchanged."""
    job = {"payload_overview": {"job_type": "run"}}
    assert parse_overview(job) == {"job_type": "run"}


def test_parse_overview_parses_json_string() -> None:
    """JSON-string payload_overview is deserialized into a dict."""
    import json

    job = {"payload_overview": json.dumps({"job_type": "grid_search", "username": "alice"})}
    result = parse_overview(job)
    assert result["job_type"] == "grid_search"
    assert result["username"] == "alice"


def test_parse_overview_invalid_json_returns_empty_dict() -> None:
    """Unparseable JSON string returns an empty dict instead of raising."""
    job = {"payload_overview": "not-json{{"}
    assert parse_overview(job) == {}


def test_parse_overview_missing_key_returns_empty_dict() -> None:
    """Job dict without payload_overview returns an empty dict."""
    assert parse_overview({}) == {}



def test_extract_estimated_remaining_returns_formatted_seconds() -> None:
    """Integer remaining seconds in latest_metrics are formatted as HH:MM:SS."""
    from ...constants import TQDM_REMAINING_KEY

    job = {"latest_metrics": {TQDM_REMAINING_KEY: 125}}  # 2m 5s
    assert extract_estimated_remaining(job) == "00:02:05"


def test_extract_estimated_remaining_float_input() -> None:
    """Float remaining seconds are truncated to whole-second HH:MM:SS."""
    from ...constants import TQDM_REMAINING_KEY

    job = {"latest_metrics": {TQDM_REMAINING_KEY: 3661.9}}  # 1h 1m 1s
    assert extract_estimated_remaining(job) == "01:01:01"


def test_extract_estimated_remaining_zero_returns_formatted_zero() -> None:
    """Zero remaining seconds formats as ``00:00:00``."""
    from ...constants import TQDM_REMAINING_KEY

    job = {"latest_metrics": {TQDM_REMAINING_KEY: 0}}
    assert extract_estimated_remaining(job) == "00:00:00"


def test_extract_estimated_remaining_missing_key_returns_none() -> None:
    """Absent tqdm remaining key returns None."""
    assert extract_estimated_remaining({"latest_metrics": {}}) is None


def test_extract_estimated_remaining_none_metrics_returns_none() -> None:
    """None latest_metrics value returns None without raising."""
    assert extract_estimated_remaining({"latest_metrics": None}) is None


def test_extract_estimated_remaining_negative_value_returns_none() -> None:
    """Negative remaining value (e.g. clock drift) returns None."""
    from ...constants import TQDM_REMAINING_KEY

    job = {"latest_metrics": {TQDM_REMAINING_KEY: -5}}
    assert extract_estimated_remaining(job) is None



def test_overview_to_base_fields_defaults_type_to_run() -> None:
    """Empty overview defaults optimization_type to 'run'."""
    fields = overview_to_base_fields({})
    assert fields["optimization_type"] == "run"


def test_overview_to_base_fields_picks_up_job_type() -> None:
    """optimization_type key is mapped through to the output fields."""
    fields = overview_to_base_fields({"optimization_type": "grid_search"})
    assert fields["optimization_type"] == "grid_search"


def test_overview_to_base_fields_pinned_and_archived_default_false() -> None:
    """pinned and archived both default to False when absent from overview."""
    fields = overview_to_base_fields({})
    assert fields["pinned"] is False
    assert fields["archived"] is False


def test_overview_to_base_fields_passes_through_model_name() -> None:
    """model_name from overview is preserved in the output fields."""
    fields = overview_to_base_fields({"model_name": "gpt-4o-mini"})
    assert fields["model_name"] == "gpt-4o-mini"


def test_overview_to_base_fields_module_kwargs_defaults_to_empty_dict() -> None:
    """module_kwargs defaults to an empty dict when absent from overview."""
    fields = overview_to_base_fields({})
    assert fields["module_kwargs"] == {}



def test_overview_to_base_fields_only_optimization_type_key() -> None:
    """The canonical key is 'optimization_type' (PAYLOAD_OVERVIEW_OPTIMIZATION_TYPE constant)."""
    fields = overview_to_base_fields({"optimization_type": "grid_search"})
    assert fields["optimization_type"] == "grid_search"


def test_overview_to_base_fields_legacy_job_type_key_is_ignored() -> None:
    """The legacy 'job_type' key is NOT read by the converter; the default 'run'
    is returned when only 'job_type' is present.  This is intentional — the
    overview is normalised to 'optimization_type' before being stored.
    """
    fields = overview_to_base_fields({"job_type": "grid_search"})
    # 'job_type' is not the active key, so we get the default
    assert fields["optimization_type"] == "run"


def test_overview_to_base_fields_both_keys_optimization_type_wins() -> None:
    """When both keys exist, 'optimization_type' (the active key) takes precedence."""
    fields = overview_to_base_fields(
        {"optimization_type": "grid_search", "job_type": "run"}
    )
    assert fields["optimization_type"] == "grid_search"


def test_overview_to_base_fields_neither_key_defaults_to_run() -> None:
    """An overview with neither key present defaults to OPTIMIZATION_TYPE_RUN ('run')."""
    fields = overview_to_base_fields({})
    assert fields["optimization_type"] == "run"
