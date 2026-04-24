from __future__ import annotations

import pytest

from core.registry.core import (
    DuplicateRegistrationError,
    ServiceRegistry,
    UnknownRegistrationError,
)



@pytest.fixture()
def registry() -> ServiceRegistry:
    """Return a fresh empty ServiceRegistry."""
    return ServiceRegistry()



def test_register_module_then_get_returns_factory(registry: ServiceRegistry) -> None:
    """Verify get_module returns the exact factory registered under a name."""
    factory = lambda **kw: None  # noqa: E731

    registry.register_module("my_module", factory)

    assert registry.get_module("my_module") is factory


def test_register_metric_then_get_returns_callable(registry: ServiceRegistry) -> None:
    """Verify get_metric returns the exact callable registered under a name."""
    metric = lambda gold, pred, trace=None: 1.0  # noqa: E731

    registry.register_metric("exact_match", metric)

    assert registry.get_metric("exact_match") is metric


def test_register_optimizer_then_get_returns_factory(registry: ServiceRegistry) -> None:
    """Verify get_optimizer returns the exact factory registered under a name."""
    opt_factory = lambda **kw: object()  # noqa: E731

    registry.register_optimizer("bootstrap", opt_factory)

    assert registry.get_optimizer("bootstrap") is opt_factory



@pytest.mark.parametrize(
    "register, get",
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
    get: str,  # noqa: ARG001
) -> None:
    """Verify registering the same name twice raises DuplicateRegistrationError."""
    fn = lambda: None  # noqa: E731
    getattr(registry, register)("name", fn)

    with pytest.raises(DuplicateRegistrationError, match="already registered"):
        getattr(registry, register)("name", fn)



@pytest.mark.parametrize(
    "get_method",
    ["get_module", "get_metric", "get_optimizer"],
    ids=["module", "metric", "optimizer"],
)
def test_unknown_lookup_raises(registry: ServiceRegistry, get_method: str) -> None:
    """Verify looking up an unregistered name raises UnknownRegistrationError."""
    with pytest.raises(UnknownRegistrationError, match="Unknown"):
        getattr(registry, get_method)("nonexistent")



def test_snapshot_empty_registry_returns_empty_lists(registry: ServiceRegistry) -> None:
    """Verify snapshot on an empty registry returns empty lists for all keys."""
    snap = registry.snapshot()

    assert snap == {"modules": [], "metrics": [], "optimizers": []}


def test_snapshot_reflects_registered_names(registry: ServiceRegistry) -> None:
    """Verify snapshot lists all registered names sorted alphabetically."""
    registry.register_module("mod_b", lambda: None)
    registry.register_module("mod_a", lambda: None)
    registry.register_metric("f1", lambda g, p: 0.0)
    registry.register_optimizer("fake_opt", lambda: None)

    snap = registry.snapshot()

    assert snap["modules"] == ["mod_a", "mod_b"]  # sorted
    assert snap["metrics"] == ["f1"]
    assert snap["optimizers"] == ["fake_opt"]


def test_snapshot_updates_after_new_registration(registry: ServiceRegistry) -> None:
    """Verify snapshot reflects new registrations after the initial snapshot."""
    registry.register_module("first", lambda: None)
    snap_before = registry.snapshot()

    registry.register_module("second", lambda: None)
    snap_after = registry.snapshot()

    assert "second" not in snap_before["modules"]
    assert "second" in snap_after["modules"]



def test_two_registries_do_not_share_state() -> None:
    """Verify distinct ServiceRegistry instances have independent storage."""
    reg_a = ServiceRegistry()
    reg_b = ServiceRegistry()
    factory = lambda: None  # noqa: E731

    reg_a.register_module("shared_name", factory)

    with pytest.raises(UnknownRegistrationError):
        reg_b.get_module("shared_name")


def test_duplicate_check_is_per_instance_not_global() -> None:
    """Verify the same name can be registered in two different registry instances."""
    reg_a = ServiceRegistry()
    reg_b = ServiceRegistry()
    factory = lambda: None  # noqa: E731

    reg_a.register_module("name", factory)
    # Should not raise even though reg_a already has "name"
    reg_b.register_module("name", factory)

    assert reg_b.get_module("name") is factory
