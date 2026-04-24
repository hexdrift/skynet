"""Unit tests for RemoteDBJobStore against an in-memory SQLite engine.

SQLite is used to avoid requiring a live Postgres instance for the fast CI gate.
The only Postgres-specific feature that cannot be emulated is the ``information_schema``
migration query inside ``RemoteDBJobStore.__init__``; this is bypassed by the
``SQLiteJobStore`` subclass defined in the module-level fixture below.

Two additional behaviours depend on a real Postgres instance and are explicitly skipped
here with a clear reason:
  - UTC timezone offset is NOT preserved by SQLite's ``DateTime`` column (it stores the
    wall-clock value as a naive string).  Tests that need timezone-aware comparisons are
    structured to compare the time *value* only.
  - The ``optimization_type`` JSON path filter (``payload_overview['optimization_type']``)
    uses ``.as_string()``, which does work on SQLite through SQLAlchemy's JSON accessor
    so those tests run normally.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import core.storage.remote as remote_mod
from core.storage.base import JobStore
from core.storage.models import Base, JobModel
from core.storage.remote import RemoteDBJobStore




class SQLiteJobStore(RemoteDBJobStore):
    """RemoteDBJobStore wired to an in-memory SQLite engine.

    Overrides only ``__init__`` to:
    - Use ``StaticPool`` (required for sqlite:///:memory: across multiple
      session factory calls to share one connection).
    - Skip the ``information_schema`` migration that is Postgres-specific.
    """

    def __init__(self, db_url: str = "sqlite:///:memory:") -> None:
        """Initialize with an in-memory SQLite engine, skipping the Postgres migration.

        Args:
            db_url: SQLAlchemy connection string; defaults to in-memory SQLite.
        """
        self._engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)




@pytest.fixture()
def store() -> SQLiteJobStore:
    """Return a fresh SQLiteJobStore with newly-created tables for each test."""
    s = SQLiteJobStore()
    yield s
    # Drop all tables so state doesn't leak between tests that share the same
    # in-memory engine handle (StaticPool reuses the connection).
    Base.metadata.drop_all(s.engine)




def test_create_job_returns_pending_status(store: SQLiteJobStore) -> None:
    """create_job() inserts a row with status=pending and the correct optimization_id."""
    result = store.create_job("job-create-1")
    assert result["status"] == "pending"
    assert result["optimization_id"] == "job-create-1"


def test_create_job_with_estimate_stored(store: SQLiteJobStore) -> None:
    """create_job() persists the estimated_remaining_seconds value."""
    result = store.create_job("job-create-2", estimated_remaining_seconds=60.0)
    assert result["estimated_remaining_seconds"] == 60.0


def test_create_job_is_retrievable(store: SQLiteJobStore) -> None:
    """After create_job(), job_exists() returns True for the new ID."""
    store.create_job("job-create-3")
    assert store.job_exists("job-create-3")


def test_create_job_created_at_is_iso_parseable(store: SQLiteJobStore) -> None:
    """create_job() stores a parseable ISO datetime in created_at."""
    result = store.create_job("job-create-4")
    # Real Postgres TIMESTAMPTZ preserves the +00:00 offset; SQLite's DateTime
    # column stores naive datetimes, so we only assert the value round-trips.
    assert result["created_at"] is not None
    datetime.fromisoformat(result["created_at"])


def test_create_job_default_fields_are_empty(store: SQLiteJobStore) -> None:
    """create_job() initializes optional fields to empty/None defaults."""
    result = store.create_job("job-create-5")
    assert result["latest_metrics"] == {}
    assert result["payload_overview"] == {}
    assert result["result"] is None
    assert result["message"] is None
    assert result["started_at"] is None
    assert result["completed_at"] is None




def test_get_job_raises_key_error_for_unknown(store: SQLiteJobStore) -> None:
    """get_job() raises KeyError when the ID does not exist in the database."""
    with pytest.raises(KeyError, match="no-such-job"):
        store.get_job("no-such-job")


def test_get_job_returns_correct_record(store: SQLiteJobStore) -> None:
    """get_job() returns the current state of the job after update_job()."""
    store.create_job("job-get-1")
    store.update_job("job-get-1", status="running")
    job = store.get_job("job-get-1")
    assert job["optimization_id"] == "job-get-1"
    assert job["status"] == "running"


def test_job_exists_true_after_create(store: SQLiteJobStore) -> None:
    """job_exists() returns True immediately after create_job()."""
    store.create_job("job-exists-1")
    assert store.job_exists("job-exists-1") is True


def test_job_exists_false_for_missing(store: SQLiteJobStore) -> None:
    """job_exists() returns False for an ID that was never created."""
    assert store.job_exists("missing-id") is False




def test_update_job_status_field(store: SQLiteJobStore) -> None:
    """update_job() persists a single field change to the database."""
    store.create_job("job-upd-1")
    store.update_job("job-upd-1", status="running")
    assert store.get_job("job-upd-1")["status"] == "running"


def test_update_job_message_field(store: SQLiteJobStore) -> None:
    """update_job() persists a message update to the database."""
    store.create_job("job-upd-2")
    store.update_job("job-upd-2", message="all good")
    assert store.get_job("job-upd-2")["message"] == "all good"


def test_update_job_multiple_fields_at_once(store: SQLiteJobStore) -> None:
    """update_job() can update multiple columns in a single call."""
    store.create_job("job-upd-3")
    store.update_job("job-upd-3", status="success", message="done", estimated_remaining_seconds=0.0)
    job = store.get_job("job-upd-3")
    assert job["status"] == "success"
    assert job["message"] == "done"
    assert job["estimated_remaining_seconds"] == 0.0


def test_update_job_datetime_string_parsed_and_stored(store: SQLiteJobStore) -> None:
    """update_job() parses ISO datetime strings for datetime fields."""
    store.create_job("job-upd-4")
    ts_str = "2026-04-14T10:00:00+00:00"
    store.update_job("job-upd-4", started_at=ts_str)
    job = store.get_job("job-upd-4")
    # The value round-trips through SQLite which loses timezone suffix,
    # but the wall-clock time must be preserved.
    stored = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00") if "Z" in job["started_at"] else job["started_at"])
    expected = datetime(2026, 4, 14, 10, 0, 0)
    assert stored.replace(tzinfo=None) == expected


def test_update_job_latest_metrics_merges(store: SQLiteJobStore) -> None:
    """update_job() merges new latest_metrics into the existing dict rather than replacing it."""
    store.create_job("job-upd-5")
    store.update_job("job-upd-5", latest_metrics={"acc": 0.8})
    store.update_job("job-upd-5", latest_metrics={"loss": 0.2})
    metrics = store.get_job("job-upd-5")["latest_metrics"]
    # RemoteDBJobStore merges dicts rather than replacing
    assert metrics.get("acc") == 0.8
    assert metrics.get("loss") == 0.2


def test_update_job_json_result_roundtrips(store: SQLiteJobStore) -> None:
    """update_job() round-trips a JSON result payload through the database intact."""
    store.create_job("job-upd-6")
    payload: dict[str, Any] = {"weights": [1, 2, 3], "config": {"k": "v"}}
    store.update_job("job-upd-6", result=payload)
    assert store.get_job("job-upd-6")["result"] == payload




def test_delete_job_removes_the_job(store: SQLiteJobStore) -> None:
    """delete_job() removes the job row so job_exists() returns False."""
    store.create_job("job-del-1")
    store.delete_job("job-del-1")
    assert not store.job_exists("job-del-1")


def test_delete_job_cascades_logs(store: SQLiteJobStore) -> None:
    """delete_job() removes all log entries for the deleted job."""
    store.create_job("job-del-2")
    store.append_log("job-del-2", level="INFO", logger_name="t", message="hi")
    store.delete_job("job-del-2")
    assert store.get_logs("job-del-2") == []


def test_delete_job_cascades_progress_events(store: SQLiteJobStore) -> None:
    """delete_job() removes all progress events for the deleted job."""
    store.create_job("job-del-3")
    store.record_progress("job-del-3", "step", {"x": 1})
    store.delete_job("job-del-3")
    assert store.get_progress_events("job-del-3") == []


def test_delete_job_tolerates_nonexistent_id(store: SQLiteJobStore) -> None:
    """delete_job() does not raise when the ID does not exist."""
    store.delete_job("ghost-id")  # must not raise




def test_get_jobs_status_by_ids_returns_map(store: SQLiteJobStore) -> None:
    """get_jobs_status_by_ids() returns a dict mapping each ID to its current status."""
    store.create_job("s1")
    store.create_job("s2")
    store.update_job("s2", status="running")
    result = store.get_jobs_status_by_ids(["s1", "s2"])
    assert result == {"s1": "pending", "s2": "running"}


def test_get_jobs_status_by_ids_omits_missing(store: SQLiteJobStore) -> None:
    """get_jobs_status_by_ids() silently omits IDs that do not exist in the database."""
    store.create_job("s3")
    result = store.get_jobs_status_by_ids(["s3", "missing-xyz"])
    assert "missing-xyz" not in result
    assert result["s3"] == "pending"


def test_get_jobs_status_by_ids_empty_input(store: SQLiteJobStore) -> None:
    """get_jobs_status_by_ids() returns an empty dict for an empty input list."""
    assert store.get_jobs_status_by_ids([]) == {}




def test_delete_jobs_returns_count_of_deleted(store: SQLiteJobStore) -> None:
    """delete_jobs() returns the number of jobs actually removed."""
    store.create_job("b1")
    store.create_job("b2")
    assert store.delete_jobs(["b1", "b2"]) == 2


def test_delete_jobs_actually_removes_jobs(store: SQLiteJobStore) -> None:
    """delete_jobs() removes each listed job so job_exists() returns False for all of them."""
    store.create_job("b3")
    store.create_job("b4")
    store.delete_jobs(["b3", "b4"])
    assert not store.job_exists("b3")
    assert not store.job_exists("b4")


def test_delete_jobs_removes_associated_logs_and_progress(store: SQLiteJobStore) -> None:
    """delete_jobs() cascades the deletion to logs and progress events."""
    store.create_job("b5")
    store.append_log("b5", level="INFO", logger_name="t", message="log entry")
    store.record_progress("b5", "step", {"m": 1})
    store.delete_jobs(["b5"])
    assert store.get_logs("b5") == []
    assert store.get_progress_events("b5") == []


def test_delete_jobs_tolerates_missing_ids(store: SQLiteJobStore) -> None:
    """delete_jobs() does not raise when some IDs in the list do not exist."""
    store.create_job("b6")
    removed = store.delete_jobs(["b6", "no-such-id"])
    assert removed == 1


def test_delete_jobs_tolerates_empty_list(store: SQLiteJobStore) -> None:
    """delete_jobs() returns 0 without raising when called with an empty list."""
    assert store.delete_jobs([]) == 0




def test_record_progress_creates_event(store: SQLiteJobStore) -> None:
    """record_progress() inserts one progress event with the correct event name and metrics."""
    store.create_job("p1")
    store.record_progress("p1", "started", {"loss": 0.5})
    events = store.get_progress_events("p1")
    assert len(events) == 1
    assert events[0]["event"] == "started"
    assert events[0]["metrics"] == {"loss": 0.5}


def test_record_progress_none_message_allowed(store: SQLiteJobStore) -> None:
    """record_progress() accepts None as the event name without raising."""
    store.create_job("p2")
    store.record_progress("p2", None, {})
    assert store.get_progress_count("p2") == 1


def test_record_progress_merges_metrics_into_job(store: SQLiteJobStore) -> None:
    """record_progress() updates latest_metrics on the parent job row."""
    store.create_job("p3")
    store.record_progress("p3", "step", {"acc": 0.9})
    job = store.get_job("p3")
    assert job["latest_metrics"].get("acc") == 0.9


def test_record_progress_json_metrics_roundtrip(store: SQLiteJobStore) -> None:
    """record_progress() round-trips nested JSON metrics through the database intact."""
    store.create_job("p4")
    metrics: dict[str, Any] = {"nested": {"a": 1}, "values": [1, 2, 3]}
    store.record_progress("p4", "step", metrics)
    events = store.get_progress_events("p4")
    assert events[0]["metrics"] == metrics


def test_get_progress_events_chronological_order(store: SQLiteJobStore) -> None:
    """get_progress_events() returns events in insertion (chronological) order."""
    store.create_job("p5")
    for i in range(3):
        store.record_progress("p5", f"step-{i}", {"i": i})
        time.sleep(0.001)  # ensure distinct timestamps
    events = store.get_progress_events("p5")
    names = [e["event"] for e in events]
    assert names == ["step-0", "step-1", "step-2"]


def test_get_progress_count_matches(store: SQLiteJobStore) -> None:
    """get_progress_count() returns the exact number of recorded progress events."""
    store.create_job("p6")
    store.record_progress("p6", "a", {})
    store.record_progress("p6", "b", {})
    assert store.get_progress_count("p6") == 2


def test_get_progress_events_empty_for_unknown_job(store: SQLiteJobStore) -> None:
    """get_progress_events() returns an empty list for a job ID that does not exist."""
    assert store.get_progress_events("unknown-job") == []


def test_progress_silently_ignored_for_deleted_job(store: SQLiteJobStore) -> None:
    """record_progress() does not raise when the job has already been deleted."""
    store.create_job("p-del")
    store.delete_job("p-del")
    # Logging / progress for a deleted job must not raise
    store.record_progress("p-del", "after delete", {})




def test_append_log_makes_entry_retrievable(store: SQLiteJobStore) -> None:
    """append_log() inserts a log entry that get_logs() returns with correct fields."""
    store.create_job("l1")
    store.append_log("l1", level="INFO", logger_name="mylogger", message="hello")
    logs = store.get_logs("l1")
    assert len(logs) == 1
    assert logs[0]["message"] == "hello"
    assert logs[0]["level"] == "INFO"
    assert logs[0]["logger"] == "mylogger"


def test_append_log_pair_index_stored(store: SQLiteJobStore) -> None:
    """append_log() persists the pair_index column when provided."""
    store.create_job("l2")
    store.append_log("l2", level="DEBUG", logger_name="lg", message="msg", pair_index=42)
    assert store.get_logs("l2")[0]["pair_index"] == 42


def test_append_log_pair_index_null_when_absent(store: SQLiteJobStore) -> None:
    """append_log() stores NULL for pair_index when the argument is omitted."""
    store.create_job("l3")
    store.append_log("l3", level="INFO", logger_name="lg", message="no pair")
    assert store.get_logs("l3")[0]["pair_index"] is None


def test_append_log_silently_ignored_for_deleted_job(store: SQLiteJobStore) -> None:
    """append_log() does not raise when the job has already been deleted."""
    store.create_job("l-del")
    store.delete_job("l-del")
    store.append_log("l-del", level="INFO", logger_name="lg", message="after delete")
    assert store.get_logs("l-del") == []


def test_get_logs_level_filter(store: SQLiteJobStore) -> None:
    """get_logs() returns only entries matching the requested log level."""
    store.create_job("l4")
    store.append_log("l4", level="INFO", logger_name="lg", message="info msg")
    store.append_log("l4", level="ERROR", logger_name="lg", message="err msg")
    errors = store.get_logs("l4", level="ERROR")
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR"


def test_get_logs_offset_pagination(store: SQLiteJobStore) -> None:
    """get_logs() skips the first N entries when offset is provided."""
    store.create_job("l5")
    for i in range(5):
        store.append_log("l5", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l5", offset=2)
    assert len(page) == 3
    assert page[0]["message"] == "msg 2"


def test_get_logs_limit_pagination(store: SQLiteJobStore) -> None:
    """get_logs() returns at most limit entries when limit is provided."""
    store.create_job("l6")
    for i in range(5):
        store.append_log("l6", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l6", limit=2)
    assert len(page) == 2


def test_get_logs_limit_and_offset_combined(store: SQLiteJobStore) -> None:
    """get_logs() correctly applies both limit and offset together."""
    store.create_job("l7")
    for i in range(10):
        store.append_log("l7", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l7", limit=3, offset=4)
    assert len(page) == 3
    assert page[0]["message"] == "msg 4"


def test_get_log_count_no_filter(store: SQLiteJobStore) -> None:
    """get_log_count() returns the total number of log entries when no level filter is given."""
    store.create_job("l8")
    store.append_log("l8", level="INFO", logger_name="lg", message="a")
    store.append_log("l8", level="WARN", logger_name="lg", message="b")
    assert store.get_log_count("l8") == 2


def test_get_log_count_with_level_filter(store: SQLiteJobStore) -> None:
    """get_log_count() counts only entries at the requested log level."""
    store.create_job("l9")
    store.append_log("l9", level="INFO", logger_name="lg", message="i")
    store.append_log("l9", level="ERROR", logger_name="lg", message="e1")
    store.append_log("l9", level="ERROR", logger_name="lg", message="e2")
    assert store.get_log_count("l9", level="ERROR") == 2


def test_get_logs_returns_empty_for_unknown_job(store: SQLiteJobStore) -> None:
    """get_logs() returns an empty list for a job ID that does not exist."""
    assert store.get_logs("unknown-job") == []




def test_set_payload_overview_stores_and_retrieves_data(store: SQLiteJobStore) -> None:
    """set_payload_overview() persists the overview dict and makes it readable via get_job()."""
    store.create_job("o1")
    overview: dict[str, Any] = {"username": "alice", "optimization_type": "gepa", "extra": [1, 2]}
    store.set_payload_overview("o1", overview)
    job = store.get_job("o1")
    assert job["payload_overview"]["username"] == "alice"
    assert job["payload_overview"]["extra"] == [1, 2]


def test_set_payload_overview_overwrites_previous(store: SQLiteJobStore) -> None:
    """set_payload_overview() replaces the entire overview on a second call."""
    store.create_job("o2")
    store.set_payload_overview("o2", {"username": "old"})
    store.set_payload_overview("o2", {"username": "new"})
    assert store.get_job("o2")["payload_overview"]["username"] == "new"


def test_set_payload_overview_sets_username_column(store: SQLiteJobStore) -> None:
    """set_payload_overview() also writes the username field to the dedicated column."""
    store.create_job("o3")
    store.set_payload_overview("o3", {"username": "carol"})
    # The store writes to the job.username column as well; verify via list_jobs filter
    jobs = store.list_jobs(username="carol")
    assert any(j["optimization_id"] == "o3" for j in jobs)




def test_list_jobs_no_filter_returns_all(store: SQLiteJobStore) -> None:
    """list_jobs() with no arguments returns every job in the store."""
    store.create_job("lj1")
    store.create_job("lj2")
    assert len(store.list_jobs()) == 2


def test_list_jobs_status_filter(store: SQLiteJobStore) -> None:
    """list_jobs() returns only jobs whose status matches the filter."""
    store.create_job("lj-pend")
    store.create_job("lj-run")
    store.update_job("lj-run", status="running")
    result = store.list_jobs(status="pending")
    ids = {j["optimization_id"] for j in result}
    assert ids == {"lj-pend"}


def test_list_jobs_username_filter(store: SQLiteJobStore) -> None:
    """list_jobs() returns only jobs belonging to the requested username."""
    store.create_job("lj-alice")
    store.set_payload_overview("lj-alice", {"username": "alice"})
    store.create_job("lj-bob")
    store.set_payload_overview("lj-bob", {"username": "bob"})
    result = store.list_jobs(username="alice")
    assert all(j["optimization_id"] == "lj-alice" for j in result)


def test_list_jobs_optimization_type_filter(store: SQLiteJobStore) -> None:
    """list_jobs() returns only jobs whose payload_overview.optimization_type matches."""
    store.create_job("lj-opt-a")
    store.set_payload_overview("lj-opt-a", {"optimization_type": "opt_a"})
    store.create_job("lj-bs")
    store.set_payload_overview("lj-bs", {"optimization_type": "bootstrap"})
    result = store.list_jobs(optimization_type="opt_a")
    ids = {j["optimization_id"] for j in result}
    assert ids == {"lj-opt-a"}


def test_list_jobs_limit(store: SQLiteJobStore) -> None:
    """list_jobs() returns at most limit rows when limit is provided."""
    for i in range(5):
        store.create_job(f"lim-{i}")
    assert len(store.list_jobs(limit=3)) == 3


def test_list_jobs_offset(store: SQLiteJobStore) -> None:
    """list_jobs() skips the first N rows when offset is provided."""
    for i in range(5):
        store.create_job(f"off-{i}")
    all_jobs = store.list_jobs()
    paged = store.list_jobs(offset=2)
    assert len(paged) == len(all_jobs) - 2


def test_list_jobs_includes_progress_and_log_counts(store: SQLiteJobStore) -> None:
    """list_jobs() includes log_count and progress_count on each returned job dict."""
    store.create_job("lj-counts")
    store.append_log("lj-counts", level="INFO", logger_name="t", message="m")
    store.record_progress("lj-counts", "step", {})
    jobs = store.list_jobs()
    job = next(j for j in jobs if j["optimization_id"] == "lj-counts")
    assert job["log_count"] == 1
    assert job["progress_count"] == 1




def test_count_jobs_total(store: SQLiteJobStore) -> None:
    """count_jobs() returns the total number of jobs with no filters applied."""
    store.create_job("cj1")
    store.create_job("cj2")
    assert store.count_jobs() == 2


def test_count_jobs_status_filter(store: SQLiteJobStore) -> None:
    """count_jobs() counts only jobs matching the given status."""
    store.create_job("cj-pend")
    store.create_job("cj-done")
    store.update_job("cj-done", status="success")
    assert store.count_jobs(status="pending") == 1
    assert store.count_jobs(status="success") == 1


def test_count_jobs_username_filter(store: SQLiteJobStore) -> None:
    """count_jobs() counts only jobs belonging to the requested username."""
    store.create_job("cj-alice")
    store.set_payload_overview("cj-alice", {"username": "alice"})
    store.create_job("cj-bob")
    store.set_payload_overview("cj-bob", {"username": "bob"})
    assert store.count_jobs(username="alice") == 1


def test_count_jobs_zero_when_empty(store: SQLiteJobStore) -> None:
    """count_jobs() returns 0 when the store has no jobs."""
    assert store.count_jobs() == 0




def test_recover_orphaned_jobs_marks_running_as_failed(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() transitions running jobs to failed status."""
    store.create_job("r1")
    store.update_job("r1", status="running")
    store.recover_orphaned_jobs()
    assert store.get_job("r1")["status"] == "failed"


def test_recover_orphaned_jobs_marks_validating_as_failed(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() transitions validating jobs to failed status."""
    store.create_job("r2")
    store.update_job("r2", status="validating")
    store.recover_orphaned_jobs()
    assert store.get_job("r2")["status"] == "failed"


def test_recover_orphaned_jobs_leaves_terminal_jobs_intact(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() does not change jobs already in a terminal state."""
    store.create_job("r3")
    store.update_job("r3", status="success")
    store.create_job("r4")
    store.update_job("r4", status="failed")
    store.recover_orphaned_jobs()
    assert store.get_job("r3")["status"] == "success"
    assert store.get_job("r4")["status"] == "failed"


def test_recover_orphaned_jobs_returns_count(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() returns the number of jobs that were recovered."""
    store.create_job("r5")
    store.update_job("r5", status="running")
    store.create_job("r6")
    store.update_job("r6", status="validating")
    store.create_job("r7")
    store.update_job("r7", status="success")
    assert store.recover_orphaned_jobs() == 2


def test_recover_orphaned_jobs_sets_completed_at(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() sets completed_at on every recovered job."""
    store.create_job("r8")
    store.update_job("r8", status="running")
    store.recover_orphaned_jobs()
    job = store.get_job("r8")
    assert job["completed_at"] is not None


def test_recover_orphaned_jobs_returns_zero_when_none_present(store: SQLiteJobStore) -> None:
    """recover_orphaned_jobs() returns 0 when all jobs are already in a terminal state."""
    store.create_job("r9")
    store.update_job("r9", status="success")
    assert store.recover_orphaned_jobs() == 0




def test_recover_pending_jobs_returns_only_pending(store: SQLiteJobStore) -> None:
    """recover_pending_jobs() returns IDs of pending jobs and omits non-pending ones."""
    store.create_job("rp1")
    store.create_job("rp2")
    store.update_job("rp2", status="success")
    pending = store.recover_pending_jobs()
    assert "rp1" in pending
    assert "rp2" not in pending


def test_recover_pending_jobs_returns_list_of_strings(store: SQLiteJobStore) -> None:
    """recover_pending_jobs() returns a list of str optimization IDs."""
    store.create_job("rp3")
    result = store.recover_pending_jobs()
    assert isinstance(result, list)
    assert all(isinstance(x, str) for x in result)


def test_recover_pending_jobs_empty_when_none_pending(store: SQLiteJobStore) -> None:
    """recover_pending_jobs() returns an empty list when no jobs are pending."""
    store.create_job("rp4")
    store.update_job("rp4", status="success")
    assert store.recover_pending_jobs() == []




def test_duplicate_optimization_id_raises_on_insert(store: SQLiteJobStore) -> None:
    """Inserting a raw row with a duplicate optimization_id raises IntegrityError."""
    store.create_job("dup-1")
    with pytest.raises(IntegrityError):
        # Bypass create_job's session so we insert a raw duplicate row
        session = store._get_session()
        try:
            job = JobModel(
                optimization_id="dup-1",
                status="pending",
                created_at=datetime.now(timezone.utc),
                latest_metrics={},
                payload_overview={},
            )
            session.add(job)
            session.commit()
        finally:
            session.rollback()
            session.close()




def test_remote_db_job_store_satisfies_job_store_protocol() -> None:
    """SQLiteJobStore (a RemoteDBJobStore subclass) satisfies the JobStore Protocol."""
    assert isinstance(SQLiteJobStore(), JobStore)




def test_update_job_unknown_field_raises_value_error(store: SQLiteJobStore) -> None:
    """update_job() raises ValueError when an unrecognised field name is passed."""
    store.create_job("uf-1")
    with pytest.raises(ValueError, match="Unknown field"):
        store.update_job("uf-1", bogus_field="x")


def test_update_job_unknown_field_message_contains_field_name(store: SQLiteJobStore) -> None:
    """The ValueError from update_job() includes the offending field name in its message."""
    store.create_job("uf-2")
    with pytest.raises(ValueError, match="totally_bogus"):
        store.update_job("uf-2", totally_bogus="value")


def test_update_job_unknown_field_does_not_corrupt_existing_data(store: SQLiteJobStore) -> None:
    """update_job() with an unknown field does not roll back a previously valid update."""
    store.create_job("uf-3")
    store.update_job("uf-3", status="running")
    with pytest.raises(ValueError):
        store.update_job("uf-3", not_a_real_field=42)
    # The earlier valid update must still be in place
    assert store.get_job("uf-3")["status"] == "running"




def test_log_eviction_oldest_entry_removed_when_cap_reached(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """append_log() evicts the oldest entry when the per-job cap is exceeded."""
    monkeypatch.setattr(remote_mod, "MAX_LOG_ENTRIES", 3)

    store.create_job("evict-log-1")
    for i in range(3):
        store.append_log("evict-log-1", level="INFO", logger_name="lg", message=f"msg-{i}")

    # Adding a 4th entry must evict msg-0 (the oldest)
    store.append_log("evict-log-1", level="INFO", logger_name="lg", message="msg-3")

    logs = store.get_logs("evict-log-1")
    messages = [lg["message"] for lg in logs]
    assert "msg-0" not in messages
    assert "msg-3" in messages


def test_log_eviction_count_stays_at_cap(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The log count for a job never exceeds MAX_LOG_ENTRIES even after many appends."""
    monkeypatch.setattr(remote_mod, "MAX_LOG_ENTRIES", 3)

    store.create_job("evict-log-2")
    for i in range(5):
        store.append_log("evict-log-2", level="INFO", logger_name="lg", message=f"msg-{i}")

    assert store.get_log_count("evict-log-2") == 3


def test_progress_eviction_oldest_entry_removed_when_cap_reached(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """record_progress() evicts the oldest event when the per-job cap is exceeded."""
    monkeypatch.setattr(remote_mod, "MAX_PROGRESS_EVENTS", 3)

    store.create_job("evict-prog-1")
    for i in range(3):
        store.record_progress("evict-prog-1", f"step-{i}", {"i": i})

    # Adding a 4th entry must evict step-0 (the oldest)
    store.record_progress("evict-prog-1", "step-3", {"i": 3})

    events = store.get_progress_events("evict-prog-1")
    event_names = [e["event"] for e in events]
    assert "step-0" not in event_names
    assert "step-3" in event_names


def test_progress_eviction_count_stays_at_cap(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The progress event count never exceeds MAX_PROGRESS_EVENTS even after many records."""
    monkeypatch.setattr(remote_mod, "MAX_PROGRESS_EVENTS", 3)

    store.create_job("evict-prog-2")
    for i in range(5):
        store.record_progress("evict-prog-2", f"step-{i}", {"i": i})

    assert store.get_progress_count("evict-prog-2") == 3


def test_progress_eviction_preserves_structural_events(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structural phase markers survive eviction while high-volume rows get dropped."""
    monkeypatch.setattr(remote_mod, "MAX_PROGRESS_EVENTS", 3)

    store.create_job("evict-prog-3")
    store.record_progress("evict-prog-3", "grid_pair_started", {"pair_index": 0})
    store.record_progress("evict-prog-3", "optimizer_progress", {"step": 0})
    store.record_progress("evict-prog-3", "optimizer_progress", {"step": 1})
    # Adding a 4th entry should evict the oldest optimizer_progress, not the
    # structural grid_pair_started marker.
    store.record_progress("evict-prog-3", "grid_pair_completed", {"pair_index": 0})

    events = store.get_progress_events("evict-prog-3")
    names = [e["event"] for e in events]
    assert "grid_pair_started" in names
    assert "grid_pair_completed" in names
    # Exactly one optimizer_progress survived — the newer one.
    assert names.count("optimizer_progress") == 1
    surviving = next(e for e in events if e["event"] == "optimizer_progress")
    assert surviving["metrics"] == {"step": 1}


def test_progress_eviction_structural_dropped_only_as_last_resort(
    store: SQLiteJobStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When every existing row is structural, the oldest structural row is evicted."""
    monkeypatch.setattr(remote_mod, "MAX_PROGRESS_EVENTS", 2)

    store.create_job("evict-prog-4")
    store.record_progress("evict-prog-4", "grid_pair_started", {"pair_index": 0})
    store.record_progress("evict-prog-4", "baseline_evaluated", {"pair_index": 0})
    # Cap is full and no non-structural rows exist — oldest structural gets evicted.
    store.record_progress("evict-prog-4", "optimized_evaluated", {"pair_index": 0})

    events = store.get_progress_events("evict-prog-4")
    names = [e["event"] for e in events]
    assert "grid_pair_started" not in names
    assert "baseline_evaluated" in names
    assert "optimized_evaluated" in names
