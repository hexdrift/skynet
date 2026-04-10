import { expect, test } from "@playwright/test";
import {
  createAuthenticatedState,
  fetchSampleJobIds,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

test.describe("SEO and accessibility regressions", () => {
  test("login page keeps unique metadata", async ({ page }) => {
    const baseUrl = await resolveAppBaseUrl();

    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });

    await expect(page).toHaveTitle("Skynet");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/login$/);
  });

  test("job detail copy affordances expose aria labels and keyboard semantics", async ({
    browser,
  }) => {
    const baseUrl = await resolveAppBaseUrl();
    const [jobId] = await fetchSampleJobIds(1);
    const authState = await createAuthenticatedState(browser, baseUrl);

    await withAuthenticatedPage(browser, authState, { width: 1440, height: 900 }, async (page) => {
      await page.goto(`${baseUrl}/jobs/${jobId}`, { waitUntil: "domcontentloaded" });

      await expect(page.getByText("סקירה")).toBeVisible({ timeout: 30_000 });

      const jobIdCopy = page.locator('code[title="לחץ להעתקה"]').first();
      await expect(jobIdCopy).toHaveAttribute("aria-label", /.+/);
      await expect(jobIdCopy).toHaveAttribute("role", "button");
      await expect(jobIdCopy).toHaveAttribute("tabindex", "0");

      const promptCopyButtons = page.locator('button[title="העתק"]');
      await expect(promptCopyButtons.first()).toHaveAttribute("aria-label", /.+/);
    });
  });

  test("dashboard analytics rows are keyboard reachable", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    await withAuthenticatedPage(browser, authState, { width: 1440, height: 900 }, async (page) => {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({
        timeout: 30_000,
      });

      await page.getByRole("tab", { name: "סטטיסטיקות" }).click();

      const rows = page.locator('[data-state="active"] tbody tr.cursor-pointer');
      const count = await rows.count();
      expect(count).toBeGreaterThan(0);

      for (let index = 0; index < count; index += 1) {
        const row = rows.nth(index);
        await expect(row).toHaveAttribute("role", "button");
        await expect(row).toHaveAttribute("tabindex", "0");
      }
    });
  });
});
