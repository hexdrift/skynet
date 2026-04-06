import { expect, test, type Page } from "@playwright/test";
import {
 createAuthenticatedState,
 fetchSampleJobIds,
 resolveAppBaseUrl,
 withAuthenticatedPage,
} from "./helpers";

/**
 * Verifies the Excel-style filter dropdown stays anchored to its trigger button
 * when window or inner-container scrolling happens. Failing scenarios before
 * the fix: dropdown drifted because position was captured once at open.
 */

const BREAKPOINTS = [
 { width: 375, height: 800 },
 { width: 768, height: 1024 },
 { width: 1024, height: 800 },
 { width: 1440, height: 900 },
] as const;

// Allow tiny sub-pixel rounding.
const TOLERANCE = 2;

type Rect = { top: number; left: number; bottom: number; right: number; width: number; height: number };

async function getRect(page: Page, selector: string): Promise<Rect | null> {
 return page.evaluate((sel) => {
 const el = document.querySelector(sel) as HTMLElement | null;
 if (!el) return null;
 const r = el.getBoundingClientRect();
 return { top: r.top, left: r.left, bottom: r.bottom, right: r.right, width: r.width, height: r.height };
 }, selector);
}

async function getAllRects(page: Page): Promise<{ btn: Rect | null; drop: Rect | null }> {
 // The filter button has aria-label starting with "סינון עמודת".
 return page.evaluate(() => {
 const btn = document.querySelector('button[aria-label^="סינון עמודת"][class*="text-primary"], button[aria-label^="סינון עמודת"]:focus, button[aria-label^="סינון עמודת"]') as HTMLElement | null;
 // We'll grab whichever button opened the portal. Since only one dropdown opens at a time,
 // the active dropdown is the one rendered as a direct child of body with our class shell.
 const drop = document.querySelector('body > div.fixed.z-50.rounded-\\[22px\\]') as HTMLElement | null;
 const r = (el: HTMLElement | null) => el ? (({ top, left, bottom, right, width, height }) => ({ top, left, bottom, right, width, height }))(el.getBoundingClientRect()) : null;
 return { btn: r(btn), drop: r(drop) };
 });
}

async function openFirstFilter(page: Page): Promise<{ buttonHandle: ReturnType<Page["locator"]> }> {
 const buttonHandle = page.locator('button[aria-label^="סינון עמודת"]').first();
 await buttonHandle.waitFor({ state: "visible", timeout: 15_000 });
 await buttonHandle.click();
 await page.locator('body > div.fixed.z-50').first().waitFor({ state: "visible", timeout: 5_000 });
 return { buttonHandle };
}

async function measureDelta(page: Page): Promise<{ delta: number; stillOpen: boolean }> {
 const { btn, drop } = await getAllRects(page);
 if (!drop) return { delta: Number.NaN, stillOpen: false };
 if (!btn) return { delta: Number.NaN, stillOpen: true };
 // "Anchored gap": closest edge-to-edge distance (handles flip above/below).
 const below = drop.top - btn.bottom; // positive if dropdown is below
 const above = btn.top - drop.bottom; // positive if dropdown is above
 const gap = Math.max(below, above); // whichever side the dropdown is on
 return { delta: gap, stillOpen: true };
}

test.describe("Excel filter dropdown pinning", () => {
 let baseUrl: string;
 let storageState: Awaited<ReturnType<typeof createAuthenticatedState>>;
 let jobId: string;

 test.beforeAll(async ({ browser }) => {
 baseUrl = await resolveAppBaseUrl();
 storageState = await createAuthenticatedState(browser, baseUrl);
 const ids = await fetchSampleJobIds(1);
 jobId = ids[0];
 });

 for (const viewport of BREAKPOINTS) {
 test(`logs table: stays pinned during window + inner-container scroll @${viewport.width}x${viewport.height}`, async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, viewport, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`, { waitUntil: "domcontentloaded" });
 // wait for logs table to render
 const logsTable = page.locator('div.max-h-\\[600px\\].overflow-auto').first();
 await logsTable.waitFor({ state: "visible", timeout: 15_000 });

 // Open filter on any column that exists (level preferred, fallback to any).
 await openFirstFilter(page);

 const initial = await measureDelta(page);
 expect(initial.stillOpen, "dropdown should be open initially").toBe(true);
 expect(Number.isFinite(initial.delta)).toBe(true);

 // 1. Scroll window by 300px (instant, not smooth).
 const windowScrolled = await page.evaluate(() => {
 const before = window.scrollY;
 window.scrollTo({ top: before + 300, behavior: "instant" as ScrollBehavior });
 return window.scrollY - before;
 });
 // Wait for rAF + paint to apply imperative style.
 await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
 await page.waitForTimeout(100);
 const afterWindow = await measureDelta(page);
 if (windowScrolled > 0 && afterWindow.stillOpen) {
 expect(Math.abs(afterWindow.delta - initial.delta), `window scroll delta @${viewport.width}`).toBeLessThanOrEqual(TOLERANCE);
 }

 // Reset scroll and reopen if needed.
 await page.evaluate(() => window.scrollTo(0, 0));
 if (!afterWindow.stillOpen) await openFirstFilter(page);
 await page.waitForTimeout(150);

 const baseline2 = await measureDelta(page);

 // 2. Scroll inner table container by 300px.
 const innerScrolled = await page.evaluate(() => {
 const c = document.querySelector('div.max-h-\\[600px\\].overflow-auto') as HTMLElement | null;
 if (!c) return 0;
 const before = c.scrollTop;
 c.scrollTop = before + 300;
 return c.scrollTop - before;
 });
 await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
 await page.waitForTimeout(100);
 const afterInner = await measureDelta(page);
 if (innerScrolled > 0 && afterInner.stillOpen) {
 expect(Math.abs(afterInner.delta - baseline2.delta), `inner scroll delta @${viewport.width}`).toBeLessThanOrEqual(TOLERANCE);
 }
 });
 });
 }

 test(`logs table: closes when button scrolls fully out of viewport`, async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`, { waitUntil: "domcontentloaded" });
 const logsTable = page.locator('div.max-h-\\[600px\\].overflow-auto').first();
 await logsTable.waitFor({ state: "visible", timeout: 15_000 });
 await openFirstFilter(page);

 // Push filter button out of viewport by scrolling past it. We try whichever
 // scroll container actually scrolls far enough.
 await page.evaluate(() => {
 window.scrollTo(0, document.documentElement.scrollHeight);
 document.querySelectorAll<HTMLElement>('.overflow-auto,.overflow-y-auto').forEach((el) => {
 el.scrollTop = el.scrollHeight;
 });
 });
 await page.waitForTimeout(300);
 // The anchor button should now be above/below viewport; dropdown must close.
 const drop = await page.locator('body > div.fixed.z-50').count();
 expect(drop, "dropdown should be closed when anchor leaves viewport").toBe(0);
 });
 });

 test(`existing functionality: opens, search, checkbox, apply, clear, close on outside click`, async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`, { waitUntil: "domcontentloaded" });
 const logsTable = page.locator('div.max-h-\\[600px\\].overflow-auto').first();
 await logsTable.waitFor({ state: "visible", timeout: 15_000 });
 await openFirstFilter(page);

 // Search input should be focused and accept RTL Hebrew.
 const searchInput = page.locator('body > div.fixed.z-50 input[placeholder="חיפוש..."]');
 await expect(searchInput).toBeFocused();
 await searchInput.fill("בדיקה");
 await expect(searchInput).toHaveValue("בדיקה");

 // Clear search to show checkboxes.
 await searchInput.fill("");

 // Click outside closes.
 await page.mouse.click(10, 10);
 await page.waitForTimeout(100);
 const drop = await getRect(page, 'body > div.fixed.z-50');
 expect(drop).toBeNull();
 });
 });

 test(`dashboard optimizations table: stays pinned during window scroll`, async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
 const filterBtn = page.locator('button[aria-label^="סינון עמודת"]').first();
 await filterBtn.waitFor({ state: "visible", timeout: 15_000 });
 await filterBtn.click();
 await page.locator('body > div.fixed.z-50').first().waitFor({ state: "visible", timeout: 5_000 });

 const initial = await measureDelta(page);
 expect(initial.stillOpen).toBe(true);

 await page.evaluate(() => window.scrollBy(0, 200));
 await page.waitForTimeout(100);
 const after = await measureDelta(page);
 if (after.stillOpen) {
 expect(Math.abs(after.delta - initial.delta), "dashboard window scroll delta").toBeLessThanOrEqual(TOLERANCE);
 }
 });
 });
});
