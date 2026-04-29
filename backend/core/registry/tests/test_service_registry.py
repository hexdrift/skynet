"""Unit tests for ``ServiceRegistry``."""

from __future__ import annotations

from typing import Any

import pytest

from core.registry.core import (
    DuplicateRegistrationError,
    ServiceRegistry,
    UnknownRegistrationError,
)


def _module_factory(**_kwargs: Any) -> object:
    """Return a placeholder module instance for registry tests."""
    return object()


def _metric(_gold: object, _pred: object, _trace: object = None) -> float:
    """Return a fixed metric score for registry tests."""
    return 1.0


def _optimizer_factory(**_kwargs: Any) -> object:
    """Return a placeholder optimizer instance for registry tests."""
    return object()


def _noop() -> None:
    """No-op factory used when the test only inspects identity."""


@pytest.fixture
def registry() -> ServiceRegistry:
    """Yield a fresh empty ``ServiceRegistry`` for each test.

    Returns:
        A new ``ServiceRegistry`` instance with no entries.
    """
    return ServiceRegistry()


def test_register_module_then_get_returns_factory(registry: ServiceRegistry) -> None:
    """Register module then get returns factory."""
    registry.register_module("my_module", _module_factory)

    assert registry.get_module("my_module") is _module_factory


def test_register_metric_then_get_returns_callable(registry: ServiceRegistry) -> None:
    """Register metric then get returns callable."""
    registry.register_metric("exact_match", _metric)

    assert registry.get_metric("exact_match") is _metric


def test_register_optimizer_then_get_returns_factory(registry: ServiceRegistry) -> None:
    """Register optimizer then get returns factory."""
    registry.register_optimizer("bootstrap", _optimizer_factory)

    assert registry.get_optimizer("bootstrap") is _optimizer_factory


@pytest.mark.parametrize(
    ("register", "get"),
    [
        ("register_module", "get_module"),
        ("register_metric", "get_metric"),
        ("register_optimizer", "get_optimizer"),
    ],
    ids=["module", "metric", "optimizer"],
)
def test_duplicate_registration_raises(
    registry: ServiceRegistry,
    register: str,
    get: str,
) -> None:
    """Duplicate registration raises."""
    getattr(registry, register)("name", _noop)

    with pytest.raises(DuplicateRegistrationError, match="already registered"):
        getattr(registry, register)("name", _noop)


@pytest.mark.parametrize(
    "get_method",
    ["get_module", "get_metric", "get_optimizer"],
    ids=["module", "metric", "optimizer"],
)
def test_unknown_lookup_raises(registry: ServiceRegistry, get_method: str) -> None:
    """Unknown lookup raises."""
    with pytest.raises(UnknownRegistrationError, match="Unknown"):
        getattr(registry, get_method)("nonexistent")


def test_snapshot_empty_registry_returns_empty_lists(registry: ServiceRegistry) -> None:
    """Snapshot empty registry returns empty lists."""
    snap = registry.snapshot()

    assert snap == {"modules": [], "metrics": [], "optimizers": []}


def test_snapshot_reflects_registered_names(registry: ServiceRegistry) -> None:
    """Snapshot reflects registered names."""
    registry.register_module("mod_b", _noop)
    registry.register_module("mod_a", _noop)
    registry.register_metric("f1", _metric)
    registry.register_optimizer("fake_opt", _noop)

    snap = registry.snapshot()

    assert snap["modules"] == ["mod_a", "mod_b"]
    assert snap["metrics"] == ["f1"]
    assert snap["optimizers"] == ["fake_opt"]


def test_snapshot_updates_after_new_registration(registry: ServiceRegistry) -> None:
    """Snapshot updates after new registration."""
    registry.register_module("first", _noop)
    snap_before = registry.snapshot()

    registry.register_module("second", _noop)
    snap_after = registry.snapshot()

    assert "second" not in snap_before["modules"]
    assert "second" in snap_after["modules"]


def test_two_registries_do_not_share_state() -> None:
    """Two registries do not share state."""
    reg_a = ServiceRegistry()
    reg_b = ServiceRegistry()

    reg_a.register_module("shared_name", _noop)

    with pytest.raises(UnknownRegistrationError):
        reg_b.get_module("shared_name")


def test_duplicate_check_is_per_instance_not_global() -> None:
    """Duplicate check is per instance not global."""
    reg_a = ServiceRegistry()
    reg_b = ServiceRegistry()

    reg_a.register_module("name", _noop)
    reg_b.register_module("name", _noop)

    assert reg_b.get_module("name") is _noop
