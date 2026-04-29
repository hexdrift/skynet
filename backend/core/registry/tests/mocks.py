"""Mock builders for registry tests.

All helpers here return lightweight stand-ins seeded with realistic names
from the production fixtures — not arbitrary strings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Final
from unittest.mock import MagicMock, patch

REAL_MODULE_NAME = "cot"
REAL_OPTIMIZER_NAME = "gepa"

_UNSET: Final[object] = object()


def fake_dspy_module() -> Callable[..., Any]:
    """Return a no-op DSPy-module-shaped factory for resolver tests.

    Returns:
        A callable that accepts arbitrary kwargs and returns a fresh object.
    """
    def _module(**_kwargs: Any) -> object:
        """Return a placeholder DSPy-module instance ignoring all kwargs."""
        return object()

    return _module


def fake_optimizer_class() -> Callable[..., Any]:
    """Return a no-op optimizer-shaped factory for resolver tests.

    Returns:
        A callable that accepts arbitrary kwargs and returns a fresh object.
    """
    def _optimizer(**_kwargs: Any) -> object:
        """Return a placeholder optimizer instance ignoring all kwargs."""
        return object()

    return _optimizer


@contextmanager
def patch_loader(
    return_value: Callable[..., Any] | object = _UNSET,
    side_effect: Any = None,
) -> Iterator[MagicMock]:
    """Yield a context patching ``_load_callable`` for resolver tests.

    Args:
        return_value: Callable to return from the patched loader. Defaults
            to a fresh ``fake_dspy_module`` when omitted; pass ``None``
            explicitly to return ``None`` from the loader.
        side_effect: Optional callable invoked per call to drive dynamic
            behaviour (raise, return, etc.).

    Yields:
        The underlying ``unittest.mock.MagicMock``.
    """
    effective_return: Any = fake_dspy_module() if return_value is _UNSET else return_value

    with patch(
        "core.registry.resolvers._load_callable",
        return_value=effective_return,
        side_effect=side_effect,
    ) as mock:
        yield mock
