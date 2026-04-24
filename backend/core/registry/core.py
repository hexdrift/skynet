from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Any

import dspy

ModuleFactory = Callable[..., "dspy.Module"]
MetricFn = Callable[..., float]
OptimizerFactory = Callable[..., Any]


class RegistryError(RuntimeError):
    """Base exception raised for registry-related issues."""


class DuplicateRegistrationError(RegistryError):
    """Raised when a user attempts to register the same key twice."""


class UnknownRegistrationError(RegistryError):
    """Raised when requesting an entry that does not exist."""


@dataclass
class ServiceRegistry:
    """Holds user-defined factories for modules, metrics, and optimizers."""

    modules: MutableMapping[str, ModuleFactory] = field(default_factory=dict)
    metrics: MutableMapping[str, MetricFn] = field(default_factory=dict)
    optimizers: MutableMapping[str, OptimizerFactory] = field(default_factory=dict)

    def register_module(self, name: str, factory: ModuleFactory) -> None:
        """Register a DSPy module factory under a short name.

        Args:
            name: Short identifier used in RunRequest.module_name.
            factory: Callable returning a dspy.Module instance.

        Raises:
            DuplicateRegistrationError: If ``name`` is already registered.
        """
        self._register(self.modules, name, factory)

    def register_metric(self, name: str, metric: MetricFn) -> None:
        """Register a metric function under a short name.

        Args:
            name: Short identifier for the metric.
            metric: Callable accepting (gold, pred[, trace]) and returning a float.

        Raises:
            DuplicateRegistrationError: If ``name`` is already registered.
        """
        self._register(self.metrics, name, metric)

    def register_optimizer(self, name: str, factory: OptimizerFactory) -> None:
        """Register an optimizer factory under a short name.

        Args:
            name: Short identifier used in RunRequest.optimizer_name.
            factory: Callable returning a DSPy teleprompt optimizer instance.

        Raises:
            DuplicateRegistrationError: If ``name`` is already registered.
        """
        self._register(self.optimizers, name, factory)

    def get_module(self, name: str) -> ModuleFactory:
        """Return the module factory registered under ``name``.

        Args:
            name: Identifier passed to register_module.

        Returns:
            The registered ModuleFactory callable.

        Raises:
            UnknownRegistrationError: If no module is registered under ``name``.
        """
        return self._get(self.modules, name, kind="module")

    def get_metric(self, name: str) -> MetricFn:
        """Return the metric function registered under ``name``.

        Args:
            name: Identifier passed to register_metric.

        Returns:
            The registered MetricFn callable.

        Raises:
            UnknownRegistrationError: If no metric is registered under ``name``.
        """
        return self._get(self.metrics, name, kind="metric")

    def get_optimizer(self, name: str) -> OptimizerFactory:
        """Return the optimizer factory registered under ``name``.

        Args:
            name: Identifier passed to register_optimizer.

        Returns:
            The registered OptimizerFactory callable.

        Raises:
            UnknownRegistrationError: If no optimizer is registered under ``name``.
        """
        return self._get(self.optimizers, name, kind="optimizer")

    def snapshot(self) -> dict[str, list[str]]:
        """Return sorted registered names keyed by asset type.

        Returns:
            Dict with keys ``"modules"``, ``"metrics"``, and ``"optimizers"``,
            each mapping to a sorted list of registered names.
        """
        return {
            "modules": sorted(self.modules.keys()),
            "metrics": sorted(self.metrics.keys()),
            "optimizers": sorted(self.optimizers.keys()),
        }

    @staticmethod
    def _register(store: MutableMapping[str, Any], name: str, value: Any) -> None:
        """Insert ``value`` into ``store`` under ``name``, raising on duplicates.

        Args:
            store: The mutable mapping to insert into.
            name: Key to register under.
            value: Factory or callable to store.

        Raises:
            DuplicateRegistrationError: If ``name`` already exists in ``store``.
        """
        if name in store:
            raise DuplicateRegistrationError(f"Entry '{name}' already registered.")
        store[name] = value

    @staticmethod
    def _get(store: Mapping[str, Any], name: str, *, kind: str) -> Any:
        """Look up ``name`` in ``store``, raising a typed error when missing.

        Args:
            store: The mapping to search.
            name: Key to look up.
            kind: Human-readable asset type used in the error message.

        Returns:
            The value stored under ``name``.

        Raises:
            UnknownRegistrationError: If ``name`` is not present in ``store``.
        """
        try:
            return store[name]
        except KeyError as exc:
            raise UnknownRegistrationError(f"Unknown {kind} '{name}'.") from exc
