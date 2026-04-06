import { expect, test, type Page } from "@playwright/test";
import {
 createAuthenticatedState,
 fetchSampleJobIds,
 resolveAppBaseUrl,
 withAuthenticatedPage,
} from "./helpers";

/**
 * Adversarial tests — probe edge cases that weren't obviously covered by the
 * pinning fix. Each test targets a concrete weakness or behavior contract.
 */

type Rect = { top: number; left: number; bottom: number; right: number; width: number; height: number };

async function getAllRects(page: Page): Promise<{ btn: Rect | null; drop: Rect | null }> {
 return page.evaluate(() => {
 const btn = document.querySelector('button[aria-label^="סינון עמודת"]') as HTMLElement | null;
 const drop = document.querySelector('body > div.fixed.z-50') as HTMLElement | null;
 const toRect = (el: HTMLElement | null) => el
 ? { top: el.getBoundingClientRect().top, left: el.getBoundingClientRect().left, bottom: el.getBoundingClientRect().bottom, right: el.getBoundingClientRect().right, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }
 : null;
 return { btn: toRect(btn), drop: toRect(drop) };
 });
}

async function gap(page: Page): Promise<number> {
 const { btn, drop } = await getAllRects(page);
 if (!btn || !drop) return Number.NaN;
 return Math.max(drop.top - btn.bottom, btn.top - drop.bottom);
}

async function openFirst(page: Page) {
 const btn = page.locator('button[aria-label^="סינון עמודת"]').first();
 await btn.waitFor({ state: "visible", timeout: 15_000 });
 await btn.click();
 await page.locator('body > div.fixed.z-50').first().waitFor({ state: "visible", timeout: 5_000 });
}

async function waitAF(page: Page) {
 await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null)))));
}

test.describe("Excel filter adversarial", () => {
 let baseUrl: string;
 let storageState: Awaited<ReturnType<typeof createAuthenticatedState>>;
 let jobId: string;

 test.beforeAll(async ({ browser }) => {
 baseUrl = await resolveAppBaseUrl();
 storageState = await createAuthenticatedState(browser, baseUrl);
 const ids = await fetchSampleJobIds(1);
 jobId = ids[0];
 });

 test("escape key closes dropdown", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 await openFirst(page);
 await page.keyboard.press("Escape");
 await page.waitForTimeout(100);
 const count = await page.locator('body > div.fixed.z-50').count();
 expect(count, "dropdown should close on Escape").toBe(0);
 });
 });

 test("apply button closes dropdown and applies selection", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 await openFirst(page);
 await page.locator('body > div.fixed.z-50 input[type="checkbox"]').first().click();
 await page.locator('body > div.fixed.z-50 button:has-text("החל")').click();
 await page.waitForTimeout(100);
 expect(await page.locator('body > div.fixed.z-50').count()).toBe(0);
 });
 });

 test("clear button closes dropdown and resets filter", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 await openFirst(page);
 await page.locator('body > div.fixed.z-50 button:has-text("נקה")').click();
 await page.waitForTimeout(100);
 expect(await page.locator('body > div.fixed.z-50').count()).toBe(0);
 });
 });

 test("dropdown stays anchored while typing RTL Hebrew in search input", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 await openFirst(page);
 const initial = await gap(page);
 const searchInput = page.locator('body > div.fixed.z-50 input[placeholder="חיפוש..."]');
 await searchInput.fill("אב");
 await page.waitForTimeout(100);
 const after = await gap(page);
 expect(Math.abs(after - initial)).toBeLessThanOrEqual(2);
 });
 });

 test("dropdown closes when anchor button is removed from DOM", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 await openFirst(page);
 await page.evaluate(() => {
 const b = document.querySelector('button[aria-label^="סינון עמודת"]');
 b?.remove();
 window.dispatchEvent(new Event("scroll"));
 });
 await waitAF(page);
 await page.waitForTimeout(200);
 const count = await page.locator('body > div.fixed.z-50').count();
 expect(count, "dropdown should close when anchor detaches").toBe(0);
 });
 });

 test("opening a different column's filter reanchors to the new button", async ({ browser }) => {
 await withAuthenticatedPage(browser, storageState, { width: 1280, height: 720 }, async (page) => {
 await page.goto(`${baseUrl}/jobs/${jobId}?tab=logs`);
 await page.locator('div.max-h-\\[600px\\].overflow-auto').first().waitFor({ state: "visible", timeout: 15_000 });
 const btns = page.locator('button[aria-label^="סינון עמודת"]');
 const count = await btns.count();
 test.skip(count < 2, "need at least 2 filterable columns");
 await btns.nth(0).click();
 await page.locator('body > div.fixed.z-50').first().waitFor({ state: "visible" });
 const b0 = await btns.nth(0).boundingBox();
 await btns.nth(1).click();
 await page.locator('body > div.fixed.z-50').first().waitFor({ state: "visible" });
 await waitAF(page);
 const { drop } = await getAllRects(page);
 const b1 = await btns.nth(1).boundingBox();
 expect(drop).not.toBeNull();
 expect(b1).not.toBeNull();
 if (drop && b1 && b0) {
 const distB1 = Math.abs(drop.right - (b1.x + b1.width));
 const distB0 = Math.abs(drop.right - (b0.x + b0.width));
 expect(distB1, "dropdown must anchor to new column button").toBeLessThan(distB0);
 }
 });
 });
});
