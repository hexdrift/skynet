import { expect, test } from "@playwright/test";
import {
  assertNoHorizontalOverflow,
  createAuthenticatedState,
  fetchSampleJobIds,
  recordConsoleErrors,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

// Layer 1: Visual Regression — Test all viewports from 640px to 2560px
const FLUID_LAYOUT_VIEWPORTS = [
  { width: 640, height: 1136 },
  { width: 800, height: 600 },
  { width: 960, height: 720 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1440 },
] as const;

const ALL_ROUTES = [
  { path: "/", label: "dashboard" },
  { path: "/submit", label: "submit" },
  { path: "/login", label: "login" },
] as const;

test.describe("Fluid Layout Visual Regression", () => {
  test("all pages render without layout issues at all viewport widths", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobA, jobB] = await fetchSampleJobIds(2);

    // Add dynamic routes that require job IDs
    const routes = [
      ...ALL_ROUTES,
      { path: `/jobs/${jobA}`, label: "job-detail" },
      { path: `/compare?jobs=${jobA},${jobB}`, label: "compare" },
    ];

    let failedChecks: string[] = [];

    for (const viewport of FLUID_LAYOUT_VIEWPORTS) {
      for (const route of routes) {
        // Skip login page for authenticated tests
        const needsAuth = route.path !== "/login";

        if (needsAuth) {
          await withAuthenticatedPage(browser, authState, viewport, async (page) => {
            const consoleErrors = recordConsoleErrors(page);

            await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });

            // Wait for route-specific content
            if (route.path === "/submit") {
              await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });
            } else if (route.path.startsWith("/jobs/")) {
              await expect(page.getByText("סקירה")).toBeVisible({ timeout: 30_000 });
            } else if (route.path.startsWith("/compare")) {
              await expect(page.getByText("VS").first()).toBeVisible({ timeout: 30_000 });
            } else {
              await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });
            }

            // Take screenshot
            await page.screenshot({
              path: testInfo.outputPath(`${route.label}-${viewport.width}px.png`),
              fullPage: true,
            });

            // Check for horizontal overflow
            try {
              await assertNoHorizontalOverflow(page, `${route.label} @ ${viewport.width}px`);
            } catch (error) {
              failedChecks.push(`OVERFLOW: ${route.label} @ ${viewport.width}px - ${error instanceof Error ? error.message : String(error)}`);
            }

            // Check for console errors
            if (consoleErrors.length > 0) {
              failedChecks.push(`CONSOLE ERRORS: ${route.label} @ ${viewport.width}px - ${consoleErrors.join(", ")}`);
            }

            // Check for layout issues
            const layoutIssues = await page.evaluate(() => {
              const issues: string[] = [];
              
              // Check for elements that overflow viewport
              const allElements = document.querySelectorAll("*");
              allElements.forEach((el) => {
                const rect = el.getBoundingClientRect();
                const computedStyle = window.getComputedStyle(el);
                
                // Skip hidden elements
                if (computedStyle.display === "none" || computedStyle.visibility === "hidden") {
                  return;
                }
                
                // Check if element extends beyond viewport width
                if (rect.right > window.innerWidth + 1) {
                  const tag = el.tagName.toLowerCase();
                  const classList = el.className;
                  issues.push(`Element overflow: ${tag}.${classList} extends to ${Math.round(rect.right)}px (viewport: ${window.innerWidth}px)`);
                }
              });
              
              return issues.slice(0, 5); // Limit to first 5 issues
            });

            if (layoutIssues.length > 0) {
              failedChecks.push(`LAYOUT ISSUES: ${route.label} @ ${viewport.width}px - ${layoutIssues.join("; ")}`);
            }
          });
        } else {
          // Login page - no auth needed
          const context = await browser.newContext({ viewport });
          const page = await context.newPage();
          
          try {
            const consoleErrors = recordConsoleErrors(page);
            
            await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });
            await expect(page.getByLabel("שם משתמש").first()).toBeVisible({ timeout: 30_000 });
            
            await page.screenshot({
              path: testInfo.outputPath(`${route.label}-${viewport.width}px.png`),
              fullPage: true,
            });
            
            try {
              await assertNoHorizontalOverflow(page, `${route.label} @ ${viewport.width}px`);
            } catch (error) {
              failedChecks.push(`OVERFLOW: ${route.label} @ ${viewport.width}px - ${error instanceof Error ? error.message : String(error)}`);
            }
            
            if (consoleErrors.length > 0) {
              failedChecks.push(`CONSOLE ERRORS: ${route.label} @ ${viewport.width}px - ${consoleErrors.join(", ")}`);
            }
          } finally {
            await context.close();
          }
        }
      }
    }

    // Report all failures at the end
    if (failedChecks.length > 0) {
      console.error("\n❌ Layout Issues Found:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, `Found ${failedChecks.length} layout issues`).toEqual([]);
  });

  test("sidebar doesn't overlap content at any width", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const failedChecks: string[] = [];

    for (const viewport of FLUID_LAYOUT_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });

        const overlaps = await page.evaluate(() => {
          const sidebar = document.querySelector('[class*="sidebar"]') || 
                         document.querySelector('nav') ||
                         document.querySelector('[role="navigation"]');
          const mainContent = document.querySelector('main');

          if (!sidebar || !mainContent) {
            return null;
          }

          const sidebarRect = sidebar.getBoundingClientRect();
          const mainRect = mainContent.getBoundingClientRect();

          // Check for overlap (accounting for RTL layout)
          const hasOverlap = !(
            sidebarRect.left >= mainRect.right ||
            sidebarRect.right <= mainRect.left
          );

          return hasOverlap ? {
            sidebarLeft: sidebarRect.left,
            sidebarRight: sidebarRect.right,
            mainLeft: mainRect.left,
            mainRight: mainRect.right,
          } : null;
        });

        if (overlaps) {
          failedChecks.push(`SIDEBAR OVERLAP @ ${viewport.width}px: ${JSON.stringify(overlaps)}`);
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n❌ Sidebar Overlap Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Sidebar should not overlap content").toEqual([]);
  });

  test("tables have horizontal scroll within container, not page-wide", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobId] = await fetchSampleJobIds(1);

    const failedChecks: string[] = [];

    // Test at smaller viewports where tables would overflow
    const narrowViewports = FLUID_LAYOUT_VIEWPORTS.filter(v => v.width <= 1024);

    for (const viewport of narrowViewports) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/jobs/${jobId}`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("סקירה")).toBeVisible({ timeout: 30_000 });

        const tableScrollIssue = await page.evaluate(() => {
          const tables = document.querySelectorAll("table");
          const issues: Array<{ hasContainer: boolean; containerOverflows: boolean }> = [];

          tables.forEach((table) => {
            const tableRect = table.getBoundingClientRect();
            const parent = table.parentElement;
            
            if (!parent) return;
            
            const parentStyle = window.getComputedStyle(parent);
            const hasScrollContainer = parentStyle.overflowX === "auto" || parentStyle.overflowX === "scroll";
            
            // Check if table is wider than viewport
            const tableOverflowsViewport = tableRect.width > window.innerWidth;
            
            issues.push({
              hasContainer: hasScrollContainer,
              containerOverflows: tableOverflowsViewport && !hasScrollContainer,
            });
          });

          return issues;
        });

        const problematicTables = tableScrollIssue.filter(t => t.containerOverflows);
        if (problematicTables.length > 0) {
          failedChecks.push(`TABLE SCROLL ISSUE @ ${viewport.width}px: ${problematicTables.length} table(s) overflow without scroll container`);
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Table Scroll Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Tables should have horizontal scroll containers").toEqual([]);
  });

  test("modals and dialogs don't overflow viewport", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const failedChecks: string[] = [];

    for (const viewport of FLUID_LAYOUT_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/submit`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });

        // Check if any visible modals/dialogs overflow
        const modalOverflow = await page.evaluate(() => {
          const modals = document.querySelectorAll('[role="dialog"], .modal, [class*="dialog"]');
          const issues: string[] = [];

          modals.forEach((modal) => {
            const rect = modal.getBoundingClientRect();
            const computedStyle = window.getComputedStyle(modal);

            // Skip hidden modals
            if (computedStyle.display === "none" || computedStyle.visibility === "hidden") {
              return;
            }

            if (rect.width > window.innerWidth || rect.height > window.innerHeight) {
              issues.push(`Modal overflow: ${rect.width}x${rect.height} > ${window.innerWidth}x${window.innerHeight}`);
            }
          });

          return issues;
        });

        if (modalOverflow.length > 0) {
          failedChecks.push(`MODAL OVERFLOW @ ${viewport.width}px: ${modalOverflow.join("; ")}`);
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Modal Overflow Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Modals should not overflow viewport").toEqual([]);
  });

  test("code editor fills parent width correctly", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const [jobId] = await fetchSampleJobIds(1);

    const failedChecks: string[] = [];

    for (const viewport of FLUID_LAYOUT_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/jobs/${jobId}`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("סקירה")).toBeVisible({ timeout: 30_000 });

        // Look for CodeMirror editor
        const editorIssue = await page.evaluate(() => {
          const editors = document.querySelectorAll('.cm-editor, [class*="codemirror"]');
          const issues: string[] = [];

          editors.forEach((editor) => {
            const editorRect = editor.getBoundingClientRect();
            const parent = editor.parentElement;
            
            if (!parent) return;
            
            const parentRect = parent.getBoundingClientRect();
            
            // Check if editor is significantly wider than parent (more than 10px)
            if (editorRect.width > parentRect.width + 10) {
              issues.push(`Editor overflow: ${Math.round(editorRect.width)}px > parent ${Math.round(parentRect.width)}px`);
            }
            
            // Check if editor extends beyond viewport
            if (editorRect.right > window.innerWidth + 1) {
              issues.push(`Editor extends beyond viewport: ${Math.round(editorRect.right)}px > ${window.innerWidth}px`);
            }
          });

          return issues;
        });

        if (editorIssue.length > 0) {
          failedChecks.push(`CODE EDITOR ISSUE @ ${viewport.width}px: ${editorIssue.join("; ")}`);
        }
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Code Editor Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    }

    expect(failedChecks, "Code editor should fill parent width correctly").toEqual([]);
  });
});
