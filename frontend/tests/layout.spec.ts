import { expect, test } from "@playwright/test";
import {
  assertNoHorizontalOverflow,
  createAuthenticatedState,
  fetchSampleJobIds,
  recordConsoleErrors,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

const VIEWPORTS = [
  { width: 375, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const;

test.describe("Responsive layout", () => {
  test("app shell stays inside the viewport and stays console-clean at every breakpoint", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobA, jobB] = await fetchSampleJobIds(2);

    const routes = [
      "/",
      "/submit",
      `/jobs/${jobA}`,
      `/compare?jobs=${jobA},${jobB}`,
    ] as const;

    for (const viewport of VIEWPORTS) {
      for (const route of routes) {
        await withAuthenticatedPage(browser, authState, viewport, async (page) => {
          const consoleErrors = recordConsoleErrors(page);

          await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });

          if (route === "/submit") {
            await expect(page.getByText("פרטים בסיסיים")).toBeVisible({ timeout: 30_000 });
          } else if (route.startsWith("/jobs/")) {
            await expect(page.getByText("סקירה")).toBeVisible({ timeout: 30_000 });
          } else if (route.startsWith("/compare")) {
            await expect(page.getByText("VS").first()).toBeVisible({ timeout: 30_000 });
          } else {
            await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });
          }

          await page.screenshot({
            path: testInfo.outputPath(
              `${route.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}-${viewport.width}x${viewport.height}.png`,
            ),
            fullPage: true,
          });

          await assertNoHorizontalOverflow(page, `${route} @ ${viewport.width}px`);
          expect(
            consoleErrors,
            `Console errors while rendering ${route} at ${viewport.width}px:\n${consoleErrors.join("\n")}`,
          ).toEqual([]);
        });
      }
    }
  });
});
