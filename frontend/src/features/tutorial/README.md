# Tutorial System — Skynet Frontend

Complete interactive tutorial system with two tracks: Quick Tour (12 steps) and Deep Dive (24 steps).

## Architecture

```
src/
├── lib/
│   └── tutorial-steps.ts          # Step definitions and types
├── hooks/
│   └── use-tutorial.ts            # State management with localStorage
└── components/
    └── tutorial/
        ├── spotlight-mask.tsx      # SVG cutout effect
        ├── tutorial-popover.tsx    # Main popover UI
        ├── tutorial-overlay.tsx    # Orchestrator (keyboard nav, positioning)
        ├── tutorial-menu.tsx       # Track selection modal
        ├── tutorial-provider.tsx   # Context provider (optional)
        └── index.ts                # Re-exports
```

## Features

### Spotlight Effect

- SVG mask with animated cutout highlighting target elements
- Smooth transitions between steps
- Pulsing glow effect for visual emphasis
- Responsive to target element size and position

### Popover UI

- **RTL-aware positioning**: Automatically adjusts arrows and placement
- **Gradient styling**: `bg-gradient-to-b from-white/95 to-[#F8F4EF]`
- **Progress bar**: Visual indicator of completion
- **Navigation**: Previous/Next buttons with Hebrew labels
- **Step counter**: "X מתוך Y" format

### Keyboard Navigation

- **Enter / ← (left arrow)**: Next step
- **→ (right arrow) / Backspace**: Previous step
- **Escape**: Exit tutorial

### State Management

- **useReducer** for predictable state updates
- **localStorage** persistence for completion tracking
- Tracks completed tutorials separately
- Allows resuming interrupted tutorials

### Responsive Positioning

- **ResizeObserver** watches target elements
- Auto-repositions on window resize and scroll
- Smart placement algorithm (`auto`, `top`, `bottom`, `left`, `right`)
- Clamps to viewport edges

## Tutorial Tracks

### Track 1: סיור מהיר (🧭 Quick Tour) — 12 Steps

1. **Welcome** — Introduction to Skynet
2. **Sidebar** — Navigation overview
3. **Dashboard KPIs** — Stats cards
4. **Dashboard Table** — Optimization history
5. **Dashboard Stats** — Analytics view
6. **New Optimization** — Start wizard
7. **Submit Wizard** — 6-step workflow
8. **Job Detail** — Pipeline + logs
9. **Serve** — Test optimized program
10. **Grid Search** — Multi-model runs
11. **Compare** — Side-by-side comparison
12. **Done** — Ready to optimize!

### Track 2: הבנת המערכת (🧠 Deep Dive) — 24 Steps

**Part 1: Concepts (4 steps)**

- Prompt optimization explanation
- Modules (Predict/CoT)
- Optimizer (GEPA)
- Scoring/metrics

**Part 2: Submit Wizard (13 steps)**

- Detailed walkthrough of each wizard step
- Column mapping, splits, models
- Code editor and metric templates
- Parameters and auto level
- Optimizer-specific settings

**Part 3: Results (7 steps)**

- Pipeline stages
- Live logs
- Score progression chart
- Inference/serve
- Grid search results
- Comparison tools
- Completion

## Data Tutorial Attributes

All target elements are marked with `data-tutorial` attributes:

### Layout

- `data-tutorial="sidebar-logo"` — Skynet logo
- `data-tutorial="sidebar-nav"` — Navigation menu

### Dashboard

- `data-tutorial="dashboard-kpis"` — Stats cards
- `data-tutorial="dashboard-table"` — Job table
- `data-tutorial="dashboard-stats"` — Analytics tab
- `data-tutorial="new-optimization"` — New optimization button
- `data-tutorial="job-link"` — Job table row (for navigation)

### Submit Wizard

- `data-tutorial="submit-wizard"` — Wizard container
- `data-tutorial="wizard-step-1"` — Basics step
- `data-tutorial="wizard-step-2"` — Dataset step
- `data-tutorial="wizard-step-3"` — Model step
- `data-tutorial="wizard-step-4"` — Code step
- `data-tutorial="wizard-step-5"` — Parameters step
- `data-tutorial="wizard-step-6"` — Review step
- `data-tutorial="wizard-next"` — Next button

### Job Detail

- `data-tutorial="pipeline-stages"` — Pipeline tracker
- `data-tutorial="score-chart"` — Score progression
- `data-tutorial="live-logs"` — Logs tab
- `data-tutorial="serve-playground"` — Playground tab content
- `data-tutorial="playground-tab"` — Playground tab trigger
- `data-tutorial="grid-search"` — Grid search results

### Compare

- `data-tutorial="compare-button"` — Compare page header

## Usage

### 1. Add to Layout

Already integrated in `src/app/layout.tsx`:

```tsx
import { TutorialOverlay, TutorialMenu } from "@/components/tutorial";

export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        {children}
        <TutorialOverlay />
        <TutorialMenu />
      </body>
    </html>
  );
}
```

### 2. Trigger from Anywhere

Use the `useTutorial` hook:

```tsx
import { useTutorial } from "@/hooks/use-tutorial";

function MyComponent() {
  const { openMenu } = useTutorial();

  return <button onClick={openMenu}>Open Tutorial</button>;
}
```

The ❓ button in the sidebar automatically opens the tutorial menu.

### 3. Add New Steps

Edit `src/lib/tutorial-steps.ts`:

```typescript
const newStep: TutorialStep = {
  id: "my-step",
  title: "כותרת בעברית",
  description: "תיאור מפורט של השלב",
  target: "[data-tutorial='my-target']",
  placement: "bottom",
  track: "quick-tour",
  beforeShow: async () => {
    // Optional: Navigate or prepare UI
    router.push("/some-page");
    await new Promise((r) => setTimeout(r, 100));
  },
};
```

Then add the corresponding `data-tutorial` attribute to your UI:

```tsx
<div data-tutorial="my-target">Target element</div>
```

## Styling

All styles use Tailwind CSS with RTL support:

### Popover

```css
rounded-2xl
bg-gradient-to-b from-white/95 to-[#F8F4EF]
border border-border/40
shadow-[0_12px_40px_rgba(28,22,18,0.15)]
direction: rtl
```

### Backdrop

```css
rgba(0,0,0,0.55)
```

### ❓ Button

```css
size-7
rounded-lg
bg-muted/50
hover:bg-muted
```

### Track Cards

```css
rounded-2xl
border-2
hover:border-primary/40
hover:shadow-[0_8px_32px_rgba(28,22,18,0.12)]
bg-gradient-to-br from-card to-card/60
```

## Accessibility

- Keyboard-navigable (Enter, arrows, Escape)
- ARIA labels on all interactive elements
- Focus management
- Screen reader friendly
- Respects `prefers-reduced-motion`

## Technical Details

### Portal Rendering

Both overlay and menu are rendered via `createPortal(component, document.body)` to escape overflow clipping and ensure proper stacking.

### beforeShow Callbacks

Each step can define async setup:

- Navigate to correct page
- Switch tabs
- Scroll elements into view
- Wait for DOM updates

### localStorage Schema

```json
{
  "skynet-tutorial-state": {
    "completedTracks": ["quick-tour"]
  }
}
```

### State Machine

```
Menu Open → Track Selected → Step 0 → Step 1 → ... → Step N → Completed
                ↓                                              ↑
              Exit ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
```

## Performance

- **Lazy loading**: TutorialOverlay only renders when active
- **Memoization**: useCallback and useMemo for expensive calculations
- **ResizeObserver**: Single observer per target element
- **Event cleanup**: All listeners removed on unmount
- **Minimal re-renders**: Isolated state in reducer

## Future Enhancements

- [ ] Video/GIF demonstrations in popover
- [ ] Interactive playground steps (user must perform action)
- [ ] Progress checkpoints (save current step)
- [ ] Branching paths based on user choices
- [ ] Achievement system for completion
- [ ] Export tutorial completion certificate
- [ ] Multi-language support (English/Hebrew toggle)
- [ ] Admin panel to edit steps without code changes
