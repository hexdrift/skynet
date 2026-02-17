"""Background worker for DSPy optimization jobs."""

from .engine import BackgroundWorker, get_worker

__all__ = ["BackgroundWorker", "get_worker"]
