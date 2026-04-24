"""Backend facade over the shared Skynet i18n catalog.

The canonical catalog lives at ``i18n/locales/he.json`` in the repo root.
Backend modules keep using ``t(key, **params)`` and the short constants below,
but the Hebrew strings and domain terms are no longer mirrored in Python code.

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

CATALOG_PATH = Path(__file__).resolve().parents[2] / "i18n" / "locales" / "he.json"
TERM_PATTERN = re.compile(r"{term\.([A-Za-z0-9_]+)}")


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _terms() -> dict[str, str]:
    terms = _catalog().get("terms", {})
    if not isinstance(terms, dict):
        return {}
    return terms


def _messages() -> dict[str, str]:
    messages = _catalog().get("messages", {})
    if not isinstance(messages, dict):
        return {}
    return messages


def _backend_constants() -> dict[str, str]:
    backend = _catalog().get("backend", {})
    constants = backend.get("constants", {}) if isinstance(backend, dict) else {}
    if not isinstance(constants, dict):
        return {}
    return constants


def term(key: str) -> str:
    """Return a canonical shared term by key, or the key when missing."""
    value = _terms().get(key)
    return value if isinstance(value, str) else key


def _constant(key: str) -> str:
    value = _backend_constants().get(key)
    return value if isinstance(value, str) else key


def _resolve_terms(template: str) -> str:
    return TERM_PATTERN.sub(lambda match: term(match.group(1)), template)


# -- Canonical terms -------------------------------------------------------

TERM_OPTIMIZATION = term("optimization")
TERM_OPTIMIZATION_PLURAL = term("optimizationPlural")
TERM_DATASET = term("dataset")
TERM_EXAMPLE = term("example")
TERM_EXAMPLE_PLURAL = term("examplePlural")
TERM_ROW = term("row")
TERM_ROW_PLURAL = term("rowPlural")
TERM_COLUMN = term("column")
TERM_INPUT_COLUMNS = term("inputColumns")
TERM_OUTPUT_COLUMN = term("outputColumnTarget")
TERM_SPLIT_TRAIN = term("splitTrain")
TERM_SPLIT_VAL = term("splitVal")
TERM_SPLIT_TEST = term("splitTest")
TERM_PROGRAM = term("program")
TERM_MODULE = term("module")
TERM_OPTIMIZER = term("optimizer")
TERM_METRIC = term("metric")
TERM_SCORE = term("score")
TERM_FINAL_SCORE = term("finalScore")
TERM_MODEL = term("model")
TERM_PAIR_PLURAL = term("pairPlural")

# -- Constants (short noun phrases reused inline) --------------------------

CANCELLATION_REASON = term("cancellationReason")

CLONE_NAME_PREFIX = _constant("cloneNamePrefix")
RETRY_NAME_PREFIX = _constant("retryNamePrefix")

GRID_SEARCH_LABEL = _constant("gridSearchLabel")
GRID_SEARCH_LABEL_DEFINITE = _constant("gridSearchLabelDefinite")
RUN_LABEL = _constant("runLabel")

SAMPLE_DATASETS: dict[str, dict[str, Any]] = _catalog()["backend"]["sampleDatasets"]


def t(key: str, **params: Any) -> str:
    """Look up and format a Hebrew user-facing string by stable semantic key.

    Returns the key itself when missing, surfacing catalog drift as an obvious
    development artifact rather than a silent blank.
    """
    template = _messages().get(key, key)
    template = _resolve_terms(template)
    if params:
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template
    return template
