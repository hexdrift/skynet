"""Backend facade over the shared Skynet i18n catalog.

The canonical catalog lives at ``i18n/locales/he.json`` in the repo root, and
``scripts/generate_i18n.py`` copies it into ``backend/core/i18n_locales/he.json``
so wheel installs keep the catalog inside the package. Backend modules keep
using ``t(key, **params)`` and the short constants below, but the Hebrew
strings and domain terms are no longer mirrored in Python code.

The formatter is intentionally small: it supports ``{name}`` params plus
``{term.someKey}`` placeholders resolved from the shared terms section. If we
need richer plural/gender formatting later, this facade is the single place to
swap in Fluent, Babel/gettext, or an ICU-compatible formatter.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Lookup the in-package copy first (works for wheel installs and air-gap),
# and fall back to the repo-root canonical when running from a source tree
# without the bundled copy. Module-level constant so import never blocks on
# disk I/O — the catalog itself is read lazily by ``_catalog()``.
_PACKAGE_CATALOG = Path(__file__).resolve().parent / "i18n_locales" / "he.json"
_REPO_CATALOG = Path(__file__).resolve().parents[2] / "i18n" / "locales" / "he.json"
CATALOG_PATH = _PACKAGE_CATALOG if _PACKAGE_CATALOG.is_file() else _REPO_CATALOG
TERM_PATTERN = re.compile(r"{term\.([A-Za-z0-9_]+)}")

_TERM_KEYS: dict[str, str] = {
    "TERM_OPTIMIZATION": "optimization",
    "TERM_OPTIMIZATION_PLURAL": "optimizationPlural",
    "TERM_DATASET": "dataset",
    "TERM_EXAMPLE": "example",
    "TERM_EXAMPLE_PLURAL": "examplePlural",
    "TERM_ROW": "row",
    "TERM_ROW_PLURAL": "rowPlural",
    "TERM_COLUMN": "column",
    "TERM_INPUT_COLUMNS": "inputColumns",
    "TERM_OUTPUT_COLUMN": "outputColumnTarget",
    "TERM_SPLIT_TRAIN": "splitTrain",
    "TERM_SPLIT_VAL": "splitVal",
    "TERM_SPLIT_TEST": "splitTest",
    "TERM_PROGRAM": "program",
    "TERM_MODULE": "module",
    "TERM_OPTIMIZER": "optimizer",
    "TERM_METRIC": "metric",
    "TERM_SCORE": "score",
    "TERM_FINAL_SCORE": "finalScore",
    "TERM_MODEL": "model",
    "TERM_PAIR_PLURAL": "pairPlural",
    "CANCELLATION_REASON": "cancellationReason",
}

_CONSTANT_KEYS: dict[str, str] = {
    "CLONE_NAME_PREFIX": "cloneNamePrefix",
    "RETRY_NAME_PREFIX": "retryNamePrefix",
    "GRID_SEARCH_LABEL": "gridSearchLabel",
    "GRID_SEARCH_LABEL_DEFINITE": "gridSearchLabelDefinite",
    "RUN_LABEL": "runLabel",
}


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    """Load and memoise the JSON i18n catalog from disk.

    Returns:
        Parsed catalog mapping. Cached for the process lifetime since the
        catalog is shipped with the wheel and never mutated at runtime.
    """
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _terms() -> dict[str, str]:
    """Return the ``terms`` section of the catalog (or an empty dict).

    Returns:
        Mapping of term key → Hebrew string, or ``{}`` when the section is
        missing or wrongly typed (caller falls back to the key itself).
    """
    terms = _catalog().get("terms", {})
    if not isinstance(terms, dict):
        return {}
    return terms


def _messages() -> dict[str, str]:
    """Return the ``messages`` section of the catalog (or an empty dict).

    Returns:
        Mapping of message key → Hebrew template, or ``{}`` when the section
        is missing or wrongly typed.
    """
    messages = _catalog().get("messages", {})
    if not isinstance(messages, dict):
        return {}
    return messages


def _backend_constants() -> dict[str, str]:
    """Return the ``backend.constants`` section of the catalog (or an empty dict).

    Returns:
        Mapping of constant key → Hebrew literal, or ``{}`` when missing.
    """
    backend = _catalog().get("backend", {})
    constants = backend.get("constants", {}) if isinstance(backend, dict) else {}
    if not isinstance(constants, dict):
        return {}
    return constants


def _sample_datasets() -> dict[str, dict[str, Any]]:
    """Return the ``backend.sampleDatasets`` section of the catalog.

    Returns:
        Mapping of dataset id → sample-dataset payload, or ``{}`` when missing
        or wrongly typed. Defensive ``.get()`` chain so a stripped or partially
        populated catalog cannot break import.
    """
    backend = _catalog().get("backend", {})
    if not isinstance(backend, dict):
        return {}
    samples = backend.get("sampleDatasets", {})
    if not isinstance(samples, dict):
        return {}
    return samples


def term(key: str) -> str:
    """Return a canonical shared term by key, or the key when missing.

    Args:
        key: Term identifier (e.g. ``"optimization"``).

    Returns:
        The Hebrew term string from the catalog, or ``key`` itself when the
        catalog has no entry.
    """
    value = _terms().get(key)
    return value if isinstance(value, str) else key


def _constant(key: str) -> str:
    """Resolve a backend-only string constant from the catalog.

    Args:
        key: Identifier under ``backend.constants`` in the catalog.

    Returns:
        The Hebrew constant, or ``key`` itself when no entry exists.
    """
    value = _backend_constants().get(key)
    return value if isinstance(value, str) else key


def __getattr__(name: str) -> Any:
    """Resolve TERM_* / SAMPLE_DATASETS / constant attributes on first access.

    Lazy module-level lookup (PEP 562) keeps imports cheap when callers only
    need ``t()`` — without this every ``import core.i18n`` would parse the
    25-KB catalog file at module-load time.

    Args:
        name: Attribute being accessed on the ``core.i18n`` module.

    Returns:
        The resolved Hebrew literal / dataset mapping.

    Raises:
        AttributeError: When ``name`` is not a recognised public symbol.
    """
    if name == "SAMPLE_DATASETS":
        return _sample_datasets()
    if name in _TERM_KEYS:
        return term(_TERM_KEYS[name])
    if name in _CONSTANT_KEYS:
        return _constant(_CONSTANT_KEYS[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def t(key: str, **params: Any) -> str:
    """Look up and format a Hebrew user-facing string by stable semantic key.

    Returns the key itself when missing, surfacing catalog drift as an obvious
    development artifact rather than a silent blank.

    Args:
        key: Catalog identifier for the message template.
        **params: Optional placeholder values substituted via ``str.format``.

    Returns:
        The localized, formatted string (or ``key`` when no template exists).
    """
    template = _messages().get(key, key)
    template = TERM_PATTERN.sub(lambda match: term(match.group(1)), template)
    if params:
        try:
            return template.format(**params)
        except (KeyError, IndexError, ValueError):
            return template
    return template


