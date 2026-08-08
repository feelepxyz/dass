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
    const dimSegments = [];
    const dimLabels = [];
    const projected = (point) => point.clone().project(state.camera);
    const worldVertex = (attribute, index, matrix) => new THREE.Vector3()
      .fromBufferAttribute(attribute, index)
      .applyMatrix4(matrix);
    // One em of the model, along the up the screen is showing: the viewer sizes
    // its values in millimetres so this projection reletters them at the size
    // they are drawn at.
    const screenUp = new THREE.Vector3(0, 1, 0).applyQuaternion(state.camera.quaternion);
    const drawn = [];
    const materialSides = new Map();
    // Every drawn line the viewer builds is a screen-space quad, which is a
    // mesh: its two ends live in the instanced start and end attributes rather
    // than in a position pair, and it must never be read as a solid.
    const linework = (node) => {
      const stroke = node.userData.stroke;
      if (!stroke) throw new Error(`drawn line ${node.uuid} carries no stroke style`);
      const start = node.geometry.attributes.instanceStart;
      const end = node.geometry.attributes.instanceEnd;
      const found = [];
      for (let index = 0; index < start.count; index += 1) {
        found.push({
          a: projected(worldVertex(start, index, node.matrixWorld)),
          b: projected(worldVertex(end, index, node.matrixWorld)),
          width: stroke.width,
          color: stroke.color,
        });
      }
      return found;
    };
    state.current.traverse((node) => {
      // A dimension is drawn over the building: the set never lets geometry cut
      // a measurement, so these are collected whole and never occlude anything.
      if (node.userData.dimText) {
        drawn.push([node, node.visible]);
        node.visible = false;
        const seat = new THREE.Vector3().setFromMatrixPosition(node.matrixWorld);
        const anchor = projected(seat);
        const rise = projected(seat.clone().addScaledVector(screenUp, node.userData.dimText.em));
        dimLabels.push({
          text: node.userData.dimText.text,
          x: anchor.x * 600,
          y: -anchor.y * 600,
          size: Math.abs(anchor.y - rise.y) * 600,
        });
        return;
      }
      if (node.userData.isDim) {
        drawn.push([node, node.visible]);
        node.visible = false;
        if (node.geometry) dimSegments.push(...linework(node));
        return;
      }
      if (node.userData.isEdge) {
        // The viewer owns the plate weights and stamps them on every line it
        // builds, so nothing here restates them.
        drawn.push([node, node.visible]);
        node.visible = false;
        lineSegments.push(...linework(node));
        return;
      }
      if (!node.isMesh) return;
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
      antialias: false,
      preserveDrawingBuffer: true,
      alpha: false,
    });
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setPixelRatio(1);
    renderer.setSize(1200, 1200, false);
    renderer.setClearColor(0xffffff, 1);
    const groundVisible = state.ground.visible;
    state.ground.visible = false;
    const readCanvas = document.createElement('canvas');
    readCanvas.width = 1200;
    readCanvas.height = 1200;
    const readContext = readCanvas.getContext('2d', { willReadFrequently: true });
    const capture = () => {
      renderer.render(state.scene, state.camera);
      readContext.drawImage(renderer.domElement, 0, 0);
      return readContext.getImageData(0, 0, 1200, 1200).data;
    };
    // Where the building is at all, whatever it is made of. The silhouette is
    // what a sheet draws heaviest, and it is also what fills the drawing white:
    // white timber leaves no colour to trace, and an unfilled SVG would take
    // the colour of whatever it is laid over.
    const MASK = 0xff00ff;
    state.scene.overrideMaterial = new THREE.MeshBasicMaterial({
      color: MASK, side: THREE.DoubleSide,
    });
    const maskPixels = capture();
    state.scene.overrideMaterial.dispose();
    state.scene.overrideMaterial = null;
    const fillPixels = capture();
    // The line finish is flat MeshBasicMaterial fills, so any colour outside the
    // palette is antialiasing or sRGB rounding, not information. Snap it back.
    const palette = [...state.palette, 0xffffff].map((hex) => [
      (hex >> 16) & 255, (hex >> 8) & 255, hex & 255,
    ]);
    for (let index = 0; index < fillPixels.length; index += 4) {
      let nearest = palette[0];
      let shortest = Infinity;
      for (const tone of palette) {
        const distance = (fillPixels[index] - tone[0]) ** 2
          + (fillPixels[index + 1] - tone[1]) ** 2
          + (fillPixels[index + 2] - tone[2]) ** 2;
        if (distance < shortest) {
          shortest = distance;
          nearest = tone;
        }
      }
      fillPixels[index] = nearest[0];
      fillPixels[index + 1] = nearest[1];
      fillPixels[index + 2] = nearest[2];
    }
    renderer.dispose();
    state.ground.visible = groundVisible;
    for (const [line, visible] of drawn) line.visible = visible;
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
    description.textContent = 'Orthographic projection with white framing, pale panels, and black construction outlines.';
    svg.append(title, description);

    const pointKey = (x, y) => y * 1201 + x;
    const pointFrom = (key) => [key % 1201, Math.floor(key / 1201)];
    const addBoundary = (edges, start, end) => {
      const exits = edges.get(start) ?? [];
      exits.push(end);
      edges.set(start, exits);
    };
    // Marching squares: every pixel of a region contributes the sides it does
    // not share with its own kind, and the sides are then walked into loops.
    const trace = (holds) => {
      const filled = (x, y) => x >= 0 && y >= 0 && x < 1200 && y < 1200 && holds(x, y);
      const edges = new Map();
      for (let y = 0; y < 1200; y += 1) {
        for (let x = 0; x < 1200; x += 1) {
          if (!filled(x, y)) continue;
          if (!filled(x, y - 1)) addBoundary(edges, pointKey(x, y), pointKey(x + 1, y));
          if (!filled(x + 1, y)) {
            addBoundary(edges, pointKey(x + 1, y), pointKey(x + 1, y + 1));
          }
          if (!filled(x, y + 1)) {
            addBoundary(edges, pointKey(x + 1, y + 1), pointKey(x, y + 1));
          }
          if (!filled(x - 1, y)) addBoundary(edges, pointKey(x, y + 1), pointKey(x, y));
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
      return loops;
    };
    const outline = (loops) => loops.map((loop) => loop.map(([x, y], index) => (
      `${index ? 'L' : 'M'}${x - 600},${y - 600}`
    )).join('') + 'Z').join('');

    // The silhouette, laid down first: white under everything, and cut at the
    // section weight the sheets give an outer edge.
    const maskLoops = trace((x, y) => maskPixels[(y * 1200 + x) * 4 + 1] < 128);
    if (maskLoops.length) {
      const mask = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      mask.setAttribute('d', outline(maskLoops));
      mask.setAttribute('fill', '#ffffff');
      mask.setAttribute('fill-rule', 'evenodd');
      mask.setAttribute('stroke', '#000000');
      mask.setAttribute('stroke-width', '1.4');
      svg.append(mask);
    }

    const colours = new Map();
    for (let index = 0; index < fillPixels.length; index += 4) {
      const red = fillPixels[index];
      const green = fillPixels[index + 1];
      const blue = fillPixels[index + 2];
      if (red === 255 && green === 255 && blue === 255) continue;
      const key = `${red},${green},${blue}`;
      colours.set(key, (colours.get(key) ?? 0) + 1);
    }
    for (const [key, count] of colours) {
      if (count < 4) continue;
      const colour = key.split(',').map(Number);
      const loops = trace((x, y) => {
        const index = (y * 1200 + x) * 4;
        return fillPixels[index] === colour[0]
          && fillPixels[index + 1] === colour[1]
          && fillPixels[index + 2] === colour[2];
      });
      if (!loops.length) continue;
      const fillPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      fillPath.setAttribute('d', outline(loops));
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
    const paths = new Map();
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
        const style = `${line.width}:${line.color}`;
        if (!paths.has(style)) paths.set(style, []);
        paths.get(style).push(
          `M${(a.x * 600).toFixed(2)},${(-a.y * 600).toFixed(2)}`
          + `L${(b.x * 600).toFixed(2)},${(-b.y * 600).toFixed(2)}`,
        );
      }
    }
    // Draw order is load-bearing: the hairline board joints have to sit under
    // the object lines, so the thinner stroke is emitted first.
    const ordered = [...paths].sort(([a], [b]) => parseFloat(a) - parseFloat(b));
    for (const [style, segments] of ordered) {
      if (!segments.length) continue;
      const [width, color] = style.split(':');
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', segments.join(''));
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', color);
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

    // The measurements go on last and whole. A sheet draws a dimension over its
    // geometry, so these are never clipped against it. Every dimension the
    // viewer builds carries the one blue hairline, so they share a path.
    if (dimSegments.length) {
      const runs = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      runs.setAttribute('d', dimSegments.map((line) => (
        `M${(line.a.x * 600).toFixed(2)},${(-line.a.y * 600).toFixed(2)}`
        + `L${(line.b.x * 600).toFixed(2)},${(-line.b.y * 600).toFixed(2)}`
      )).join(''));
      runs.setAttribute('fill', 'none');
      runs.setAttribute('stroke', dimSegments[0].color);
      runs.setAttribute('stroke-width', String(dimSegments[0].width));
      runs.setAttribute('vector-effect', 'non-scaling-stroke');
      runs.setAttribute('stroke-linecap', 'round');
      svg.append(runs);
    }
    // A standalone SVG inherits none of the page's typography, so the value
    // states its own face and falls back to whatever mono the reader has.
    for (const label of dimLabels) {
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', label.x.toFixed(2));
      text.setAttribute('y', label.y.toFixed(2));
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('dominant-baseline', 'central');
      text.setAttribute('fill', '#1668c4');
      text.setAttribute(
        'font-family',
        'InputMono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      );
      text.setAttribute('font-size', label.size.toFixed(1));
      text.setAttribute('letter-spacing', '0.04em');
      text.textContent = label.text;
      svg.append(text);
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
