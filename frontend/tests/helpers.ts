import { expect, type Browser, type Page, type StorageState, type ViewportSize } from "@playwright/test";

const APP_BASE_URLS = [
  process.env.PLAYWRIGHT_BASE_URL,
  "http://localhost:3000",
  "http://localhost:3001",
].filter((value): value is string => Boolean(value));

const API_BASE_URL = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";
const TEST_USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "admin";

let cachedAppBaseUrl: Promise<string> | null = null;

export async function resolveAppBaseUrl(): Promise<string> {
  if (!cachedAppBaseUrl) {
    cachedAppBaseUrl = (async () => {
      for (const baseUrl of APP_BASE_URLS) {
        try {
          const response = await fetch(`${baseUrl}/login`, { redirect: "manual" });
          const html = await response.text();
          if (html.includes("Skynet")) {
            return baseUrl;
          }
        } catch {
          // Try the next candidate.
        }
      }

      throw new Error(`Unable to resolve the frontend base URL. Tried: ${APP_BASE_URLS.join(", ")}`);
    })();
  }

  return cachedAppBaseUrl;
}

export async function fetchSampleJobIds(count = 2): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/jobs?limit=${Math.max(count, 2)}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch sample jobs: ${response.status}`);
  }

  const payload = (await response.json()) as { items?: Array<{ job_id?: string }> };
  const ids = (payload.items ?? [])
    .map((item) => item.job_id)
    .filter((id): id is string => Boolean(id));

  if (ids.length < count) {
    throw new Error(`Need at least ${count} jobs for the tests, found ${ids.length}`);
  }

  return ids.slice(0, count);
}

export async function createAuthenticatedState(browser: Browser, baseUrl: string): Promise<StorageState> {
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    await page.goto(`${baseUrl}/login`, { waitUntil: "domcontentloaded" });
    await expect(page.getByLabel("שם משתמש")).toBeVisible();
    await page.getByLabel("שם משתמש").fill(TEST_USERNAME);
    await page.getByRole("button", { name: "התחבר" }).click();
    await page.waitForURL((url) => url.origin === new URL(baseUrl).origin && url.pathname === "/", {
      timeout: 30_000,
    });
    await expect(page.getByRole("heading", { name: "לוח בקרה" })).toBeVisible({ timeout: 30_000 });
    return await context.storageState();
  } finally {
    await context.close();
  }
}

export async function withAuthenticatedPage<T>(
  browser: Browser,
  storageState: StorageState,
  viewport: ViewportSize,
  fn: (page: Page) => Promise<T>,
): Promise<T> {
  const context = await browser.newContext({ storageState, viewport });
  const page = await context.newPage();

  try {
    return await fn(page);
  } finally {
    await context.close();
  }
}

export function recordConsoleErrors(page: Page): string[] {
  const errors: string[] = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });

  page.on("pageerror", (error) => {
    errors.push(error.message);
  });

  return errors;
}

export async function assertNoHorizontalOverflow(page: Page, label: string): Promise<void> {
  const metrics = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    const body = document.body;

    return {
      rootClientWidth: root.clientWidth,
      rootScrollWidth: root.scrollWidth,
      bodyClientWidth: body.clientWidth,
      bodyScrollWidth: body.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });

  expect(
    metrics.rootScrollWidth,
    `${label}: document overflowed horizontally (${metrics.rootScrollWidth}px > ${metrics.rootClientWidth}px)`,
  ).toBeLessThanOrEqual(metrics.rootClientWidth + 1);
  expect(
    metrics.bodyScrollWidth,
    `${label}: body overflowed horizontally (${metrics.bodyScrollWidth}px > ${metrics.bodyClientWidth}px)`,
  ).toBeLessThanOrEqual(metrics.bodyClientWidth + 1);
}

export type InteractiveElementSnapshot = {
  tag: string;
  text: string;
  ariaLabel: string | null;
  title: string | null;
  role: string | null;
  width: number;
  height: number;
  top: number;
  left: number;
  right: number;
  bottom: number;
};

export async function collectVisibleInteractiveElements(page: Page): Promise<InteractiveElementSnapshot[]> {
  const selector = [
    "button",
    "a[href]",
    "input:not([type='hidden'])",
    "select",
    "textarea",
    "summary",
    "[role='button']",
    "[role='link']",
    "[role='menuitem']",
    "[role='tab']",
    "[role='switch']",
    "[role='checkbox']",
    "[tabindex='0']",
  ].join(",");

  return await page.locator(selector).evaluateAll((nodes) => {
    const { innerWidth, innerHeight } = window;

    return nodes
      .map((node) => {
        const element = node as HTMLElement;
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);

        return {
          tag: element.tagName.toLowerCase(),
          text: (element.textContent ?? "").replace(/\s+/g, " ").trim(),
          ariaLabel: element.getAttribute("aria-label"),
          title: element.getAttribute("title"),
          role: element.getAttribute("role"),
          width: rect.width,
          height: rect.height,
          top: rect.top,
          left: rect.left,
          right: rect.right,
          bottom: rect.bottom,
          display: style.display,
          visibility: style.visibility,
          opacity: style.opacity,
        };
      })
      .filter((item) => {
        if (item.display === "none" || item.visibility === "hidden" || item.opacity === "0") {
          return false;
        }

        if (item.width <= 0 || item.height <= 0) {
          return false;
        }

        const intersectsViewport =
          item.right > 0 &&
          item.bottom > 0 &&
          item.left < innerWidth &&
          item.top < innerHeight;

        return intersectsViewport;
      });
  });
}
