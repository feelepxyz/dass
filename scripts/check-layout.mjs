// Prove the document itself never scrolls sideways, at every width that matters.
//
//   node scripts/check-layout.mjs
//
// Individual stock bars and wide tables are allowed their own scroller; the page
// is not. Reports any element wider than the viewport that is not one of those.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';
import playwright from './../render/node_modules/playwright-core/index.js';

const { chromium } = playwright;
const ROOT = resolve(import.meta.dirname, '..');
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.glb': 'model/gltf-binary',
  '.woff2': 'font/woff2',
};

const server = createServer(async (req, res) => {
  const path = join(ROOT, 'build', decodeURIComponent(req.url.split('?')[0]));
  if (!existsSync(path)) {
    res.writeHead(404).end('not found');
    return;
  }
  res.writeHead(200, { 'content-type': TYPES[extname(path)] ?? 'application/octet-stream' });
  res.end(await readFile(path));
});
await new Promise((done) => server.listen(0, done));
const origin = `http://127.0.0.1:${server.address().port}`;

const cache = join(process.env.HOME, 'Library/Caches/ms-playwright');
const executablePath = [
  'chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  'chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
].map((rel) => join(cache, rel)).find((path) => existsSync(path));

const browser = await chromium.launch({ executablePath });
let failed = false;
for (const width of [390, 768, 1024, 1440]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(`${origin}/cut-guide.html`, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const report = await page.evaluate((viewport) => {
    const allowed = (node) => node.closest('.stock-scroll, .table-scroll') !== null;
    const wide = [];
    for (const node of document.querySelectorAll('body *')) {
      const box = node.getBoundingClientRect();
      if (allowed(node)) continue;
      // Both a too-wide box and one pushed past the right edge scroll the page.
      if (box.width > viewport + 1 || box.right > viewport + 1) {
        wide.push(
          `${node.tagName.toLowerCase()}.${node.className || '(none)'} ` +
          `w=${Math.round(box.width)} right=${Math.round(box.right)}`,
        );
      }
    }
    return {
      scrollWidth: document.documentElement.scrollWidth,
      wide: [...new Set(wide)].slice(0, 8),
    };
  }, width);
  const scrolls = report.scrollWidth > width + 1;
  if (scrolls || report.wide.length) failed = true;
  console.log(
    `${width}px  document ${report.scrollWidth}px  ${scrolls ? 'SCROLLS SIDEWAYS' : 'ok'}` +
    (report.wide.length ? `\n   overflowing: ${report.wide.join('\n                ')}` : ''),
  );
  await page.close();
}
await browser.close();
server.close();
process.exit(failed ? 1 : 0);
