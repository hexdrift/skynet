"""Regression guard for backend Hebrew user-facing copy.

Backend Hebrew copy should live in ``core.i18n``. Tests may assert rendered
messages, but production modules should reference catalog keys or named
constants so terminology stays aligned with the frontend vocabulary.
"""

from __future__ import annotations

from pathlib import Path

HEBREW_CHARS = {chr(c) for c in range(0x0590, 0x05FF + 1)}


def test_backend_hebrew_copy_is_centralized_in_i18n_catalog() -> None:
    """No backend module outside ``core/i18n.py`` contains raw Hebrew characters."""
    core_root = Path(__file__).resolve().parents[2] / "core"
    offenders: list[str] = []

    for path in core_root.rglob("*.py"):
        relative = path.relative_to(core_root)
        if relative == Path("i18n.py") or "tests" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(ch in HEBREW_CHARS for ch in text):
            offenders.append(str(relative))

    assert offenders == []
