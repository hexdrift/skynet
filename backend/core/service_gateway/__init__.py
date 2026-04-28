"""Service gateway package exposing the DspyService and shared error type."""

from __future__ import annotations

from ..exceptions import ServiceError
from .optimization.core import DspyService

__all__ = ["DspyService", "ServiceError"]
