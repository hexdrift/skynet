"""Status and type filters shared by the optimization router files.

These derive from the Pydantic :class:`~core.models.OptimizationStatus`
enum and the wire-level ``OPTIMIZATION_TYPE_*`` strings in
:mod:`core.constants`. Grouping them here keeps every router file in this
subpackage aligned on a single source of truth without forcing each one
to import :mod:`_helpers` for unrelated symbols.
"""

from __future__ import annotations

from ...constants import OPTIMIZATION_TYPE_GRID_SEARCH, OPTIMIZATION_TYPE_RUN
from ...models import OptimizationStatus

TERMINAL_STATUSES = {
    OptimizationStatus.success,
    OptimizationStatus.failed,
    OptimizationStatus.cancelled,
    # Paused is "terminal" in the lifecycle sense — no worker holds it and it has a
    # completed_at — but it is resumable (see ``is_resumable``). Grouping it here
    # keeps est-remaining, the cancel guard, and frontend active/terminal logic correct.
    OptimizationStatus.paused,
}

VALID_STATUSES = {s.value for s in OptimizationStatus}

VALID_OPTIMIZATION_TYPES = {OPTIMIZATION_TYPE_RUN, OPTIMIZATION_TYPE_GRID_SEARCH}
