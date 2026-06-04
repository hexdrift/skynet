"""Runtime bundle loader for the generalist agent.

The runtime call site reads ``load_bundle(model_id)``, then builds a
fresh ``ReActV2`` for every request via ``fresh_program_for_bundle``. The
``(path, mtime_ns)`` cache key picks up an atomic ConfigMap swap without
requiring a pod restart — see ``training_ground_SPEC.md`` §8.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from ..tool_overlay import (
    BundleIncompatibleError,
    ToolSchemaDriftError,
    _apply_bundle_tool_overrides,
    _assert_tool_set_matches,
    fresh_program_for_bundle,
    hash_tool_schema,
    snapshot_tool_schema_hashes,
)
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
    "_apply_bundle_tool_overrides",
    "_assert_tool_set_matches",
    "bundle_path_for",
    "fresh_program_for_bundle",
    "hash_tool_schema",
    "load_bundle",
    "reset_cache",
    "snapshot_tool_schema_hashes",
]


# Keep ``Any`` referenced for future type annotations on cache-clear callbacks.
_ = Any
