"""Application entrypoint for the Skynet backend.

Loads environment variables from ``backend/.env``, configures logging, builds
the ``ServiceRegistry`` and the FastAPI ``app`` object, and exposes
``run_server`` as the script entrypoint that boots Uvicorn.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from core.api.app import create_app
from core.api.observability import configure_logging
from core.registry import ServiceRegistry

load_dotenv(Path(__file__).parent / ".env")

# Must run before create_app() so loggers acquired during router import
# inherit the configured formatter, not Uvicorn's default.
configure_logging()

registry = ServiceRegistry()
app = create_app(registry=registry)


def run_server() -> None:
    """Boot the FastAPI application using Uvicorn, honouring API_HOST / API_PORT."""
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
