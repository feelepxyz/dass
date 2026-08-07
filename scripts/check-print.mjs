// Prove the printed set never splits a drawing and never prints an empty sheet.
//
//   node scripts/check-print.mjs [--pdf docs/verification/guide/shots/cut-guide.pdf]
//
// A block that carries `break-inside:avoid` is only honoured while it fits on
// one page; once it outgrows the page box the browser breaks inside it anyway,
// which is how a drawing ends up cut in half. So the check is geometric: every
// unbreakable block must measure less than the printable page. It also renders
// the PDF and reports any page with no ink on it.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { extname, join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import playwright from './../web/render/node_modules/playwright-core/index.js';

const { chromium } = playwright;
const ROOT = resolve(import.meta.dirname, '..');
const PDF = process.argv.includes('--pdf')
  ? process.argv[process.argv.indexOf('--pdf') + 1]
  : join(ROOT, 'docs/verification/guide/shots/cut-guide.pdf');

// A4 landscape at the sheet's @page margin (14mm 9mm 10mm), in CSS pixels.
const MM = 96 / 25.4;
const PAGE = { width: (297 - 18) * MM, height: (210 - 24) * MM };
// Blocks the print stylesheet promises to keep whole.
// A unit now runs across the sheets it needs: its general arrangement opens on
// one, its numbered steps run on from there. What must never break is a single
// drawing, so a step is proved whole here even though its unit is not.
const UNBREAKABLE = '.drawing, .step, .stock, .note';

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
const page = await browser.newPage({
  viewport: { width: Math.round(PAGE.width), height: Math.round(PAGE.height) },
});
await page.goto(`${origin}/cut-guide.html`, { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);
// The model has to be drawn before the print still can be taken from it.
await page.waitForFunction(
  () => document.querySelector('.viewer-status')?.hidden === true,
  null,
  { timeout: 20000 },
).catch(() => console.log('note: the model never finished; checking the photo fallback'));

let failed = false;

await page.emulateMedia({ media: 'print' });
// Real browsers fire `beforeprint`; print-to-PDF only switches the media, so the
// page takes its still off the media query. Prove the sheet got the drawn model.
await page.waitForFunction(
  () => document.body.classList.contains('has-print-model'),
  null,
  { timeout: 10000 },
).catch(() => {});
const model = await page.evaluate(() => ({
  still: document.body.classList.contains('has-print-model'),
  bytes: document.querySelector('.viewer-print')?.src.length ?? 0,
}));
console.log(
  model.still
    ? `title sheet  drawn model, ${Math.round(model.bytes / 1024)}KB still  ok`
    : 'title sheet  NO MODEL STILL — falling back to the photograph',
);
if (!model.still) failed = true;
const blocks = await page.evaluate(({ height, selector }) => {
  const over = [];
  for (const node of document.querySelectorAll(selector)) {
    const box = node.getBoundingClientRect();
    if (box.height > height) {
      over.push({
        what: `${node.tagName.toLowerCase()}.${node.className || '(none)'}`,
        label: node.querySelector('h2, h3, figcaption, header')?.textContent.trim().slice(0, 44) ?? '',
        height: Math.round(box.height),
      });
    }
  }
  return over;
}, { height: PAGE.height, selector: UNBREAKABLE });

console.log(
  `page box   ${Math.round(PAGE.width)} x ${Math.round(PAGE.height)}px  (A4 landscape, 14/9/10mm margin)`,
);
if (blocks.length) {
  failed = true;
  console.log(`unbreakable blocks TALLER THAN THE PAGE: ${blocks.length}`);
  for (const block of blocks) {
    console.log(`   ${block.height}px  ${block.what}  ${block.label}`);
  }
} else {
  console.log('unbreakable blocks  all fit one page  ok');
}

// Paper has no scrollbar: anything wider than the page is simply lost off the
// edge, so a box that outgrows its column is a printed defect, not a scroller.
const wide = await page.evaluate((limit) => {
  const over = [];
  for (const node of document.querySelectorAll('main *')) {
    const box = node.getBoundingClientRect();
    if (box.width > limit + 1 || box.right > limit + 1) {
      over.push(
        `${node.tagName.toLowerCase()}.${node.className || '(none)'} ` +
        `w=${Math.round(box.width)} right=${Math.round(box.right)}`,
      );
    }
  }
  return [...new Set(over)].slice(0, 8);
}, PAGE.width);
if (wide.length) {
  failed = true;
  console.log(`over the page width: ${wide.length}\n   ${wide.join('\n   ')}`);
} else {
  console.log('page width  nothing runs off the sheet  ok');
}

// The plate is the reason any of this matters; report how large it prints.
const MM_PX = 96 / 25.4;
const plates = await page.evaluate((MM_PX) => [...document.querySelectorAll('.drawing .plate')].map((svg) => {
  const box = svg.getBoundingClientRect();
  const [, , vw, vh] = svg.getAttribute('viewBox').split(/\s+/).map(Number);
  // Hidden perspective toggle layers have no box; they are not printed and
  // must not make the visible minimum code size report as zero.
  if (box.width === 0 || box.height === 0) return null;
  // preserveAspectRatio letterboxes the drawing inside its box.
  const scale = Math.min(box.width / vw, box.height / vh);
  // A step plate letters larger inside the same 1000-unit space than a key
  // plate does, so the size is read off a real mark. A plate that carries no
  // code mark has no code size to report and must not stand in for one.
  const mark = svg.querySelector('.mark');
  const size = mark ? parseFloat(getComputedStyle(mark).fontSize) : null;
  return {
    ref: svg.closest('.drawing')?.querySelector('.drawing-ref')?.textContent.trim() ?? '',
    mark: size === null ? null : +(size * scale / (96 / 25.4) * 72 / 25.4).toFixed(1),
    plate: `${Math.round(box.width / MM_PX)} x ${Math.round(box.height / MM_PX)}mm`,
  };
}).filter(Boolean), MM_PX);
const marked = plates.filter((plate) => plate.mark !== null);
const smallest = marked.reduce((low, plate) => (plate.mark < low.mark ? plate : low), marked[0]);
console.log(
  `plates      ${plates.length} drawings, ${marked.length} coded  ` +
  `smallest code mark ${smallest.mark}pt (${smallest.ref}, ${smallest.plate})`,
);
await page.emulateMedia({ media: null });

await mkdir(join(ROOT, 'docs/verification/guide/shots'), { recursive: true });
await writeFile(PDF, await page.pdf({ preferCSSPageSize: true, printBackground: true }));
await browser.close();
server.close();

// An empty sheet in a set that trades on exactness reads as a mistake.
const raster = join(tmpdir(), `dass-print-${process.pid}`);
await mkdir(raster, { recursive: true });
try {
  execFileSync('pdftoppm', ['-png', '-r', '40', PDF, join(raster, 'page')]);
  const { readdir } = await import('node:fs/promises');
  const pages = (await readdir(raster)).filter((name) => name.endsWith('.png')).sort();
  const blank = [];
  for (const name of pages) {
    const bytes = await readFile(join(raster, name));
    // A sheet with nothing on it compresses to almost nothing.
    if (bytes.length < 2500) blank.push(name.match(/(\d+)\.png$/)[1]);
  }
  if (blank.length) {
    failed = true;
    console.log(`pages       ${pages.length}  BLANK: ${blank.join(', ')}`);
  } else {
    console.log(`pages       ${pages.length}  none blank  ok`);
  }
} catch (error) {
  console.log(`pages       not rasterised (${error.message.split('\n')[0]})`);
}
await rm(raster, { recursive: true, force: true });
console.log(`pdf         ${PDF}`);
process.exit(failed ? 1 : 0);
