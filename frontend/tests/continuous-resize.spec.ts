import { expect, test } from "@playwright/test";
import {
  createAuthenticatedState,
  fetchSampleJobIds,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

// Layer 3: Continuous Resize Test
test.describe("Continuous Resize", () => {
  test("dashboard page handles continuous viewport resize smoothly", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const failedChecks: string[] = [];
    const layoutSnapshots: Array<{ width: number; metrics: any }> = [];

    // Resize from 2560px down to 640px in 100px steps
    const startWidth = 2560;
    const endWidth = 640;
    const step = 100;
    const height = 1440;

    for (let width = startWidth; width >= endWidth; width -= step) {
      await withAuthenticatedPage(browser, authState, { width, height }, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" }).first()).toBeVisible({ timeout: 30_000 });

        // Wait for any animations/transitions to complete
        await page.waitForTimeout(300);

        // Capture layout metrics
        const metrics = await page.evaluate(() => {
          const root = document.scrollingElement ?? document.documentElement;
          const body = document.body;

          // Get all visible elements count
          const allElements = Array.from(document.querySelectorAll("*"));
          const visibleElements = allElements.filter((el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              rect.width > 0 &&
              rect.height > 0
            );
          });

          // Check for horizontal scrollbar
          const hasHorizontalScroll = root.scrollWidth > root.clientWidth;

          // Get max element right edge
          let maxRight = 0;
          allElements.forEach((el) => {
            const rect = el.getBoundingClientRect();
            if (rect.right > maxRight) {
              maxRight = rect.right;
            }
          });

          return {
            viewportWidth: window.innerWidth,
            documentWidth: root.scrollWidth,
            bodyWidth: body.scrollWidth,
            hasHorizontalScroll,
            visibleElementCount: visibleElements.length,
            maxElementRight: Math.round(maxRight),
          };
        });

        layoutSnapshots.push({ width, metrics });

        // Take screenshot at each step
        await page.screenshot({
          path: testInfo.outputPath(`dashboard-resize-${width}px.png`),
          fullPage: false, // Don't scroll, just capture viewport
        });

        // Check for horizontal overflow
        if (metrics.hasHorizontalScroll) {
          failedChecks.push(
            `HORIZONTAL SCROLL @ ${width}px: Document width ${metrics.documentWidth}px exceeds viewport`
          );
        }

        // Check if content extends beyond viewport
        if (metrics.maxElementRight > metrics.viewportWidth + 1) {
          failedChecks.push(
            `ELEMENT OVERFLOW @ ${width}px: Element extends to ${metrics.maxElementRight}px (viewport: ${metrics.viewportWidth}px)`
          );
        }
      });
    }

    // Analyze layout snapshots for sudden jumps or disappearing content
    for (let i = 1; i < layoutSnapshots.length; i++) {
      const prev = layoutSnapshots[i - 1];
      const curr = layoutSnapshots[i];

      // Check for sudden element count changes (more than 20% difference)
      const elementCountDiff = Math.abs(
        curr.metrics.visibleElementCount - prev.metrics.visibleElementCount
      );
      const elementCountRatio = elementCountDiff / prev.metrics.visibleElementCount;

      if (elementCountRatio > 0.2) {
        failedChecks.push(
          `LAYOUT JUMP @ ${curr.width}px: ${elementCountDiff} elements changed (${Math.round(elementCountRatio * 100)}% difference from ${prev.width}px)`
        );
      }
    }

    // Report results
    console.log("\n📊 Continuous Resize Test Results:");
    console.log(`Tested ${layoutSnapshots.length} viewport widths from ${startWidth}px to ${endWidth}px`);
    
    if (failedChecks.length === 0) {
      console.log("✅ All resize steps passed smoothly!");
    } else {
      console.error("\n❌ Issues Found During Resize:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    // Log sample metrics for debugging
    console.log("\nSample Layout Metrics:");
    [startWidth, 1920, 1280, 1024, 800, endWidth].forEach((w) => {
      const snapshot = layoutSnapshots.find((s) => s.width === w);
      if (snapshot) {
        console.log(
          `  ${w}px: ${snapshot.metrics.visibleElementCount} visible elements, ` +
          `max right: ${snapshot.metrics.maxElementRight}px`
        );
      }
    });

    expect(failedChecks, `Found ${failedChecks.length} issues during continuous resize`).toEqual([]);
  });

  test("job detail page handles continuous resize smoothly", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobId] = await fetchSampleJobIds(1);

    const failedChecks: string[] = [];
    const widths = [2560, 2000, 1600, 1280, 1024, 800, 640];

    for (const width of widths) {
      await withAuthenticatedPage(browser, authState, { width, height: 1440 }, async (page) => {
        await page.goto(`${baseUrl}/jobs/${jobId}`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("סקירה").first()).toBeVisible({ timeout: 30_000 });

        // Wait for animations
        await page.waitForTimeout(300);

        const issues = await page.evaluate(() => {
          const problems: string[] = [];
          const root = document.scrollingElement ?? document.documentElement;

          // Check horizontal overflow
          if (root.scrollWidth > root.clientWidth + 1) {
            problems.push(`Horizontal overflow: ${root.scrollWidth}px > ${root.clientWidth}px`);
          }

          // Check if tabs/sections are visible
          const tabs = document.querySelectorAll('[role="tab"], [role="tablist"]');
          if (tabs.length > 0) {
            tabs.forEach((tab) => {
              const rect = tab.getBoundingClientRect();
              if (rect.right > window.innerWidth + 1) {
                problems.push(`Tab overflow: extends to ${Math.round(rect.right)}px`);
              }
            });
          }

          return problems;
        });

        if (issues.length > 0) {
          failedChecks.push(`ISSUES @ ${width}px: ${issues.join("; ")}`);
        }

        await page.screenshot({
          path: testInfo.outputPath(`job-detail-resize-${width}px.png`),
          fullPage: false,
        });
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n❌ Job Detail Resize Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Job detail page should resize smoothly").toEqual([]);
  });

  test("submit wizard handles continuous resize smoothly", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const failedChecks: string[] = [];
    const widths = [2560, 1920, 1440, 1280, 1024, 800, 640];

    for (const width of widths) {
      await withAuthenticatedPage(browser, authState, { width, height: 1440 }, async (page) => {
        await page.goto(`${baseUrl}/submit`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });

        await page.waitForTimeout(300);

        const issues = await page.evaluate(() => {
          const problems: string[] = [];
          const root = document.scrollingElement ?? document.documentElement;

          if (root.scrollWidth > root.clientWidth + 1) {
            problems.push(`Horizontal overflow: ${root.scrollWidth}px > ${root.clientWidth}px`);
          }

          // Check form fields are visible and not cut off
          const inputs = document.querySelectorAll("input, select, textarea");
          inputs.forEach((input) => {
            const rect = input.getBoundingClientRect();
            if (rect.right > window.innerWidth + 1) {
              const label = (input as HTMLElement).getAttribute("aria-label") || 
                           (input as HTMLElement).getAttribute("name") || 
                           "unknown field";
              problems.push(`Form field overflow: ${label} extends to ${Math.round(rect.right)}px`);
            }
          });

          return problems;
        });

        if (issues.length > 0) {
          failedChecks.push(`ISSUES @ ${width}px: ${issues.join("; ")}`);
        }

        await page.screenshot({
          path: testInfo.outputPath(`submit-wizard-resize-${width}px.png`),
          fullPage: false,
        });
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n❌ Submit Wizard Resize Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Submit wizard should resize smoothly").toEqual([]);
  });
});
