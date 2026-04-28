"""Background worker for DSPy optimization jobs.

Engine, log handler, and subprocess runner are reached via their
submodules (``core.worker.engine``, ``core.worker.log_handler``,
``core.worker.subprocess_runner``). Re-exporting from ``__init__``
would force every importer of any submodule to load ``engine``, which
imports ``service_gateway``, which loads ``optimization.core``, which
needs ``log_handler`` — a cycle. Keeping this file empty breaks it.
"""

from __future__ import annotations

__all__: list[str] = []
