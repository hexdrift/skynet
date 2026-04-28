"""Background worker for DSPy optimization jobs."""

from __future__ import annotations

from .engine import BackgroundWorker, get_worker, reset_worker_for_tests

# ``reset_worker_for_tests`` is exposed at the package surface for test isolation;
# production code must not call this.
__all__ = ["BackgroundWorker", "get_worker", "reset_worker_for_tests"]
