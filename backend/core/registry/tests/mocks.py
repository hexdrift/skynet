"""Mock builders for registry tests.

All helpers here return lightweight stand-ins seeded with realistic names
from the production fixtures — not arbitrary strings.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

# Canonical names drawn from the live-captured fixture files.
REAL_MODULE_NAME = "cot"
REAL_OPTIMIZER_NAME = "gepa"


def fake_dspy_module() -> Callable[..., Any]:
    """Return a no-op DSPy-module-shaped factory for resolver tests."""
    # Resolver only needs the factory to be callable — it does not inspect the result.
    def _module(**kwargs: Any) -> object:
        return object()

    return _module


def fake_optimizer_class() -> Callable[..., Any]:
    """Return a no-op optimizer-shaped factory for resolver tests."""
    def _optimizer(**kwargs: Any) -> object:
        return object()

    return _optimizer


@contextmanager
def patch_loader(return_value: Callable[..., Any] | None = None, side_effect: Any = None):
    """Yield a context patching ``_load_callable`` for resolver tests.

    Args:
        return_value: Default callable for the patched loader. Defaults to a
            ``fake_dspy_module`` instance when both arguments are omitted.
        side_effect: Optional callable invoked per call to drive dynamic
            behaviour (raise, return, etc.).

    Yields:
        The underlying ``unittest.mock`` object.
    """
    if return_value is None and side_effect is None:
        return_value = fake_dspy_module()

    with patch(
        "core.registry.resolvers._load_callable",
        return_value=return_value,
        side_effect=side_effect,
    ) as mock:
        yield mock
