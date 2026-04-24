"""Tests for resolver helpers.

DSPy-alias paths (predict, cot, gepa) exercise real DSPy imports and are
covered only partially here — see "Coverage gaps" in the report.  All
other behaviors are exercised without touching DSPy.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from core.registry.resolvers import (
    MODULE_ALIASES,
    OPTIMIZER_ALIASES,
    ResolverError,
    _load_callable,
    _match_module_alias,
    _match_optimizer_alias,
    _wrap_callable,
    resolve_module_factory,
    resolve_optimizer_factory,
)
from core.registry.tests.mocks import (
    REAL_MODULE_NAME,
    REAL_OPTIMIZER_NAME,
    fake_dspy_module,
    patch_loader,
)



@pytest.mark.parametrize(
    "name, expected_key",
    [
        ("predict", "predict"),
        ("PREDICT", "predict"),  # case-insensitive
        ("cot", "cot"),
        ("CoT", "cot"),
    ],
    ids=["predict_lower", "predict_upper", "cot_lower", "cot_mixed"],
)
def test_match_module_alias_known_names(name: str, expected_key: str) -> None:
    """Verify _match_module_alias resolves known alias names case-insensitively."""
    result = _match_module_alias(name)

    assert result is MODULE_ALIASES[expected_key]


def test_match_module_alias_unknown_returns_none() -> None:
    """Verify _match_module_alias returns None for an unregistered name."""
    assert _match_module_alias("totally_unknown") is None



@pytest.mark.parametrize(
    "name, expected_key",
    [
        ("gepa", "gepa"),
        ("GEPA", "gepa"),
    ],
    ids=["gepa_lower", "gepa_upper"],
)
def test_match_optimizer_alias_known_names(name: str, expected_key: str) -> None:
    """Verify _match_optimizer_alias resolves known optimizer names case-insensitively."""
    result = _match_optimizer_alias(name)

    assert result == OPTIMIZER_ALIASES[expected_key]


def test_match_optimizer_alias_unknown_returns_none() -> None:
    """Verify _match_optimizer_alias returns None for an unregistered name."""
    assert _match_optimizer_alias("unknown_optimizer") is None



def test_load_callable_stdlib_path_returns_callable() -> None:
    """Verify _load_callable returns a callable for a valid stdlib dotted path."""
    # os.path.join is a well-known stdlib callable
    target = _load_callable("os.path.join")

    assert callable(target)


def test_load_callable_bad_module_raises_resolver_error() -> None:
    """Verify _load_callable raises ResolverError when the module cannot be imported."""
    with pytest.raises(ResolverError, match="Unable to import"):
        _load_callable("no_such_package_xyz.SomeClass")


def test_load_callable_missing_attribute_raises_resolver_error() -> None:
    """Verify _load_callable raises ResolverError for a missing attribute."""
    with pytest.raises(ResolverError, match="has no attribute"):
        _load_callable("os.path.NO_SUCH_ATTRIBUTE_XYZ")


def test_load_callable_non_callable_attribute_raises_resolver_error() -> None:
    """Verify _load_callable raises ResolverError when the attribute is not callable."""
    # os.path.sep is a string constant, not callable
    with pytest.raises(ResolverError, match="not callable"):
        _load_callable("os.path.sep")



def test_wrap_callable_preserves_call_behavior() -> None:
    """Verify _wrap_callable produces a callable that invokes the original target."""
    def add(a: int, b: int) -> int:
        return a + b

    wrapped = _wrap_callable(add)

    assert wrapped(1, 2) == 3


def test_wrap_callable_copies_signature() -> None:
    """Verify _wrap_callable preserves the original function's inspect signature."""

    def my_fn(x: int, y: str = "hello") -> None:
        pass

    wrapped = _wrap_callable(my_fn)

    assert str(inspect.signature(wrapped)) == str(inspect.signature(my_fn))


def test_wrap_callable_returns_callable() -> None:
    """Verify _wrap_callable returns a callable object."""
    wrapped = _wrap_callable(len)

    assert isinstance(wrapped, Callable)



def test_resolve_module_factory_unknown_raises() -> None:
    """Verify resolve_module_factory raises ResolverError for completely unknown names."""
    with pytest.raises(ResolverError, match="Unknown module"):
        resolve_module_factory("completely_unknown_module")


def test_resolve_module_factory_non_dspy_dotted_path_raises() -> None:
    """Verify resolve_module_factory rejects dotted paths not starting with 'dspy.'."""
    # Has a dot but does NOT start with "dspy." so should raise
    with pytest.raises(ResolverError, match="Unknown module"):
        resolve_module_factory("some.other.Module")


def test_resolve_module_factory_dspy_prefix_with_bad_path_raises() -> None:
    """Verify resolve_module_factory raises ResolverError for an invalid dspy path."""
    with pytest.raises(ResolverError):
        resolve_module_factory("dspy.NonExistentClassXYZ9999")


def test_resolve_module_factory_returns_tuple_of_callable_and_bool() -> None:
    """Verify resolve_module_factory returns a (callable, bool) tuple."""
    # Patch _load_callable so we never actually import dspy
    with patch_loader(return_value=fake_dspy_module()):
        result = resolve_module_factory("dspy.SomeFakeClass")

    factory, auto_sig = result
    assert callable(factory)
    assert isinstance(auto_sig, bool)



def test_resolve_optimizer_factory_unknown_raises() -> None:
    """Verify resolve_optimizer_factory raises ResolverError for unknown names."""
    with pytest.raises(ResolverError, match="Unknown optimizer"):
        resolve_optimizer_factory("no_such_optimizer")


def test_resolve_optimizer_factory_non_dspy_dotted_path_raises() -> None:
    """Verify resolve_optimizer_factory rejects dotted paths not starting with 'dspy.'."""
    with pytest.raises(ResolverError, match="Unknown optimizer"):
        resolve_optimizer_factory("some.other.Optimizer")


def test_resolve_optimizer_factory_dspy_prefix_with_bad_path_raises() -> None:
    """Verify resolve_optimizer_factory raises ResolverError for an invalid dspy path."""
    with pytest.raises(ResolverError):
        resolve_optimizer_factory("dspy.teleprompt.NonExistentXYZ9999")


def test_resolve_optimizer_factory_returns_callable() -> None:
    """Verify resolve_optimizer_factory returns a callable."""
    with patch_loader(return_value=fake_dspy_module()):
        result = resolve_optimizer_factory("dspy.SomeFakeOptimizer")

    assert callable(result)



def test_resolve_module_factory_alias_first_path_fails_second_succeeds() -> None:
    """When the first alias path raises ResolverError the resolver tries the next."""
    dummy = fake_dspy_module()
    call_log: list[str] = []

    def selective_load(path: str) -> Callable[..., Any]:
        call_log.append(path)
        # "cot" has two paths: dspy.modules.ChainOfThought and dspy.ChainOfThought
        if path == "dspy.modules.ChainOfThought":
            raise ResolverError("first path unavailable")
        return dummy

    with patch_loader(side_effect=selective_load):
        factory, auto_sig = resolve_module_factory(REAL_MODULE_NAME)

    assert callable(factory)
    assert auto_sig is True
    # Both paths must have been attempted
    assert "dspy.modules.ChainOfThought" in call_log
    assert "dspy.ChainOfThought" in call_log


def test_resolve_module_factory_alias_all_paths_fail_raises_resolver_error() -> None:
    """Verify resolve_module_factory re-raises ResolverError when all alias paths fail."""

    def always_fail(path: str) -> Callable[..., Any]:
        raise ResolverError(f"cannot load {path}")

    with patch_loader(side_effect=always_fail):
        with pytest.raises(ResolverError, match=REAL_MODULE_NAME):
            resolve_module_factory(REAL_MODULE_NAME)


def test_resolve_module_factory_alias_all_paths_fail_error_mentions_name() -> None:
    """Verify the ResolverError message includes the original alias name on total failure."""

    def always_fail(path: str) -> Callable[..., Any]:
        raise ResolverError(f"nope: {path}")

    with patch_loader(side_effect=always_fail):
        with pytest.raises(ResolverError) as exc_info:
            resolve_module_factory(REAL_MODULE_NAME)

    assert REAL_MODULE_NAME in str(exc_info.value)
