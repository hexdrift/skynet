import { expect, test } from "@playwright/test";
import chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";
import {
  createAuthenticatedState,
  resolveAppBaseUrl,
} from "./helpers";

type LighthouseCategoryKey = "performance" | "accessibility" | "best-practices" | "seo";

const MINIMUMS: Record<LighthouseCategoryKey, number> = {
  performance: 85,
  accessibility: 95,
  "best-practices": 95,
  seo: 95,
};

function cookieHeaderFromState(cookies: Array<{ name: string; value: string }>): string {
  return cookies.map(({ name, value }) => `${name}=${value}`).join("; ");
}

async function auditPage(url: string, extraHeaders?: Record<string, string>) {
  let chrome: Awaited<ReturnType<typeof chromeLauncher.launch>> | undefined;
  try {
    chrome = await chromeLauncher.launch({
      chromeFlags: [
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
      ],
    });

    const result = await lighthouse(
      url,
      {
        port: chrome.port,
        logLevel: "error",
        output: "json",
        extraHeaders,
      },
      {
        extends: "lighthouse:default",
        settings: {
          onlyCategories: Object.keys(MINIMUMS),
          formFactor: "mobile",
          screenEmulation: {
            mobile: true,
            width: 375,
            height: 844,
            deviceScaleFactor: 2,
            disabled: false,
          },
          throttlingMethod: "simulate",
        },
      },
    );

    if (!result) {
      throw new Error(`Lighthouse returned no result for ${url}`);
    }

    const scores = Object.fromEntries(
      Object.entries(result.lhr.categories).map(([key, category]) => [key, Math.round((category?.score ?? 0) * 100)]),
    ) as Record<LighthouseCategoryKey, number>;

    for (const [category, minimum] of Object.entries(MINIMUMS) as Array<[LighthouseCategoryKey, number]>) {
      expect(
        scores[category],
        `Lighthouse ${category} score for ${url} was ${scores[category]}, expected >= ${minimum}`,
      ).toBeGreaterThanOrEqual(minimum);
    }
  } finally {
    if (chrome) {
      await chrome.kill();
    }
  }
}

test.describe("Lighthouse budgets", () => {
  test("authenticated dashboard and login page meet the minimum score thresholds", async ({ browser }) => {
    const baseUrl = await resolveAppBaseUrl();
    const authState = await createAuthenticatedState(browser, baseUrl);
    const cookieHeader = cookieHeaderFromState(authState.cookies);

    await auditPage(`${baseUrl}/login`);
    await auditPage(`${baseUrl}/`, { Cookie: cookieHeader });
  });
});
