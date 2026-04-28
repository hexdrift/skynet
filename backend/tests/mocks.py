"""Mock builders for top-level backend tests."""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch


def fake_service_registry() -> MagicMock:
    """Return a labelled ``MagicMock`` standing in for ``ServiceRegistry``."""
    return MagicMock(name="ServiceRegistry_instance")


def fake_fastapi_app() -> MagicMock:
    """Return a labelled ``MagicMock`` standing in for the FastAPI app."""
    return MagicMock(name="FastAPI_app")


@contextmanager
def patch_main_dependencies(registry: Any = None, app: Any = None):
    """Patch heavy side-effects (dotenv, DB, uvicorn) that fire at ``main.py`` import time.

    Args:
        registry: Optional override for the patched ``ServiceRegistry`` instance.
        app: Optional override for the patched FastAPI app instance.

    Yields:
        ``None`` while all four patches are active.
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
    """Remove ``main`` from ``sys.modules`` and re-import with side-effects patched out.

    Args:
        registry: Optional override for the patched ``ServiceRegistry`` instance.
        app: Optional override for the patched FastAPI app instance.

    Returns:
        The freshly-imported ``main`` module.
    """
    sys.modules.pop("main", None)
    with patch_main_dependencies(registry=registry, app=app):
        return importlib.import_module("main")
