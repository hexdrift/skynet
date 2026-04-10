#!/usr/bin/env node
/**
 * App responsiveness test — exercises real user flows and measures
 * click-to-visible latency, navigation speed, and API response times.
 *
 * Run: node tests/responsiveness.mjs
 */
import { chromium } from "@playwright/test";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
const API  = process.env.API_URL ?? "http://localhost:8000";
const RESULTS_DIR = path.join(__dirname, "..", "perf-results");
fs.mkdirSync(RESULTS_DIR, { recursive: true });

// ─── Helpers ────────────────────────────────────────────────────────────────

async function time(label, fn) {
  const t0 = Date.now();
  await fn();
  const ms = Date.now() - t0;
  return { label, ms };
}

async function waitFor(page, sel, timeout = 5000) {
  await page.waitForSelector(sel, { state: "visible", timeout });
}

// ─── Login ──────────────────────────────────────────────────────────────────

async function login(page) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.waitForSelector('input[id="login-username"]', { timeout: 10000 });
  await page.fill('input[id="login-username"]', "admin");
  await page.click('button[type="submit"]');
  await page.waitForURL("**/", { timeout: 15000 });
  await page.waitForTimeout(2000); // splash
}

// ─── API latency ────────────────────────────────────────────────────────────

async function measureApiLatency() {
  const results = [];

  const endpoints = [
    { label: "GET /health", url: `${API}/health` },
    { label: "GET /models", url: `${API}/models` },
    { label: "GET /queue", url: `${API}/queue` },
    { label: "GET /jobs?limit=20", url: `${API}/jobs?limit=20` },
    { label: "GET /jobs?limit=200", url: `${API}/jobs?limit=200` },
    { label: "GET /jobs/sidebar?limit=20", url: `${API}/jobs/sidebar?limit=20` },
  ];

  for (const ep of endpoints) {
    // Cold request
    const t0 = Date.now();
    const res = await fetch(ep.url);
    const coldMs = Date.now() - t0;
    const bodySize = (await res.text()).length;

    // Warm request (should benefit from any server-side caching)
    const t1 = Date.now();
    await fetch(ep.url);
    const warmMs = Date.now() - t1;

    results.push({
      label: ep.label,
      cold_ms: coldMs,
      warm_ms: warmMs,
      body_bytes: bodySize,
    });
  }

  return results;
}

// ─── Page load tests ────────────────────────────────────────────────────────

async function measurePageLoads(browser) {
  const results = [];

  // 1. Login page cold load
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const r = await time("Login page cold load", async () => {
      await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
      await page.waitForSelector('input[id="login-username"]', { timeout: 10000 });
    });
    results.push(r);
    await ctx.close();
  }

  // 2. Login → Dashboard navigation (includes auth + redirect + splash)
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const page = await ctx.newPage();
    const r = await time("Login → Dashboard (full auth flow)", async () => {
      await login(page);
    });
    results.push(r);

    // 3. Dashboard → Submit navigation (use sidebar link with force)
    {
      const r2 = await time("Dashboard → Submit (client nav)", async () => {
        await page.locator('aside a[href="/submit"]').first().click({ force: true });
        await page.waitForSelector('input[placeholder*="ניתוח"]', { timeout: 5000 });
      });
      results.push(r2);
    }

    // 4. Submit → Dashboard navigation
    {
      const r3 = await time("Submit → Dashboard (client nav)", async () => {
        await page.locator('aside a[href="/"]').first().click({ force: true });
        await page.waitForLoadState("networkidle").catch(() => {});
      });
      results.push(r3);
    }

    await ctx.close();
  }

  return results;
}

// ─── Interaction tests ──────────────────────────────────────────────────────

async function measureInteractions(browser) {
  const results = [];

  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "he-IL" });
  const page = await ctx.newPage();
  await login(page);

  // ── Dashboard interactions ──
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);

  // Tab switch: jobs → analytics
  {
    const tab = page.locator('button:has-text("סטטיסטיקות")');
    if (await tab.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Dashboard: tab → analytics", async () => {
        await tab.click();
        await page.waitForTimeout(50);
      });
      results.push(r);
    }
  }

  // Tab switch: analytics → jobs
  {
    const tab = page.locator('button:has-text("אופטימיזציות")');
    if (await tab.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Dashboard: tab → jobs", async () => {
        await tab.click();
        await page.waitForTimeout(50);
      });
      results.push(r);
    }
  }

  // Compare mode toggle
  {
    const btn = page.locator('button[aria-label="השוואה"]');
    if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
      const r = await time("Dashboard: compare toggle ON", async () => {
        await btn.click();
        await page.waitForTimeout(50);
      });
      results.push(r);

      // Cancel compare
      const cancel = page.locator('button:has-text("ביטול")');
      if (await cancel.isVisible({ timeout: 1000 }).catch(() => false)) {
        const r2 = await time("Dashboard: compare toggle OFF", async () => {
          await cancel.click();
          await page.waitForTimeout(50);
        });
        results.push(r2);
      }
    }
  }

  // Click first table row (navigate to job detail)
  {
    const firstRow = page.locator('table tbody tr').first();
    if (await firstRow.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Dashboard: click job row → detail page", async () => {
        await firstRow.click();
        await page.waitForSelector('[data-slot="card"]', { timeout: 8000 });
      });
      results.push(r);

      // Back to dashboard
      const backLink = page.locator('a[href="/"]').first();
      if (await backLink.isVisible({ timeout: 2000 }).catch(() => false)) {
        const r2 = await time("Job detail: back → dashboard", async () => {
          await backLink.click({ force: true });
          await page.waitForLoadState("networkidle").catch(() => {});
        });
        results.push(r2);
      }
    }
  }

  // ── Submit page interactions ──
  await page.goto(`${BASE}/submit`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);

  // Fill job name
  {
    const input = page.locator('input[placeholder*="ניתוח"]');
    if (await input.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Submit: fill job name", async () => {
        await input.fill("test optimization");
        await page.waitForTimeout(30);
      });
      results.push(r);
    }
  }

  // Toggle job type: run → grid
  {
    const gridBtn = page.locator('button:has-text("סריקה")');
    if (await gridBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Submit: toggle job type → grid", async () => {
        await gridBtn.click();
        await page.waitForTimeout(50);
      });
      results.push(r);
    }
  }

  // Toggle job type: grid → run
  {
    const runBtn = page.locator('button:has-text("ריצה בודדת")');
    if (await runBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Submit: toggle job type → run", async () => {
        await runBtn.click();
        await page.waitForTimeout(50);
      });
      results.push(r);
    }
  }

  // Click Next button (wizard step)
  {
    const nextBtn = page.locator('button:has-text("הבא")');
    if (await nextBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Submit: wizard Next click", async () => {
        await nextBtn.click();
        await page.waitForTimeout(100);
      });
      results.push(r);
    }
  }

  // ── Sidebar interactions ──
  // Click sidebar nav items
  {
    const submitNav = page.locator('aside a[href="/submit"]').first();
    if (await submitNav.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Sidebar: click Submit nav", async () => {
        await submitNav.click({ force: true });
        await page.waitForSelector('input[placeholder*="ניתוח"]', { timeout: 5000 });
      });
      results.push(r);
    }

    const dashNav = page.locator('aside a[href="/"]').first();
    if (await dashNav.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r2 = await time("Sidebar: click Dashboard nav", async () => {
        await dashNav.click({ force: true });
        await page.waitForLoadState("networkidle").catch(() => {});
      });
      results.push(r2);
    }
  }

  // ── Sidebar search ──
  {
    const search = page.locator('aside input[placeholder="חיפוש..."]');
    if (await search.isVisible({ timeout: 2000 }).catch(() => false)) {
      const r = await time("Sidebar: type search query", async () => {
        await search.fill("test");
        await page.waitForTimeout(50);
      });
      results.push(r);

      const r2 = await time("Sidebar: clear search", async () => {
        await search.fill("");
        await page.waitForTimeout(50);
      });
      results.push(r2);
    }
  }

  // ── Sidebar collapse/expand ──
  {
    const collapseBtn = page.locator('aside button[aria-label="כווץ סרגל צד"]');
    if (await collapseBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      const r = await time("Sidebar: collapse (incl 300ms anim)", async () => {
        await collapseBtn.click();
        await page.waitForTimeout(300); // sidebar CSS transition
      });
      results.push(r);

      const expandBtn = page.locator('aside button[aria-label="פתח סרגל צד"]');
      if (await expandBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
        const r2 = await time("Sidebar: expand (incl 300ms anim)", async () => {
          await expandBtn.click();
          await page.waitForTimeout(300);
        });
        results.push(r2);
      }
    }
  }

  await ctx.close();
  return results;
}

// ─── Cache effectiveness ────────────────────────────────────────────────────

async function measureCacheEffectiveness(browser) {
  const results = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await login(page);

  // Measure network requests on dashboard load
  const requests1 = [];
  page.on("request", (req) => {
    if (req.url().includes(":8000/")) requests1.push({ url: req.url(), method: req.method() });
  });
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);

  // Navigate away and back — check if cached
  const requests2 = [];
  page.removeAllListeners("request");
  page.on("request", (req) => {
    if (req.url().includes(":8000/")) requests2.push({ url: req.url(), method: req.method() });
  });
  await page.goto(`${BASE}/submit`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.goto(`${BASE}/`, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);

  results.push({
    label: "Dashboard first load API requests",
    value: requests1.length,
    detail: requests1.map(r => `${r.method} ${new URL(r.url).pathname}`).join(", "),
  });
  results.push({
    label: "Dashboard revisit API requests",
    value: requests2.length,
    detail: requests2.map(r => `${r.method} ${new URL(r.url).pathname}`).join(", "),
  });

  await ctx.close();
  return results;
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("\n🧪 SKYNET RESPONSIVENESS TEST");
  console.log("═".repeat(60));
  console.log(`Frontend: ${BASE}`);
  console.log(`Backend:  ${API}`);
  console.log(`Time:     ${new Date().toISOString()}\n`);

  // 1. API latency
  console.log("📡 API Latency (direct backend calls)");
  console.log("─".repeat(55));
  const apiResults = await measureApiLatency();
  for (const r of apiResults) {
    const size = r.body_bytes > 1024 ? `${(r.body_bytes / 1024).toFixed(1)}KB` : `${r.body_bytes}B`;
    console.log(`  ${r.label.padEnd(30)} cold: ${String(r.cold_ms).padStart(4)}ms  warm: ${String(r.warm_ms).padStart(4)}ms  (${size})`);
  }

  // 2. Page loads
  console.log("\n📄 Page Load Times");
  console.log("─".repeat(55));
  const browser = await chromium.launch({ headless: true });
  const pageResults = await measurePageLoads(browser);
  for (const r of pageResults) {
    const emoji = r.ms < 300 ? "🟢" : r.ms < 1000 ? "🟡" : "🔴";
    console.log(`  ${emoji} ${r.label.padEnd(42)} ${String(r.ms).padStart(5)}ms`);
  }

  // 3. Interactions
  console.log("\n⚡ Interaction Latency (click-to-response)");
  console.log("─".repeat(55));
  const interactionResults = await measureInteractions(browser);
  for (const r of interactionResults) {
    const emoji = r.ms < 100 ? "🟢" : r.ms < 200 ? "🟡" : "🔴";
    console.log(`  ${emoji} ${r.label.padEnd(42)} ${String(r.ms).padStart(5)}ms`);
  }

  // 4. Cache effectiveness
  console.log("\n🗄️  Cache Effectiveness");
  console.log("─".repeat(55));
  const cacheResults = await measureCacheEffectiveness(browser);
  for (const r of cacheResults) {
    console.log(`  ${r.label}: ${r.value} requests`);
    if (r.detail) console.log(`    → ${r.detail}`);
  }

  await browser.close();

  // Summary
  const allTimings = [...pageResults, ...interactionResults].map(r => r.ms);
  const avg = Math.round(allTimings.reduce((a, b) => a + b, 0) / allTimings.length);
  const max = Math.max(...allTimings);
  const min = Math.min(...allTimings);
  const p95 = allTimings.sort((a, b) => a - b)[Math.floor(allTimings.length * 0.95)];
  const slowCount = allTimings.filter(t => t > 200).length;

  console.log("\n" + "═".repeat(60));
  console.log("📊 SUMMARY");
  console.log("─".repeat(55));
  console.log(`  Total interactions measured:  ${allTimings.length}`);
  console.log(`  Average latency:             ${avg}ms`);
  console.log(`  P95 latency:                 ${p95}ms`);
  console.log(`  Min / Max:                   ${min}ms / ${max}ms`);
  console.log(`  Interactions > 200ms:         ${slowCount} (${((slowCount/allTimings.length)*100).toFixed(0)}%)`);
  console.log(`  API calls on dashboard:      ${apiResults.find(r => r.label.includes("sidebar"))?.warm_ms ?? "?"}ms (sidebar)`);
  console.log("═".repeat(60) + "\n");

  // Write results
  const output = {
    timestamp: new Date().toISOString(),
    api: apiResults,
    pages: pageResults,
    interactions: interactionResults,
    cache: cacheResults,
    summary: { avg, p95, min, max, slow_count: slowCount, total: allTimings.length },
  };
  fs.writeFileSync(path.join(RESULTS_DIR, "responsiveness.json"), JSON.stringify(output, null, 2));

  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
