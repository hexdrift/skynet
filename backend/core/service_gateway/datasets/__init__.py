"""Dataset profiling and split-planning utilities.

:mod:`profiler` inspects a raw dataset and emits schema/quality
diagnostics; :mod:`planner` recommends train/val/test split sizes given
profile results and user preferences.
"""

from __future__ import annotations
