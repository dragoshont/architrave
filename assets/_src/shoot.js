// Regenerate the README images from assets/_src/*.html via headless Microsoft Edge.
// Prereq:  npm i -D playwright      (Edge is launched via channel 'msedge')
// Run:     node assets/_src/shoot.js
const { chromium } = require('playwright');
const ASSETS = __dirname.replace(/\/_src$/, '');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const ctx = await browser.newContext({ deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  for (const [name, w, h] of [['overview', 1240, 560], ['cli', 900, 640]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto('file://' + ASSETS + '/_src/' + name + '.html', { waitUntil: 'load' });
    await page.waitForTimeout(250);
    const el = await page.$('body');
    await el.screenshot({ path: ASSETS + '/' + name + '.png' });
    const box = await el.boundingBox();
    console.log(name, '→', Math.round(box.width) + 'x' + Math.round(box.height));
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
