"""Tool-schema overlay, drift detection, and fresh-program assembly.

Shared by both the training-ground runtime (``registry.py``, which
re-exports every symbol here for back-compat) and the ``/serve`` path in
``core/api``. Pulling these helpers out of ``training_ground/registry.py``
lets the API re-source a persisted ReAct program without importing the
training-ground package — the serve path only needs the overlay + drift
machinery, not the bundle loader.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

import dspy

if TYPE_CHECKING:
    from .training_ground.types import Bundle

logger = logging.getLogger(__name__)


class BundleIncompatibleError(RuntimeError):
    """A bundle was found but the runtime cannot safely load it.

    The most common cause is a DSPy / GEPA version skew between the
    optimizer pod that produced the bundle and the runtime pod that's
    trying to load it.
    """


class ToolSchemaDriftError(RuntimeError):
    """The live MCP schema for a tool no longer matches the bundle's hash.

    Mounting a stale bundle against a refactored MCP surface is a
    correctness bug, not a runtime degradation — fail hard so the rollout
    falls back to the seed program instead of silently mis-prompting the
    model.
    """


def fresh_program_for_bundle(
    bundle: Bundle,
    mcp_tools: list[dspy.Tool],
    *,
    seed_signature: type[dspy.Signature],
) -> dspy.ReActV2:
    """Build a fresh ``ReActV2`` whose tool roster matches the bundle.

    Drift detection compares only the intersection of the bundle's
    recorded tools and the live phased roster. A live MCP turn may
    legitimately expose fewer tools than the bundle saw at training
    (``tools_for(state)`` phases by wizard state) — that's expected, not
    drift. A schema-hash mismatch on a tool present in both sides is
    drift and raises ``ToolSchemaDriftError``.

    The caller's ``mcp_tools`` list is **not** mutated: the overlays
    are applied to deep clones, so the same list can be reused across
    requests without self-triggering drift on the next
    ``_assert_tool_set_matches`` call.

    Args:
        bundle: The mounted bundle (as returned by :func:`load_bundle`).
        mcp_tools: The live MCP tool list for this request — the tools
            available to ``tools_for(state)`` post-phasing.
        seed_signature: The ``dspy.Signature`` subclass for the agent —
            passed through so the runtime owns the canonical class instead
            of re-importing it here.

    Returns:
        A configured ``ReActV2`` ready to be ``dspy.streamify``-wrapped.

    Raises:
        ToolSchemaDriftError: when a tool present in both the bundle and
            the live roster has a different schema hash.
    """
    _assert_tool_set_matches(bundle.tool_schema_hashes, mcp_tools)
    isolated_tools = [tool.model_copy(deep=True) for tool in mcp_tools]
    _apply_bundle_tool_overrides(
        isolated_tools,
        tool_descriptions=bundle.tool_descriptions,
        tool_arg_descriptions=bundle.tool_arg_descriptions,
    )
    _apply_tool_name_overrides(isolated_tools, bundle.tool_names)
    program = dspy.ReActV2(
        seed_signature, tools=isolated_tools, max_iters=bundle.max_iters
    )
    program.load_state(bundle.program_state)
    return program


def _apply_bundle_tool_overrides(
    mcp_tools: list[dspy.Tool],
    *,
    tool_descriptions: dict[str, str],
    tool_arg_descriptions: dict[str, dict[str, str]],
) -> None:
    """Re-apply GEPA-mutated tool wording on top of live MCP tools, in place.

    ``program.save(save_program=False)`` discards the program's tools
    dict, so the optimized ``desc`` and per-arg ``description`` overlays
    are persisted on the bundle separately and re-applied here before
    ReActV2 is constructed. Missing tool / arg names are silently
    skipped — they map to live-only tools that the bundle didn't see at
    training time.
    """
    if not tool_descriptions and not tool_arg_descriptions:
        return
    live_by_name = {tool.name: tool for tool in mcp_tools}
    for tool_name, desc in tool_descriptions.items():
        tool = live_by_name.get(tool_name)
        if tool is None or not desc:
            continue
        tool.desc = desc
    for tool_name, arg_map in tool_arg_descriptions.items():
        tool = live_by_name.get(tool_name)
        if tool is None or not isinstance(tool.args, dict):
            continue
        for arg_name, description in arg_map.items():
            schema = tool.args.get(arg_name)
            if isinstance(schema, dict) and description:
                schema["description"] = description


def _apply_tool_name_overrides(
    mcp_tools: list[dspy.Tool],
    tool_names: dict[str, str] | None,
) -> None:
    """Rename re-sourced canonical tools to their GEPA-proposed display names, in place.

    Mirrors the rollout-time rename so the served agent sees the same roster GEPA
    optimized. Must run AFTER drift-check + desc/arg overlays (those key on the
    canonical names that the recorded schema hashes use), and BEFORE ``ReActV2``
    is built (it re-keys its tool map by ``tool.name``). Collisions — two
    canonicals proposing the same display name — keep the canonical name on the
    colliding tools and log, matching :func:`replay.resolve_proposed_names`. A
    ``None`` / empty map is a no-op, preserving pre-rename behavior exactly.
    """
    if not tool_names:
        return
    live_names = {tool.name for tool in mcp_tools}
    desired: dict[str, str] = {}
    for tool in mcp_tools:
        proposed = tool_names.get(tool.name)
        desired[tool.name] = proposed if isinstance(proposed, str) and proposed else tool.name
    claimants: dict[str, list[str]] = {}
    for canonical, name in desired.items():
        claimants.setdefault(name, []).append(canonical)
    for tool in mcp_tools:
        canonical = tool.name
        name = desired[canonical]
        if name == canonical:
            continue
        owners = claimants[name]
        if len(owners) > 1 or name in live_names:
            logger.warning(
                "Proposed tool name %r collides on serve; keeping canonical %r.",
                name,
                canonical,
            )
            continue
        tool.name = name


def hash_tool_schema(tool: dspy.Tool) -> str:
    """Hash a tool's schema (name + desc + args) for drift detection.

    Encoded with strict canonical JSON — ``allow_nan=False`` rejects
    NaN/Inf, ``separators=(",", ":")`` strips whitespace, and no
    ``default=`` coercion is allowed so a non-JSON value in ``tool.args``
    fails fast rather than silently hashing as a Python ``repr``. The hash
    intentionally covers ``desc`` so a prompt-only edit on the MCP side
    invalidates the bundle — the optimized instructions may rely on the
    old wording.

    Raises:
        TypeError: when ``tool.args`` contains a non-JSON value, so the
            caller can re-record before the bundle drifts silently.
    """
    payload = {
        "name": tool.name,
        "desc": tool.desc or "",
        "args": tool.args or {},
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def snapshot_tool_schema_hashes(tools: list[dspy.Tool]) -> dict[str, str]:
    """Build the ``{tool_name: sha256_hex}`` map persisted with each turn."""
    return {tool.name: hash_tool_schema(tool) for tool in tools}


def _assert_tool_set_matches(
    expected_hashes: dict[str, str],
    live_tools: list[dspy.Tool],
    *,
    strict: bool = False,
) -> None:
    """Compare the recorded hashes with the live tool roster — raise on drift.

    By default the comparison is intersection-only: a schema-hash mismatch on
    a tool present in **both** sets is drift and hard-fails, while
    recorded-only tools (phased out by ``tools_for(state)`` for this turn) and
    live-only tools (added after training) are tolerated as legitimate runtime
    conditions. The generalist run/bundle path (:func:`fresh_program_for_bundle`)
    requires this leniency, since per-turn wizard-state phasing routinely
    exposes a subset of the trained roster.

    ``strict`` additionally requires exact set equality: a recorded tool absent
    from the live roster (removed from the surface) or a live tool the snapshot
    never recorded (added to the surface) is also drift. The served react
    surfaces — serve-info materialisation and the live chat driver — use strict
    mode so a run only serves against the exact tool surface it was optimised
    against; anything else fails hard rather than silently mis-prompting.

    Args:
        expected_hashes: ``{tool_name: schema_hash}`` recorded at training time.
        live_tools: The roster resolved from the live MCP surface for this call.
        strict: When ``True``, also fail on tools missing from or added to the
            live roster, not just hash mismatches on the intersection.

    Raises:
        ToolSchemaDriftError: On an intersection hash mismatch (always); and,
            under ``strict``, on any recorded-but-missing or live-but-unrecorded
            tool.
    """
    live_by_name = {tool.name: tool for tool in live_tools}
    drifted = sorted(
        name
        for name, expected in expected_hashes.items()
        if name in live_by_name and hash_tool_schema(live_by_name[name]) != expected
    )
    problems: list[str] = []
    if drifted:
        problems.append(f"schema-hash mismatch on {drifted!r}")
    if strict:
        missing = sorted(set(expected_hashes) - set(live_by_name))
        added = sorted(set(live_by_name) - set(expected_hashes))
        if missing:
            problems.append(f"recorded tools absent from the live surface {missing!r}")
        if added:
            problems.append(f"unrecorded tools on the live surface {added!r}")
    if problems:
        raise ToolSchemaDriftError(
            "Tool surface drifted from the optimized snapshot — "
            + "; ".join(problems)
            + " — re-record before reload"
        )


__all__ = [
    "BundleIncompatibleError",
    "ToolSchemaDriftError",
    "fresh_program_for_bundle",
    "hash_tool_schema",
    "snapshot_tool_schema_hashes",
]

# ``_apply_tool_name_overrides`` is shared with the /serve helper but kept
# underscore-prefixed (internal overlay machinery, like
# ``_apply_bundle_tool_overrides``) and intentionally absent from ``__all__``.
