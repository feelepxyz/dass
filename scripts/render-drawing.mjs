// Export the model viewer's line finish as static drawing-set SVGs.
//
//   node scripts/render-drawing.mjs
//
// The camera and palette live in the guide, so this capture cannot drift from
// the view a reader sees at the top of the page.
import { createServer } from 'node:http';
import { homedir } from 'node:os';
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync, mkdirSync } from 'node:fs';
import { extname, join, resolve } from 'node:path';
import playwright from './../web/render/node_modules/playwright-core/index.js';

const { chromium } = playwright;
const ROOT = resolve(import.meta.dirname, '..');
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.glb': 'model/gltf-binary',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2',
};
const outDir = resolve(ROOT, 'build/renders');
mkdirSync(outDir, { recursive: true });

const server = createServer(async (request, response) => {
  if (request.url.split('?')[0] === '/favicon.ico') {
    response.writeHead(204).end();
    return;
  }
  const path = resolve(ROOT, decodeURIComponent(request.url.split('?')[0]).replace(/^\/+/, ''));
  if (!path.startsWith(ROOT) || !existsSync(path)) {
    response.writeHead(404).end('not found');
    return;
  }
  response.writeHead(200, { 'content-type': TYPES[extname(path)] ?? 'application/octet-stream' });
  response.end(await readFile(path));
});
await new Promise((done) => server.listen(0, done));
const origin = `http://127.0.0.1:${server.address().port}`;

const cache = join(homedir(), 'Library/Caches/ms-playwright');
const executablePath = [
  'chromium-1228/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
  'chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
].map((relative) => join(cache, relative)).find((path) => existsSync(path));

const browser = await chromium.launch({ executablePath, args: ['--force-color-profile=srgb'] });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 2 });
const problems = [];
page.on('pageerror', (error) => problems.push(String(error)));
page.on('console', (message) => message.type() === 'error' && problems.push(message.text()));

await page.goto(`${origin}/build/cut-guide.html`, { waitUntil: 'networkidle' });
await page.waitForFunction(
  () => document.querySelector('.viewer-status')?.hidden === true,
  null,
  { timeout: 30000 },
);
async function writeDrawing(name) {
  const markup = await page.evaluate(async (variant) => {
    const state = window.__dassDrawing;
    if (!state?.current) throw new Error('model viewer did not expose its drawing state');
    const { THREE } = state;

    state.current.updateMatrixWorld(true);
    state.camera.updateMatrixWorld(true);

    // The WebGL depth buffer decides the visible flat fills. Those colour
    // masks are traced back into SVG paths; construction edges are clipped
    // against the same projected depth before their vector linework is added.
    const triangles = [];
    const lineSegments = [];
    const projected = (point) => point.clone().project(state.camera);
    const worldVertex = (attribute, index, matrix) => new THREE.Vector3()
      .fromBufferAttribute(attribute, index)
      .applyMatrix4(matrix);
    const edgeLines = [];
    const materialSides = new Map();
    state.current.traverse((node) => {
      if (node.isLine && node.userData.isEdge) {
        edgeLines.push([node, node.visible]);
        node.visible = false;
        const position = node.geometry.attributes.position;
        const index = node.geometry.index;
        const count = index ? index.count : position.count;
        for (let offset = 0; offset + 1 < count; offset += 2) {
          const first = index ? index.getX(offset) : offset;
          const second = index ? index.getX(offset + 1) : offset + 1;
          const a = projected(worldVertex(position, first, node.matrixWorld));
          const b = projected(worldVertex(position, second, node.matrixWorld));
          lineSegments.push({
            a,
            b,
            width: node.userData.isPlankSeam ? 0.75 : 1.25,
          });
        }
        return;
      }
      if (!node.isMesh || node.userData.isEdge) return;
      if (!materialSides.has(node.material)) {
        materialSides.set(node.material, node.material.side);
        node.material.side = THREE.FrontSide;
      }
      const position = node.geometry.attributes.position;
      const index = node.geometry.index;
      const count = index ? index.count : position.count;
      for (let offset = 0; offset + 2 < count; offset += 3) {
        const points = [0, 1, 2].map((step) => {
          const vertex = index ? index.getX(offset + step) : offset + step;
          return projected(worldVertex(position, vertex, node.matrixWorld));
        });
        const area = (points[1].x - points[0].x) * (points[2].y - points[0].y)
          - (points[1].y - points[0].y) * (points[2].x - points[0].x);
        if (Math.abs(area) < 1e-10) continue;
        triangles.push({
          points,
          area,
          xmin: Math.min(...points.map((point) => point.x)),
          xmax: Math.max(...points.map((point) => point.x)),
          ymin: Math.min(...points.map((point) => point.y)),
          ymax: Math.max(...points.map((point) => point.y)),
        });
      }
    });

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      preserveDrawingBuffer: true,
      alpha: false,
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setPixelRatio(1);
    renderer.setSize(1200, 1200, false);
    renderer.setClearColor(0xffffff, 1);
    const groundVisible = state.ground.visible;
    state.ground.visible = false;
    renderer.render(state.scene, state.camera);
    const fillCanvas = document.createElement('canvas');
    fillCanvas.width = 1200;
    fillCanvas.height = 1200;
    const fillContext = fillCanvas.getContext('2d', { willReadFrequently: true });
    fillContext.drawImage(renderer.domElement, 0, 0);
    const fillPixels = fillContext.getImageData(0, 0, 1200, 1200).data;
    renderer.dispose();
    state.ground.visible = groundVisible;
    for (const [line, visible] of edgeLines) line.visible = visible;
    for (const [material, side] of materialSides) material.side = side;

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '-600 -600 1200 1200');
    svg.setAttribute('width', '1200');
    svg.setAttribute('height', '1200');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-labelledby', 'drawing-title drawing-description');
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.id = 'drawing-title';
    title.textContent = variant === 'open'
      ? 'Finished outdoor toilet with the door open and roof lifted'
      : 'Finished outdoor toilet with the door and roof closed';
    const description = document.createElementNS('http://www.w3.org/2000/svg', 'desc');
    description.id = 'drawing-description';
    description.textContent = 'Orthographic isometric projection with white framing, pale panels, and black construction outlines.';
    svg.append(title, description);

    const colours = new Map();
    for (let index = 0; index < fillPixels.length; index += 4) {
      const red = fillPixels[index];
      const green = fillPixels[index + 1];
      const blue = fillPixels[index + 2];
      if (red === 255 && green === 255 && blue === 255) continue;
      const key = `${red},${green},${blue}`;
      colours.set(key, (colours.get(key) ?? 0) + 1);
    }
    const pointKey = (x, y) => y * 1201 + x;
    const pointFrom = (key) => [key % 1201, Math.floor(key / 1201)];
    const colourAt = (x, y, colour) => {
      if (x < 0 || y < 0 || x >= 1200 || y >= 1200) return false;
      const index = (y * 1200 + x) * 4;
      return fillPixels[index] === colour[0]
        && fillPixels[index + 1] === colour[1]
        && fillPixels[index + 2] === colour[2];
    };
    const addBoundary = (edges, start, end) => {
      const exits = edges.get(start) ?? [];
      exits.push(end);
      edges.set(start, exits);
    };
    for (const [key, count] of colours) {
      if (count < 4) continue;
      const colour = key.split(',').map(Number);
      const edges = new Map();
      for (let y = 0; y < 1200; y += 1) {
        for (let x = 0; x < 1200; x += 1) {
          if (!colourAt(x, y, colour)) continue;
          if (!colourAt(x, y - 1, colour)) {
            addBoundary(edges, pointKey(x, y), pointKey(x + 1, y));
          }
          if (!colourAt(x + 1, y, colour)) {
            addBoundary(edges, pointKey(x + 1, y), pointKey(x + 1, y + 1));
          }
          if (!colourAt(x, y + 1, colour)) {
            addBoundary(edges, pointKey(x + 1, y + 1), pointKey(x, y + 1));
          }
          if (!colourAt(x - 1, y, colour)) {
            addBoundary(edges, pointKey(x, y + 1), pointKey(x, y));
          }
        }
      }
      const loops = [];
      while (edges.size) {
        const [start, exits] = edges.entries().next().value;
        const loop = [start];
        let current = exits.pop();
        if (!exits.length) edges.delete(start);
        let guard = 0;
        while (current !== start && guard < 100000) {
          loop.push(current);
          const next = edges.get(current);
          if (!next?.length) break;
          current = next.pop();
          if (!next.length) edges.delete(loop.at(-1));
          guard += 1;
        }
        if (current === start && loop.length > 2) loops.push(loop.map(pointFrom));
      }
      if (!loops.length) continue;
      const fillPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      fillPath.setAttribute('d', loops.map((loop) => loop.map(([x, y], index) => (
        `${index ? 'L' : 'M'}${x - 600},${y - 600}`
      )).join('') + 'Z').join(''));
      fillPath.setAttribute(
        'fill',
        `#${colour.map((channel) => channel.toString(16).padStart(2, '0')).join('')}`,
      );
      fillPath.setAttribute('fill-rule', 'evenodd');
      svg.append(fillPath);
    }

    const cross = (ax, ay, bx, by) => ax * by - ay * bx;
    const intersection = (a, b, c, d) => {
      const rx = b.x - a.x;
      const ry = b.y - a.y;
      const sx = d.x - c.x;
      const sy = d.y - c.y;
      const denominator = cross(rx, ry, sx, sy);
      if (Math.abs(denominator) < 1e-10) return null;
      const qx = c.x - a.x;
      const qy = c.y - a.y;
      const t = cross(qx, qy, sx, sy) / denominator;
      const u = cross(qx, qy, rx, ry) / denominator;
      return t > 1e-8 && t < 1 - 1e-8 && u >= -1e-8 && u <= 1 + 1e-8
        ? t
        : null;
    };
    const barycentric = (x, y, triangle) => {
      const [a, b, c] = triangle.points;
      const alpha = ((b.y - c.y) * (x - c.x) + (c.x - b.x) * (y - c.y))
        / triangle.area;
      const beta = ((c.y - a.y) * (x - c.x) + (a.x - c.x) * (y - c.y))
        / triangle.area;
      const gamma = 1 - alpha - beta;
      return [alpha, beta, gamma];
    };
    const inside = (weights) => weights.every((weight) => weight >= -1e-7);
    const pointAt = (line, t) => ({
      x: line.a.x + (line.b.x - line.a.x) * t,
      y: line.a.y + (line.b.y - line.a.y) * t,
      z: line.a.z + (line.b.z - line.a.z) * t,
    });
    const paths = new Map([[0.75, []], [1.25, []]]);
    for (const line of lineSegments) {
      const xmin = Math.min(line.a.x, line.b.x);
      const xmax = Math.max(line.a.x, line.b.x);
      const ymin = Math.min(line.a.y, line.b.y);
      const ymax = Math.max(line.a.y, line.b.y);
      const candidates = triangles.filter((triangle) => !(
        triangle.xmax < xmin || triangle.xmin > xmax
        || triangle.ymax < ymin || triangle.ymin > ymax
      ));
      const cuts = [0, 1];
      for (const triangle of candidates) {
        for (let edge = 0; edge < 3; edge += 1) {
          const t = intersection(
            line.a,
            line.b,
            triangle.points[edge],
            triangle.points[(edge + 1) % 3],
          );
          if (t !== null) cuts.push(t);
        }
      }
      cuts.sort((a, b) => a - b);
      const unique = cuts.filter(
        (cut, index) => index === 0 || Math.abs(cut - cuts[index - 1]) > 1e-6,
      );
      for (let index = 0; index + 1 < unique.length; index += 1) {
        const start = unique[index];
        const end = unique[index + 1];
        if (end - start < 1e-6) continue;
        const middle = pointAt(line, (start + end) / 2);
        const occluded = candidates.some((triangle) => {
          const weights = barycentric(middle.x, middle.y, triangle);
          if (!inside(weights)) return false;
          const depth = weights.reduce(
            (sum, weight, vertex) => sum + weight * triangle.points[vertex].z,
            0,
          );
          return depth < middle.z - 2e-5;
        });
        if (occluded) continue;
        const a = pointAt(line, start);
        const b = pointAt(line, end);
        paths.get(line.width).push(
          `M${(a.x * 600).toFixed(2)},${(-a.y * 600).toFixed(2)}`
          + `L${(b.x * 600).toFixed(2)},${(-b.y * 600).toFixed(2)}`,
        );
      }
    }
    for (const [width, segments] of paths) {
      if (!segments.length) continue;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', segments.join(''));
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', '#151515');
      path.setAttribute('stroke-width', String(width));
      path.setAttribute('vector-effect', 'non-scaling-stroke');
      path.setAttribute('stroke-linejoin', 'round');
      path.setAttribute('stroke-linecap', 'round');
      svg.append(path);
    }
    for (const path of svg.querySelectorAll('path')) {
      path.setAttribute('vector-effect', 'non-scaling-stroke');
      path.setAttribute('stroke-linejoin', 'round');
      path.setAttribute('stroke-linecap', 'round');
    }
    return '<?xml version="1.0" encoding="UTF-8"?>\n'
      + new XMLSerializer().serializeToString(svg);
  }, name);
  await writeFile(join(outDir, `drawing-${name}.svg`), markup);
}

await writeDrawing('open');

await page.click('.viewer .pill[data-variant="closed"]');
await page.waitForFunction(
  () => document.querySelector('.viewer-status')?.hidden === true,
  null,
  { timeout: 30000 },
);
await page.waitForTimeout(250);
await writeDrawing('closed');

if (problems.length) console.log(`console problems:\n  ${problems.join('\n  ')}`);
await browser.close();
server.close();
console.log(`wrote drawing SVGs to ${outDir}`);
