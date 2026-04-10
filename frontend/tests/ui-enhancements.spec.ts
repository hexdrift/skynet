import {
  expect,
  test,
  type Browser,
  type BrowserContext,
  type Page,
  type StorageState,
  type ViewportSize,
} from "@playwright/test";

import { assertNoHorizontalOverflow, createAuthenticatedState, resolveAppBaseUrl } from "./helpers";

const DESKTOP_VIEWPORT = { width: 1280, height: 900 } as const;
const MOBILE_VIEWPORT = { width: 375, height: 844 } as const;

const DASHBOARD_QUEUE = {
  pending_jobs: 0,
  active_jobs: 0,
  worker_threads: 1,
  workers_alive: true,
};

const STATUS_JOBS = [
  {
    job_id: "job-success",
    job_type: "run",
    status: "success",
    created_at: "2025-01-01T12:00:00.000Z",
    elapsed_seconds: 65,
    module_name: "OptimizerModule",
    optimizer_name: "MIPROv2",
    dataset_rows: 10,
    username: "admin",
  },
  {
    job_id: "job-running",
    job_type: "grid_search",
    status: "running",
    created_at: "2025-01-01T12:05:00.000Z",
    elapsed_seconds: 12,
    module_name: "OptimizerModule",
    optimizer_name: "GEPA",
    dataset_rows: 22,
    username: "admin",
  },
  {
    job_id: "job-failed",
    job_type: "run",
    status: "failed",
    created_at: "2025-01-01T12:10:00.000Z",
    elapsed_seconds: 8,
    module_name: "OptimizerModule",
    optimizer_name: "MIPROv2",
    dataset_rows: 5,
    username: "admin",
  },
] as const;

async function openDashboardWithMocks(
  browser: Browser,
  viewport: ViewportSize,
  jobs: ReadonlyArray<Record<string, unknown>>,
  authState: StorageState,
  baseUrl: string,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ storageState: authState, viewport });
  const page = await context.newPage();

  await page.route(/\/jobs(?:\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: jobs,
        total: jobs.length,
        limit: 200,
        offset: 0,
      }),
    });
  });

  await page.route(/\/queue$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(DASHBOARD_QUEUE),
    });
  });

  await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });

  return { context, page };
}

/* ── Login page tests (no auth needed) ── */

test.describe("Login page enhancements", () => {
  let baseUrl: string;

  test.beforeAll(async () => {
    baseUrl = await resolveAppBaseUrl();
  });

  test("particle canvas is decorative and non-interactive", async ({ page }) => {
    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("שם משתמש")).toBeVisible();

    const particleCanvas = page.locator('canvas[aria-hidden="true"]').first();
    await expect(particleCanvas).toBeVisible();

    const attrs = await particleCanvas.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        ariaHidden: el.getAttribute("aria-hidden"),
        pointerEvents: styles.pointerEvents,
      };
    });

    expect(attrs.ariaHidden).toBe("true");
    expect(attrs.pointerEvents).toBe("none");
  });

  test("login card is responsive — fits inside 375px viewport with no overflow", async ({
    page,
  }) => {
    // Test mobile: card should not overflow
    await page.setViewportSize(MOBILE_VIEWPORT);
    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("שם משתמש")).toBeVisible();
    await page.waitForTimeout(800);

    const loginCard = page.locator('[data-slot="card"]');
    const mobileMetrics = await loginCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return {
        width: rect.width,
        left: rect.left,
        right: rect.right,
        viewportWidth: window.innerWidth,
      };
    });

    // Card should fit within viewport with padding
    expect(mobileMetrics.right).toBeLessThanOrEqual(mobileMetrics.viewportWidth + 1);
    expect(mobileMetrics.left).toBeGreaterThanOrEqual(-1);
    expect(mobileMetrics.width).toBeLessThan(375);

    await assertNoHorizontalOverflow(page, "login page @ 375px");

    // Test desktop: card should be wider than mobile
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await page.waitForTimeout(300);

    const desktopMetrics = await loginCard.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return { width: rect.width };
    });

    expect(desktopMetrics.width).toBeGreaterThan(mobileMetrics.width);
  });
});

/* ── Dashboard tests (auth needed) ── */

test.describe("Dashboard enhancements", () => {
  let baseUrl: string;
  let authState: StorageState;

  test.beforeAll(async ({ browser }) => {
    baseUrl = await resolveAppBaseUrl();
    authState = await createAuthenticatedState(browser, baseUrl);
  });

  test("main area has page-gradient and grid-pattern classes, pill CTA, animated wordmark, no img logo", async ({
    browser,
  }) => {
    const { context, page } = await openDashboardWithMocks(
      browser,
      DESKTOP_VIEWPORT,
      [],
      authState,
      baseUrl,
    );

    try {
      const main = page.locator("main.page-gradient.grid-pattern");
      await expect(main).toBeVisible();
      await expect(main).toHaveClass(/page-gradient/);
      await expect(main).toHaveClass(/grid-pattern/);

      // Pill CTA button
      const pillButton = page
        .locator('[data-slot="button"][data-size="pill"]')
        .filter({ hasText: "אופטימיזציה חדשה" });
      await expect(pillButton).toBeVisible();

      await expect(pillButton).toHaveAttribute("data-size", "pill");

      // Animated wordmark visible on desktop
      await expect(page.locator("header [aria-label='SKYNET']")).toBeVisible();

      // No old img logo in header
      await expect(page.locator("header img")).toHaveCount(0);
    } finally {
      await context.close();
    }
  });

  test("mobile header uses text fallback instead of animated wordmark", async ({ browser }) => {
    const { context, page } = await openDashboardWithMocks(
      browser,
      MOBILE_VIEWPORT,
      [],
      authState,
      baseUrl,
    );

    try {
      await expect(page.locator("header [aria-label='SKYNET']")).toBeHidden();
      await expect(page.locator("header").getByText("SKYNET", { exact: true })).toBeVisible();
    } finally {
      await context.close();
    }
  });

  test("status badges have glow pill classes", async ({ browser }) => {
    const { context, page } = await openDashboardWithMocks(
      browser,
      DESKTOP_VIEWPORT,
      STATUS_JOBS,
      authState,
      baseUrl,
    );

    try {
      const successBadge = page.locator(".status-pill-success").first();
      const runningBadge = page.locator(".status-pill-running").first();
      const failedBadge = page.locator(".status-pill-failed").first();

      await expect(successBadge).toBeVisible();
      await expect(runningBadge).toBeVisible();
      await expect(failedBadge).toBeVisible();

      for (const badge of [successBadge, runningBadge, failedBadge]) {
        const boxShadow = await badge.evaluate((el) => window.getComputedStyle(el).boxShadow);
        expect(boxShadow).not.toBe("none");
      }
    } finally {
      await context.close();
    }
  });
});
