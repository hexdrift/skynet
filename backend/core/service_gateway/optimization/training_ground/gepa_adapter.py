"""Pure parsers between a ReActV2 program and the GEPA candidate blob.

GEPA mutates a single composite ``tool_module:react`` text blob carrying the
inner predictor's instructions plus per-tool descriptions/names/arg-docs. These
helpers seed that blob from a program and read the proposer's edits back out so
the live react engine (``run_react``) can apply them through the stock
``gepa.adapters.dspy_adapter.DspyAdapter.build_program``. The functions are
side-effect-free and depend only on ``dspy`` + the candidate dict shape.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dspy
from gepa.adapters.dspy_adapter.dspy_adapter import TOOL_MODULE_PREFIX

logger = logging.getLogger(__name__)

TERMINAL_TOOL_NAMES = frozenset({"submit", "finish"})
"""The synthetic loop-exit tool the program appends to every roster — ``submit``
on ReActV2, ``finish`` on classic ReAct. Excluded from the optimizable tool
surface because it carries no user-tunable description."""


TOOL_MODULE_KEY = f"{TOOL_MODULE_PREFIX}:react"
"""Neutral composite key holding every mutable text for the candidate program.

Domain-agnostic replacement for the legacy ``:generalist`` key. Candidate
parsing accepts either key (see :data:`_LEGACY_MODULE_KEY`) so candidates
seeded before the rename still load."""

_LEGACY_MODULE_KEY = f"{TOOL_MODULE_PREFIX}:generalist"
"""Pre-rename composite key — still parsed for back-compat with old candidates."""

REACT_PREDICTOR_NAME = "react"
"""Inner-predictor name on ReActV2 — used by the seed candidate and reflective
dataset routing."""


def seed_candidate_from_program(program: dspy.Module) -> dict[str, str]:
    """Build the GEPA seed candidate from a ReActV2 program.

    GEPA mutates one composite ``tool_module:react`` blob so the
    instruction proposer optimizes the inner predictor's instructions and
    the tool descriptions jointly. Mirrors ``DspyAdapter.build_program``
    expectations (see ``gepa/adapters/dspy_adapter/dspy_adapter.py:180``).

    Args:
        program: The seed ReActV2 instance with its baseline signature
            and tool descriptions wired in.

    Returns:
        ``{"tool_module:react": "<json blob>"}`` where the blob is
        ``{"react": <instructions>, "tools": {<canonical>: {"name": ...,
        "desc": ..., "args": ...}}}``. The blob is keyed by canonical name and
        seeds ``name`` equal to the canonical name so GEPA can mutate a clearer
        display name the agent sees while matching stays canonical.
    """
    instructions = _extract_react_instructions(program)
    tools_payload: dict[str, dict[str, Any]] = {}
    for name, tool in _collect_tools(program).items():
        if name in TERMINAL_TOOL_NAMES:
            continue
        tools_payload[name] = {
            "name": name,
            "desc": tool.desc or "",
            "args": _serialize_tool_args(tool.args),
        }
    config = {REACT_PREDICTOR_NAME: instructions, "tools": tools_payload}
    return {TOOL_MODULE_KEY: json.dumps(config, ensure_ascii=False, sort_keys=True)}


def _candidate_blob_key(candidate: dict[str, str]) -> str:
    """Return the composite-blob key present on ``candidate``.

    Prefers the neutral ``tool_module:react`` key but falls back to the legacy
    ``tool_module:generalist`` key so candidates seeded before the rename still
    parse. Defaults to the neutral key when neither is present (an empty blob).
    """
    if TOOL_MODULE_KEY in candidate:
        return TOOL_MODULE_KEY
    if _LEGACY_MODULE_KEY in candidate:
        return _LEGACY_MODULE_KEY
    return TOOL_MODULE_KEY


def _parse_candidate_blob(candidate: dict[str, str]) -> dict[str, Any]:
    """Parse the composite ``tool_module:*`` JSON blob, swallowing errors.

    The reflective proposer can occasionally return a malformed blob — when
    that happens we want the candidate to fall back to the seed's text
    silently and have the rollout failure-score, not raise out of
    ``evaluate`` before the per-example try block catches it.
    """
    key = _candidate_blob_key(candidate)
    raw = candidate.get(key)
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "Candidate %s blob is not valid JSON — falling back to seed overrides",
            key,
        )
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _candidate_tool_descriptions(candidate: dict[str, str]) -> dict[str, str]:
    """Pull tool descriptions (no arg-level edits) out of the candidate."""
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    descriptions: dict[str, str] = {}
    if not isinstance(tools, dict):
        return descriptions
    for name, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        desc = payload.get("desc")
        if isinstance(desc, str) and desc:
            descriptions[name] = desc
    return descriptions


def _candidate_tool_names(candidate: dict[str, str]) -> dict[str, str]:
    """Extract the GEPA-proposed display name per canonical tool.

    Each ``tools[<canonical>]`` payload may carry a ``name`` GEPA mutated to a
    clearer label the agent sees. Entries whose proposed name is missing/blank
    fall back to the canonical key, so the result is always identity when no
    rename was proposed (the seed sets ``name == canonical``).

    Returns:
        ``{canonical_name: proposed_name}`` — never empty unless the blob has no
        tools; identity for any tool whose proposed name is absent or blank.
    """
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    names: dict[str, str] = {}
    if not isinstance(tools, dict):
        return names
    for canonical, payload in tools.items():
        if not isinstance(payload, dict):
            names[canonical] = canonical
            continue
        proposed = payload.get("name")
        if isinstance(proposed, str) and proposed.strip():
            names[canonical] = proposed.strip()
        else:
            names[canonical] = canonical
    return names


def _candidate_tool_arg_descriptions(
    candidate: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Extract arg-level description overrides keyed by tool then arg."""
    parsed = _parse_candidate_blob(candidate)
    tools = parsed.get("tools") or {}
    out: dict[str, dict[str, str]] = {}
    if not isinstance(tools, dict):
        return out
    for name, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            continue
        arg_descs: dict[str, str] = {}
        for arg_name, arg_schema in args.items():
            if not isinstance(arg_schema, dict):
                continue
            desc = arg_schema.get("description")
            if isinstance(desc, str) and desc:
                arg_descs[arg_name] = desc
        if arg_descs:
            out[name] = arg_descs
    return out


def _extract_react_instructions(program: dspy.Module) -> str:
    """Return the inner ``react`` predictor's instruction text."""
    for name, predictor in program.named_predictors():
        if name == REACT_PREDICTOR_NAME:
            return getattr(predictor.signature, "instructions", "") or ""
    return getattr(program.signature, "instructions", "") or ""  # type: ignore[attr-defined]


def _collect_tools(program: dspy.Module) -> dict[str, dspy.Tool]:
    """Return the program's ``Tool`` map (excluding the synthetic submit)."""
    candidate = getattr(program, "tools", None)
    if not isinstance(candidate, dict):
        return {}
    return {
        name: tool
        for name, tool in candidate.items()
        if isinstance(tool, dspy.Tool)
    }


def _serialize_tool_args(args: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Round-trip the tool arg schema through JSON-safe primitives."""
    if not isinstance(args, dict):
        return {}
    payload: dict[str, dict[str, Any]] = {}
    for arg_name, schema in args.items():
        if isinstance(schema, dict):
            payload[arg_name] = dict(schema)
        else:
            payload[arg_name] = {"description": str(schema)}
    return payload


__all__ = [
    "REACT_PREDICTOR_NAME",
    "TOOL_MODULE_KEY",
    "seed_candidate_from_program",
]

# The ``_candidate_*`` parsers are imported by run_react (the bundle + overlay
# persist paths); they are underscore-prefixed and intentionally absent from
# ``__all__``.
