import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import {
  createAuthenticatedState,
  fetchSampleJobIds,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

// Layer 2: Accessibility checks at 800px and 1920px
const A11Y_VIEWPORTS = [
  { width: 800, height: 600, label: "narrow" },
  { width: 1920, height: 1080, label: "wide" },
] as const;

test.describe("Fluid Layout Accessibility", () => {
  test("all pages pass axe-core checks at narrow and wide viewports", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobA, jobB] = await fetchSampleJobIds(2);

    const routes = [
      { path: "/", label: "dashboard" },
      { path: "/submit", label: "submit" },
      { path: `/jobs/${jobA}`, label: "job-detail" },
      { path: `/compare?jobs=${jobA},${jobB}`, label: "compare" },
    ];

    const allViolations: Array<{ route: string; viewport: string; violations: any[] }> = [];

    for (const viewport of A11Y_VIEWPORTS) {
      for (const route of routes) {
        await withAuthenticatedPage(browser, authState, viewport, async (page) => {
          await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });

          // Wait for route-specific content
          if (route.path === "/submit") {
            await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });
          } else if (route.path.startsWith("/jobs/")) {
            await expect(page.getByText("סקירה").first()).toBeVisible({ timeout: 30_000 });
          } else if (route.path.startsWith("/compare")) {
            await expect(page.getByText("VS").first()).toBeVisible({ timeout: 30_000 });
          } else {
            await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });
          }

          // Run axe-core accessibility scan
          const accessibilityScanResults = await new AxeBuilder({ page })
            .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
            .analyze();

          if (accessibilityScanResults.violations.length > 0) {
            allViolations.push({
              route: route.label,
              viewport: `${viewport.label} (${viewport.width}px)`,
              violations: accessibilityScanResults.violations,
            });
          }

          // Take screenshot for reference
          await page.screenshot({
            path: testInfo.outputPath(`a11y-${route.label}-${viewport.label}.png`),
            fullPage: false,
          });
        });
      }
    }

    // Report all violations
    if (allViolations.length > 0) {
      console.error("\n❌ Accessibility Violations Found:\n");
      allViolations.forEach(({ route, viewport, violations }) => {
        console.error(`\n${route} @ ${viewport}:`);
        violations.forEach((violation) => {
          console.error(`  ⚠️  ${violation.id}: ${violation.description}`);
          console.error(`      Impact: ${violation.impact}`);
          console.error(`      Affected elements: ${violation.nodes.length}`);
          violation.nodes.slice(0, 3).forEach((node: any) => {
            console.error(`        - ${node.html.substring(0, 100)}...`);
          });
        });
      });

      const totalViolations = allViolations.reduce((sum, item) => sum + item.violations.length, 0);
      expect(totalViolations, `Found ${totalViolations} accessibility violations`).toBe(0);
    } else {
      console.log("✅ All accessibility checks passed!");
    }
  });

  test("interactive elements meet minimum touch target size at all viewports", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const TOUCH_TARGET_VIEWPORTS = [
      { width: 640, height: 1136 },
      { width: 800, height: 600 },
      { width: 1024, height: 768 },
      { width: 1920, height: 1080 },
    ];

    const failedChecks: string[] = [];

    for (const viewport of TOUCH_TARGET_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });

        const tooSmall = await page.evaluate(() => {
          const MIN_SIZE = 44; // WCAG 2.1 Level AAA minimum touch target size
          const selector = [
            "button",
            "a[href]",
            "input:not([type='hidden'])",
            "select",
            "textarea",
            "[role='button']",
            "[role='link']",
            "[role='tab']",
            "[tabindex='0']",
          ].join(",");

          const elements = Array.from(document.querySelectorAll(selector));
          const small: Array<{ tag: string; text: string; size: string }> = [];

          elements.forEach((el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);

            // Skip hidden elements
            if (
              style.display === "none" ||
              style.visibility === "hidden" ||
              rect.width === 0 ||
              rect.height === 0
            ) {
              return;
            }

            // Check if in viewport
            if (
              rect.bottom > 0 &&
              rect.top < window.innerHeight &&
              rect.right > 0 &&
              rect.left < window.innerWidth
            ) {
              if (rect.width < MIN_SIZE || rect.height < MIN_SIZE) {
                small.push({
                  tag: el.tagName.toLowerCase(),
                  text: (el.textContent || "").trim().substring(0, 30),
                  size: `${Math.round(rect.width)}×${Math.round(rect.height)}px`,
                });
              }
            }
          });

          return small.slice(0, 10); // Limit to first 10
        });

        if (tooSmall.length > 0) {
          failedChecks.push(
            `SMALL TOUCH TARGETS @ ${viewport.width}px: Found ${tooSmall.length} elements smaller than 44px\n` +
            tooSmall.map(t => `  - ${t.tag} "${t.text}" (${t.size})`).join("\n")
          );
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Touch Target Issues:\n");
      failedChecks.forEach((check) => {
        console.error(check);
      });
    }

    expect(failedChecks, "All interactive elements should meet minimum touch target size").toEqual([]);
  });

  test("keyboard navigation works at all viewport sizes", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const KEYBOARD_NAV_VIEWPORTS = [
      { width: 800, height: 600 },
      { width: 1920, height: 1080 },
    ];

    const failedChecks: string[] = [];

    for (const viewport of KEYBOARD_NAV_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });

        // Tab through interactive elements
        const tabCount = 10;
        const focusedElements: Array<{ tag: string; visible: boolean }> = [];

        for (let i = 0; i < tabCount; i++) {
          await page.keyboard.press("Tab");
          await page.waitForTimeout(100);

          const focusInfo = await page.evaluate(() => {
            const focused = document.activeElement;
            if (!focused) return null;

            const rect = focused.getBoundingClientRect();
            const style = window.getComputedStyle(focused);
            
            // Check if focus outline is visible
            const hasVisibleOutline = 
              style.outline !== "none" && 
              style.outline !== "" ||
              style.boxShadow.includes("focus") ||
              focused.classList.toString().includes("focus");

            return {
              tag: focused.tagName.toLowerCase(),
              visible: rect.width > 0 && rect.height > 0,
              inViewport: 
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= window.innerHeight &&
                rect.right <= window.innerWidth,
              hasOutline: hasVisibleOutline,
            };
          });

          if (focusInfo) {
            focusedElements.push({
              tag: focusInfo.tag,
              visible: focusInfo.visible && focusInfo.inViewport,
            });

            // Check if focused element has visible focus indicator
            if (!focusInfo.hasOutline && focusInfo.visible) {
              failedChecks.push(
                `NO FOCUS INDICATOR @ ${viewport.width}px: ${focusInfo.tag} element lacks visible focus outline`
              );
            }
          }
        }

        // Verify we could tab to interactive elements
        const interactiveElements = focusedElements.filter(
          (el) => ["button", "a", "input", "select", "textarea"].includes(el.tag)
        );

        if (interactiveElements.length === 0) {
          failedChecks.push(
            `KEYBOARD NAV ISSUE @ ${viewport.width}px: Could not tab to any interactive elements`
          );
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Keyboard Navigation Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Keyboard navigation should work at all viewport sizes").toEqual([]);
  });

  test("RTL layout is correct at all widths", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const RTL_VIEWPORTS = [
      { width: 640, height: 1136 },
      { width: 1024, height: 768 },
      { width: 1920, height: 1080 },
    ];

    const failedChecks: string[] = [];

    for (const viewport of RTL_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });

        const rtlIssues = await page.evaluate(() => {
          const issues: string[] = [];

          // Check document direction
          const htmlDir = document.documentElement.dir;
          if (htmlDir !== "rtl") {
            issues.push(`Document direction is "${htmlDir}", expected "rtl"`);
          }

          // Check for elements using physical properties instead of logical
          const allElements = document.querySelectorAll("*");
          let physicalPropsCount = 0;

          allElements.forEach((el) => {
            const style = window.getComputedStyle(el);
            const inlineStyle = (el as HTMLElement).style;

            // Check for physical properties in inline styles (more problematic)
            const inlineStyleText = inlineStyle.cssText;
            if (
              inlineStyleText.includes("margin-left") ||
              inlineStyleText.includes("margin-right") ||
              inlineStyleText.includes("padding-left") ||
              inlineStyleText.includes("padding-right") ||
              inlineStyleText.includes("border-left") ||
              inlineStyleText.includes("border-right") ||
              inlineStyleText.includes("left:") ||
              inlineStyleText.includes("right:")
            ) {
              physicalPropsCount++;
            }
          });

          if (physicalPropsCount > 10) {
            issues.push(
              `Found ${physicalPropsCount} elements with physical directional properties (should use logical properties)`
            );
          }

          // Check text alignment
          const headings = document.querySelectorAll("h1, h2, h3, h4, h5, h6");
          headings.forEach((heading) => {
            const style = window.getComputedStyle(heading);
            if (style.textAlign === "left") {
              issues.push(`Heading uses text-align: left instead of text-align: start`);
            }
          });

          return issues;
        });

        if (rtlIssues.length > 0) {
          failedChecks.push(`RTL ISSUES @ ${viewport.width}px:\n  ${rtlIssues.join("\n  ")}`);
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ RTL Layout Issues:\n");
      failedChecks.forEach((check) => {
        console.error(check);
      });
    }

    expect(failedChecks, "RTL layout should be correct at all widths").toEqual([]);
  });
});
