# Skynet Frontend — Copilot Instructions

Next.js 16 App Router · React 19 · Tailwind v4 · shadcn/Radix · Framer Motion · Lucide. Hebrew-first (RTL), light mode only. See `frontend/.impeccable.md` for the full design context; this file is the condensed version Copilot should consult on every suggestion.

## Design Context

### Users
External developers who build with LLMs but are **not** data scientists or ML specialists. They want to ship an optimization without reading a paper. Labels, defaults, and copy must translate DSPy concepts into plain engineering language.

### Brand Personality
**Easy · Reliable · Valuable.** Voice: clear, factual, no jargon. Tone: calm and confident — never hype, never cute, never apologetic. Emotional goal: the user should feel in control and unhurried. Submitting an optimization should feel like sending a well-formed API request.

### Aesthetic Direction
Reference: **Vercel.** Restrained typography, generous whitespace, decisive contrast, tiny delightful motion, zero ornament.

- **Palette**: warm monochromatic — cream `#faf8f5` bg, near-black-brown `#1c1612` fg, dark-brown `#3d2e22` primary. Chart ramp is a 5-step brown gradient. Accent colors (`--danger`, `--success`, `--warning`) used only for state.
- **Theme**: light mode only. Don't design for dark unless explicitly asked.
- **Typography**: Heebo Variable (body/UI), Inter Variable (headings), base 16px. Hierarchy is currently under-expressed — strengthen it when given the chance.
- **Motion**: `--duration-fast: 120ms`, `--duration-base: 160ms`, `--ease-snappy`. State transitions, not decoration.
- **Radius**: `0.5rem` base.
- **Icons**: Lucide only, stroke 1.5–2, text color.

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
