"""Job storage backend for Skynet optimization service.

PostgreSQL only. No SQLite.
"""

from ..config import settings
from .base import JobStore
from .remote import RemoteDBJobStore


def get_job_store() -> JobStore:
    """Return the PostgreSQL job store backend.

    Reads REMOTE_DB_URL from settings for the connection string.

    Returns:
        JobStore: PostgreSQL storage backend.

    Raises:
        RuntimeError: If REMOTE_DB_URL is not set.
    """
    if not settings.remote_db_url:
        raise RuntimeError(
            "REMOTE_DB_URL is not set. Configure your PostgreSQL connection:\n"
            "  REMOTE_DB_URL=postgresql://user:password@host:5432/skynet\n"
            "See backend/.env.example for a template."
        )
    return RemoteDBJobStore(db_url=settings.remote_db_url.get_secret_value())


__all__ = ["JobStore", "RemoteDBJobStore", "get_job_store"]
