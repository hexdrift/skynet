"""Inline SVG SKYNET wordmark for notification emails.

Ported verbatim from the frontend ``shared/ui/animated-wordmark.tsx`` so the
email logo is pixel-identical to the app's. Each letter carries the same four
variants (default / glyph / serif / sans); a CSS ``:hover`` cross-fade cycles
them to echo the app's morph in clients that honour ``<style>`` + ``:hover``
(the browser preview, Apple Mail, Outlook web). Outlook desktop strips both SVG
and animation, so the header falls back to plain ``SKYNET`` text via an MSO
conditional comment in :mod:`core.notifications.notifier`.
"""

from __future__ import annotations

TOTAL_WIDTH = 475

# (offset, default-path, glyph-rects[(x,y,w,h)], serif-path, sans-path) per letter.
LETTERS: list[dict] = [
    {
        "offset": 0,
        "default": "M34.9,92C54,92,69.5,80.5,69.5,61.1C69.5,43,56,30.3,34.9,30.3v13.4c-9.7,0-16.9-4.3-16.9-13.1 c0-8.8,6.2-14,17.4-14c9.2,0,14.7,3.8,16.1,8.8h17C67.2,11.4,54,0,35,0C14.9,0,0.6,12.6,0.6,31c0,18.4,14.9,29.5,34.3,29.5V47.8 c10.3,0,17.4,4.6,17.4,13.7c0,9-7.2,14.1-17.3,14.1c-9.1,0-15.4-4-17.3-9.5H0C2.5,80.6,15.8,92,34.9,92z",
        "glyph": [(37.8, 36.6, 22.6, 22.6), (10.4, 9.1, 22.6, 22.6), (10.4, 64, 22.6, 22.6)],
        "serif": "M34,91.9c-15.2,0-27.8-7.7-31.1-21l11.8-3.7c2.4,12.6,10.8,21,20.8,21c9.4,0,15.7-6.5,15.7-15.8 C51.3,45.8,5.7,55.6,5.7,24.3C5.7,9.8,16.7,0,33.7,0c13.4,0,25.7,7,29.5,19.4l-11.9,3.7C48.7,11.3,40.7,3.7,32,3.7 c-8.8,0-14.8,5.8-14.8,14.4c0,24,46.5,15.8,46.5,47.8C63.7,81.8,52.1,91.9,34,91.9z",
        "sans": "M35.3,92c-10.4,0-18.8-2.4-25-7.3C4.1,79.9,0.9,73.3,0.9,65H13c0,5.7,2.1,10,6.2,13c4.1,2.9,9.5,4.4,16.2,4.4 c3,0,5.9-0.3,8.5-0.9c2.6-0.6,4.9-1.6,7-2.8c2.1-1.3,3.7-3,4.9-5.2c1.2-2.2,1.8-4.8,1.8-7.6c0-1.5-0.2-2.8-0.5-4 c-0.4-1.2-0.8-2.2-1.4-3.1c-0.5-0.9-1.4-1.7-2.5-2.5c-1.2-0.8-2.2-1.5-3.3-1.9c-1-0.5-2.5-1.1-4.6-1.7c-2-0.6-3.7-1.1-5.3-1.5 c-1.5-0.4-3.7-0.9-6.5-1.6c-2.2-0.5-4-0.9-5.3-1.3c-1.3-0.3-3-0.8-5-1.4s-3.6-1.1-4.9-1.6c-1.2-0.5-2.7-1.2-4.4-1.9 c-1.6-0.8-3-1.6-4-2.4c-1-0.8-2.1-1.8-3.1-2.9c-1.1-1.2-2-2.4-2.5-3.7c-0.6-1.2-1.1-2.7-1.5-4.3c-0.4-1.7-0.6-3.4-0.6-5.2 c0-7.4,3-13.5,9-18.2c5.9-4.6,13.7-7,23-7c9.8,0,17.8,2.4,24,7.3s9.3,11.3,9.3,19H56c0-5-2-9-6-12.1c-4-3.1-9.2-4.7-15.6-4.7 c-6,0-11,1.4-14.9,4s-5.9,6.4-5.9,11.4c0,1.4,0.2,2.6,0.5,3.7c0.4,1.1,0.8,2.1,1.4,2.9c0.6,0.8,1.4,1.7,2.6,2.4 c1.2,0.7,2.4,1.4,3.4,1.9c1.1,0.5,2.7,1.1,4.7,1.7c2.1,0.6,3.9,1.1,5.5,1.6c1.7,0.4,3.9,0.9,6.8,1.7c2.2,0.5,3.9,0.9,5.1,1.3 c1.2,0.3,2.9,0.7,4.9,1.3c2,0.6,3.6,1.1,4.8,1.6c1.2,0.5,2.5,1.1,4.2,1.9c1.6,0.8,2.9,1.5,3.8,2.4c0.9,0.8,2,1.8,3,2.9 c1.1,1.1,1.9,2.4,2.5,3.7c0.6,1.3,1,2.8,1.4,4.4c0.4,1.7,0.6,3.5,0.6,5.4c0,7.6-3,13.9-8.9,18.9C54.1,89.5,45.9,92,35.3,92z",
    },
    {
        "offset": 75,
        "default": "M 0 2.1 h 22 v 87.9 h -22 Z M 20 52 L 55 2.1 h 22 L 20 62 Z M 36 45 L 65 90 h -25 L 20 50 Z",
        "glyph": [(0, 35, 22.6, 22.6), (45, 2.1, 22.6, 22.6), (45, 68, 22.6, 22.6)],
        "serif": "M 8 2.1 h 18 v 3.8 h -5 v 78.3 h 5 v 3.8 h -18 v -3.8 h 5 v -78.3 h -5 Z M 18 52 L 65 2.1 h 18 v 3.8 L 22 55 Z M 35 40 L 72 86.2 h 10 v 3.8 h -25 L 18 50 Z",
        "sans": "M 2 2.1 h 11 v 87.9 h -11 Z M 6 46 L 52 2.1 h 14 L 6 54 Z M 28 35 L 66 90 h -14 L 16 45 Z",
    },
    {
        "offset": 155,
        "default": "M36.8,90 h18.4 V52.9 L83,2.2 h-21.2 l-25,46.9 V90 z M20.7,40.6 h20.7 L20.7,2.2 h-20.7 L20.7,40.6 z",
        "glyph": [(30.7, 35.4, 22.2, 22.2), (3.7, 8.5, 22.2, 22.2), (57.7, 62.5, 22.2, 22.2)],
        "serif": "M26.8,90 v-1.8 c6.9,-0.7 10.2,-2.4 10.2,-9.5 V49.4 l-19.6,-34.1 c-4.4,-7.9 -7.2,-10.4 -12.2,-11.2 V2.2 h31.7 V4 c-8.1,0.7 -8.9,3.1 -4.4,11.1 l16.5,29 l16.4,-29 c4.4,-8 3,-10.5 -6.2,-11.1 V2.2 h23.3 V4 c-5.8,0.8 -8.7,3.3 -13.1,11.1 l-19.4,34.1 v29.3 c0,7.1 3.4,8.8 10.3,9.5 v1.8 L26.8,90 Z",
        "sans": "M82.9,2.2 l-32.9,59.5 V90 h-11.5 V61.7 L5.8,2.2 h12.7 L44.3,50 l25.9,-47.8 H82.9 z",
    },
    {
        "offset": 245,
        "default": "M 0 2.1 h 22 v 87.9 h -22 Z M 52 2.1 h 22 v 87.9 h -22 Z M 0 2.1 l 74 87.9 h -22 l -52 -87.9 Z",
        "glyph": [(0, 68, 22.6, 22.6), (25, 35, 22.6, 22.6), (50, 2.1, 22.6, 22.6)],
        "serif": "M 8 2.1 h 18 v 3.8 h -5 v 78.3 h 5 v 3.8 h -18 v -3.8 h 5 v -78.3 h -5 Z M 56 2.1 h 18 v 3.8 h -5 v 78.3 h 5 v 3.8 h -18 v -3.8 h 5 v -78.3 h -5 Z M 16 2.1 l 45 87.9 h 13 l -45 -87.9 Z",
        "sans": "M 2 2.1 h 11 v 87.9 h -11 Z M 52 2.1 h 11 v 87.9 h -11 Z M 2 2.1 l 61 87.9 h -11 l -50 -87.9 Z",
    },
    {
        "offset": 325,
        "default": "M 0 2.1 h 62 v 20 h -40 v 14 h 32 v 18 h -32 v 16 h 42 v 20 h -64 Z",
        "glyph": [(2, 2.1, 22.6, 22.6), (24, 35, 22.6, 22.6), (2, 68, 22.6, 22.6)],
        "serif": "M 10 2.1 h 52 v 22 h -3.8 c -1,-8 -4,-12 -12,-12 h -20 v 32 h 16 c 4,0 6,-2 8,-8 h 3.8 v 24 h -3.8 c -2,-6 -4,-8 -8,-8 h -16 v 34 h 22 c 8,0 12,-4 14,-14 h 3.8 v 20 h -60 v -3.8 h 6 v -78.3 h -6 Z",
        "sans": "M 2 2.1 h 50 v 10.2 h -39 v 28 h 32 v 10.2 h -32 v 29.3 h 41 v 10.2 h -52 Z",
    },
    {
        "offset": 395,
        "default": "M27.6,90 L46.9,90 L46.9,19.5 L74.5,19.5 L74.5,2.1 L0,2.1 L0,19.5 L27.6,19.5 Z",
        "glyph": [(26.4, 35.3, 21.7, 21.7), (52.7, 9, 21.7, 21.7), (0.1, 61.7, 21.7, 21.7)],
        "serif": "M71.1,2.1 l3,24 h-1.7 c-2.8,-12.8 -9.3,-20.3 -21.2,-20.3 h-7.3 v73.2 c0,6.6 2.9,8.7 10.7,9.5 v1.8 H20 v-1.8 c7.9,-0.8 10.7,-2.9 10.7,-9.5 V5.8 h-7.3 c-11.8,0 -18.5,7.5 -21.2,20.3 h-1.7 l3,-24 C3.5,2.1 71.1,2.1 71.1,2.1 z",
        "sans": "M2,12.3 V2.1 h70.3 v10.2 h-29.4 V90 h-11.5 V12.3 H2 z",
    },
]

# Per-letter (duration, delay, direction). The navbar logo morphs on hover by
# picking letters at RANDOM and independently — not as a travelling wave. A
# uniform duration + regular stagger reads as a wave (the splash look), so each
# letter instead gets its own coprime-ish duration and an alternating direction;
# the letters then drift out of phase and morph independently, like the navbar.
_LETTER_TIMING = [
    ("2.4s", "0s", "normal"),
    ("3.1s", "-0.9s", "reverse"),
    ("2.7s", "-1.7s", "normal"),
    ("3.5s", "-0.5s", "reverse"),
    ("2.2s", "-2.0s", "reverse"),
    ("3.8s", "-1.3s", "normal"),
]

# Four keyframes hand each variant a dwelling ~quarter of the cycle with
# overlapping cross-fades, so one variant is legible at a time before easing into
# the next. Hover-only (resting leaves the default variant opaque, others hidden),
# matching the navbar — not the splash's autoMorph-on-mount.
WORDMARK_CSS = (
    ".wm{display:inline-block;line-height:0;text-decoration:none}"
    ".wm .vg{opacity:0;transition:opacity .3s cubic-bezier(.215,.61,.355,1)}"
    ".wm .v-default{opacity:1}"
    "@keyframes wmA{0%{opacity:1}18%{opacity:1}30%{opacity:0}88%{opacity:0}100%{opacity:1}}"
    "@keyframes wmB{0%{opacity:0}18%{opacity:0}30%{opacity:1}43%{opacity:1}55%{opacity:0}100%{opacity:0}}"
    "@keyframes wmC{0%{opacity:0}43%{opacity:0}55%{opacity:1}68%{opacity:1}80%{opacity:0}100%{opacity:0}}"
    "@keyframes wmD{0%{opacity:0}68%{opacity:0}80%{opacity:1}93%{opacity:1}100%{opacity:0}}"
    ".wm:hover .vg{animation-timing-function:ease-in-out;animation-iteration-count:infinite}"
    ".wm:hover .v-default{animation-name:wmA}"
    ".wm:hover .v-glyph{animation-name:wmB}"
    ".wm:hover .v-serif{animation-name:wmC}"
    ".wm:hover .v-sans{animation-name:wmD}"
    + "".join(
        f".wm:hover .l{i} .vg{{animation-duration:{dur};animation-delay:{delay};animation-direction:{direction}}}"
        for i, (dur, delay, direction) in enumerate(_LETTER_TIMING)
    )
)


def wordmark_svg(height: int = 26, color: str = "#1c1612") -> str:
    """Return the inline SVG SKYNET wordmark, sized to ``height`` px.

    Args:
        height: Rendered height in px (width scales by the 475:92 viewBox).
        color: Fill color for the glyphs (defaults to the app foreground ink).

    Returns:
        An ``<svg>`` string with one ``<g class="ltr lN">`` per letter, each
        holding the four variant subgroups the hover morph cross-fades.
    """
    width = round(TOTAL_WIDTH / 92 * height)
    parts = []
    for i, letter in enumerate(LETTERS):
        rects = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>' for (x, y, w, h) in letter["glyph"])
        groups = (
            f'<path class="vg v-default" d="{letter["default"]}"/>'
            f'<g class="vg v-glyph">{rects}</g>'
            f'<path class="vg v-serif" d="{letter["serif"]}"/>'
            f'<path class="vg v-sans" d="{letter["sans"]}"/>'
        )
        parts.append(f'<g class="ltr l{i}" transform="translate({letter["offset"]},0)">{groups}</g>')
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {TOTAL_WIDTH} 92" '
        f'fill="{color}" stroke="none" xmlns="http://www.w3.org/2000/svg" '
        'style="overflow:visible;display:block">'
        f"{''.join(parts)}</svg>"
    )
