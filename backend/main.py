"""Application entrypoint for the Skynet backend.

Loads environment variables from ``backend/.env``, configures logging, builds
the ``ServiceRegistry`` and the FastAPI ``app`` object, and exposes
``run_server`` as the script entrypoint that boots Uvicorn.
"""

from __future__ import annotations

from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from core import ServiceRegistry, create_app
from core.api.observability import configure_logging

load_dotenv(Path(__file__).parent / ".env")

# Must run before create_app() so loggers acquired during router import
# inherit the configured formatter, not Uvicorn's default.
configure_logging()

registry = ServiceRegistry()
app = create_app(registry=registry)


def run_server() -> None:
    """Boot the FastAPI application using Uvicorn on ``0.0.0.0:8000``."""
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
