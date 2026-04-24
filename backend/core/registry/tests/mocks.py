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
    """Return a minimal callable that satisfies the registry module contract.

    The resolver only needs the factory to be callable; it does not inspect
    the returned object during resolution.

    Returns:
        A no-op factory callable that accepts ``**kwargs`` and returns an object.
    """

    def _module(**kwargs: Any) -> object:
        return object()

    return _module


def fake_optimizer_class() -> Callable[..., Any]:
    """Return a minimal callable that satisfies the registry optimizer contract.

    Returns:
        A no-op callable that accepts ``**kwargs`` and returns an object.
    """

    def _optimizer(**kwargs: Any) -> object:
        return object()

    return _optimizer


@contextmanager
def patch_loader(return_value: Callable[..., Any] | None = None, side_effect: Any = None):
    """Context manager that patches ``core.registry.resolvers._load_callable``.

    Args:
        return_value: Value to return from _load_callable.  Defaults to
            ``fake_dspy_module()`` when neither argument is supplied.
        side_effect: Callable or exception to use as side_effect instead of
            return_value.  Mirrors ``unittest.mock.patch`` semantics.

    Yields:
        The ``unittest.mock.MagicMock`` object used to patch ``_load_callable``.
    """
    if return_value is None and side_effect is None:
        return_value = fake_dspy_module()

    with patch(
        "core.registry.resolvers._load_callable",
        return_value=return_value,
        side_effect=side_effect,
    ) as mock:
        yield mock
