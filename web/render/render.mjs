// Node half of the photoreal renderer: serves the project over HTTP, drives
// scene.mjs in headless Chromium, writes one PNG per view.
//
//   node web/render/render.mjs --manifest build/renders/manifest.json --out build/renders
//
// Normally invoked through `uv run render-photo`, which builds the GLBs and texture
// maps this needs.
import { createServer } from 'node:http';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { extname, join, resolve } from 'node:path';
import { existsSync } from 'node:fs';
import { chromium } from 'playwright-core';

const ROOT = resolve(import.meta.dirname, '../..');

// Keep the open and closed forest plates on the same world-space camera.
// The anchor is the centre of the open assembly used to compose the plate.
// Using one fixed datum stops the smaller closed bounds from shifting the shell.
const IN_SITU_CAMERA = Object.freeze({
  azimuth: -44,
  cameraHeight: 1300,
  distance: 4200,
  frameWidth: 2500,
  offsetX: 0,
  offsetY: 0,
  anchorX: 643.37172,
  anchorY: 0,
  anchorZ: 26.016753,
});

// azimuth: 0 looks at the door (front), +90 from the right, 180 from the back.
// elevation: 0 eye-level, 90 straight down.
export const VIEWS = [
  {
    name: 'open-hero', variant: 'open',
    azimuth: -36, elevation: 10, fov: 30, distance: 0.94, targetLift: -0.04,
    sunAzimuth: -18, sunElevation: 42,
  },
  {
    name: 'open-doorway', variant: 'open',
    azimuth: -12, elevation: 3, fov: 38, distance: 0.70, targetLift: -0.10,
    sunAzimuth: -8, sunElevation: 40,
  },
  {
    name: 'open-interior', variant: 'open',
    azimuth: -28, elevation: 24, fov: 34, distance: 0.74, targetLift: 0.04,
    sunAzimuth: -10, sunElevation: 58,
  },
  {
    name: 'open-rear-quarter', variant: 'open',
    azimuth: -132, elevation: 15, fov: 32, distance: 0.96,
    sunAzimuth: -58, sunElevation: 42,
  },
  {
    name: 'closed-hero', variant: 'closed',
    azimuth: 38, elevation: 11, fov: 30, distance: 0.92, targetLift: -0.04,
    sunAzimuth: -32, sunElevation: 38,
  },
  {
    name: 'closed-front-left', variant: 'closed',
    azimuth: -42, elevation: 7, fov: 32, distance: 0.94,
    sunAzimuth: 30, sunElevation: 34,
  },
  {
    name: 'closed-rear-quarter', variant: 'closed',
    azimuth: 146, elevation: 13, fov: 32, distance: 0.94,
    sunAzimuth: 226, sunElevation: 40,
  },
  {
    name: 'closed-low', variant: 'closed',
    azimuth: 16, elevation: -3, fov: 36, distance: 0.88, targetLift: -0.12,
    sunAzimuth: 96, sunElevation: 26,
  },
  {
    name: 'closed-above', variant: 'closed',
    azimuth: 28, elevation: 44, fov: 32, distance: 0.92,
    sunAzimuth: -46, sunElevation: 56,
  },
  // Composited into background.jpg.  The clearing is about 3 m across, which
  // is what fixes the model's scale in the plate; the camera is held level at
  // roughly chest height, matching how the photograph was taken. `frameWidth`
  // makes the structure fill the guide frame at the same scale as the model.
  //
  // The plate is lit from the camera's left and well above: the fence post at
  // its right edge is bright down its left face and dark down its right, and
  // the birch trunks behind it read the same way.  Both shots put the sun there
  // and carry enough exposure and sky to sit in the photograph's own range.
  {
    name: 'in-situ-closed', variant: 'closed', photo: true, aspect: 3 / 4,
    ...IN_SITU_CAMERA,
    sunAzimuth: -46, sunElevation: 38, exposure: 1.0, envIntensity: 1.55,
    sunIntensity: 9, shadowOpacity: 0.42,
  },
  {
    name: 'in-situ-open', variant: 'open', photo: true, aspect: 3 / 4,
    ...IN_SITU_CAMERA,
    sunAzimuth: -110, sunElevation: 38, exposure: 1.0, envIntensity: 1.55,
    sunIntensity: 9, shadowOpacity: 0.42,
  },
  // Straight-on elevations: orthographic, plain background, no ground.
  { name: 'flat-front', variant: 'closed', projection: 'orthographic', azimuth: 0, elevation: 0 },
  { name: 'flat-back', variant: 'closed', projection: 'orthographic', azimuth: 180, elevation: 0 },
  { name: 'flat-left', variant: 'closed', projection: 'orthographic', azimuth: -90, elevation: 0 },
  { name: 'flat-right', variant: 'closed', projection: 'orthographic', azimuth: 90, elevation: 0 },
  { name: 'flat-top', variant: 'closed', projection: 'orthographic', azimuth: 0, elevation: 90 },
  { name: 'flat-bottom', variant: 'closed', projection: 'orthographic', azimuth: 0, elevation: -90 },
  { name: 'flat-front-open', variant: 'open', projection: 'orthographic', azimuth: 0, elevation: 0 },
];

const MIME = {
  '.html': 'text/html', '.mjs': 'text/javascript', '.js': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.glb': 'model/gltf-binary', '.map': 'application/json',
};

function serveProject() {
  const server = createServer(async (request, response) => {
    const path = resolve(ROOT, decodeURIComponent(request.url.split('?')[0]).replace(/^\/+/, ''));
    if (!path.startsWith(ROOT) || !existsSync(path)) {
      console.error(`[http] 404 ${request.url}`);
      response.writeHead(404).end('not found');
      return;
    }
    try {
      response.writeHead(200, { 'content-type': MIME[extname(path)] ?? 'application/octet-stream' });
      response.end(await readFile(path));
    } catch (error) {
      response.writeHead(500).end(String(error));
    }
  });
  return new Promise((done) => server.listen(0, '127.0.0.1', () => done(server)));
}

function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const cache = join(process.env.HOME, 'Library/Caches/ms-playwright');
  const candidates = [
    'chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    'chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  ].map((relative) => join(cache, relative));
  candidates.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome');
  const found = candidates.find((path) => existsSync(path));
  if (!found) throw new Error('no Chromium found; set CHROMIUM_PATH');
  return found;
}

function parseArgs(argv) {
  const args = { width: 1600, height: 1200, supersample: 2, views: null };
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i].replace(/^--/, '');
    const value = argv[i + 1];
    args[key] = ['width', 'height', 'supersample'].includes(key) ? Number(value) : value;
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args['list-views']) {
    for (const view of VIEWS) {
      const kind = view.projection === 'orthographic' ? 'orthographic' : 'perspective';
      console.log(`${view.name.padEnd(20)} ${view.variant.padEnd(7)} ${kind}`);
    }
    return;
  }
  const manifest = JSON.parse(await readFile(resolve(args.manifest), 'utf8'));
  const outDir = resolve(args.out ?? 'build/renders');
  await mkdir(outDir, { recursive: true });

  const wanted = args.views
    ? args.views.split(',').map((name) => name.trim())
    : VIEWS.map((view) => view.name);
  const unknown = wanted.filter((name) => !VIEWS.some((view) => view.name === name));
  if (unknown.length) throw new Error(`unknown view(s): ${unknown.join(', ')}`);
  const views = VIEWS.filter((view) => wanted.includes(view.name));

  const server = await serveProject();
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({
    executablePath: findChromium(),
    args: [
      '--headless=new',
      '--use-angle=metal',
      '--enable-unsafe-swiftshader',
      '--ignore-gpu-blocklist',
      '--enable-gpu',
    ],
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  page.on('console', (message) => {
    if (message.type() === 'error') console.error('[page]', message.text());
  });
  page.on('pageerror', (error) => console.error('[page]', error.message));
  await page.goto(`${origin}/web/render/scene.html`, { waitUntil: 'load' });
  await page.waitForFunction(() => Boolean(window.dass));

  await page.evaluate((config) => window.dass.boot(config), {
    woodColor: `${origin}/${manifest.textures.color}`,
    woodNormal: `${origin}/${manifest.textures.normal}`,
    woodRoughness: `${origin}/${manifest.textures.roughness}`,
    corrugation: `${origin}/${manifest.textures.corrugation}`,
    plankColor: `${origin}/${manifest.textures.plank.color}`,
    plankNormal: `${origin}/${manifest.textures.plank.normal}`,
    plankRoughness: `${origin}/${manifest.textures.plank.roughness}`,
    plankAtlas: manifest.textures.plank,
    photo: manifest.photo ? `${origin}/${manifest.photo}` : null,
  });

  const baseSize = { width: args.width, height: args.height, supersample: args.supersample };
  const written = [];
  let loaded = null;
  for (const view of views) {
    if (view.variant !== loaded) {
      const bounds = await page.evaluate((config) => window.dass.loadModel(config), {
        model: `${origin}/${manifest.variants[view.variant]}`,
        parts: manifest.parts,
      });
      console.log(`loaded ${view.variant}: ${bounds.parts} parts, `
        + `${bounds.max.map((v, i) => (v - bounds.min[i]).toFixed(0)).join(' x ')} mm, `
        + JSON.stringify(bounds.roles));
      loaded = view.variant;
    }
    // A view with a fixed aspect (a photo plate) sizes itself from --width.
    const size = view.aspect
      ? { width: args.width, height: Math.round(args.width / view.aspect), supersample: args.supersample }
      : baseSize;
    const started = Date.now();
    const dataUrl = await page.evaluate(
      ([viewConfig, sizeConfig]) => window.dass.renderView(viewConfig, sizeConfig),
      [view, size],
    );
    const file = join(outDir, `${view.name}.png`);
    await writeFile(file, Buffer.from(dataUrl.split(',')[1], 'base64'));
    written.push(file);
    console.log(`${view.name}.png  ${((Date.now() - started) / 1000).toFixed(1)}s`);
  }

  await browser.close();
  server.close();
  console.log(`\nwrote ${written.length} render(s) to ${outDir}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
