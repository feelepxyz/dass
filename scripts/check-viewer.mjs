// Drive the guide's model viewer and prove both finishes render.
//
//   node scripts/check-viewer.mjs
//
// Clicks TEXTURED, waits for the timber pipeline to finish, and writes a shot of
// each finish so the material can be reviewed alongside the drawn one.
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
const outDir = resolve(ROOT, 'docs/verification/guide/shots');
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
const executablePath = [
  'chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  'chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
].map((rel) => join(cache, rel)).find((path) => existsSync(path));

const browser = await chromium.launch({ executablePath });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1000 },
  deviceScaleFactor: 2,
});
const problems = [];
page.on('pageerror', (error) => problems.push(String(error)));
page.on('console', (m) => m.type() === 'error' && problems.push(m.text()));

await page.goto(`${origin}/cut-guide.html`, { waitUntil: 'networkidle' });
const viewer = page.locator('.viewer');
await viewer.scrollIntoViewIfNeeded();
await page.waitForFunction(
  () => document.querySelector('.viewer-status')?.hidden === true,
  null, { timeout: 30000 },
);
await viewer.screenshot({ path: join(outDir, 'viewer-line.png') });
console.log('line finish rendered');

await page.click('.pill[data-finish="textured"]');
await page.waitForFunction(
  () => document.querySelector('.viewer-status')?.hidden === true,
  null, { timeout: 60000 },
);
await page.waitForTimeout(1200);
await viewer.screenshot({ path: join(outDir, 'viewer-textured.png') });
console.log('textured finish rendered');

// Prove a pick still names the piece in the finish that is showing.
const box = await page.locator('.viewer-canvas').boundingBox();
await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.62);
await page.waitForTimeout(400);
const tip = await page.locator('.viewer-tip').textContent();
console.log('picked:', (tip ?? '').trim().slice(0, 80) || '(nothing)');
await viewer.screenshot({ path: join(outDir, 'viewer-picked.png') });

if (problems.length) console.log('console problems:\n  ' + problems.join('\n  '));
await browser.close();
server.close();
