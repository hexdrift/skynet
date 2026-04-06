"""Job storage backend for Skynet optimization service.

PostgreSQL only. No SQLite.
"""

import os

from .base import JobStore
from .remote import RemoteDBJobStore


def get_job_store() -> JobStore:
    """Return the PostgreSQL job store backend.

    Reads REMOTE_DB_URL for the connection string.

    Returns:
        JobStore: PostgreSQL storage backend.

    Raises:
        RuntimeError: If REMOTE_DB_URL is not set.
    """
    url = os.getenv("REMOTE_DB_URL")
    if not url:
        raise RuntimeError(
            "REMOTE_DB_URL is not set. Configure your PostgreSQL connection:\n"
            "  REMOTE_DB_URL=postgresql://user:password@host:5432/skynet\n"
            "See backend/.env.example for a template."
        )
    return RemoteDBJobStore(db_url=url)


__all__ = ["JobStore", "RemoteDBJobStore", "get_job_store"]
