"""Top-level package for the Skynet backend.

Re-exports the small set of objects that callers outside ``core`` are expected
to construct: the FastAPI app factory, the dependency-injection registry, the
DSPy service gateway, the persistent job store, and the background worker.
"""

from .api import create_app
from .registry import ServiceRegistry
from .service_gateway import DspyService
from .storage import RemoteDBJobStore
from .worker import BackgroundWorker, get_worker

__all__ = [
    "BackgroundWorker",
    "DspyService",
    "RemoteDBJobStore",
    "ServiceRegistry",
    "create_app",
    "get_worker",
]
