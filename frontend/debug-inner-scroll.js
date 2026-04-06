const { chromium } = require('@playwright/test');

(async () => {
 const browser = await chromium.launch({ headless: true });
 const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
 const page = await ctx.newPage();

 // Capture console messages
 page.on('console', msg => console.log('BROWSER:', msg.text()));

 await page.goto('http://localhost:3000/login');
 await page.getByLabel('שם משתמש').fill('admin');
 await page.getByRole('button', { name: 'התחבר' }).click();
 await page.waitForURL('**/', { timeout: 30000 });

 const jobsResp = await page.request.get('http://localhost:8000/jobs?limit=1');
 const jobs = await jobsResp.json();
 const jobId = jobs.items[0].job_id;

 await page.goto(`http://localhost:3000/jobs/${jobId}?tab=logs`);
 await page.waitForSelector('div.max-h-\\[600px\\].overflow-auto', { timeout: 15000 });

 const filterBtn = page.locator('button[aria-label="סינון עמודת רמה"]');
 await filterBtn.scrollIntoViewIfNeeded();
 await filterBtn.click();
 await page.waitForSelector('body > div.fixed.z-50', { timeout: 5000 });

 // Check the dropdown's style attribute after open
 const initialState = await page.evaluate(() => {
 const b = document.querySelector('button[aria-label="סינון עמודת רמה"]');
 const d = document.querySelector('body > div.fixed.z-50');
 return {
 btnRect: b.getBoundingClientRect(),
 dropStyle: d.getAttribute('style'),
 dropRect: d.getBoundingClientRect()
 };
 });
 console.log('\nInitial state:');
 console.log('  btn.top:', initialState.btnRect.top, 'btn.bottom:', initialState.btnRect.bottom);
 console.log('  drop.top:', initialState.dropRect.top, 'drop style:', initialState.dropStyle);

 // Scroll 5 times by 20px each, measure after each
 for (let i = 0; i < 5; i++) {
 await page.evaluate(() => {
 const c = document.querySelector('div.max-h-\\[600px\\].overflow-auto');
 c.scrollTop = c.scrollTop + 20;
 });
 await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r()))));

 const s = await page.evaluate(() => {
 const b = document.querySelector('button[aria-label="סינון עמודת רמה"]');
 const d = document.querySelector('body > div.fixed.z-50');
 const c = document.querySelector('div.max-h-\\[600px\\].overflow-auto');
 if (!d) return { closed: true };
 return {
 scrollTop: c.scrollTop,
 btnTop: b.getBoundingClientRect().top,
 btnBottom: b.getBoundingClientRect().bottom,
 dropTop: d.getBoundingClientRect().top,
 dropStyle: d.getAttribute('style'),
 expected: b.getBoundingClientRect().bottom + 6,
 delta: d.getBoundingClientRect().top - (b.getBoundingClientRect().bottom + 6)
 };
 });
 console.log(`\nAfter scroll ${(i + 1) * 20}:`);
 console.log(` scrollTop=${s.scrollTop}, btn.top=${s.btnTop?.toFixed(2)}, btn.bottom=${s.btnBottom?.toFixed(2)}`);
 console.log(` drop.top=${s.dropTop?.toFixed(2)}, expected=${s.expected?.toFixed(2)}, delta=${s.delta?.toFixed(2)}`);
 console.log(` style="${s.dropStyle}"`);
 }

 await browser.close();
})();
