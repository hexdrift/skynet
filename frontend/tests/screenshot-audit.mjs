import { chromium } from "@playwright/test";
import fs from "fs";
import path from "path";

const BASE_URL = "http://localhost:3001";

const VIEWPORTS = [
  { width: 640, height: 1080, label: "640px" },
  { width: 800, height: 1080, label: "800px" },
  { width: 960, height: 1080, label: "960px" },
  { width: 1024, height: 1080, label: "1024px" },
  { width: 1280, height: 1080, label: "1280px" },
  { width: 1440, height: 1080, label: "1440px" },
  { width: 1920, height: 1080, label: "1920px" },
  { width: 2560, height: 1080, label: "2560px" },
];

const SCREENSHOTS_DIR = "/tmp/baseline-screenshots";
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

async function testPage(browser, url, pageName, skipAuth = false) {
  console.log(`\n📄 Testing ${pageName} (${url})`);

  for (const vp of VIEWPORTS) {
    try {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
      });
      const page = await context.newPage();

      // For login page, no auth needed
      if (!skipAuth && url !== "/login") {
        // Try to auth first
        await page.goto(`${BASE_URL}/login`, { waitUntil: "load" });
        // Look for login form and submit with dev credentials
        const textInputs = await page.locator('input[type="text"]').all();
        if (textInputs.length > 0) {
          await textInputs[0].fill("testuser");
        }
        const passInputs = await page.locator('input[type="password"]').all();
        if (passInputs.length > 0) {
          await passInputs[0].fill("skynet");
        }
        const buttons = await page.locator("button").all();
        if (buttons.length > 0) {
          await buttons[0].click({ timeout: 1000 }).catch(() => {});
          await page.waitForURL(/.*/, { timeout: 3000 }).catch(() => {});
        }
      }

      // Now navigate to target page
      await page.goto(`${BASE_URL}${url}`, { waitUntil: "load" });
      await page.waitForTimeout(1000);

      const filename = `baseline-${pageName}-${vp.label}.png`;
      const filepath = path.join(SCREENSHOTS_DIR, filename);
      await page.screenshot({ path: filepath, fullPage: false });

      console.log(`  ✓ ${vp.label}`);
      await context.close();
    } catch (e) {
      console.log(`  ✗ ${vp.label}: ${e.message.split("\n")[0]}`);
    }
  }
}

async function main() {
  const browser = await chromium.launch();

  const pages = [
    { url: "/login", name: "login", skipAuth: true },
    { url: "/", name: "dashboard", skipAuth: false },
    { url: "/submit", name: "submit", skipAuth: false },
  ];

  for (const p of pages) {
    await testPage(browser, p.url, p.name, p.skipAuth);
  }

  await browser.close();
  console.log(`\n✅ Finished! Screenshots saved to ${SCREENSHOTS_DIR}`);
  console.log("");
  console.log("To view: open /tmp/baseline-screenshots/");
}

main().catch(console.error);
