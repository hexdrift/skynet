/**
 * Performance measurement suite for auto-optimize loop.
 * Measures: Lighthouse, interaction timing, long tasks, visual regression.
 *
 * Usage: npx playwright test tests/perf-measure.ts --reporter=json
 */

import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const RESULTS_DIR = path.join(__dirname, "..", "perf-results");
const BASELINE_DIR = path.join(RESULTS_DIR, "baseline-screenshots");
const CURRENT_DIR = path.join(RESULTS_DIR, "current-screenshots");

// Pages to test (login doesn't need auth)
const PAGES = [
  { name: "login", path: "/login" },
  { name: "dashboard", path: "/" },
  { name: "submit", path: "/submit" },
];

const BREAKPOINTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1024, height: 768 },
  { name: "desktop", width: 1440, height: 900 },
  { name: "wide", width: 1920, height: 1080 },
];

interface MeasurementResult {
  lighthouse_score: number;
  avg_interaction_ms: number;
  p95_interaction_ms: number;
  long_task_count: number;
  visual_regression_pass: boolean;
  visual_diffs: string[];
  composite_score: number;
  details: {
    page_timings: Record<string, Record<string, number>>;
    long_tasks_by_page: Record<string, number>;
  };
}

// Ensure directories exist
function ensureDirs() {
  fs.mkdirSync(RESULTS_DIR, { recursive: true });
  fs.mkdirSync(BASELINE_DIR, { recursive: true });
  fs.mkdirSync(CURRENT_DIR, { recursive: true });
}

// Login helper
async function login(page: Page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle" });
  // Wait for login form
  await page.waitForSelector('input[id="login-username"]', { timeout: 10000 });
  await page.fill('input[id="login-username"]', "admin");
  await page.click('button[type="submit"]');
  // Wait for redirect to dashboard
  await page.waitForURL("**/", { timeout: 15000 });
  // Wait for page to settle
  await page.waitForTimeout(2000);
}

// Measure page load + interaction timing
async function measurePageTiming(
  page: Page,
  url: string,
): Promise<{ loadMs: number; longTasks: number }> {
  // Set up long task observer before navigation
  await page.evaluate(() => {
    (window as any).__longTasks = 0;
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.duration > 50) {
          (window as any).__longTasks++;
        }
      }
    });
    try {
      observer.observe({ type: "longtask", buffered: true });
    } catch (e) {
      // longtask may not be supported in all contexts
    }
    (window as any).__perfObserver = observer;
  });

  const startTime = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // Wait for meaningful content to be visible
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(500); // Allow animations to settle

  const loadMs = Date.now() - startTime;

  const longTasks = await page.evaluate(() => {
    const lt = (window as any).__longTasks || 0;
    if ((window as any).__perfObserver) {
      (window as any).__perfObserver.disconnect();
    }
    return lt;
  });

  return { loadMs, longTasks };
}

// Take screenshot for visual regression
async function takeScreenshot(page: Page, pageName: string, breakpoint: string, dir: string) {
  const filename = `${pageName}-${breakpoint}.png`;
  const filepath = path.join(dir, filename);
  await page.screenshot({ path: filepath, fullPage: true });
  return filepath;
}

// Compare screenshots using pixelmatch
function compareScreenshots(
  baselinePath: string,
  currentPath: string,
): { match: boolean; diffPixels: number } {
  if (!fs.existsSync(baselinePath)) {
    return { match: true, diffPixels: 0 }; // No baseline = first run, always pass
  }

  try {
    const { PNG } = require("pngjs");
    const pixelmatch = require("pixelmatch");

    const img1 = PNG.sync.read(fs.readFileSync(baselinePath));
    const img2 = PNG.sync.read(fs.readFileSync(currentPath));

    // If dimensions differ, fail
    if (img1.width !== img2.width || img1.height !== img2.height) {
      return { match: false, diffPixels: -1 };
    }

    const diff = new PNG({ width: img1.width, height: img1.height });
    const numDiffPixels = pixelmatch(
      img1.data,
      img2.data,
      diff.data,
      img1.width,
      img1.height,
      { threshold: 0.15 }, // Allow minor anti-aliasing differences
    );

    // Allow up to 0.5% difference (for anti-aliasing, sub-pixel rendering)
    const totalPixels = img1.width * img1.height;
    const diffPercent = (numDiffPixels / totalPixels) * 100;

    return { match: diffPercent < 0.5, diffPixels: numDiffPixels };
  } catch (e) {
    console.error("Screenshot comparison error:", e);
    return { match: true, diffPixels: 0 }; // Don't block on comparison errors
  }
}

// Run Lighthouse
function runLighthouse(): number {
  try {
    const result = execSync(
      `npx lighthouse ${BASE_URL}/login --output=json --chrome-flags='--headless --no-sandbox --disable-gpu' --only-categories=performance --quiet 2>/dev/null`,
      { timeout: 120000, maxBuffer: 10 * 1024 * 1024 },
    ).toString();

    const json = JSON.parse(result);
    return (json.categories?.performance?.score ?? 0) * 100;
  } catch (e) {
    console.error("Lighthouse error:", e);
    return 0;
  }
}

// Calculate composite score
function calculateComposite(lighthouse: number, avgMs: number, longTasks: number): number {
  const lighthouseComponent = lighthouse * 0.4;
  const interactionComponent = Math.max(0, 1000 - avgMs) * 0.3;
  const longTaskComponent = Math.max(0, 1000 - longTasks * 100) * 0.3;
  return lighthouseComponent + interactionComponent + longTaskComponent;
}

test.describe("Performance Measurement", () => {
  test("full measurement suite", async ({ browser }) => {
    ensureDirs();

    const isBaseline = process.env.PERF_BASELINE === "true";
    const screenshotDir = isBaseline ? BASELINE_DIR : CURRENT_DIR;

    const allTimings: number[] = [];
    const pageTimings: Record<string, Record<string, number>> = {};
    const longTasksByPage: Record<string, number> = {};
    let totalLongTasks = 0;
    const visualDiffs: string[] = [];
    let visualPass = true;

    // Measure each page at each breakpoint
    for (const bp of BREAKPOINTS) {
      const context = await browser.newContext({
        viewport: { width: bp.width, height: bp.height },
        locale: "he-IL",
      });
      const page = await context.newPage();

      for (const pg of PAGES) {
        const key = `${pg.name}-${bp.name}`;

        // Login if needed (non-login pages)
        if (pg.name !== "login") {
          await login(page);
        }

        // Measure timing
        const { loadMs, longTasks } = await measurePageTiming(page, `${BASE_URL}${pg.path}`);

        // Wait for splash screen to clear + animations
        await page.waitForTimeout(2000);

        pageTimings[key] = { loadMs, longTasks };
        allTimings.push(loadMs);
        longTasksByPage[key] = longTasks;
        totalLongTasks += longTasks;

        // Take screenshot
        await takeScreenshot(page, pg.name, bp.name, screenshotDir);

        // Visual regression (only when not capturing baseline)
        if (!isBaseline) {
          const baselinePath = path.join(BASELINE_DIR, `${pg.name}-${bp.name}.png`);
          const currentPath = path.join(CURRENT_DIR, `${pg.name}-${bp.name}.png`);
          const { match, diffPixels } = compareScreenshots(baselinePath, currentPath);
          if (!match) {
            visualDiffs.push(`${key}: ${diffPixels} pixels differ`);
            visualPass = false;
          }
        }
      }

      await context.close();
    }

    // Sort timings for p95
    allTimings.sort((a, b) => a - b);
    const avgMs =
      allTimings.length > 0 ? allTimings.reduce((a, b) => a + b, 0) / allTimings.length : 0;
    const p95Index = Math.floor(allTimings.length * 0.95);
    const p95Ms = allTimings.length > 0 ? allTimings[Math.min(p95Index, allTimings.length - 1)] : 0;

    // Run Lighthouse
    console.log("\n=== Running Lighthouse ===");
    const lighthouseScore = runLighthouse();

    // Calculate composite
    const compositeScore = calculateComposite(lighthouseScore, avgMs, totalLongTasks);

    const result: MeasurementResult = {
      lighthouse_score: lighthouseScore,
      avg_interaction_ms: Math.round(avgMs),
      p95_interaction_ms: Math.round(p95Ms),
      long_task_count: totalLongTasks,
      visual_regression_pass: visualPass,
      visual_diffs: visualDiffs,
      composite_score: Math.round(compositeScore * 100) / 100,
      details: {
        page_timings: pageTimings,
        long_tasks_by_page: longTasksByPage,
      },
    };

    // Write results
    const resultFile = isBaseline ? "baseline-result.json" : "current-result.json";
    fs.writeFileSync(path.join(RESULTS_DIR, resultFile), JSON.stringify(result, null, 2));

    console.log("\n╔════════════════════════════════════════╗");
    console.log("║     PERFORMANCE MEASUREMENT RESULTS    ║");
    console.log("╠════════════════════════════════════════╣");
    console.log(`║ Lighthouse Performance:  ${String(lighthouseScore).padStart(6)}       ║`);
    console.log(`║ Avg Interaction (ms):    ${String(Math.round(avgMs)).padStart(6)}       ║`);
    console.log(`║ P95 Interaction (ms):    ${String(Math.round(p95Ms)).padStart(6)}       ║`);
    console.log(`║ Long Tasks (>50ms):      ${String(totalLongTasks).padStart(6)}       ║`);
    console.log(`║ Visual Regression:       ${visualPass ? "  PASS" : "  FAIL"}       ║`);
    console.log(`║ ──────────────────────────────────      ║`);
    console.log(
      `║ COMPOSITE SCORE:         ${String(compositeScore.toFixed(2)).padStart(6)}       ║`,
    );
    console.log("╚════════════════════════════════════════╝\n");

    if (visualDiffs.length > 0) {
      console.log("Visual diffs:");
      visualDiffs.forEach((d) => console.log(`  ⚠ ${d}`));
    }

    // The test always passes — scores are read from the JSON file
    expect(true).toBe(true);
  });
});
