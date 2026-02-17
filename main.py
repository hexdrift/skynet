from __future__ import annotations
import logging
import os
import uvicorn
from core import ServiceRegistry, create_app

# [WORKER-FIX] configure logging so worker thread logs actually appear in OpenShift
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

registry = ServiceRegistry()
app = create_app(registry=registry)


def run_server() -> None:
    """Start the FastAPI server via Uvicorn.

    Returns:
        None.
    """
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run_server()
