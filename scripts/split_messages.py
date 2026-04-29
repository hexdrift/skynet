"""One-shot splitter for ``frontend/src/shared/lib/messages.ts``.

Reads the monolithic ``MESSAGES`` object and writes one
``frontend/src/features/<name>/messages.ts`` per top-level feature group,
plus a thin ``shared/lib/messages.ts`` that re-aggregates every slice.

Run once during the PER-83 phase 4 migration; not part of the normal codegen
loop. Idempotent: re-running rewrites the same files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend" / "src" / "shared" / "lib" / "messages.ts"
FEATURES_DIR = ROOT / "frontend" / "src" / "features"
SHARED_OUT = ROOT / "frontend" / "src" / "shared" / "messages"

# Map every catalog key prefix to a destination slice. `auto.features.<f>.*`
# always maps to the `<f>` slice; everything else falls through these rules.
PREFIX_TO_SLICE = {
    "submit": "submit",
    "wizard": "submit",
    "dashboard": "dashboard",
    "sidebar": "sidebar",
    "explore": "explore",
    "compare": "compare",
    "tagger": "tagger",
    "tutorial": "tutorial",
    "settings": "settings",
    "auth": "auth",
    "optimization": "optimizations",
    "serve": "optimizations",
    "agent": "agent-panel",
    "agentpanel": "agent-panel",
    "approval": "agent-panel",
    "model": "shared",
    "shared": "shared",
    "clipboard": "shared",
    "not_found": "shared",
    "app": "shared",
}

# Top-level slice name → (output path, JS export identifier).
SLICE_TARGETS: dict[str, tuple[Path, str]] = {
    "submit": (FEATURES_DIR / "submit" / "messages.ts", "submitMessages"),
    "dashboard": (FEATURES_DIR / "dashboard" / "messages.ts", "dashboardMessages"),
    "sidebar": (FEATURES_DIR / "sidebar" / "messages.ts", "sidebarMessages"),
    "explore": (FEATURES_DIR / "explore" / "messages.ts", "exploreMessages"),
    "compare": (FEATURES_DIR / "compare" / "messages.ts", "compareMessages"),
    "tagger": (FEATURES_DIR / "tagger" / "messages.ts", "taggerMessages"),
    "tutorial": (FEATURES_DIR / "tutorial" / "messages.ts", "tutorialMessages"),
    "settings": (FEATURES_DIR / "settings" / "messages.ts", "settingsMessages"),
    "auth": (FEATURES_DIR / "auth" / "messages.ts", "authMessages"),
    "optimizations": (FEATURES_DIR / "optimizations" / "messages.ts", "optimizationsMessages"),
    "agent-panel": (FEATURES_DIR / "agent-panel" / "messages.ts", "agentPanelMessages"),
    "shared": (SHARED_OUT / "messages.ts", "sharedMessages"),
}


def _slice_for(key: str) -> str:
    """Pick the slice file for a catalog key.

    ``auto.features.<f>.*`` is routed to ``<f>``; ``auto.<top>.*`` and bare
    ``<top>.*`` fall through ``PREFIX_TO_SLICE`` and default to ``shared``.

    Args:
        key: A dotted catalog key.

    Returns:
        Slice name from :data:`SLICE_TARGETS`.
    """
    if key.startswith("auto.features."):
        feature = key.split(".", 3)[2]
        return PREFIX_TO_SLICE.get(feature, "shared")
    head = key.split(".", 1)[0]
    if head == "auto":
        nested = key.split(".", 2)[1]
        return PREFIX_TO_SLICE.get(nested, "shared")
    return PREFIX_TO_SLICE.get(head, "shared")


def _parse_entries(body: str) -> list[tuple[str, str]]:
    """Walk the MESSAGES object body and yield ``(key, raw_value)`` pairs.

    Handles single-line entries, multi-line template literals, and nested
    interpolations. Whitespace between entries is preserved into the raw
    value so the regenerated output stays formatting-stable.

    Args:
        body: Source text between ``MESSAGES = {`` and the matching ``}``.

    Returns:
        List of ``(key, raw_value)`` pairs in source order.
    """
    entries: list[tuple[str, str]] = []
    i = 0
    while i < len(body):
        while i < len(body) and body[i] in " \t\r\n,":
            i += 1
        if i >= len(body):
            break
        if body[i] != '"':
            raise ValueError(f"Unexpected char {body[i]!r} at offset {i}")
        end_quote = body.index('"', i + 1)
        key = body[i + 1 : end_quote]
        i = end_quote + 1
        while i < len(body) and body[i] in " \t":
            i += 1
        if body[i] != ":":
            raise ValueError(f"Expected ':' at offset {i}, got {body[i]!r}")
        i += 1
        while i < len(body) and body[i] in " \t":
            i += 1
        value_start = i
        depth = 0
        in_str: str | None = None
        in_tmpl = False
        while i < len(body):
            ch = body[i]
            if in_str is not None:
                if ch == "\\" and i + 1 < len(body):
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if in_tmpl:
                if ch == "\\" and i + 1 < len(body):
                    i += 2
                    continue
                if ch == "`":
                    in_tmpl = False
                    i += 1
                    continue
                if ch == "$" and i + 1 < len(body) and body[i + 1] == "{":
                    depth += 1
                    i += 2
                    continue
                if ch == "}" and depth > 0:
                    depth -= 1
                    i += 1
                    continue
                i += 1
                continue
            if ch in ('"', "'"):
                in_str = ch
                i += 1
                continue
            if ch == "`":
                in_tmpl = True
                i += 1
                continue
            if ch == "(":
                depth += 1
                i += 1
                continue
            if ch == ")":
                depth -= 1
                i += 1
                continue
            if ch == "," and depth == 0:
                break
            i += 1
        raw_value = body[value_start:i].rstrip()
        entries.append((key, raw_value))
    return entries


def _render_slice(name: str, ident: str, items: list[tuple[str, str]]) -> str:
    """Render a slice TS file.

    Args:
        name: Display name (used only for the docstring).
        ident: Exported const identifier.
        items: ``(key, raw_value)`` pairs to emit verbatim.

    Returns:
        Full TS source for the slice file.
    """
    body_lines = [f'  "{key}": {value},' for key, value in items]
    needs_terms = any("TERMS." in value for _, value in items)
    header = [
        "// Generated by scripts/split_messages.py. Do not edit by hand.",
        "//",
        f"// Hebrew UI strings owned by the {name} feature slice.",
        "",
    ]
    if needs_terms:
        header.append('import { TERMS } from "@/shared/lib/terms";')
        header.append("")
    return "\n".join(
        [
            *header,
            f"export const {ident} = {{",
            *body_lines,
            "} as const;",
            "",
        ]
    )


def _render_aggregator(slice_imports: list[tuple[str, str, Path]]) -> str:
    """Render the new ``shared/lib/messages.ts`` aggregator.

    Args:
        slice_imports: ``(slice_name, ident, output_path)`` for every
            non-empty slice that should be re-exported.

    Returns:
        Full TS source for the aggregator.
    """
    imports = [
        f'import {{ {ident} }} from "{_import_path(path)}";'
        for _, ident, path in slice_imports
    ]
    spreads = [f"  ...{ident}," for _, ident, _ in slice_imports]
    return "\n".join(
        [
            "/**",
            " * Aggregated Hebrew UI catalog for the application.",
            " *",
            " * Per-feature slices live in ``features/<name>/messages.ts``; this",
            " * file just re-exports the union and provides ``msg`` / ``formatMsg``",
            " * helpers. ESLint blocks new inline Hebrew literals outside the",
            " * slice files and ``i18n/locales/he.json`` (PER-83 phase 4).",
            " */",
            "",
            'import { formatTemplate } from "@/shared/lib/i18n";',
            *imports,
            "",
            "export const MESSAGES = {",
            *spreads,
            "} as const;",
            "",
            "export type MessageKey = keyof typeof MESSAGES;",
            "",
            "/**",
            " * Look up a user-facing string by key. Silently returns the key",
            " * itself if not found so missing messages surface as a dev-visible",
            ' * "key not translated" artifact instead of a silent blank.',
            " */",
            "export function msg(key: MessageKey): string {",
            "  return MESSAGES[key] ?? key;",
            "}",
            "",
            "export function formatMsg(",
            "  key: MessageKey,",
            "  params: Record<string, string | number>,",
            "): string {",
            "  return formatTemplate(msg(key), params);",
            "}",
            "",
        ]
    )


def _import_path(path: Path) -> str:
    """Convert an output path to its ``@/...`` import alias.

    Args:
        path: Absolute filesystem path under ``frontend/src``.

    Returns:
        TS import alias without the ``.ts`` suffix.
    """
    rel = path.relative_to(ROOT / "frontend" / "src")
    no_ext = rel.with_suffix("")
    return f"@/{no_ext.as_posix()}"


def main() -> int:
    """Run the split.

    Returns:
        Process exit status: ``0`` on success, ``1`` when the source file
        has unexpected structure.
    """
    text = SRC.read_text(encoding="utf-8")
    match = re.search(r"export const MESSAGES = \{\n", text)
    if not match:
        print("MESSAGES literal not found", file=sys.stderr)
        return 1
    body_start = match.end()
    end_marker = "\n} as const;\n"
    end_idx = text.index(end_marker, body_start)
    body = text[body_start:end_idx]
    entries = _parse_entries(body)

    grouped: dict[str, list[tuple[str, str]]] = {name: [] for name in SLICE_TARGETS}
    for key, value in entries:
        grouped[_slice_for(key)].append((key, value))

    slice_imports: list[tuple[str, str, Path]] = []
    for slice_name, items in grouped.items():
        path, ident = SLICE_TARGETS[slice_name]
        if not items:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_render_slice(slice_name, ident, items), encoding="utf-8")
        slice_imports.append((slice_name, ident, path))

    SRC.write_text(_render_aggregator(slice_imports), encoding="utf-8")
    print(f"Wrote {len(slice_imports)} slices, {sum(len(v) for v in grouped.values())} entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
