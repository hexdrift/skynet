/**
 * Tutorial System Tests
 * 
 * Comprehensive test suite for the interactive tutorial overlay system
 * covering step definitions, UI components, keyboard navigation, and persistence.
 */

import { expect, test, type Browser, type Page, type StorageState } from "@playwright/test";
import { createAuthenticatedState, resolveAppBaseUrl } from "./helpers";

const VIEWPORT = { width: 1280, height: 900 };
const STORAGE_KEY = "skynet-tutorial-state";

/**
 * Helper: Open the tutorial menu
 */
async function openTutorialMenu(page: Page): Promise<void> {
  // Click the help button (❓) in the sidebar
  await page.click('button[aria-label="פתח מדריך"]');
  await expect(page.locator("text=בחרו מסלול למידה")).toBeVisible({ timeout: 5000 });
}

/**
 * Helper: Start a tutorial track
 */
async function startTrack(page: Page, trackName: "סיור מהיר" | "הבנת המערכת"): Promise<void> {
  await openTutorialMenu(page);
  await page.click(`text=${trackName}`);
  // Wait for popover to appear
  await page.waitForSelector('[class*="fixed z-[9999]"]', { timeout: 5000 });
}

/**
 * Helper: Get current tutorial storage
 */
async function getTutorialStorage(page: Page): Promise<Record<string, unknown> | null> {
  return await page.evaluate((key) => {
    const stored = localStorage.getItem(key);
    return stored ? JSON.parse(stored) : null;
  }, STORAGE_KEY);
}

/**
 * Helper: Clear tutorial storage
 */
async function clearTutorialStorage(page: Page): Promise<void> {
  await page.evaluate((key) => {
    localStorage.removeItem(key);
  }, STORAGE_KEY);
}

/* ══════════════════════════════════════════════════════════════
   Test Suite: Step Definitions Validation
   ══════════════════════════════════════════════════════════════ */

test.describe("Tutorial Step Definitions", () => {
  test("all quick-tour steps have required fields and Hebrew text", async ({ page }) => {
    await page.goto("data:text/html,<script type='module'>import { TUTORIAL_TRACKS } from '/src/lib/tutorial-steps.ts';window.tracks=TUTORIAL_TRACKS;</script>");
    
    const quickTourTrack = await page.evaluate(() => {
      return (window as any).tracks.find((t: any) => t.id === "quick-tour");
    });

    expect(quickTourTrack).toBeTruthy();
    expect(quickTourTrack.name).toBe("סיור מהיר");
    expect(quickTourTrack.icon).toBe("🧭");
    expect(quickTourTrack.steps.length).toBe(12);

    for (const step of quickTourTrack.steps) {
      // Check required fields exist
      expect(step.id).toBeTruthy();
      expect(step.title).toBeTruthy();
      expect(step.description).toBeTruthy();
      expect(step.target).toBeTruthy();
      expect(step.track).toBe("quick-tour");

      // Validate Hebrew text (no English placeholders like "TODO" or "TBD")
      expect(step.title).not.toMatch(/TODO|TBD|FIXME|XXX/i);
      expect(step.description).not.toMatch(/TODO|TBD|FIXME|XXX/i);

      // Check target selector format
      expect(step.target).toMatch(/^\[data-tutorial=/);
    }
  });

  test("all deep-dive steps have required fields and Hebrew text", async ({ page }) => {
    await page.goto("data:text/html,<script type='module'>import { TUTORIAL_TRACKS } from '/src/lib/tutorial-steps.ts';window.tracks=TUTORIAL_TRACKS;</script>");
    
    const deepDiveTrack = await page.evaluate(() => {
      return (window as any).tracks.find((t: any) => t.id === "deep-dive");
    });

    expect(deepDiveTrack).toBeTruthy();
    expect(deepDiveTrack.name).toBe("הבנת המערכת");
    expect(deepDiveTrack.icon).toBe("🧠");
    expect(deepDiveTrack.steps.length).toBe(24);

    for (const step of deepDiveTrack.steps) {
      expect(step.id).toBeTruthy();
      expect(step.title).toBeTruthy();
      expect(step.description).toBeTruthy();
      expect(step.target).toBeTruthy();
      expect(step.track).toBe("deep-dive");
      
      expect(step.title).not.toMatch(/TODO|TBD|FIXME|XXX/i);
      expect(step.description).not.toMatch(/TODO|TBD|FIXME|XXX/i);
      expect(step.target).toMatch(/^\[data-tutorial=/);
    }
  });

  test("no duplicate step IDs within each track", async ({ page }) => {
    await page.goto("data:text/html,<script type='module'>import { TUTORIAL_TRACKS } from '/src/lib/tutorial-steps.ts';window.tracks=TUTORIAL_TRACKS;</script>");
    
    const tracks = await page.evaluate(() => {
      return (window as any).tracks;
    });

    for (const track of tracks) {
      const stepIds = track.steps.map((s: any) => s.id);
      const uniqueIds = new Set(stepIds);
      expect(uniqueIds.size).toBe(stepIds.length);
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Data-Tutorial Attributes
   ══════════════════════════════════════════════════════════════ */

test.describe("Data-Tutorial Attributes Presence", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("dashboard page has all required data-tutorial attributes", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible();

      // Check key tutorial targets exist
      await expect(page.locator('[data-tutorial="sidebar-logo"]')).toBeVisible();
      await expect(page.locator('[data-tutorial="sidebar-nav"]')).toBeVisible();
      await expect(page.locator('[data-tutorial="new-optimization"]')).toBeVisible();
      await expect(page.locator('[data-tutorial="dashboard-kpis"]')).toBeVisible();
      
      // Check table appears (may be empty, but element should exist)
      const tableContainer = page.locator('[data-tutorial="dashboard-table"]');
      await expect(tableContainer).toBeAttached();

      // Check analytics tab target
      await page.click('button[role="tab"]:has-text("אנליטיקס")');
      await expect(page.locator('[data-tutorial="dashboard-stats"]')).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("submit page has wizard step attributes", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/submit`, { waitUntil: "domcontentloaded" });
      await expect(page.getByText("אשף אופטימיזציה")).toBeVisible();

      // Check wizard container
      await expect(page.locator('[data-tutorial="submit-wizard"]')).toBeVisible();
      
      // Check step 1 (basics)
      await expect(page.locator('[data-tutorial="wizard-step-1"]')).toBeVisible();

      // Navigate to step 2 and check
      const nextButton = page.locator('[data-tutorial="wizard-next"]');
      await expect(nextButton).toBeVisible();
      // Note: May be disabled if form is incomplete, but should exist
    } finally {
      await context.close();
    }
  });

  test("compare page has compare-button attribute", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/compare`, { waitUntil: "domcontentloaded" });
      
      // Compare page should have the compare-button attribute
      await expect(page.locator('[data-tutorial="compare-button"]')).toBeVisible();
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Tutorial Menu Component
   ══════════════════════════════════════════════════════════════ */

test.describe("Tutorial Menu", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("opens when help button (❓) is clicked", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      
      await openTutorialMenu(page);
      
      // Check modal content
      await expect(page.locator("text=בחרו מסלול למידה")).toBeVisible();
      await expect(page.locator("text=סיור מהיר")).toBeVisible();
      await expect(page.locator("text=הבנת המערכת")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("displays two track cards with correct icons and descriptions", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await openTutorialMenu(page);

      // Check quick tour card
      const quickTourCard = page.locator('button:has-text("סיור מהיר")');
      await expect(quickTourCard).toBeVisible();
      await expect(quickTourCard.locator("text=🧭")).toBeVisible();
      await expect(quickTourCard.locator("text=12 שלבים")).toBeVisible();

      // Check deep dive card
      const deepDiveCard = page.locator('button:has-text("הבנת המערכת")');
      await expect(deepDiveCard).toBeVisible();
      await expect(deepDiveCard.locator("text=🧠")).toBeVisible();
      await expect(deepDiveCard.locator("text=24 שלבים")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("closes when X button is clicked", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await openTutorialMenu(page);
      
      await page.click('button[aria-label="סגור תפריט"]');
      
      // Menu should disappear
      await expect(page.locator("text=בחרו מסלול למידה")).toBeHidden();
    } finally {
      await context.close();
    }
  });

  test("closes when backdrop is clicked", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await openTutorialMenu(page);
      
      // Click backdrop (outside modal)
      await page.click('.bg-black\\/60', { position: { x: 10, y: 10 } });
      
      // Menu should disappear
      await expect(page.locator("text=בחרו מסלול למידה")).toBeHidden({ timeout: 2000 });
    } finally {
      await context.close();
    }
  });

  test("starts tutorial when track card is clicked", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // First step should appear
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeVisible();
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Tutorial Popover Component
   ══════════════════════════════════════════════════════════════ */

test.describe("Tutorial Popover", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("renders step content with title, description, and progress", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Check first step content
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeVisible();
      await expect(page.locator("text=פלטפורמה לאופטימיזציה אוטומטית")).toBeVisible();
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
      
      // Check navigation buttons
      await expect(page.locator("button:has-text('הבא')")).toBeVisible();
      await expect(page.locator("button:has-text('הקודם')")).toBeDisabled(); // First step
    } finally {
      await context.close();
    }
  });

  test("Next button advances to next step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Click Next
      await page.click("button:has-text('הבא')");
      
      // Should show step 2
      await expect(page.locator("text=ניווט במערכת")).toBeVisible();
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();
      
      // Previous button should now be enabled
      await expect(page.locator("button:has-text('הקודם')")).toBeEnabled();
    } finally {
      await context.close();
    }
  });

  test("Previous button goes back to previous step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Go to step 2
      await page.click("button:has-text('הבא')");
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();

      // Go back
      await page.click("button:has-text('הקודם')");
      
      // Should show step 1 again
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeVisible();
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("Last step shows 'סיים' button instead of 'הבא'", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Navigate to last step (12th)
      for (let i = 0; i < 11; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(200);
      }

      // Check last step
      await expect(page.locator("text=12 מתוך 12")).toBeVisible();
      await expect(page.locator("button:has-text('סיים')")).toBeVisible();
      await expect(page.locator("button:has-text('הבא')")).toBeHidden();
    } finally {
      await context.close();
    }
  });

  test("X button closes tutorial", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Close tutorial
      await page.click('button[aria-label="סגור מדריך"]');
      
      // Popover should disappear
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeHidden();
    } finally {
      await context.close();
    }
  });

  test("progress bar animates with step progression", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Check progress bar exists
      const progressBar = page.locator('.h-1.bg-muted\\/30 .bg-gradient-to-r');
      await expect(progressBar).toBeVisible();

      // Progress should increase after clicking Next
      const initialWidth = await progressBar.evaluate((el) => {
        return window.getComputedStyle(el).width;
      });

      await page.click("button:has-text('הבא')");
      await page.waitForTimeout(500); // Wait for animation

      const newWidth = await progressBar.evaluate((el) => {
        return window.getComputedStyle(el).width;
      });

      // Width should have increased
      expect(parseFloat(newWidth)).toBeGreaterThan(parseFloat(initialWidth));
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Spotlight Mask
   ══════════════════════════════════════════════════════════════ */

test.describe("Spotlight Mask", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("renders SVG mask with cutout for target element", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Check SVG mask exists
      const svg = page.locator('svg[aria-hidden="true"]').first();
      await expect(svg).toBeVisible();

      // Check mask and rect elements exist
      await expect(svg.locator('mask')).toBeAttached();
      await expect(svg.locator('rect[fill="white"]')).toBeAttached();
      await expect(svg.locator('rect[fill="black"]')).toBeAttached();
    } finally {
      await context.close();
    }
  });

  test("mask updates when navigating to next step with different target", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Get initial mask rect position
      const svg = page.locator('svg[aria-hidden="true"]').first();
      const initialRect = await svg.locator('rect[fill="black"]').first().evaluate((el) => {
        return { x: el.getAttribute('x'), y: el.getAttribute('y') };
      });

      // Move to next step
      await page.click("button:has-text('הבא')");
      await page.waitForTimeout(300);

      // Mask should update
      const newRect = await svg.locator('rect[fill="black"]').first().evaluate((el) => {
        return { x: el.getAttribute('x'), y: el.getAttribute('y') };
      });

      // Position should change (different target element)
      expect(newRect.x).not.toBe(initialRect.x);
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Keyboard Navigation
   ══════════════════════════════════════════════════════════════ */

test.describe("Keyboard Navigation", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("Enter key advances to next step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
      
      await page.keyboard.press("Enter");
      
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("ArrowLeft (RTL: next) advances to next step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      await page.keyboard.press("ArrowLeft");
      
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("ArrowRight (RTL: prev) goes to previous step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Go to step 2
      await page.keyboard.press("Enter");
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();

      // Go back with ArrowRight
      await page.keyboard.press("ArrowRight");
      
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("Backspace goes to previous step", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      await page.keyboard.press("Enter");
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();

      await page.keyboard.press("Backspace");
      
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("Escape closes tutorial", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      await page.keyboard.press("Escape");
      
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeHidden();
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: LocalStorage Persistence
   ══════════════════════════════════════════════════════════════ */

test.describe("LocalStorage Persistence", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test.beforeEach(async ({ browser }) => {
    // Clear storage before each test
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
    await clearTutorialStorage(page);
    await context.close();
  });

  test("completed tracks are persisted to localStorage", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Complete the tutorial by going to last step and clicking "סיים"
      for (let i = 0; i < 11; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(100);
      }
      
      await page.click("button:has-text('סיים')");
      await page.waitForTimeout(300);

      // Check localStorage
      const storage = await getTutorialStorage(page);
      expect(storage).toBeTruthy();
      expect(storage?.completedTracks).toContain("quick-tour");
    } finally {
      await context.close();
    }
  });

  test("completed tracks persist across page reloads", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Complete tutorial
      for (let i = 0; i < 11; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(100);
      }
      await page.click("button:has-text('סיים')");
      await page.waitForTimeout(300);

      // Reload page
      await page.reload({ waitUntil: "domcontentloaded" });

      // Open menu and check for completed badge
      await openTutorialMenu(page);
      
      const quickTourCard = page.locator('button:has-text("סיור מהיר")');
      await expect(quickTourCard.locator("text=✓ הושלם")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("multiple tracks can be marked as completed", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      
      // Complete quick tour
      await startTrack(page, "סיור מהיר");
      for (let i = 0; i < 11; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(50);
      }
      await page.click("button:has-text('סיים')");
      await page.waitForTimeout(300);

      // Complete deep dive
      await page.click('button[aria-label="פתח מדריך"]');
      await page.click("text=הבנת המערכת");
      for (let i = 0; i < 23; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(50);
      }
      await page.click("button:has-text('סיים')");
      await page.waitForTimeout(300);

      // Check storage
      const storage = await getTutorialStorage(page);
      expect(storage?.completedTracks).toContain("quick-tour");
      expect(storage?.completedTracks).toContain("deep-dive");
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Full Integration Flow
   ══════════════════════════════════════════════════════════════ */

test.describe("Full Tutorial Flow", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("complete quick tour tutorial from start to finish", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await clearTutorialStorage(page);

      // Start quick tour
      await startTrack(page, "סיור מהיר");

      // Navigate through all 12 steps
      for (let i = 1; i <= 12; i++) {
        await expect(page.locator(`text=${i} מתוך 12`)).toBeVisible();
        
        if (i < 12) {
          await page.click("button:has-text('הבא')");
          await page.waitForTimeout(100);
        } else {
          // Last step - click finish
          await expect(page.locator("button:has-text('סיים')")).toBeVisible();
          await page.click("button:has-text('סיים')");
        }
      }

      // Tutorial should close
      await expect(page.locator("text=12 מתוך 12")).toBeHidden({ timeout: 2000 });

      // Track should be marked complete
      const storage = await getTutorialStorage(page);
      expect(storage?.completedTracks).toContain("quick-tour");
    } finally {
      await context.close();
    }
  });

  test("can restart a completed tutorial", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      
      // Complete tutorial first
      await startTrack(page, "סיור מהיר");
      for (let i = 0; i < 11; i++) {
        await page.click("button:has-text('הבא')");
        await page.waitForTimeout(50);
      }
      await page.click("button:has-text('סיים')");
      await page.waitForTimeout(300);

      // Restart the same tutorial
      await openTutorialMenu(page);
      await page.click("text=סיור מהיר");

      // Should start from beginning
      await expect(page.locator("text=1 מתוך 12")).toBeVisible();
      await expect(page.locator("text=ברוכים הבאים ל-Skynet")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("tutorial can be interrupted and does not auto-resume", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await clearTutorialStorage(page);
      
      // Start tutorial
      await startTrack(page, "סיור מהיר");
      
      // Navigate to step 3
      await page.click("button:has-text('הבא')");
      await page.click("button:has-text('הבא')");
      await expect(page.locator("text=3 מתוך 12")).toBeVisible();

      // Close tutorial
      await page.keyboard.press("Escape");

      // Reload page
      await page.reload({ waitUntil: "domcontentloaded" });

      // Tutorial should NOT auto-resume
      await expect(page.locator("text=3 מתוך 12")).toBeHidden();
      
      // But help button should still be visible
      await expect(page.locator('button[aria-label="פתח מדריך"]')).toBeVisible();
    } finally {
      await context.close();
    }
  });
});

/* ══════════════════════════════════════════════════════════════
   Test Suite: Hebrew Text Verification
   ══════════════════════════════════════════════════════════════ */

test.describe("Hebrew Text Verification", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("all UI text in tutorial components is in Hebrew", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      
      // Open menu
      await openTutorialMenu(page);

      // Check menu text
      await expect(page.locator("text=בחרו מסלול למידה")).toBeVisible();
      await expect(page.locator("text=למדו איך להשתמש ב-Skynet")).toBeVisible();

      // Start tutorial
      await page.click("text=סיור מהיר");

      // Check popover text
      await expect(page.locator("button:has-text('הבא')")).toBeVisible();
      await expect(page.locator("button:has-text('הקודם')")).toBeVisible();
      
      // Navigate to ensure consistent Hebrew throughout
      await page.click("button:has-text('הבא')");
      await page.waitForTimeout(200);
      
      // All step numbers should be in format "X מתוך Y" (Hebrew)
      await expect(page.locator("text=2 מתוך 12")).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("no English placeholder text remains in tutorial steps", async ({ browser }) => {
    const context = await browser.newContext({ storageState: authState, viewport: VIEWPORT });
    const page = await context.newPage();

    try {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await startTrack(page, "סיור מהיר");

      // Navigate through all steps and check for English placeholders
      for (let i = 0; i < 12; i++) {
        // Get all visible text
        const bodyText = await page.locator('[dir="rtl"]').first().textContent();
        
        // Check for common placeholder patterns
        expect(bodyText).not.toMatch(/\bTODO\b/i);
        expect(bodyText).not.toMatch(/\bTBD\b/i);
        expect(bodyText).not.toMatch(/\bFIXME\b/i);
        expect(bodyText).not.toMatch(/\bXXX\b/i);
        expect(bodyText).not.toMatch(/placeholder/i);
        expect(bodyText).not.toMatch(/lorem ipsum/i);

        if (i < 11) {
          await page.click("button:has-text('הבא')");
          await page.waitForTimeout(100);
        }
      }
    } finally {
      await context.close();
    }
  });
});
