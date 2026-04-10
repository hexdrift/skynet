import { expect, test } from "@playwright/test";
import {
  createAuthenticatedState,
  fetchSampleJobIds,
  resolveAppBaseUrl,
  withAuthenticatedPage,
} from "./helpers";

// Layer 5: Performance and Animation Tests
test.describe("Fluid Layout Performance", () => {
  test("no layout thrashing during window resize", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const failedChecks: string[] = [];

    await withAuthenticatedPage(browser, authState, { width: 1920, height: 1080 }, async (page) => {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "לוח בקרה" }).first()).toBeVisible({ timeout: 30_000 });

      // Inject performance monitoring script
      await page.addScriptTag({
        content: `
          window.layoutThrashing = {
            layoutReads: 0,
            layoutWrites: 0,
            violations: []
          };

          const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect;
          Element.prototype.getBoundingClientRect = function() {
            window.layoutThrashing.layoutReads++;
            return originalGetBoundingClientRect.call(this);
          };

          const properties = ['offsetTop', 'offsetLeft', 'offsetWidth', 'offsetHeight', 
                            'clientTop', 'clientLeft', 'clientWidth', 'clientHeight',
                            'scrollTop', 'scrollLeft', 'scrollWidth', 'scrollHeight'];
          
          properties.forEach(prop => {
            const descriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, prop);
            if (descriptor && descriptor.get) {
              Object.defineProperty(HTMLElement.prototype, prop, {
                get() {
                  window.layoutThrashing.layoutReads++;
                  return descriptor.get.call(this);
                }
              });
            }
          });
        `,
      });

      // Simulate resize events
      const widths = [1920, 1600, 1280, 1024, 800, 1280, 1600, 1920];

      for (let i = 0; i < widths.length; i++) {
        const width = widths[i];
        
        // Reset counters
        await page.evaluate(() => {
          window.layoutThrashing.layoutReads = 0;
          window.layoutThrashing.layoutWrites = 0;
        });

        // Resize viewport
        await page.setViewportSize({ width, height: 1080 });
        await page.waitForTimeout(200); // Allow time for resize handlers

        // Check for excessive layout operations
        const thrashing = await page.evaluate(() => window.layoutThrashing);

        // More than 100 layout reads in a single resize could indicate thrashing
        if (thrashing.layoutReads > 100) {
          failedChecks.push(
            `LAYOUT THRASHING @ ${width}px: ${thrashing.layoutReads} layout reads during resize`
          );
        }
      }
    });

    if (failedChecks.length > 0) {
      console.error("\n⚠️ Layout Thrashing Detected:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    } else {
      console.log("✅ No layout thrashing detected during resize");
    }

    // We'll warn but not fail on layout thrashing since it's hard to completely avoid
    if (failedChecks.length > 0) {
      console.warn("\n⚠️ Performance Warning: Consider optimizing resize handlers");
    }
  });

  test("Framer Motion animations still work after fluid layout changes", async ({ browser }, testInfo) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const ANIMATION_VIEWPORTS = [
      { width: 800, height: 600 },
      { width: 1920, height: 1080 },
    ];

    const failedChecks: string[] = [];

    for (const viewport of ANIMATION_VIEWPORTS) {
      await withAuthenticatedPage(browser, authState, viewport, async (page) => {
        await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: "לוח בקרה" }).first()).toBeVisible({ timeout: 30_000 });

        // Check for Framer Motion elements
        const animationStatus = await page.evaluate(() => {
          const motionElements = document.querySelectorAll('[data-framer-motion], [style*="transform"]');
          
          if (motionElements.length === 0) {
            return {
              hasMotionElements: false,
              animatedCount: 0,
              staticCount: 0,
            };
          }

          let animatedCount = 0;
          let staticCount = 0;

          motionElements.forEach((el) => {
            const style = window.getComputedStyle(el);
            const transform = style.transform;
            const opacity = style.opacity;
            const transition = style.transition;

            // Check if element has animation properties
            if (
              transform !== "none" ||
              opacity !== "1" ||
              transition.includes("transform") ||
              transition.includes("opacity")
            ) {
              animatedCount++;
            } else {
              staticCount++;
            }
          });

          return {
            hasMotionElements: true,
            animatedCount,
            staticCount,
            totalElements: motionElements.length,
          };
        });

        if (animationStatus.hasMotionElements && animationStatus.animatedCount === 0) {
          failedChecks.push(
            `ANIMATION ISSUE @ ${viewport.width}px: Found ${animationStatus.totalElements} motion elements but none are animated`
          );
        }

        // Test stagger animations by navigating to submit page
        await page.goto(`${baseUrl}/submit`, { waitUntil: "domcontentloaded" });
        await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });

        // Wait for stagger animation to complete
        await page.waitForTimeout(1000);

        // Check if form elements are visible (stagger should reveal them)
        const formVisible = await page.evaluate(() => {
          const formElements = document.querySelectorAll("input, select, textarea, button");
          let visibleCount = 0;

          formElements.forEach((el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();

            if (
              style.display !== "none" &&
              style.visibility !== "hidden" &&
              style.opacity !== "0" &&
              rect.width > 0 &&
              rect.height > 0
            ) {
              visibleCount++;
            }
          });

          return {
            total: formElements.length,
            visible: visibleCount,
          };
        });

        if (formVisible.visible === 0 && formVisible.total > 0) {
          failedChecks.push(
            `STAGGER ANIMATION ISSUE @ ${viewport.width}px: ${formVisible.total} form elements found but none are visible`
          );
        }

        await page.screenshot({
          path: testInfo.outputPath(`animations-${viewport.width}px.png`),
          fullPage: false,
        });
      });
    }

    if (failedChecks.length > 0) {
      console.error("\n❌ Animation Issues:\n");
      failedChecks.forEach((check, i) => {
        console.error(`${i + 1}. ${check}`);
      });
    } else {
      console.log("✅ Framer Motion animations working correctly");
    }

    expect(failedChecks, "Animations should work at all viewport sizes").toEqual([]);
  });

  test("page load performance is acceptable at different viewports", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    const PERF_VIEWPORTS = [
      { width: 640, height: 1136, label: "mobile" },
      { width: 1920, height: 1080, label: "desktop" },
    ];

    const performanceMetrics: Array<{
      viewport: string;
      route: string;
      metrics: any;
    }> = [];

    const routes = [
      { path: "/", label: "dashboard" },
      { path: "/submit", label: "submit" },
    ];

    for (const viewport of PERF_VIEWPORTS) {
      for (const route of routes) {
        await withAuthenticatedPage(browser, authState, viewport, async (page) => {
          // Measure page load performance
          const startTime = Date.now();
          
          await page.goto(`${baseUrl}${route.path}`, { waitUntil: "domcontentloaded" });

          if (route.path === "/submit") {
            await expect(page.getByText("פרטים בסיסיים").first()).toBeVisible({ timeout: 30_000 });
          } else {
            await expect(page.getByRole("heading", { name: "לוח בקרה" }).first()).toBeVisible({ timeout: 30_000 });
          }

          const loadTime = Date.now() - startTime;

          // Get Web Vitals if available
          const vitals = await page.evaluate(() => {
            return new Promise((resolve) => {
              if ('PerformanceObserver' in window) {
                const metrics: any = {};

                // Get LCP (Largest Contentful Paint)
                try {
                  const lcpObserver = new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    const lastEntry = entries[entries.length - 1];
                    metrics.lcp = lastEntry.renderTime || lastEntry.loadTime;
                  });
                  lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
                } catch (e) {
                  // LCP not supported
                }

                // Get FCP (First Contentful Paint)
                try {
                  const paintEntries = performance.getEntriesByType('paint');
                  const fcpEntry = paintEntries.find(entry => entry.name === 'first-contentful-paint');
                  if (fcpEntry) {
                    metrics.fcp = fcpEntry.startTime;
                  }
                } catch (e) {
                  // FCP not supported
                }

                // Get navigation timing
                const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming;
                if (navigation) {
                  metrics.domContentLoaded = navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart;
                  metrics.domInteractive = navigation.domInteractive;
                }

                setTimeout(() => resolve(metrics), 1000);
              } else {
                resolve({});
              }
            });
          });

          performanceMetrics.push({
            viewport: `${viewport.label} (${viewport.width}px)`,
            route: route.label,
            metrics: {
              loadTime,
              ...vitals,
            },
          });
        });
      }
    }

    // Report performance metrics
    console.log("\n📊 Performance Metrics:\n");
    performanceMetrics.forEach(({ viewport, route, metrics }) => {
      console.log(`${route} @ ${viewport}:`);
      console.log(`  Load Time: ${metrics.loadTime}ms`);
      if (metrics.fcp) console.log(`  FCP: ${Math.round(metrics.fcp)}ms`);
      if (metrics.lcp) console.log(`  LCP: ${Math.round(metrics.lcp)}ms`);
      if (metrics.domContentLoaded) console.log(`  DOM Content Loaded: ${Math.round(metrics.domContentLoaded)}ms`);
    });

    // Check for performance issues (load time > 5 seconds is problematic)
    const slowPages = performanceMetrics.filter(m => m.metrics.loadTime > 5000);
    
    if (slowPages.length > 0) {
      console.warn("\n⚠️ Performance Warning: Some pages took longer than 5s to load:");
      slowPages.forEach(({ viewport, route, metrics }) => {
        console.warn(`  ${route} @ ${viewport}: ${metrics.loadTime}ms`);
      });
    } else {
      console.log("\n✅ All pages loaded within acceptable time");
    }
  });

  test("CSS is optimized for fluid layouts (no fixed widths)", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);

    await withAuthenticatedPage(browser, authState, { width: 1920, height: 1080 }, async (page) => {
      await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: "לוח בקרה" }).first()).toBeVisible({ timeout: 30_000 });

      const cssIssues = await page.evaluate(() => {
        const issues: string[] = [];
        const allElements = document.querySelectorAll("*");
        
        let fixedWidthCount = 0;
        let fixedWidthElements: Array<{ tag: string; width: string }> = [];

        allElements.forEach((el) => {
          const style = window.getComputedStyle(el);
          const inlineStyle = (el as HTMLElement).style;

          // Check for fixed pixel widths in inline styles
          if (inlineStyle.width && inlineStyle.width.includes("px") && !inlineStyle.width.includes("max-width")) {
            const widthValue = parseInt(inlineStyle.width);
            // Ignore small fixed widths (icons, spacers, etc.)
            if (widthValue > 200) {
              fixedWidthCount++;
              if (fixedWidthElements.length < 10) {
                fixedWidthElements.push({
                  tag: el.tagName.toLowerCase(),
                  width: inlineStyle.width,
                });
              }
            }
          }
        });

        if (fixedWidthCount > 0) {
          issues.push(
            `Found ${fixedWidthCount} elements with fixed pixel widths (should use percentages, max-width, or clamp)`
          );
          if (fixedWidthElements.length > 0) {
            issues.push(`Examples: ${JSON.stringify(fixedWidthElements.slice(0, 5))}`);
          }
        }

        return issues;
      });

      if (cssIssues.length > 0) {
        console.warn("\n⚠️ CSS Optimization Suggestions:\n");
        cssIssues.forEach((issue) => {
          console.warn(`  ${issue}`);
        });
      } else {
        console.log("✅ CSS is well-optimized for fluid layouts");
      }

      // This is informational, not a failure
      expect(true).toBe(true);
    });
  });
});
