"""DSPy optimization pipeline: compile, evaluate, persist, and stream progress.

This subpackage groups every module that participates in running an
optimization job end-to-end: :mod:`core` (the :class:`DspyService` facade),
:mod:`data` (dataset loading and splitting), :mod:`optimizers`
(per-strategy compile helpers), :mod:`progress` (tqdm / callback capture),
:mod:`artifacts` (program persistence), :mod:`timing` (LM call timing
callback), and :mod:`validators` (payload-level checks).
"""

from __future__ import annotations

from .core import DspyService

__all__ = ["DspyService"]
