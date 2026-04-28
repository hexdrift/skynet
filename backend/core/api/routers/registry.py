"""Read-only registry snapshot router.

Exposes the set of module, metric, and optimizer names currently registered
with the backing ``ServiceRegistry``. Used by the generalist agent to
discover which optimizer / module identifiers are valid before driving a
submission, and by the frontend to populate dropdowns.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...registry import ServiceRegistry


class RegistrySnapshotResponse(BaseModel):
    """Names of registered modules, metrics, and optimizers."""

    modules: list[str]
    metrics: list[str]
    optimizers: list[str]


def create_registry_router(*, registry: ServiceRegistry) -> APIRouter:
    """Build the registry snapshot router.

    Args:
        registry: The ``ServiceRegistry`` whose snapshot should be exposed.

    Returns:
        A FastAPI ``APIRouter`` with the ``/registry`` route mounted.
    """
    router = APIRouter()

    @router.get(
        "/registry",
        response_model=RegistrySnapshotResponse,
        summary="List registered modules, metrics, and optimizers",
        tags=["agent"],
    )
    def get_registry_snapshot() -> RegistrySnapshotResponse:
        """Return sorted names of every registered module, metric, and optimizer.

        Returns:
            A ``RegistrySnapshotResponse`` with three sorted name lists.
        """
        snap = registry.snapshot()
        return RegistrySnapshotResponse(
            modules=snap["modules"],
            metrics=snap["metrics"],
            optimizers=snap["optimizers"],
        )

    return router
