"""Live-Postgres concurrency tests for ``RemoteDBJobStore.claim_next_job``.

These tests verify that ``FOR UPDATE SKIP LOCKED`` actually serializes
concurrent claimers — something SQLite cannot exercise because it lacks
row-level locking. They are gated on ``REMOTE_DB_URL`` so they only run
when an operator deliberately points the suite at a real Postgres
instance::

    REMOTE_DB_URL=postgresql://skynet:skynet@localhost:5432/skynet \
        pytest backend/core/storage/tests/test_remote_jobstore_postgres.py

Without that env var the entire module is skipped, so unit-test CI is
unaffected.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command
from core.storage.remote import RemoteDBJobStore

REMOTE_DB_URL = os.environ.get("REMOTE_DB_URL")
BACKEND_DIR = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.skipif(
    not REMOTE_DB_URL or not REMOTE_DB_URL.startswith("postgresql"),
    reason="REMOTE_DB_URL not set to a postgresql:// URL — skipping live-DB tests.",
)


@pytest.fixture(scope="module")
def store() -> Iterator[RemoteDBJobStore]:
    """Yield a single store backed by the real Postgres for the whole module.

    The live database is upgraded to Alembic head first so model changes
    such as new indexed columns are present before rows are inserted.
    The store is reused across tests to avoid repeating that setup work.
    """
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", REMOTE_DB_URL or "")
    command.upgrade(alembic_cfg, "head")

    s = RemoteDBJobStore(REMOTE_DB_URL)
    try:
        yield s
    finally:
        s.engine.dispose()


@pytest.fixture
def seeded_jobs(store: RemoteDBJobStore) -> Iterator[list[str]]:
    """Seed a uniquely-prefixed batch of pending jobs and clean them up after.

    Using a per-test UUID prefix keeps these tests safe to run against a
    shared Postgres without colliding with real data or with parallel
    test runs.
    """
    prefix = f"concurrency-test-{uuid.uuid4().hex[:8]}"
    ids = [f"{prefix}-{i:03d}" for i in range(20)]
    for oid in ids:
        store.create_job(oid)
    try:
        yield ids
    finally:
        store.delete_jobs(ids)


def test_concurrent_claimers_never_collide(
    store: RemoteDBJobStore, seeded_jobs: list[str]
) -> None:
    """Twenty pending rows + ten concurrent claimers → every claim is unique.

    The pool launches more workers than rows so that some workers MUST
    receive ``None``. We assert (a) no two workers received the same
    ``optimization_id`` and (b) the count of successful claims equals the
    seed count.
    """
    expected_ids = set(seeded_jobs)
    worker_count = 10
    claims_per_worker = 3

    def worker(worker_idx: int) -> list[str | None]:
        worker_id = f"pod-{worker_idx}"
        out: list[str | None] = []
        for _ in range(claims_per_worker):
            row = store.claim_next_job(worker_id, lease_seconds=60.0)
            out.append(row["optimization_id"] if row else None)
        return out

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = list(pool.map(worker, range(worker_count)))

    claimed: list[str] = [oid for batch in results for oid in batch if oid is not None]

    assert len(claimed) == len(set(claimed)), (
        f"Duplicate claim detected — FOR UPDATE SKIP LOCKED failed. "
        f"Got {len(claimed)} claims but only {len(set(claimed))} unique IDs."
    )
    assert set(claimed).issubset(expected_ids), (
        "Claim returned an unexpected ID — test bled into other rows."
    )
    assert len(claimed) == len(expected_ids), (
        f"Expected all {len(expected_ids)} seeded jobs to be claimed, "
        f"got {len(claimed)}."
    )


def test_claim_records_owner_and_lease(
    store: RemoteDBJobStore, seeded_jobs: list[str]
) -> None:
    """A successful claim must persist ``claimed_by`` and ``lease_expires_at``.

    This is the read-back path the orphan-recovery loop relies on; if
    the UPDATE silently dropped these columns the lease would never
    expire and stuck workers would never be reclaimed. The columns
    aren't in the public TypedDict, so we query them directly.
    """
    row = store.claim_next_job("pod-solo", lease_seconds=42.0)
    assert row is not None
    assert row["status"] == "validating"

    with store.engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT claimed_by, claimed_at, lease_expires_at "
                "FROM jobs WHERE optimization_id = :oid"
            ),
            {"oid": row["optimization_id"]},
        ).fetchone()

    assert result is not None
    claimed_by, claimed_at, lease_expires_at = result
    assert claimed_by == "pod-solo"
    assert claimed_at is not None
    assert lease_expires_at is not None
    assert lease_expires_at > claimed_at
