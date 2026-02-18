"""Background worker for DSPy optimization jobs."""

from .engine import BackgroundWorker, get_worker, reset_worker_for_tests

__all__ = ["BackgroundWorker", "get_worker", "reset_worker_for_tests"]
