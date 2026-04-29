"""Real cached fixtures captured from a live run of the Skynet API.

Every file here was captured from a running backend — nothing is hand-built.
Unit tests that need a realistic OptimizationStatusResponse, ProgramArtifact,
GridSearchResponse, progress event, or dataset row should load them from here
instead of fabricating domain objects.

Canonical job fixtures (each has `.detail.json`, `.summary.json`, `.logs.json`):
    jobs/success_single_gepa        — gepa/cot run, 864 logs, real base64 pickle
    jobs/success_grid               — 2-pair grid-search, both pairs with artifacts
    jobs/failed_runtime             — failure during LM call, 22 logs, real traceback
    jobs/failed_pre_validation      — failure at build_language_model, 1 log
    jobs/cancelled_pre_work         — cancelled before worker started
    jobs/cancelled_mid_run          — cancelled after dataset_splits_ready

Datasets:
    datasets/math_small.json        — 20-row head of data/math_problems.json

All raw captures (14 existing DB jobs + 4 new recordings) live under `jobs/raw/`.
Anything in `jobs/*.json` at the top level is a copy of a raw file, not a derivative.

Usage:
    from tests.fixtures import load_fixture

    detail = load_fixture("jobs/success_single_gepa.detail.json")
    summary = load_fixture("jobs/success_single_gepa.summary.json")
    dataset = load_fixture("datasets/math_small.json")
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

FIXTURES_ROOT = Path(__file__).parent


@cache
def _read(path: str) -> str:
    """Read and cache the raw text of a fixture file at *path* relative to FIXTURES_ROOT.

    Args:
        path: Relative path from ``FIXTURES_ROOT``, e.g. ``"jobs/success_single_gepa.detail.json"``.

    Returns:
        The raw text contents of the fixture file.
    """
    return (FIXTURES_ROOT / path).read_text()


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by relative path.

    Args:
        name: Path relative to `backend/tests/fixtures/`, e.g.
            ``"jobs/success_single_gepa.detail.json"``.

    Returns:
        The parsed JSON payload (fresh dict/list on every call — mutation is safe).

    Raises:
        FileNotFoundError: If the fixture file does not exist.
    """
    return json.loads(_read(name))
