from __future__ import annotations

import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from ..constants import RESOLUTION_HINT

DSPY_PREFIX = "dspy."


@dataclass(frozen=True)
class ModuleAlias:
    """Describe how to resolve a module alias."""

    paths: tuple[str, ...]
    auto_signature: bool = False


MODULE_ALIASES: dict[str, ModuleAlias] = {
    "predict": ModuleAlias(("dspy.Predict",), auto_signature=True),
    "cot": ModuleAlias(
        (
            "dspy.modules.ChainOfThought",
            "dspy.ChainOfThought",
        ),
        auto_signature=True,
    ),
}

OPTIMIZER_ALIASES: dict[str, str] = {
    "gepa": "dspy.teleprompt.GEPA",
}

AUTO_SIGNATURE_PATHS = {path for alias in MODULE_ALIASES.values() if alias.auto_signature for path in alias.paths}


class ResolverError(RuntimeError):
    """Raised when a requested DSPy asset cannot be resolved."""


def resolve_module_factory(name: str) -> tuple[Callable[..., Any], bool]:
    """Resolve a module factory from aliases or dotted paths.

    Args:
        name: Short alias (e.g. ``"predict"``) or dotted dspy path (e.g. ``"dspy.Predict"``).

    Returns:
        A ``(factory, auto_signature)`` tuple where ``auto_signature`` is True
        when the service gateway should auto-inject a compiled DSPy signature
        rather than requiring one in ``module_kwargs``.

    Raises:
        ResolverError: If ``name`` cannot be resolved to a callable.
    """

    spec = _match_module_alias(name)
    if spec is not None:
        last_error: Exception | None = None
        for path in spec.paths:
            try:
                target = _load_callable(path)
                return _wrap_callable(target), spec.auto_signature
            except ResolverError as exc:  # pragma: no cover - best effort fallbacks
                last_error = exc
                continue
        raise ResolverError(f"Unknown module '{name}'. {RESOLUTION_HINT}") from last_error
    if name.startswith(DSPY_PREFIX):
        target = _load_callable(name)
        auto_signature = name in AUTO_SIGNATURE_PATHS
        return _wrap_callable(target), auto_signature
    raise ResolverError(f"Unknown module '{name}'. {RESOLUTION_HINT}")


def resolve_optimizer_factory(name: str) -> Callable[..., Any]:
    """Resolve an optimizer factory from aliases or dotted paths.

    Args:
        name: Short alias (e.g. ``"gepa"``) or dotted dspy path.

    Returns:
        A wrapped callable that instantiates the optimizer when called.

    Raises:
        ResolverError: If ``name`` cannot be resolved to a callable.
    """

    path = _match_optimizer_alias(name)
    if path:
        target = _load_callable(path)
        return _wrap_callable(target)
    if name.startswith(DSPY_PREFIX):
        target = _load_callable(name)
        return _wrap_callable(target)
    raise ResolverError(f"Unknown optimizer '{name}'. {RESOLUTION_HINT}")


def _match_module_alias(name: str) -> ModuleAlias | None:
    """Return the ModuleAlias for ``name`` (case-insensitive), or None if unknown.

    Args:
        name: Alias name to look up (e.g. ``"predict"`` or ``"cot"``).

    Returns:
        The matching ``ModuleAlias``, or ``None`` when the name is not registered.
    """
    return MODULE_ALIASES.get(name.lower())


def _match_optimizer_alias(name: str) -> str | None:
    """Return the dotted-path string for ``name`` (case-insensitive), or None if unknown.

    Args:
        name: Alias name to look up (e.g. ``"gepa"``).

    Returns:
        Dotted import path string, or ``None`` when the name is not registered.
    """
    return OPTIMIZER_ALIASES.get(name.lower())


def _load_callable(path: str) -> Callable[..., Any]:
    """Import a callable attribute specified by dotted path (e.g. ``dspy.Predict``).

    Args:
        path: Dotted import path in ``module.attribute`` form.

    Returns:
        The callable attribute resolved from ``path``.

    Raises:
        ResolverError: If the module cannot be imported or the attribute is missing or not callable.
    """
    module_path, attribute = path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise ResolverError(f"Unable to import '{module_path}': {exc}") from exc
    try:
        target = getattr(module, attribute)
    except AttributeError as exc:
        raise ResolverError(f"Module '{module_path}' has no attribute '{attribute}'.") from exc
    if not callable(target):
        raise ResolverError(f"Attribute '{path}' is not callable.")
    return target


def _wrap_callable(target: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap ``target`` in a thin factory that preserves its call signature.

    Args:
        target: The callable to wrap.

    Returns:
        A new callable that forwards all positional and keyword arguments to ``target``.
    """
    try:
        signature = inspect.signature(target)
    except (ValueError, TypeError):
        signature = None

    @wraps(target)
    def factory(*args: Any, **kwargs: Any) -> Any:
        return target(*args, **kwargs)

    if signature is not None:
        factory.__signature__ = signature
    return factory
