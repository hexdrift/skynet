"""Cross-replica serialization for one-shot DDL at startup.

Multi-pod deployments boot every api replica roughly simultaneously, and each
one calls ``Base.metadata.create_all`` to ensure the schema exists. Postgres
implicitly creates a composite type for every ``CREATE TABLE``; that catalog
write is not safe under concurrent execution, so a losing replica hits
``pg_type_typname_nsp_index`` with ``UniqueViolation`` and exits before serving
traffic. The blocking advisory lock here lets exactly one replica run the DDL
while peers wait, then proceed through a no-op ``create_all``.

Uses ``pg_advisory_xact_lock`` (transaction-scoped) so the lock is released by
the wrapping ``COMMIT`` — required under pgbouncer ``transaction`` pooling,
where session-scoped locks survive across unrelated client sessions.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

SCHEMA_BOOTSTRAP_LOCK_KEY = 742137000003


@contextmanager
def schema_bootstrap_lock(engine: Any) -> Iterator[Any]:
    """Hold a blocking transaction-scoped advisory lock and yield a bound connection.

    On PostgreSQL, opens one transaction on ``engine``, acquires
    ``pg_advisory_xact_lock(SCHEMA_BOOTSTRAP_LOCK_KEY)`` (blocking until the
    leader releases), and yields the connection so the caller can bind
    ``metadata.create_all`` to the same transaction. The lock releases when
    the transaction commits on context exit.

    On non-PostgreSQL dialects (tests / SQLite) the function yields ``None``
    so single-process callers can fall back to passing the engine directly.

    Args:
        engine: SQLAlchemy engine used to source the lock-holding connection.

    Yields:
        A connection bound to the locking transaction on PostgreSQL, or
        ``None`` on other dialects.
    """
    if engine is None or engine.dialect.name != "postgresql":
        yield None
        return
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SCHEMA_BOOTSTRAP_LOCK_KEY})
        yield conn
