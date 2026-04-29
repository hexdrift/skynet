# Skynet Frontend — Copilot Instructions

Next.js 16 App Router · React 19 · Tailwind v4 · shadcn/ui (Radix-based primitives) · Framer Motion · Lucide. Hebrew-first (RTL), light mode only. See `frontend/.impeccable.md` for the full design context (keep both files in sync); this file is the condensed version Copilot should consult on every suggestion.

## Design Context

### Users
External developers who build with LLMs but are **not** data scientists or ML specialists. They want to ship an optimization without reading a paper. Labels, defaults, and copy must translate DSPy concepts into plain engineering language.

### Brand Personality
**Easy · Reliable · Valuable.** Voice: clear, factual, no jargon. Tone: calm and confident — never hype, never cute, never apologetic. Emotional goal: the user should feel in control and unhurried. Submitting an optimization should feel like sending a well-formed API request.

### Aesthetic Direction
Reference: **Vercel.** Restrained typography, generous whitespace, decisive contrast, tiny delightful motion details, zero ornament.

- **Palette**: warm monochromatic — cream `#FAF8F5` bg, deep brown `#1C1612` fg, dark-brown `#3D2E22` primary. Chart ramp is a 5-step brown gradient. Accent colors (`--danger`, `--success`, `--warning`) used only for state. Tokens defined in `src/app/globals.css`.
- **Theme**: light mode only — dark theme is not wired up. Don't design for dark unless explicitly asked.
- **Typography**: Heebo Variable (body/UI), Inter Variable (headings), base 16px. Build hierarchy through size, weight, and whitespace — not color or borders.
- **Motion**: `--duration-fast: 120ms`, `--duration-base: 160ms`, `--ease-snappy` (defined in `src/app/globals.css`). State transitions, not decoration.
- **Radius**: `0.5rem` base.
- **Icons**: Lucide only, default stroke 1.5 (vary for emphasis), text color.

### Design Principles
1. **Boring is a feature.** Prefer the dull, correct affordance over the clever one.
2. **Hebrew is the primary language, not an afterthought.** Test RTL first, Latin second. Mixed-direction strings (English code in Hebrew sentences) must not break.
3. **Type hierarchy carries the page.** Use size, weight, and whitespace — not color, borders, or cards — to build structure.
4. **Whitespace over decoration.** When in doubt, remove.
5. **Explain the ML, don't expose it.** If a setting can't be explained in one sentence, it probably shouldn't be user-facing.

### Accessibility
- **WCAG AA baseline** — contrast, focus rings, keyboard reachability, non-negotiable.
- **Hebrew typography is a hard constraint.** Don't swap Heebo. Watch line-height. Never letter-space Hebrew. Hebrew has no true italic — don't fake it.
- **Mixed direction**: use `dir="ltr"` or `<bdi>` for English identifiers inside Hebrew UI.
- **Reduced motion**: respect `prefers-reduced-motion`. Nothing critical depends on motion.

## Code Conventions

- **No inline Hebrew literals.** Hebrew copy lives in `src/shared/lib/{messages,tooltips,terms}.ts`, `src/shared/messages/**`, or per-feature `src/features/<feature>/messages.ts`. ESLint rejects Hebrew literals anywhere else.
- **Canonical terms** (e.g. אופטימיזציה, דאטאסט, מודל רפלקציה, אופטימייזר, פונקציית מדידה) come from `TERMS` in `src/shared/lib/terms.ts`. Import and reference — never inline.
- **Path alias**: `@/*` resolves to `./src/*`. Cross-module imports use `@/...`; within a feature, use relative paths to siblings, and reach into another feature only through its `@/features/<name>` public index — feature internals (`@/features/*/components/*`, `hooks/*`, `lib/*`, `constants`) are blocked by ESLint.

## Project Structure

Per-feature code lives under `src/features/<feature>/{components,hooks,lib,constants.ts,index.ts}`. Cross-feature primitives live under `src/shared/`. See `AGENTS.md` for the full layout.
