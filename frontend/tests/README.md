# Fluid Layout Test Suite

Comprehensive testing for the fluid layout overhaul, covering visual regression, accessibility, performance, and responsive behavior.

## Test Files

### New Test Files (Fluid Layout Specific)

#### 1. `fluid-layout-regression.spec.ts`

**Purpose:** Visual regression testing across all viewports  
**Coverage:**

- 5 routes × 8 viewports = 40 page/viewport combinations
- Horizontal overflow detection
- Console error tracking
- Layout issue detection (overlapping, cut-off content)
- Component-specific checks (sidebar, tables, modals, code editor)

**Viewports Tested:**

- 640px (mobile)
- 800px (small tablet)
- 960px (tablet)
- 1024px (tablet landscape / small desktop)
- 1280px (desktop)
- 1440px (large desktop)
- 1920px (full HD)
- 2560px (2K/retina)

**Run:**

```bash
npx playwright test fluid-layout-regression
```

#### 2. `continuous-resize.spec.ts`

**Purpose:** Smooth resize behavior validation  
**Coverage:**

- Programmatic viewport resize from 2560px down to 640px in 100px steps
- Layout jump detection (element count changes > 20%)
- Element overflow tracking
- Screenshot at each step for visual verification
- Tests 3 critical pages: Dashboard, Job Detail, Submit Wizard

**Run:**

```bash
npx playwright test continuous-resize
```

#### 3. `fluid-layout-a11y.spec.ts`

**Purpose:** Accessibility compliance at different viewports  
**Coverage:**

- axe-core WCAG 2.1 Level AA checks at 800px and 1920px
- Touch target minimum size (44px) at 4 viewport widths
- Keyboard navigation testing (Tab order, focus indicators)
- RTL/Hebrew layout verification (dir attribute, logical properties)

**Run:**

```bash
npx playwright test fluid-layout-a11y
```

#### 4. `fluid-layout-performance.spec.ts`

**Purpose:** Performance and animation validation  
**Coverage:**

- Layout thrashing detection during resize (monitors getBoundingClientRect calls)
- Framer Motion animation verification
- Page load performance metrics (FCP, LCP, DOM Content Loaded)
- CSS optimization checks (detecting fixed pixel widths)
- Stagger animation testing

**Run:**

```bash
npx playwright test fluid-layout-performance
```

---

### Existing Test Files (Updated)

#### 5. `layout.spec.ts`

**Purpose:** Original responsive layout tests  
**Status:** Updated selectors to fix duplicate text issues  
**Coverage:**

- App shell viewport containment
- Console error tracking
- 5 viewports (375px, 768px, 1024px, 1440px, 1920px)

#### 6. `mobile.spec.ts`

**Purpose:** Mobile touch target testing  
**Status:** Updated selectors to fix duplicate text issues  
**Coverage:**

- 44px minimum touch target size at 375px and 768px
- Interactive element detection
- Touch-friendly UI validation

#### 7. `helpers.ts`

**Purpose:** Shared test utilities  
**No changes needed** - all helpers still work

---

## Running Tests

### Run All Fluid Layout Tests

```bash
cd frontend
export PLAYWRIGHT_BASE_URL=http://localhost:3001
export PLAYWRIGHT_API_URL=http://localhost:8000

# All new fluid layout tests
npx playwright test fluid-layout-regression continuous-resize fluid-layout-a11y fluid-layout-performance

# All tests (including existing)
npm test
```

### Run Individual Test Suites

```bash
# Visual regression only
npx playwright test fluid-layout-regression --reporter=list

# Continuous resize only
npx playwright test continuous-resize --reporter=list

# Accessibility only
npx playwright test fluid-layout-a11y --reporter=list

# Performance only
npx playwright test fluid-layout-performance --reporter=list

# Existing layout tests
npx playwright test layout --reporter=list
npx playwright test mobile --reporter=list
```

### Run Specific Tests

```bash
# Run one test by name
npx playwright test --grep "sidebar doesn't overlap"

# Run tests for specific viewport
npx playwright test --grep "640px"

# Run with headed browser (see what's happening)
npx playwright test fluid-layout-regression --headed

# Run with debug mode
npx playwright test fluid-layout-regression --debug
```

### Generate Test Report

```bash
# Run tests and generate HTML report
npx playwright test --reporter=html

# Open report
npx playwright show-report
```

---

## Test Results Location

After running tests, results are saved to:

- **Screenshots:** `test-results/{test-name}/test-failed-*.png`
- **Error Context:** `test-results/{test-name}/error-context.md`
- **Full Report:** `test-results/index.html` (if using HTML reporter)

---

## Current Status (2026-04-07)

| Test Suite               | Tests  | Passed | Failed | Status               |
| ------------------------ | ------ | ------ | ------ | -------------------- |
| fluid-layout-regression  | 5      | 1      | 4      | ❌ FAILED            |
| continuous-resize        | 3      | 0      | 3      | ❌ FAILED            |
| fluid-layout-a11y        | 4      | 0      | 0      | ⏸️ NOT RUN           |
| fluid-layout-performance | 4      | 0      | 0      | ⏸️ NOT RUN           |
| layout (existing)        | 1      | 0      | 1      | ❌ FAILED            |
| mobile (existing)        | 2      | 0      | 2      | ❌ FAILED            |
| **TOTAL**                | **19** | **1**  | **10** | **❌ 93% FAIL RATE** |

See [TEST_REPORT.md](../TEST_REPORT.md) for detailed findings.

---

## Known Issues to Fix

### P0 - Critical (blocks deployment)

1. **Horizontal overflow** - Elements extend beyond viewport at all widths
2. **Sidebar mobile overflow** - Sidebar extends to 840px on 640px viewport
3. **Decorative orb overflow** - Background orbs overflow on narrow viewports
4. **React hydration mismatch** - SSR/client discrepancy on submit page

### P1 - High (accessibility issues)

5. **Touch target sizing** - Multiple buttons < 44px minimum

### P2 - Medium (test coverage)

6. Complete component-specific tests (tables, modals, code editor)
7. Run full accessibility test suite

### P3 - Low (nice to have)

8. Performance testing and optimization
9. Cross-browser testing
10. Manual device testing

---

## Test Patterns & Best Practices

### Viewport Testing Pattern

```typescript
const VIEWPORTS = [
  { width: 640, height: 1136 }, // Mobile
  { width: 1024, height: 768 }, // Tablet
  { width: 1920, height: 1080 }, // Desktop
];

for (const viewport of VIEWPORTS) {
  await withAuthenticatedPage(browser, authState, viewport, async (page) => {
    // Test code here
  });
}
```

### Overflow Detection Pattern

```typescript
const metrics = await page.evaluate(() => {
  const root = document.scrollingElement ?? document.documentElement;
  return {
    viewportWidth: window.innerWidth,
    documentWidth: root.scrollWidth,
    hasOverflow: root.scrollWidth > root.clientWidth,
  };
});

expect(metrics.hasOverflow).toBe(false);
```

### Touch Target Validation Pattern

```typescript
const tooSmall = await page.evaluate(() => {
  const MIN_SIZE = 44;
  const elements = document.querySelectorAll("button, a[href], input");
  return Array.from(elements).filter((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width < MIN_SIZE || rect.height < MIN_SIZE;
  });
});

expect(tooSmall).toEqual([]);
```

### RTL Layout Check Pattern

```typescript
const rtlIssues = await page.evaluate(() => {
  const issues = [];

  // Check document direction
  if (document.documentElement.dir !== "rtl") {
    issues.push("Document direction is not RTL");
  }

  // Check for physical properties instead of logical
  const elements = document.querySelectorAll("*");
  elements.forEach((el) => {
    const style = el.style.cssText;
    if (style.includes("margin-left") || style.includes("margin-right")) {
      issues.push("Element uses physical margin properties");
    }
  });

  return issues;
});
```

---

## Next Steps

1. Fix P0 issues (horizontal overflow, sidebar, orbs, hydration)
2. Re-run all tests and verify green status
3. Run accessibility tests
4. Run performance tests
5. Generate final test report
6. Manual testing on real devices

---

## Contributing

When adding new tests:

1. Follow existing test patterns
2. Use shared helpers from `helpers.ts`
3. Add meaningful test descriptions
4. Include screenshots for visual tests
5. Document expected behavior
6. Update this README with new test info
