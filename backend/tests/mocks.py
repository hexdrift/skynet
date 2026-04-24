"""Mock builders for top-level backend tests."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch


def fake_service_registry() -> MagicMock:
    """Return a MagicMock standing in for a ServiceRegistry instance."""
    return MagicMock(name="ServiceRegistry_instance")


def fake_fastapi_app() -> MagicMock:
    """Return a MagicMock standing in for a FastAPI application instance."""
    return MagicMock(name="FastAPI_app")


@contextmanager
def patch_main_dependencies(registry: Any = None, app: Any = None):
    """Patch heavy side-effects (dotenv, DB, uvicorn) that fire at main.py import time.

    Args:
        registry: Optional mock to use as the ServiceRegistry; defaults to a fresh
            :func:`fake_service_registry` mock.
        app: Optional mock to use as the FastAPI app; defaults to a fresh
            :func:`fake_fastapi_app` mock.
    """
    if registry is None:
        registry = fake_service_registry()
    if app is None:
        app = fake_fastapi_app()

    with (
        patch("dotenv.load_dotenv"),
        patch("core.ServiceRegistry", return_value=registry),
        patch("core.create_app", return_value=app),
        patch("uvicorn.run"),
    ):
        yield


def import_main_fresh(registry: Any = None, app: Any = None):
    """Remove main from sys.modules and re-import it with side-effects patched out.

    Args:
        registry: Optional mock to substitute for ServiceRegistry.
        app: Optional mock to substitute for the FastAPI app.

    Returns:
        The freshly imported ``main`` module with all heavy side-effects mocked.
    """
    sys.modules.pop("main", None)
    with patch_main_dependencies(registry=registry, app=app):
        import main as _main
    return _main
