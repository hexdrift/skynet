import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:3099";

test.describe("axe-core accessibility scan", () => {
  test("login page has zero critical/serious violations", async ({ page }) => {
    await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
    await page.waitForTimeout(3000); // wait for splash screen

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    const critical = results.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );

    if (critical.length > 0) {
      console.log("Critical/serious violations:");
      for (const v of critical) {
        console.log(`  [${v.impact}] ${v.id}: ${v.description}`);
        for (const node of v.nodes.slice(0, 3)) {
          console.log(`    - ${node.html.substring(0, 120)}`);
          console.log(`      Fix: ${node.failureSummary?.substring(0, 120)}`);
        }
      }
    }

    expect(critical.length, `Found ${critical.length} critical/serious violations`).toBe(0);
  });
});
