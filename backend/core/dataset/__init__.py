"""Dataset profiling and split-plan recommendations.

Pure functions that inspect an uploaded dataset and suggest sensible
train/val/test fractions plus warnings. Called from the submit wizard
via ``POST /datasets/profile`` and surfaces a preview card the user can
accept or override. The runtime splitter in
``service_gateway.data.split_examples`` still applies the final fractions
at job-execution time, so this module is purely advisory.
"""

from .planner import recommend_split
from .profiler import profile_dataset

__all__ = [
    "profile_dataset",
    "recommend_split",
]
