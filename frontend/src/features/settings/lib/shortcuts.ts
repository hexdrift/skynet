import type { AgentShortcut } from "./prefs";

const isMac =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.platform);

const NON_RECORDABLE = new Set([
  "Control",
  "Shift",
  "Alt",
  "Meta",
  "OS",
  "CapsLock",
  "NumLock",
  "ScrollLock",
  "ContextMenu",
  "Tab",
]);

function prettifyKey(key: string): string {
  if (key.length === 1) return key.toUpperCase();
  if (key.startsWith("Arrow")) return key.slice(5);
  return key;
}

export function formatShortcut(s: AgentShortcut): string {
  const parts: string[] = [];
  if (s.ctrl) parts.push("Ctrl");
  if (s.alt) parts.push(isMac ? "⌥" : "Alt");
  if (s.shift) parts.push("Shift");
  if (s.meta) parts.push(isMac ? "⌘" : "Win");
  parts.push(prettifyKey(s.key));
  return parts.join(" + ");
}

export function matchShortcut(e: KeyboardEvent, s: AgentShortcut): boolean {
  if (e.ctrlKey !== s.ctrl) return false;
  if (e.altKey !== s.alt) return false;
  if (e.shiftKey !== s.shift) return false;
  if (e.metaKey !== s.meta) return false;
  return e.key.toLowerCase() === s.key.toLowerCase();
}

export function recordShortcut(e: KeyboardEvent): AgentShortcut | null {
  if (NON_RECORDABLE.has(e.key)) return null;
  if (!e.ctrlKey && !e.altKey && !e.metaKey) return null;
  return {
    key: e.key.length === 1 ? e.key.toLowerCase() : e.key,
    ctrl: e.ctrlKey,
    alt: e.altKey,
    shift: e.shiftKey,
    meta: e.metaKey,
  };
}
