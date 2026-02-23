"""Job storage backends for DSPy optimization service."""

import os

from .base import JobStore
from .local import LocalDBJobStore
from .remote import RemoteDBJobStore


def get_job_store() -> JobStore:
    """Return the configured job store backend.

    Backend is selected via the JOB_STORE_BACKEND env var (default: 'local').
    When 'remote' is selected, REMOTE_DB_URL must also be set.
    """
    backend = os.getenv("JOB_STORE_BACKEND", "local").lower()
    if backend == "local":
        return LocalDBJobStore()
    if backend == "remote":
        url = os.getenv("REMOTE_DB_URL")
        if not url:
            raise RuntimeError("JOB_STORE_BACKEND=remote but REMOTE_DB_URL is not set")
        return RemoteDBJobStore(db_url=url)
    raise RuntimeError(f"Unknown JOB_STORE_BACKEND={backend!r}. Valid values: 'local', 'remote'")


__all__ = ["JobStore", "LocalDBJobStore", "RemoteDBJobStore", "get_job_store"]
