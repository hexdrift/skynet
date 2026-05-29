"""Regression guard for backend Hebrew user-facing copy.

Backend Hebrew copy should live in ``core.i18n``. Tests may assert rendered
messages, but production modules should reference catalog keys or named
constants so terminology stays aligned with the frontend vocabulary.
"""

from __future__ import annotations

from pathlib import Path

HEBREW_CHARS = {chr(c) for c in range(0x0590, 0x05FF + 1)}

# Modules allowed to contain raw Hebrew. ``i18n.py`` is the catalog itself.
# ``generalist.py`` holds the agent's LLM system prompt (a ``dspy.Signature``
# docstring) whose few-shot examples are written in Hebrew so the model answers
# Hebrew users in kind — that is prompt content fed to the model, not
# user-facing copy rendered via the i18n catalog, so it is exempt from the
# centralization guard.
_EXEMPT_MODULES = {Path("i18n.py"), Path("service_gateway/agents/generalist.py")}


def test_backend_hebrew_copy_is_centralized_in_i18n_catalog() -> None:
    """No backend module outside the exempt set contains raw Hebrew characters."""
    core_root = Path(__file__).resolve().parents[2] / "core"
    offenders: list[str] = []

    for path in core_root.rglob("*.py"):
        relative = path.relative_to(core_root)
        if relative in _EXEMPT_MODULES or "tests" in relative.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if any(ch in HEBREW_CHARS for ch in text):
            offenders.append(str(relative))

    assert offenders == []
