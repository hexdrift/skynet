import { expect, test } from "@playwright/test";
import {
  collectVisibleInteractiveElements,
  createAuthenticatedState,
  fetchSampleJobIds,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

const MOBILE_VIEWPORTS = [
  { width: 375, height: 844 },
  { width: 768, height: 1024 },
] as const;

test.describe("Mobile touch targets", () => {
  for (const viewport of MOBILE_VIEWPORTS) {
    test(`interactive controls are at least 44px at ${viewport.width}px`, async ({ browser }) => {
      const baseUrl = await resolveAppBaseUrl();
      const authState = await createAuthenticatedState(browser, baseUrl);
      const [jobId] = await fetchSampleJobIds(1);

      const routes = ["/", "/submit", `/jobs/${jobId}`] as const;

      for (const route of routes) {
        await withAuthenticatedPage(browser, authState, viewport, async (page) => {
          await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded" });

          if (route === "/") {
            await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({
              timeout: 30_000,
            });
          } else if (route === "/submit") {
            await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });
          } else {
            await expect(page.getByText("סקירה").first()).toBeVisible({ timeout: 30_000 });
          }

          const interactiveElements = await collectVisibleInteractiveElements(page);
          const tooSmall = interactiveElements.filter(
            (element) => element.width < 44 || element.height < 44,
          );

          expect(
            tooSmall,
            `Touch targets smaller than 44px on ${route} at ${viewport.width}px:\n${JSON.stringify(
              tooSmall.slice(0, 20),
              null,
              2,
            )}`,
          ).toEqual([]);
        });
      }
    });
  }
});
