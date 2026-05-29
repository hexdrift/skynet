"""Runtime bundle loader for the generalist agent.

The runtime call site reads ``load_bundle(model_id)``, then builds a
fresh ``ReActV2`` for every request via ``fresh_program_for_bundle``. The
``(path, mtime_ns)`` cache key picks up an atomic ConfigMap swap without
requiring a pod restart — see ``training_ground_SPEC.md`` §8.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import dspy

from .types import Bundle

logger = logging.getLogger(__name__)


BUNDLES_ROOT_ENV_VAR = "SKYNET_BUNDLES_ROOT"
DEFAULT_BUNDLES_ROOT = Path(
    "/etc/skynet/bundles"
).expanduser()
"""Production mount point. Local dev override the env var to point at
``backend/core/service_gateway/optimization/training_ground/bundles/``."""

CURRENT_BUNDLE_FILENAME = "current.json"


class BundleNotFoundError(FileNotFoundError):
    """No bundle is mounted for the requested ``model_id``."""


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


def _bundles_root() -> Path:
    """Resolve the bundle mount root, honoring the env override."""
    raw = os.environ.get(BUNDLES_ROOT_ENV_VAR)
    if raw:
        return Path(raw).expanduser()
    return DEFAULT_BUNDLES_ROOT


def bundle_path_for(model_id: str) -> Path:
    """Return the on-disk path that holds the active bundle for ``model_id``."""
    return _bundles_root() / model_id / CURRENT_BUNDLE_FILENAME


@functools.lru_cache(maxsize=8)
def _load_bundle_immutable(path_str: str, mtime_ns: int) -> Bundle:
    """Read, validate, and cache one bundle keyed on ``(path, mtime_ns)``.

    The ``mtime_ns`` arg is the cache key — when k8s atomically rotates
    the ConfigMap symlink the next ``load_bundle`` sees a new mtime and
    bypasses the cache transparently.
    """
    path = Path(path_str)
    payload = json.loads(path.read_text())
    bundle = Bundle.model_validate(payload)
    _assert_bundle_compatible(bundle)
    # Keep ``mtime_ns`` in scope so the cache argument is not lint-removed.
    _ = mtime_ns
    return bundle


def load_bundle(model_id: str) -> Bundle:
    """Return the active bundle for ``model_id``.

    Raises:
        BundleNotFoundError: when no bundle file exists for ``model_id``.
        BundleIncompatibleError: when the bundle's DSPy/GEPA versions or
            bundle_format_version are not supported by the runtime.
    """
    path = bundle_path_for(model_id)
    if not path.exists():
        raise BundleNotFoundError(f"No bundle mounted at {path}")
    return _load_bundle_immutable(str(path), path.stat().st_mtime_ns)


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
    expected_hashes: dict[str, str], live_tools: list[dspy.Tool]
) -> None:
    """Compare the bundle's hashes with the live tool roster — raise on drift.

    Only tools present in **both** sets are compared. Bundle-only tools
    are treated as phased out by ``tools_for(state)`` for this turn (a
    legitimate runtime condition). Live-only tools are treated as
    additions made after training (the bundle simply didn't see them).
    A schema-hash mismatch on a tool present in both is hard-fail.
    """
    live_by_name = {tool.name: tool for tool in live_tools}
    drifted: list[str] = []
    for name, expected in expected_hashes.items():
        live_tool = live_by_name.get(name)
        if live_tool is None:
            continue
        actual = hash_tool_schema(live_tool)
        if actual != expected:
            drifted.append(name)
    if drifted:
        raise ToolSchemaDriftError(
            f"Bundle schema hash mismatch for tools {drifted!r} — re-record before reload"
        )


def _assert_bundle_compatible(bundle: Bundle) -> None:
    """Validate the bundle against the runtime's installed package versions."""
    if bundle.bundle_format_version != 1:
        raise BundleIncompatibleError(
            f"Unsupported bundle_format_version {bundle.bundle_format_version}; "
            "this runtime understands 1"
        )
    runtime_dspy = _installed_version("dspy")
    runtime_gepa = _installed_version("gepa")
    if runtime_dspy and runtime_dspy != bundle.dspy_version:
        raise BundleIncompatibleError(
            f"Bundle dspy_version={bundle.dspy_version!r} but runtime has {runtime_dspy!r}; "
            "tighten the pin before deploying"
        )
    if runtime_gepa and runtime_gepa != bundle.gepa_version:
        raise BundleIncompatibleError(
            f"Bundle gepa_version={bundle.gepa_version!r} but runtime has {runtime_gepa!r}; "
            "tighten the pin before deploying"
        )


def _installed_version(distribution_name: str) -> str | None:
    """Return the installed version of ``distribution_name`` or ``None``."""
    try:
        return version(distribution_name)
    except PackageNotFoundError:
        return None


def reset_cache() -> None:
    """Drop the bundle cache. Useful for tests and manual cache busting."""
    _load_bundle_immutable.cache_clear()


__all__ = [
    "BundleIncompatibleError",
    "BundleNotFoundError",
    "ToolSchemaDriftError",
    "bundle_path_for",
    "fresh_program_for_bundle",
    "hash_tool_schema",
    "load_bundle",
    "reset_cache",
    "snapshot_tool_schema_hashes",
]


# Keep ``Any`` referenced for future type annotations on cache-clear callbacks.
_ = Any
