"""Tests for unified per-user storage accounting (``core.storage.usage``).

Runs against an in-memory SQLite engine (the sibling job-store tests' pattern: a
``RemoteDBJobStore`` subclass that skips the pgvector bootstrap so
``Base.metadata.create_all`` stands up every table). Covers the compact-JSON
sizer, the empty-user fast path, and the ``jobs.stored_bytes`` write path that
the optimizations category sums.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.storage.models import Base
from core.storage.remote import RemoteDBJobStore
from core.storage.usage import STORAGE_CATEGORIES, compute_user_storage, json_byte_size


class _SQLiteJobStore(RemoteDBJobStore):
    """RemoteDBJobStore on in-memory SQLite (skips the pgvector bootstrap)."""

    def __init__(self) -> None:
        """Build an in-memory SQLite engine and create the ORM tables."""
        self._engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(bind=self._engine)


@pytest.fixture
def store() -> Iterator[_SQLiteJobStore]:
    """Yield a fresh SQLite-backed store and drop its tables afterwards."""
    s = _SQLiteJobStore()
    yield s
    Base.metadata.drop_all(s.engine)


def test_json_byte_size_none_is_zero() -> None:
    """``json_byte_size(None)`` is 0 — an absent JSON column costs nothing."""
    assert json_byte_size(None) == 0


def test_json_byte_size_matches_compact_utf8_length() -> None:
    """``json_byte_size`` measures the compact-JSON UTF-8 byte length."""
    value = {"q": "שלום", "a": 4}
    expected = len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))
    assert json_byte_size(value) == expected


def test_compute_user_storage_empty_user_is_all_zero(store: _SQLiteJobStore) -> None:
    """A user with nothing stored totals zero with every category present."""
    usage = compute_user_storage(store.engine, "ghost")
    assert usage.total == 0
    assert set(usage.breakdown) == set(STORAGE_CATEGORIES)
    assert all(value == 0 for value in usage.breakdown.values())


def test_compute_user_storage_blank_username_short_circuits(store: _SQLiteJobStore) -> None:
    """A blank username returns the all-zero usage without scanning tables."""
    usage = compute_user_storage(store.engine, "   ")
    assert usage.total == 0


def test_stored_bytes_tracks_payload_and_result(store: _SQLiteJobStore) -> None:
    """Writing payload/result sets ``stored_bytes`` and feeds the optimizations total."""
    store.create_job("job-1", username="alice")
    payload = {"signature_code": "x", "rows": [{"q": "1", "a": "1"}]}
    result = {"score": 0.9}
    store.update_job("job-1", payload=payload, result=result)

    expected = json_byte_size(payload) + json_byte_size(result) + json_byte_size({})
    usage = compute_user_storage(store.engine, "alice")
    assert usage.breakdown["optimizations"] == expected
    assert usage.total == expected


def test_set_payload_overview_folds_overview_into_stored_bytes(store: _SQLiteJobStore) -> None:
    """``set_payload_overview`` recomputes ``stored_bytes`` to include the overview."""
    store.create_job("job-2", username="alice")
    store.update_job("job-2", payload={"a": 1})
    overview = {"name": "My run"}
    store.set_payload_overview("job-2", overview)

    expected = json_byte_size({"a": 1}) + json_byte_size(None) + json_byte_size(overview)
    assert compute_user_storage(store.engine, "alice").breakdown["optimizations"] == expected


def test_compute_user_storage_is_owner_scoped(store: _SQLiteJobStore) -> None:
    """One user's job bytes never leak into another user's total."""
    store.create_job("job-a", username="alice")
    store.update_job("job-a", payload={"owner": "alice"})
    store.create_job("job-b", username="bob")
    store.update_job("job-b", payload={"owner": "bob"})

    alice = compute_user_storage(store.engine, "alice")
    expected = json_byte_size({"owner": "alice"}) + json_byte_size({})
    assert alice.breakdown["optimizations"] == expected
    assert alice.total == alice.breakdown["optimizations"]
