"""Contract tests for the JobStore interface.

Every test here exercises a guarantee documented in ``core.storage.base.JobStore``.
The test target is ``FakeJobStore`` (defined in this package's conftest.py), an
in-memory implementation that satisfies the full protocol.  Any future
implementation MUST satisfy these same guarantees.

``RemoteDBJobStore`` is deliberately absent: it requires a live PostgreSQL
connection and therefore belongs in the integration tier (``backend/tests/``).
"""

from __future__ import annotations

import pytest

from core.storage.base import JobStore
from core.storage.tests.conftest import FakeJobStore


def test_create_job_returns_pending_dict(store: FakeJobStore) -> None:
    """``create_job`` returns a dict in pending status."""
    result = store.create_job("job-1")
    assert result["optimization_id"] == "job-1"
    assert result["status"] == "pending"


def test_create_job_with_estimate(store: FakeJobStore) -> None:
    """``create_job`` stores the supplied ETA."""
    result = store.create_job("job-2", estimated_remaining_seconds=120.0)
    assert result["estimated_remaining_seconds"] == 120.0


def test_create_job_makes_job_findable(store: FakeJobStore) -> None:
    """``create_job`` makes the new ID findable via ``job_exists``."""
    store.create_job("job-3")
    assert store.job_exists("job-3")


def test_create_job_return_is_independent_copy(store: FakeJobStore) -> None:
    """Mutating the returned dict does not affect stored state."""
    returned = store.create_job("job-4")
    returned["status"] = "mutated"
    assert store.get_job("job-4")["status"] == "pending"


def test_get_job_raises_key_error_for_unknown_id(store: FakeJobStore) -> None:
    """``get_job`` raises ``KeyError`` for unknown IDs."""
    with pytest.raises(KeyError, match="nonexistent"):
        store.get_job("nonexistent")


def test_get_job_returns_correct_job(store: FakeJobStore) -> None:
    """``get_job`` returns the seeded record for a known ID."""
    store.seed_job("alpha", status="success")
    job = store.get_job("alpha")
    assert job["optimization_id"] == "alpha"
    assert job["status"] == "success"


def test_get_job_returns_independent_copy(store: FakeJobStore) -> None:
    """Mutating the returned dict from ``get_job`` does not affect stored state."""
    store.seed_job("beta")
    copy = store.get_job("beta")
    copy["status"] = "mutated"
    assert store.get_job("beta")["status"] == "pending"


def test_job_exists_true_for_existing(store: FakeJobStore) -> None:
    """``job_exists`` returns ``True`` for seeded jobs."""
    store.seed_job("gamma")
    assert store.job_exists("gamma") is True


def test_job_exists_false_for_missing(store: FakeJobStore) -> None:
    """``job_exists`` returns ``False`` for missing IDs."""
    assert store.job_exists("missing") is False


def test_update_job_changes_field(store: FakeJobStore) -> None:
    """``update_job`` overwrites the targeted field."""
    store.seed_job("u1", status="pending")
    store.update_job("u1", status="running")
    assert store.get_job("u1")["status"] == "running"


def test_update_job_multiple_fields(store: FakeJobStore) -> None:
    """``update_job`` applies multiple field updates atomically."""
    store.seed_job("u2")
    store.update_job("u2", status="success", message="done")
    job = store.get_job("u2")
    assert job["status"] == "success"
    assert job["message"] == "done"


def test_delete_job_removes_job(store: FakeJobStore) -> None:
    """``delete_job`` removes the row."""
    store.seed_job("d1")
    store.delete_job("d1")
    assert not store.job_exists("d1")


def test_delete_job_removes_logs(store: FakeJobStore) -> None:
    """``delete_job`` cascades to log entries."""
    store.seed_job("d2")
    store.append_log("d2", level="INFO", logger_name="test", message="hi")
    store.delete_job("d2")
    assert store.get_logs("d2") == []


def test_delete_job_removes_progress_events(store: FakeJobStore) -> None:
    """``delete_job`` cascades to progress events."""
    store.seed_job("d3")
    store.record_progress("d3", message="step", metrics={"x": 1})
    store.delete_job("d3")
    assert store.get_progress_events("d3") == []


def test_delete_job_tolerates_nonexistent_id(store: FakeJobStore) -> None:
    """``delete_job`` is a no-op for unknown IDs."""
    # Must not raise — silently ignore missing IDs.
    store.delete_job("ghost")


def test_get_jobs_status_by_ids_returns_map(store: FakeJobStore) -> None:
    """``get_jobs_status_by_ids`` returns the matching ``{id: status}`` map."""
    store.seed_job("s1", status="pending")
    store.seed_job("s2", status="running")
    result = store.get_jobs_status_by_ids(["s1", "s2"])
    assert result == {"s1": "pending", "s2": "running"}


def test_get_jobs_status_by_ids_omits_missing(store: FakeJobStore) -> None:
    """Missing IDs are absent from the status map."""
    store.seed_job("s3", status="success")
    result = store.get_jobs_status_by_ids(["s3", "missing-id"])
    assert "missing-id" not in result
    assert result["s3"] == "success"


def test_get_jobs_status_by_ids_empty_list(store: FakeJobStore) -> None:
    """``get_jobs_status_by_ids`` with an empty list returns an empty dict."""
    assert store.get_jobs_status_by_ids([]) == {}


def test_delete_jobs_returns_count_of_removed(store: FakeJobStore) -> None:
    """``delete_jobs`` returns the number of rows actually removed."""
    store.seed_job("b1")
    store.seed_job("b2")
    removed = store.delete_jobs(["b1", "b2"])
    assert removed == 2


def test_delete_jobs_actually_removes(store: FakeJobStore) -> None:
    """``delete_jobs`` removes every targeted row."""
    store.seed_job("b3")
    store.seed_job("b4")
    store.delete_jobs(["b3", "b4"])
    assert not store.job_exists("b3")
    assert not store.job_exists("b4")


def test_delete_jobs_tolerates_missing_ids(store: FakeJobStore) -> None:
    """``delete_jobs`` ignores missing IDs and counts only removals."""
    store.seed_job("b5")
    removed = store.delete_jobs(["b5", "no-such-job"])
    assert removed == 1


def test_delete_jobs_tolerates_duplicates(store: FakeJobStore) -> None:
    """``delete_jobs`` deduplicates IDs in the input list."""
    store.seed_job("b6")
    removed = store.delete_jobs(["b6", "b6"])
    assert removed == 1


def test_record_progress_appends_event(store: FakeJobStore) -> None:
    """``record_progress`` appends a single event with the supplied payload."""
    store.seed_job("p1")
    store.record_progress("p1", message="step 1", metrics={"loss": 0.5})
    events = store.get_progress_events("p1")
    assert len(events) == 1
    assert events[0]["message"] == "step 1"
    assert events[0]["metrics"] == {"loss": 0.5}


def test_record_progress_none_message_allowed(store: FakeJobStore) -> None:
    """``record_progress`` accepts a ``None`` message."""
    store.seed_job("p2")
    store.record_progress("p2", message=None, metrics={})
    assert store.get_progress_count("p2") == 1


def test_get_progress_events_chronological_order(store: FakeJobStore) -> None:
    """``get_progress_events`` returns events in insertion order."""
    store.seed_job("p3")
    for i in range(3):
        store.record_progress("p3", message=f"step {i}", metrics={"i": i})
    events = store.get_progress_events("p3")
    messages = [e["message"] for e in events]
    assert messages == ["step 0", "step 1", "step 2"]


def test_get_progress_count_matches_events(store: FakeJobStore) -> None:
    """``get_progress_count`` matches the number of events recorded."""
    store.seed_job("p4")
    store.record_progress("p4", message="a", metrics={})
    store.record_progress("p4", message="b", metrics={})
    assert store.get_progress_count("p4") == 2


def test_get_progress_events_returns_copy(store: FakeJobStore) -> None:
    """Mutating the returned events list does not affect stored state."""
    store.seed_job("p5")
    store.record_progress("p5", message="x", metrics={})
    returned = store.get_progress_events("p5")
    returned.clear()
    assert store.get_progress_count("p5") == 1


def test_get_progress_events_empty_for_unknown_job(store: FakeJobStore) -> None:
    """``get_progress_events`` returns an empty list for unknown IDs."""
    assert store.get_progress_events("unknown") == []


def test_append_log_makes_entry_retrievable(store: FakeJobStore) -> None:
    """``append_log`` writes an entry that ``get_logs`` returns."""
    store.seed_job("l1")
    store.append_log("l1", level="INFO", logger_name="mylogger", message="hello")
    logs = store.get_logs("l1")
    assert len(logs) == 1
    assert logs[0]["message"] == "hello"
    assert logs[0]["level"] == "INFO"


def test_append_log_pair_index_stored(store: FakeJobStore) -> None:
    """``append_log`` persists a supplied ``pair_index`` value."""
    store.seed_job("l2")
    store.append_log("l2", level="DEBUG", logger_name="lg", message="m", pair_index=7)
    assert store.get_logs("l2")[0]["pair_index"] == 7


def test_get_logs_level_filter(store: FakeJobStore) -> None:
    """``get_logs`` respects the ``level`` filter."""
    store.seed_job("l3")
    store.append_log("l3", level="INFO", logger_name="lg", message="info msg")
    store.append_log("l3", level="ERROR", logger_name="lg", message="err msg")
    errors = store.get_logs("l3", level="ERROR")
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR"


def test_get_logs_offset_pagination(store: FakeJobStore) -> None:
    """``get_logs`` skips the requested offset."""
    store.seed_job("l4")
    for i in range(5):
        store.append_log("l4", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l4", offset=2)
    assert len(page) == 3
    assert page[0]["message"] == "msg 2"


def test_get_logs_limit_pagination(store: FakeJobStore) -> None:
    """``get_logs`` honors the ``limit`` parameter."""
    store.seed_job("l5")
    for i in range(5):
        store.append_log("l5", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l5", limit=2)
    assert len(page) == 2


def test_get_logs_limit_and_offset(store: FakeJobStore) -> None:
    """``get_logs`` combines ``limit`` and ``offset`` correctly."""
    store.seed_job("l6")
    for i in range(10):
        store.append_log("l6", level="INFO", logger_name="lg", message=f"msg {i}")
    page = store.get_logs("l6", limit=3, offset=4)
    assert len(page) == 3
    assert page[0]["message"] == "msg 4"


def test_get_log_count_no_filter(store: FakeJobStore) -> None:
    """``get_log_count`` returns the total without filters."""
    store.seed_job("l7")
    store.append_log("l7", level="INFO", logger_name="lg", message="a")
    store.append_log("l7", level="WARN", logger_name="lg", message="b")
    assert store.get_log_count("l7") == 2


def test_get_log_count_with_level_filter(store: FakeJobStore) -> None:
    """``get_log_count`` restricts the count to the requested level."""
    store.seed_job("l8")
    store.append_log("l8", level="INFO", logger_name="lg", message="a")
    store.append_log("l8", level="ERROR", logger_name="lg", message="b")
    store.append_log("l8", level="ERROR", logger_name="lg", message="c")
    assert store.get_log_count("l8", level="ERROR") == 2


def test_get_logs_returns_empty_for_unknown_job(store: FakeJobStore) -> None:
    """``get_logs`` returns an empty list for unknown IDs."""
    assert store.get_logs("unknown") == []


def test_set_payload_overview_stores_data(store: FakeJobStore) -> None:
    """``set_payload_overview`` persists the supplied summary."""
    store.seed_job("o1")
    store.set_payload_overview("o1", {"username": "alice", "job_type": "opt_a"})
    job = store.get_job("o1")
    assert job["payload_overview"]["username"] == "alice"


def test_set_payload_overview_overwrites_previous(store: FakeJobStore) -> None:
    """``set_payload_overview`` overwrites a prior value."""
    store.seed_job("o2", payload_overview={"username": "old"})
    store.set_payload_overview("o2", {"username": "new"})
    assert store.get_job("o2")["payload_overview"]["username"] == "new"


@pytest.mark.parametrize(
    ("filter_kwargs", "expected_ids"),
    [
        ({"status": "pending"}, {"j-pending-1", "j-pending-2"}),
        ({"status": "running"}, {"j-running-1"}),
        ({"username": "alice"}, {"j-pending-1", "j-running-1"}),
        ({"username": "bob"}, {"j-pending-2"}),
        ({"optimization_type": "opt_a"}, {"j-pending-1", "j-running-1"}),
        ({"optimization_type": "bootstrap"}, {"j-pending-2"}),
        ({"status": "pending", "username": "alice"}, {"j-pending-1"}),
        ({"status": "running", "username": "bob"}, set()),
    ],
)
def test_list_jobs_filters(
    store: FakeJobStore,
    filter_kwargs: dict,
    expected_ids: set,
) -> None:
    """``list_jobs`` returns the rows matching the supplied filters."""
    store.seed_job(
        "j-pending-1",
        status="pending",
        payload_overview={"username": "alice", "job_type": "opt_a"},
    )
    store.seed_job(
        "j-pending-2",
        status="pending",
        payload_overview={"username": "bob", "job_type": "bootstrap"},
    )
    store.seed_job(
        "j-running-1",
        status="running",
        payload_overview={"username": "alice", "job_type": "opt_a"},
    )
    result_ids = {j["optimization_id"] for j in store.list_jobs(**filter_kwargs)}
    assert result_ids == expected_ids


def test_list_jobs_limit(store: FakeJobStore) -> None:
    """``list_jobs`` honors the ``limit`` parameter."""
    for i in range(5):
        store.seed_job(f"lim-{i}")
    assert len(store.list_jobs(limit=3)) == 3


def test_list_jobs_offset(store: FakeJobStore) -> None:
    """``list_jobs`` skips the requested offset."""
    for i in range(5):
        store.seed_job(f"off-{i}")
    all_jobs = store.list_jobs()
    paged = store.list_jobs(offset=2)
    assert len(paged) == len(all_jobs) - 2


def test_list_jobs_no_filter_returns_all(store: FakeJobStore) -> None:
    """``list_jobs`` without filters returns every row."""
    store.seed_job("all-1")
    store.seed_job("all-2")
    assert len(store.list_jobs()) == 2


@pytest.mark.parametrize(
    ("filter_kwargs", "expected_count"),
    [
        ({}, 3),
        ({"status": "pending"}, 2),
        ({"status": "running"}, 1),
        ({"username": "alice"}, 2),
        ({"username": "bob"}, 1),
        ({"optimization_type": "opt_a"}, 2),
        ({"status": "pending", "username": "alice"}, 1),
    ],
)
def test_count_jobs_filters(
    store: FakeJobStore,
    filter_kwargs: dict,
    expected_count: int,
) -> None:
    """``count_jobs`` returns the count matching the supplied filters."""
    store.seed_job(
        "cj-1",
        status="pending",
        payload_overview={"username": "alice", "job_type": "opt_a"},
    )
    store.seed_job(
        "cj-2",
        status="pending",
        payload_overview={"username": "bob", "job_type": "bootstrap"},
    )
    store.seed_job(
        "cj-3",
        status="running",
        payload_overview={"username": "alice", "job_type": "opt_a"},
    )
    assert store.count_jobs(**filter_kwargs) == expected_count


def test_recover_orphaned_jobs_marks_running_as_failed(store: FakeJobStore) -> None:
    """``recover_orphaned_jobs`` transitions ``running`` to ``failed``."""
    store.seed_job("r1", status="running")
    store.recover_orphaned_jobs()
    assert store.get_job("r1")["status"] == "failed"


def test_recover_orphaned_jobs_marks_validating_as_failed(store: FakeJobStore) -> None:
    """``recover_orphaned_jobs`` transitions ``validating`` to ``failed``."""
    store.seed_job("r2", status="validating")
    store.recover_orphaned_jobs()
    assert store.get_job("r2")["status"] == "failed"


def test_recover_orphaned_jobs_leaves_terminal_jobs_intact(store: FakeJobStore) -> None:
    """``recover_orphaned_jobs`` leaves terminal-status jobs untouched."""
    store.seed_job("r3", status="success")
    store.seed_job("r4", status="failed")
    store.recover_orphaned_jobs()
    assert store.get_job("r3")["status"] == "success"
    assert store.get_job("r4")["status"] == "failed"


def test_recover_orphaned_jobs_returns_count(store: FakeJobStore) -> None:
    """``recover_orphaned_jobs`` returns the number of recovered rows."""
    store.seed_job("r5", status="running")
    store.seed_job("r6", status="validating")
    store.seed_job("r7", status="success")
    assert store.recover_orphaned_jobs() == 2


def test_recover_orphaned_jobs_returns_zero_when_nothing_to_recover(store: FakeJobStore) -> None:
    """``recover_orphaned_jobs`` returns zero when no rows need recovery."""
    store.seed_job("r8", status="success")
    assert store.recover_orphaned_jobs() == 0


def test_recover_pending_jobs_returns_pending_ids(store: FakeJobStore) -> None:
    """``recover_pending_jobs`` returns IDs of currently-pending jobs."""
    store.seed_job("rp1", status="pending")
    store.seed_job("rp2", status="success")
    pending = store.recover_pending_jobs()
    assert "rp1" in pending
    assert "rp2" not in pending


def test_recover_pending_jobs_returns_list_of_strings(store: FakeJobStore) -> None:
    """``recover_pending_jobs`` returns a plain ``list[str]``."""
    store.seed_job("rp3", status="pending")
    result = store.recover_pending_jobs()
    assert isinstance(result, list)
    assert all(isinstance(x, str) for x in result)


def test_recover_pending_jobs_empty_when_none_pending(store: FakeJobStore) -> None:
    """``recover_pending_jobs`` returns an empty list when no rows pend."""
    store.seed_job("rp4", status="success")
    assert store.recover_pending_jobs() == []


def test_fake_job_store_satisfies_protocol() -> None:
    """``FakeJobStore`` satisfies the ``JobStore`` runtime protocol."""
    assert isinstance(FakeJobStore(), JobStore)


def test_protocol_rejects_instance_missing_all_methods() -> None:
    """Protocol check rejects classes lacking every required method."""

    class Empty:
        pass

    assert not isinstance(Empty(), JobStore)


def test_protocol_rejects_instance_missing_one_method() -> None:
    """Removing any single required method breaks protocol conformance.

    ``JobStore`` is a runtime-checkable Protocol; Python only checks that
    the named attributes exist (not their signatures), so we verify by
    removing each method name one by one.
    """
    protocol_methods = [
        name for name in dir(JobStore) if not name.startswith("_") and callable(getattr(JobStore, name, None))
    ]
    assert protocol_methods, "Protocol has no public methods — test setup is wrong"

    for missing_method in protocol_methods:
        # Build each one-method-short permutation to prove every protocol
        # member is required by the runtime-checkable interface.
        attrs = {m: lambda self, *a, **kw: None for m in protocol_methods if m != missing_method}
        IncompleteClass = type("IncompleteClass", (), attrs)  # noqa: N806 — runtime-built class

        obj = IncompleteClass()
        assert not isinstance(obj, JobStore), (
            f"Expected isinstance() to return False when '{missing_method}' is missing, but it returned True"
        )


def test_protocol_accepts_minimal_conforming_class() -> None:
    """Protocol check accepts any class declaring all required methods."""
    protocol_methods = [
        name for name in dir(JobStore) if not name.startswith("_") and callable(getattr(JobStore, name, None))
    ]

    attrs = {m: lambda self, *a, **kw: None for m in protocol_methods}
    MinimalClass = type("MinimalClass", (), attrs)  # noqa: N806 — runtime-built class

    assert isinstance(MinimalClass(), JobStore)
