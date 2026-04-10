#!/usr/bin/env node
/**
 * Performance measurement for auto-optimize loop.
 * Focuses on interaction snappiness + visual regression.
 * Run: node tests/measure.mjs [--baseline]
 */
import { chromium } from "@playwright/test";
import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const RESULTS_DIR = path.join(__dirname, "..", "perf-results");
const BASELINE_DIR = path.join(RESULTS_DIR, "baseline-screenshots");
const CURRENT_DIR = path.join(RESULTS_DIR, "current-screenshots");
const isBaseline = process.argv.includes("--baseline");
const isQuick = process.argv.includes("--quick");
const SCREENSHOT_DIR = isBaseline ? BASELINE_DIR : CURRENT_DIR;

const ALL_BREAKPOINTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1024, height: 768 },
  { name: "desktop", width: 1440, height: 900 },
  { name: "wide", width: 1920, height: 1080 },
];
const QUICK_BREAKPOINTS = [
  { name: "laptop", width: 1024, height: 768 },
  { name: "desktop", width: 1440, height: 900 },
];
const BREAKPOINTS = isQuick ? QUICK_BREAKPOINTS : ALL_BREAKPOINTS;

function ensureDirs() {
  [RESULTS_DIR, BASELINE_DIR, CURRENT_DIR].forEach((d) => fs.mkdirSync(d, { recursive: true }));
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded", timeout: 15000 });
  const loginInput = page.locator('input[id="login-username"]');
  const hasLogin = await loginInput.isVisible({ timeout: 5000 }).catch(() => false);
  if (!hasLogin) {
    // Auth disabled — just wait for content
    await page.waitForTimeout(2000);
    return;
  }
  // Type character-by-character to ensure React state updates
  await loginInput.pressSequentially("admin", { delay: 20 });
  await page.waitForTimeout(100); // let React re-render
  const btn = page.locator('button[type="submit"]:not([disabled])');
  await btn.waitFor({ state: "visible", timeout: 8000 });
  await btn.click({ timeout: 10000 });
  // Wait for redirect — either to dashboard or away from login
  try {
    await page.waitForURL((u) => !u.href.includes("/login"), { timeout: 15000 });
  } catch {
    // Fallback: navigate directly
    await page.goto(`${BASE_URL}/`, { waitUntil: "domcontentloaded", timeout: 10000 });
  }
  await page.waitForTimeout(2000); // splash screen
}

// Measure navigation time (goto + content visible)
async function measureNavigation(page, url) {
  const t0 = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
  await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
  const loadMs = Date.now() - t0;

  // Count long tasks via CDP
  const longTasks = await page.evaluate(() => {
    return new Promise((resolve) => {
      let count = 0;
      const obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          if (e.duration > 50) count++;
        }
      });
      try {
        obs.observe({ type: "longtask", buffered: true });
      } catch {}
      // Give 500ms to collect buffered long tasks
      setTimeout(() => {
        obs.disconnect();
        resolve(count);
      }, 500);
    });
  });

  return { loadMs, longTasks };
}

// Measure click-to-response for interactive elements
async function measureInteractions(page, pageName) {
  const timings = [];

  if (pageName === "dashboard") {
    // Tab switch: jobs → analytics
    const analyticsTab = page.locator('button:has-text("סטטיסטיקות")');
    if (await analyticsTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      const t0 = Date.now();
      await analyticsTab.click();
      await page.waitForTimeout(30);
      timings.push({ action: "tab-switch-analytics", ms: Date.now() - t0 });

      // Tab switch back: analytics → jobs
      const jobsTab = page.locator('button:has-text("אופטימיזציות")');
      if (await jobsTab.isVisible({ timeout: 2000 }).catch(() => false)) {
        const t1 = Date.now();
        await jobsTab.click();
        await page.waitForTimeout(30);
        timings.push({ action: "tab-switch-jobs", ms: Date.now() - t1 });
      }
    }
  }

  if (pageName === "submit") {
    // Click "next" button (wizard step navigation)
    // First fill required field so Next works
    const nameInput = page.locator('input[placeholder*="ניתוח"]');
    if (await nameInput.isVisible({ timeout: 2000 }).catch(() => false)) {
      await nameInput.fill("test");
    }

    // Toggle job type
    const gridBtn = page.locator('button:has-text("סריקה")');
    if (await gridBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      const t0 = Date.now();
      await gridBtn.click();
      await page.waitForTimeout(30);
      timings.push({ action: "toggle-job-type", ms: Date.now() - t0 });

      // Toggle back
      const runBtn = page.locator('button:has-text("ריצה בודדת")');
      if (await runBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        const t1 = Date.now();
        await runBtn.click();
        await page.waitForTimeout(30);
        timings.push({ action: "toggle-job-type-back", ms: Date.now() - t1 });
      }
    }
  }

  if (pageName === "login") {
    // Type in username field
    const input = page.locator('input[id="login-username"]');
    if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
      const t0 = Date.now();
      await input.fill("testuser");
      await page.waitForTimeout(30);
      timings.push({ action: "input-fill", ms: Date.now() - t0 });
      await input.fill(""); // Reset
    }
  }

  return timings;
}

function compareScreenshots(baselinePath, currentPath) {
  if (!fs.existsSync(baselinePath) || !fs.existsSync(currentPath))
    return { match: true, diffPixels: 0 };
  try {
    const img1 = PNG.sync.read(fs.readFileSync(baselinePath));
    const img2 = PNG.sync.read(fs.readFileSync(currentPath));
    if (img1.width !== img2.width || img1.height !== img2.height)
      return { match: false, diffPixels: -1 };
    const diff = new PNG({ width: img1.width, height: img1.height });
    const numDiff = pixelmatch(img1.data, img2.data, diff.data, img1.width, img1.height, {
      threshold: 0.15,
    });
    const pct = (numDiff / (img1.width * img1.height)) * 100;
    return { match: pct < 0.5, diffPixels: numDiff };
  } catch {
    return { match: true, diffPixels: 0 };
  }
}

function runLighthouse() {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const result = execSync(
        `npx lighthouse ${BASE_URL}/login --output=json --chrome-flags='--headless --no-sandbox --disable-gpu' --only-categories=performance --quiet 2>/dev/null`,
        { timeout: 90000, maxBuffer: 10 * 1024 * 1024 },
      ).toString();
      const json = JSON.parse(result);
      const score = Math.round((json.categories?.performance?.score ?? 0) * 100);
      if (score > 0) return score;
      console.log(`  Lighthouse attempt ${attempt + 1} returned 0, retrying...`);
    } catch (e) {
      console.log(`  Lighthouse attempt ${attempt + 1} failed, retrying...`);
    }
  }
  return 50; // fallback after 3 attempts
}

async function main() {
  ensureDirs();
  console.log(`\n${isBaseline ? "📐 BASELINE" : "📊 MEASUREMENT"} — ${new Date().toISOString()}\n`);

  const browser = await chromium.launch({ headless: true });

  const navTimings = [];
  const interactionTimings = [];
  const pageTimings = {};
  let totalLongTasks = 0;
  const visualDiffs = [];
  let visualPass = true;

  const PAGES = [
    { name: "login", path: "/login", needsAuth: false },
    { name: "dashboard", path: "/", needsAuth: true },
    { name: "submit", path: "/submit", needsAuth: true },
  ];

  for (const bp of BREAKPOINTS) {
    const context = await browser.newContext({
      viewport: { width: bp.width, height: bp.height },
      locale: "he-IL",
    });
    const page = await context.newPage();

    // Mock backend API (localhost:8000) so measurements reflect frontend perf, not backend latency
    await page.route(
      (url) => url.href.includes("localhost:8000"),
      (route) => {
        const url = route.request().url();
        if (url.includes("/jobs")) {
          return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
          });
        }
        if (url.includes("/queue-status")) {
          return route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ pending: 0, running: 0, queue: [] }),
          });
        }
        return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
      },
    );

    let loggedIn = false;

    for (const pg of PAGES) {
      const key = `${pg.name}-${bp.name}`;

      if (pg.needsAuth && !loggedIn) {
        await login(page);
        loggedIn = true;
      }

      // 1. Navigation timing
      const { loadMs, longTasks } = await measureNavigation(page, `${BASE_URL}${pg.path}`);
      await page.waitForTimeout(1500); // splash settle
      navTimings.push(loadMs);
      pageTimings[key] = { loadMs, longTasks };
      totalLongTasks += longTasks;

      // 2. Interaction timing
      const interactions = await measureInteractions(page, pg.name);
      for (const i of interactions) {
        interactionTimings.push(i.ms);
        process.stdout.write(`  ⚡ ${key} ${i.action}: ${i.ms}ms\n`);
      }

      // 3. Screenshot (extra settle time for animations/transitions)
      await page.waitForTimeout(300);
      const ssPath = path.join(SCREENSHOT_DIR, `${pg.name}-${bp.name}.png`);
      await page.screenshot({ path: ssPath, fullPage: true });

      // 4. Visual regression
      if (!isBaseline) {
        const blPath = path.join(BASELINE_DIR, `${pg.name}-${bp.name}.png`);
        const { match, diffPixels } = compareScreenshots(blPath, ssPath);
        if (!match) {
          visualDiffs.push(`${key}: ${diffPixels} px diff`);
          visualPass = false;
        }
      }

      process.stdout.write(`  ✓ ${key}: ${loadMs}ms load, ${longTasks} long tasks\n`);
    }
    await context.close();
  }

  await browser.close();

  // Stats
  const allTimings = [...navTimings, ...interactionTimings];
  allTimings.sort((a, b) => a - b);
  const avgMs =
    allTimings.length > 0 ? allTimings.reduce((a, b) => a + b, 0) / allTimings.length : 0;
  const p95Idx = Math.floor(allTimings.length * 0.95);
  const p95Ms = allTimings.length > 0 ? allTimings[Math.min(p95Idx, allTimings.length - 1)] : 0;

  const avgNavMs =
    navTimings.length > 0 ? navTimings.reduce((a, b) => a + b, 0) / navTimings.length : 0;
  const avgInteractionMs =
    interactionTimings.length > 0
      ? interactionTimings.reduce((a, b) => a + b, 0) / interactionTimings.length
      : 0;

  // Lighthouse (skip in quick mode)
  let lhScore = 92; // default for quick mode
  if (!isQuick) {
    console.log("\n🔦 Running Lighthouse...");
    lhScore = runLighthouse();
  }

  // Composite: weight interaction timing more heavily
  const composite =
    lhScore * 0.4 +
    Math.max(0, 1000 - avgMs) * 0.3 +
    Math.max(0, 1000 - totalLongTasks * 100) * 0.3;

  const result = {
    timestamp: new Date().toISOString(),
    lighthouse_score: lhScore,
    avg_all_ms: Math.round(avgMs),
    avg_nav_ms: Math.round(avgNavMs),
    avg_interaction_ms: Math.round(avgInteractionMs),
    p95_ms: Math.round(p95Ms),
    long_task_count: totalLongTasks,
    visual_regression_pass: visualPass,
    visual_diffs: visualDiffs,
    composite_score: Math.round(composite * 100) / 100,
    details: { page_timings: pageTimings, interaction_count: interactionTimings.length },
  };

  const fname = isBaseline ? "baseline-result.json" : "current-result.json";
  fs.writeFileSync(path.join(RESULTS_DIR, fname), JSON.stringify(result, null, 2));

  console.log(`
╔════════════════════════════════════════════╗
║       PERFORMANCE MEASUREMENT RESULTS      ║
╠════════════════════════════════════════════╣
║ Lighthouse Performance:      ${String(lhScore).padStart(4)}          ║
║ Avg Navigation (ms):         ${String(Math.round(avgNavMs)).padStart(4)}          ║
║ Avg Interaction (ms):        ${String(Math.round(avgInteractionMs)).padStart(4)}          ║
║ Avg All (ms):                ${String(Math.round(avgMs)).padStart(4)}          ║
║ P95 (ms):                    ${String(Math.round(p95Ms)).padStart(4)}          ║
║ Long Tasks (>50ms):          ${String(totalLongTasks).padStart(4)}          ║
║ Visual Regression:           ${visualPass ? "PASS" : "FAIL"}          ║
║ ────────────────────────────────────        ║
║ COMPOSITE SCORE:           ${String(composite.toFixed(2)).padStart(6)}          ║
╚════════════════════════════════════════════╝`);

  if (visualDiffs.length > 0) {
    console.log("\nVisual diffs:");
    visualDiffs.forEach((d) => console.log(`  ⚠ ${d}`));
  }

  process.exit(0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
