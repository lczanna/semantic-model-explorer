/**
 * Playwright tests for landing page responsive layout.
 *
 * Verifies that the privacy badge ("100% local, no network needed") and
 * file-type badges do not overflow the viewport on smartphone, tablet,
 * and desktop screen widths.
 *
 * Usage:
 *   node tests/test-responsive.mjs
 */

import { createRequire } from 'module';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const require = createRequire('/opt/node22/lib/node_modules/playwright/index.mjs');
const { chromium } = require('/opt/node22/lib/node_modules/playwright/index.js');

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixtureUrl = `file://${resolve(__dirname, 'landing-fixture.html')}`;

const viewports = [
  { name: 'iPhone SE',  width: 320,  height: 568 },
  { name: 'iPhone 13',  width: 390,  height: 844 },
  { name: 'Pixel 7',    width: 412,  height: 915 },
  { name: 'iPad Mini',  width: 768,  height: 1024 },
  { name: 'Desktop',    width: 1280, height: 800 },
];

let passed = 0;
let failed = 0;

const browser = await chromium.launch({
  args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--single-process'],
});

const page = await browser.newPage();

for (const vp of viewports) {
  await page.setViewportSize({ width: vp.width, height: vp.height });
  await page.goto(fixtureUrl, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(200);

  const result = await page.evaluate(() => {
    const badge = document.querySelector('.privacy-badge');
    const badgeRect = badge.getBoundingClientRect();

    const header = document.querySelector('.landing-header');
    const headerRect = header.getBoundingClientRect();

    const fileTypes = document.querySelector('.file-types');
    const fileTypesRect = fileTypes.getBoundingClientRect();

    const vw = window.innerWidth;

    return {
      vw,
      badgeRight: Math.round(badgeRect.right),
      badgeLeft: Math.round(badgeRect.left),
      badgeWidth: Math.round(badgeRect.width),
      badgeFits: badgeRect.right <= vw && badgeRect.left >= 0,
      headerFits: headerRect.right <= vw && headerRect.left >= 0,
      fileTypesFit: fileTypesRect.right <= vw && fileTypesRect.left >= 0,
      noHorizontalScroll: document.body.scrollWidth <= vw,
    };
  });

  const allPass = result.badgeFits && result.headerFits && result.fileTypesFit && result.noHorizontalScroll;

  if (allPass) {
    console.log(`  PASS  ${vp.name} (${vp.width}x${vp.height})`);
    passed++;
  } else {
    console.log(`  FAIL  ${vp.name} (${vp.width}x${vp.height})`);
    if (!result.badgeFits)          console.log(`        Privacy badge overflows (right: ${result.badgeRight}, left: ${result.badgeLeft}, viewport: ${result.vw})`);
    if (!result.headerFits)         console.log(`        Header overflows`);
    if (!result.fileTypesFit)       console.log(`        File type badges overflow`);
    if (!result.noHorizontalScroll) console.log(`        Page has horizontal scroll (scrollWidth > clientWidth)`);
    failed++;
  }
}

await browser.close();

console.log(`\n${passed} passed, ${failed} failed out of ${viewports.length} viewports`);
process.exit(failed > 0 ? 1 : 0);
