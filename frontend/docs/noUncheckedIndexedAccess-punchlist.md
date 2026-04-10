# `noUncheckedIndexedAccess` punch list

Enabling `noUncheckedIndexedAccess: true` in `frontend/tsconfig.json` surfaces
50 errors across 12 files. Most are legitimate null-deref risks that should be
fixed, but doing so in a single sweep is outside the scope of the current
audit refactor. Two of the clearest ones are already fixed on the pilot branch
(`src/app/compare/page.tsx:210` and `src/app/optimizations/[id]/data-tab.tsx:115`).

The remaining 48 errors (captured below) should be fixed in a dedicated PR.
Enable the flag locally, run `npx tsc --noEmit`, and work through them.

## Error snapshot

```
src/app/optimizations/[id]/data-tab.tsx(180,46): error TS2345: arg 'number | undefined'
src/app/optimizations/[id]/page.tsx(258,26): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(264,27): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(273,27): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(282,24): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(283,27): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(292,24): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(293,27): TS2345: 'string | undefined'
src/app/optimizations/[id]/page.tsx(2163,15): TS2532: possibly 'undefined'
src/app/optimizations/[id]/page.tsx(2247,79): TS2532: possibly 'undefined'
src/app/optimizations/[id]/page.tsx(2685,46): TS18048: 'info' is possibly 'undefined'
src/app/optimizations/[id]/page.tsx(2686,61): TS18048: 'info' is possibly 'undefined'
src/app/optimizations/[id]/page.tsx(2691,62): TS18048: 'info' is possibly 'undefined'

src/components/animated-wordmark.tsx(155,18): TS2345: 'number | undefined'
src/components/animated-wordmark.tsx(164,3): TS2322: union type cannot be undefined
src/components/animated-wordmark.tsx(251,42): TS2345: same union type

src/components/motion.tsx(206,6): TS18048: 'entry' possibly undefined

src/components/particle-hero.tsx(66,9): TS2322: string | undefined
src/components/particle-hero.tsx(142,24): TS2532: 2D grid access
src/components/particle-hero.tsx(142,41): TS2532: 2D grid access
src/components/particle-hero.tsx(143,24): TS2532: 2D grid access
src/components/particle-hero.tsx(143,41): TS2532: 2D grid access
src/components/particle-hero.tsx(148,26): TS2532: 2D grid access
src/components/particle-hero.tsx(148,42): TS2532: 2D grid access
src/components/particle-hero.tsx(149,26): TS2532: 2D grid access
src/components/particle-hero.tsx(149,42): TS2532: 2D grid access

src/components/tutorial/tutorial-overlay.tsx(70,13): TS2532: possibly undefined

src/features/submit/hooks/use-submit-wizard.ts(204,39): TS2769: Record<string, unknown> | undefined

src/lib/parse-dataset.ts(56,34): TS2345: 'string | undefined'

src/lib/tutorial-demo-data.ts(150,114): TS2532: possibly undefined
src/lib/tutorial-demo-data.ts(199,114): TS2532: possibly undefined

...plus ~20 more in other files (run `npx tsc --noEmit` with the
flag re-enabled to see the full list)
```

## Common fix patterns

| Issue | Fix |
|---|---|
| `arr[i]` when `i` is known valid | `arr[i]!` (non-null assertion) |
| Destructure with fallback | `const [a = ""] = optimizationIds` |
| 2D grid: `grid[y][x]` | `const row = grid[y]; if (!row) continue; const cell = row[x];` |
| Map lookup | `const v = map.get(k); if (v === undefined) return;` |
| Optional param | Narrow type: `if (!info) return null;` |

## Re-enabling

Once all sites are fixed:
1. Add `"noUncheckedIndexedAccess": true` to `frontend/tsconfig.json` `compilerOptions`
2. Run `npx tsc --noEmit` to confirm zero errors
3. Run `npm run build` to confirm Turbopack is happy
4. Commit
