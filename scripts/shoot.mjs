// Screenshot the built guide for visual review.
//
//   node scripts/shoot.mjs [--width 1440] [--out docs/verification/guide/shots] [--full]
//
// Uses the chromium that web/render/node_modules already carries, so nothing new is
// installed and the page is served over http (module imports need an origin).
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { existsSync, mkdirSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';
import playwright from './../web/render/node_modules/playwright-core/index.js';

const { chromium } = playwright;

const ROOT = resolve(import.meta.dirname, '..');
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.glb': 'model/gltf-binary',
  '.woff2': 'font/woff2',
};

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at < 0 ? fallback : args[at + 1];
};
const widths = (flag('width', '1440,390')).split(',').map(Number);
const outDir = resolve(ROOT, flag('out', 'docs/verification/guide/shots'));
const pageName = flag('page', 'cut-guide.html');
const full = args.includes('--full');
const sections = (flag('sections', '')).split(',').filter(Boolean);

mkdirSync(outDir, { recursive: true });

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
const candidates = [
  'chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  'chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
].map((rel) => join(cache, rel));
const executablePath = candidates.find((path) => existsSync(path));

const browser = await chromium.launch({ executablePath, args: ['--force-color-profile=srgb'] });
for (const width of widths) {
  const page = await browser.newPage({
    viewport: { width, height: Math.round(width * 0.72) },
    deviceScaleFactor: 2,
  });
  const problems = [];
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(message.text());
  });
  page.on('pageerror', (error) => problems.push(String(error)));
  page.on('response', (response) => {
    if (response.status() >= 400) problems.push(`${response.status()} ${response.url()}`);
  });
  await page.goto(`${origin}/${pageName}`, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);

  if (sections.length) {
    for (const id of sections) {
      const target = page.locator(id.startsWith('.') ? id : `#${id}`).first();
      await target.scrollIntoViewIfNeeded();
      await page.waitForTimeout(250);
      const name = id.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '');
      await target.screenshot({ path: join(outDir, `${name}-${width}.png`) });
    }
  } else {
    await page.screenshot({ path: join(outDir, `guide-${width}.png`), fullPage: full });
  }
  if (problems.length) console.log(`[${width}px] console errors:\n  ${problems.join('\n  ')}`);
  await page.close();
}
await browser.close();
server.close();
console.log(`wrote shots to ${outDir}`);
