import * as React from "react";

const URL_RE = /https?:\/\/[^\s<>"]+/g;
const URL_TRAILING_RE = /[.,;:!?)\]}'"]+$/;

/**
 * Linkify URLs inside a string, keeping trailing sentence punctuation
 * (`.`, `,`, `)`, `]`, …) outside the anchor href so links like
 * `https://example.com).` don't render with a broken trailing `).`
 * inside the underline.
 */
export function linkifyMessage(text: string, anchorClass: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  let lastIdx = 0;
  let key = 0;
  for (const m of text.matchAll(URL_RE)) {
    const matchIdx = m.index ?? 0;
    if (matchIdx > lastIdx) nodes.push(text.slice(lastIdx, matchIdx));
    const raw = m[0];
    const trailingMatch = URL_TRAILING_RE.exec(raw);
    const trailing = trailingMatch ? trailingMatch[0] : "";
    const url = trailing ? raw.slice(0, raw.length - trailing.length) : raw;
    nodes.push(
      <a key={key++} href={url} target="_blank" rel="noopener noreferrer" className={anchorClass}>
        {url}
      </a>,
    );
    if (trailing) nodes.push(trailing);
    lastIdx = matchIdx + raw.length;
  }
  if (lastIdx < text.length) nodes.push(text.slice(lastIdx));
  return nodes;
}
