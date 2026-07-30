// The timber pipeline: how a CAD solid becomes a textured board.
//
// Shared by the photoreal renderer (scene.mjs) and by the model viewer inside
// the cut guide, so a board carries the same grain, the same per-board tone and
// the same lap in both. Nothing here touches a scene, a camera or a light: it
// takes meshes and textures and gives them UVs and materials.
//
// The exported GLB carries positions and normals only, so every UV on the model
// is generated here at load time.
import * as THREE from 'three';

// Physical size the wood sheet covers, in millimetres. Smaller numbers mean
// tighter grain; birch ply faces are roughly this scale.
export const WOOD_SPAN_MM = { u: 980, v: 552 };
export const CORRUGATION_PITCH_MM = 76;

// Categories the workshop builds out of råspont boards rather than as a sheet.
// CAD draws each of them as one solid panel; this cuts them back into boards so
// no two neighbours carry the same figure.
export const PLANK_CATEGORIES = /^(?:.*cladding|floor|seat top|seat side|roof board)$/;
// Coprime with the atlas cell count, so stepping across a wall never lands two
// adjacent boards on the same strip.
const PLANK_SLOT_STRIDE = 3;

// Both the framing and the boards come off the same photographed timber, so
// these tints only lift or knock back what the photo already carries: the
// planed frame a touch paler and cooler than the sawn cladding around it.
export const MATERIALS = {
  wood: { tint: 0xe4dbcd, roughness: 0.74 },
  cladding: { tint: 0xf4ead8, roughness: 0.66 },
  'dark wood': { tint: 0x8d7861, roughness: 0.6 },
  metal: { tint: 0x3a3d40, roughness: 0.38, metalness: 1.0 },
  // Corrugated sheet: painted black on top, bare galvanised underneath.
  'roof top': { tint: 0x17191a, roughness: 0.44, metalness: 0.72 },
  'roof under': { tint: 0xd2d6da, roughness: 0.45, metalness: 0.55 },
};

export function hash(string) {
  let h = 2166136261;
  for (let i = 0; i < string.length; i += 1) {
    h ^= string.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

/**
 * The exporter emits one mesh per box face, named `<part>_1` ... `<part>_6`,
 * so a mesh name has to be walked back to the part it came from. Part names
 * can themselves end in a number (`hinge_fixed_1`), hence the loop.
 */
export function partKeyFor(parts, name) {
  let key = name;
  while (!(key in parts)) {
    const cut = key.lastIndexOf('_');
    if (cut < 0 || !/^\d+$/.test(key.slice(cut + 1))) return null;
    key = key.slice(0, cut);
  }
  return key;
}

export function loadTexture(url, colorSpace, options = {}) {
  const {
    wrapS = THREE.RepeatWrapping,
    wrapT = wrapS,
    anisotropy = 1,
  } = options;
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(url, (texture) => {
      texture.wrapS = wrapS;
      texture.wrapT = wrapT;
      texture.colorSpace = colorSpace;
      texture.anisotropy = anisotropy;
      resolve(texture);
    }, undefined, reject);
  });
}

/**
 * Per-triangle box mapping: the grain runs along `grainAxis`, and each face
 * samples the sheet in the plane it actually faces, so faces and end grain are
 * never stretched. A per-part offset stops neighbouring boards repeating the
 * same figure.
 */
export function applyBoxUVs(mesh, grainAxis, seed, spanU, spanV) {
  let geometry = mesh.geometry;
  if (geometry.index) {
    geometry = geometry.toNonIndexed();
    mesh.geometry = geometry;
  }
  const offsetU = hash(`${seed}:u`) * spanU;
  const offsetV = hash(`${seed}:v`) * spanV;

  const position = geometry.attributes.position;
  const uv = new Float32Array(position.count * 2);
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const point = new THREE.Vector3();

  for (let i = 0; i < position.count; i += 3) {
    a.fromBufferAttribute(position, i);
    b.fromBufferAttribute(position, i + 1);
    c.fromBufferAttribute(position, i + 2);
    normal.copy(b).sub(a).cross(c.sub(a));
    const n = [Math.abs(normal.x), Math.abs(normal.y), Math.abs(normal.z)];
    const facing = n.indexOf(Math.max(...n));
    const uAxis = grainAxis === facing ? (facing === 0 ? 1 : 0) : grainAxis;
    const vAxis = 3 - facing - uAxis;
    for (let k = 0; k < 3; k += 1) {
      point.fromBufferAttribute(position, i + k);
      const p = point.toArray();
      uv[(i + k) * 2] = (p[uAxis] + offsetU) / spanU;
      uv[(i + k) * 2 + 1] = (p[vAxis] + offsetV) / spanV;
    }
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

/** Total area of a mesh, and its area-weighted normal, in geometry space. */
function faceArea(geometry, normal) {
  const position = geometry.attributes.position;
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  let area = 0;
  normal.set(0, 0, 0);
  for (let i = 0; i < position.count; i += 3) {
    a.fromBufferAttribute(position, i);
    b.fromBufferAttribute(position, i + 1);
    c.fromBufferAttribute(position, i + 2);
    b.sub(a).cross(c.sub(a));
    area += b.length() * 0.5;
    normal.add(b);
  }
  normal.normalize();
  return area;
}

/**
 * How a boarded panel is laid out: the face it presents, the way its boards
 * run, the way they stack, and its extent along each. Taken from the mesh
 * normals rather than the bounding box, because the open door arrives rotated
 * about its hinge and its box then says nothing about which way the boards go.
 */
export function plankFrame(group) {
  const normal = new THREE.Vector3();
  const candidate = new THREE.Vector3();
  let widest = 0;
  for (const mesh of group.meshes) {
    const area = faceArea(mesh.geometry, candidate);
    if (area > widest) {
      widest = area;
      normal.copy(candidate);
    }
  }

  // Boards stand upright wherever the panel does; a floor or a seat top lays
  // them front to back instead. Geometry space is the CAD frame, so Z is up.
  const along = new THREE.Vector3(0, 0, 1).addScaledVector(normal, -normal.z);
  if (along.lengthSq() < 0.05) along.set(0, 1, 0).addScaledVector(normal, -normal.y);
  along.normalize();
  const across = new THREE.Vector3().crossVectors(normal, along).normalize();

  const frame = {
    normal,
    along,
    across,
    origin: { along: Infinity, across: Infinity, thick: Infinity },
    alongSpan: 0,
  };
  let alongMax = -Infinity;
  const point = new THREE.Vector3();
  for (const mesh of group.meshes) {
    const position = mesh.geometry.attributes.position;
    for (let i = 0; i < position.count; i += 1) {
      point.fromBufferAttribute(position, i);
      const reach = point.dot(along);
      frame.origin.along = Math.min(frame.origin.along, reach);
      frame.origin.across = Math.min(frame.origin.across, point.dot(across));
      frame.origin.thick = Math.min(frame.origin.thick, point.dot(normal));
      alongMax = Math.max(alongMax, reach);
    }
  }
  frame.alongSpan = alongMax - frame.origin.along;
  return frame;
}

/** Sutherland-Hodgman clip of a convex polygon down to one board's slab. */
function clipToSlab(polygon, axis, low, width) {
  let clipped = polygon;
  for (const [limit, sign] of [[low, 1], [low + width, -1]]) {
    const kept = [];
    for (let i = 0; i < clipped.length; i += 1) {
      const a = clipped[i];
      const b = clipped[(i + 1) % clipped.length];
      const da = sign * (a.dot(axis) - limit);
      const db = sign * (b.dot(axis) - limit);
      if (da >= 0) kept.push(a);
      if ((da >= 0) !== (db >= 0)) kept.push(a.clone().lerp(b, da / (da - db)));
    }
    if (kept.length < 3) return kept;
    clipped = kept;
  }
  return clipped;
}

/** Which strip a board takes, which way round it is laid, and its own colour. */
function boardStyle(key, board, atlas, slack) {
  const seed = `${key}:${board}`;
  const spin = Math.floor(hash(`${key}:spin`) * atlas.cells);
  const slot = (board * PLANK_SLOT_STRIDE + spin) % atlas.cells;
  return {
    slot: (slot + atlas.cells) % atlas.cells,
    offset: hash(`${seed}:offset`) * slack,
    flipAlong: hash(`${seed}:flip`) < 0.5,
    flipAcross: hash(`${seed}:turn`) < 0.5,
    tone: 1 + (hash(`${seed}:tone`) - 0.5) * 0.16,
    warm: 1 + (hash(`${seed}:warm`) - 0.5) * 0.05,
  };
}

/**
 * Cut a panel into boards and give each one its own strip of the atlas.
 *
 * Every triangle is clipped to the slabs the boards cover, so a board boundary
 * becomes a real edge in the geometry and its UVs can jump there. Each board
 * then draws a different cell, laid either way round and started at a different
 * point along its length, and carries its own tone as a vertex colour.
 */
export function applyPlankUVs(mesh, frame, key, atlas) {
  const position = mesh.geometry.attributes.position;
  const normals = mesh.geometry.attributes.normal;
  const cover = atlas.coverMm / atlas.boardMm;
  // Half the lap, kept clear at both edges of the cell so filtering at the
  // smaller mip levels never reaches into the strip next door.
  const inset = (1 - cover) / 2;
  const slack = Math.max(0, atlas.lengthMm - frame.alongSpan);

  const positions = [];
  const outNormals = [];
  const uvs = [];
  const colors = [];
  const triangle = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const faceNormal = new THREE.Vector3();
  const styles = new Map();

  for (let i = 0; i < position.count; i += 3) {
    for (let k = 0; k < 3; k += 1) triangle[k].fromBufferAttribute(position, i + k);
    faceNormal.fromBufferAttribute(normals, i);
    // A board's lapped edge takes its width from the board's thickness; its
    // face and its sawn end take theirs from the run across the panel.
    const lapped = Math.abs(faceNormal.dot(frame.across)) > 0.5;

    const reach = triangle.map((p) => p.dot(frame.across) - frame.origin.across);
    const first = Math.max(0, Math.floor(Math.min(...reach) / atlas.coverMm));
    const last = Math.floor(Math.max(Math.max(...reach) - 1e-3, 0) / atlas.coverMm);
    for (let board = first; board <= last; board += 1) {
      const low = frame.origin.across + board * atlas.coverMm;
      const polygon = clipToSlab(triangle, frame.across, low, atlas.coverMm);
      if (polygon.length < 3) continue;
      if (!styles.has(board)) styles.set(board, boardStyle(key, board, atlas, slack));
      const style = styles.get(board);
      for (let fan = 1; fan < polygon.length - 1; fan += 1) {
        for (const p of [polygon[0], polygon[fan], polygon[fan + 1]]) {
          const thick = p.dot(frame.normal) - frame.origin.thick;
          // Only one of these varies over any given face, so the same
          // expression serves the board's face, its edge and its end.
          let u = (p.dot(frame.along) - frame.origin.along + thick + style.offset) / atlas.lengthMm;
          let v = (lapped ? thick : p.dot(frame.across) - low) / atlas.boardMm;
          if (style.flipAlong) u = -u;
          if (style.flipAcross) v = cover - v;
          positions.push(p.x, p.y, p.z);
          outNormals.push(faceNormal.x, faceNormal.y, faceNormal.z);
          uvs.push(u, (style.slot + inset + v) / atlas.cells);
          colors.push(style.tone * style.warm, style.tone, style.tone / style.warm);
        }
      }
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(outNormals, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  mesh.geometry = geometry;
}

/**
 * Planar UVs on fixed axes. The roof needs its corrugations pinned to world
 * axes -- running down the slope, rippling across the width -- rather than
 * inferred per face like the timber.
 */
export function applyPlanarUVs(mesh, uAxis, vAxis, spanU, spanV) {
  let geometry = mesh.geometry;
  if (geometry.index) {
    geometry = geometry.toNonIndexed();
    mesh.geometry = geometry;
  }
  const position = geometry.attributes.position;
  const uv = new Float32Array(position.count * 2);
  const point = new THREE.Vector3();
  for (let i = 0; i < position.count; i += 1) {
    const p = point.fromBufferAttribute(position, i).toArray();
    uv[i * 2] = p[uAxis] / spanU;
    uv[i * 2 + 1] = p[vAxis] / spanV;
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

/** Average world normal of a mesh, used to tell the roof's faces apart. */
export function averageNormal(mesh) {
  const attribute = mesh.geometry.attributes.normal;
  const sum = new THREE.Vector3();
  const one = new THREE.Vector3();
  for (let i = 0; i < attribute.count; i += 1) {
    sum.add(one.fromBufferAttribute(attribute, i));
  }
  return sum.normalize().applyQuaternion(mesh.getWorldQuaternion(new THREE.Quaternion()));
}

/**
 * Group the exporter's per-face meshes back into the parts they came from, so
 * grain direction and tone are decided once per board rather than once per
 * face. The box is kept in geometry space, which is what the UV passes read
 * positions in.
 */
export function groupByPart(root, parts) {
  const groups = new Map();
  root.traverse((child) => {
    if (!child.isMesh) return;
    const key = partKeyFor(parts, child.name) ?? child.name;
    const part = parts[key] ?? {};
    const planked = PLANK_CATEGORIES.test(part.category ?? '');
    let role = part.material ?? 'wood';
    if (role === 'wood' && planked) role = 'cladding';
    if (!groups.has(key)) groups.set(key, { role, planked, meshes: [], box: new THREE.Box3() });
    const group = groups.get(key);
    group.meshes.push(child);
    child.geometry.computeBoundingBox();
    group.box.union(child.geometry.boundingBox);
  });
  return groups;
}

/**
 * Give every mesh under `root` its UVs and its timber material.
 *
 * `textures` carries the sheet maps, `plank` the board atlas maps, and `atlas`
 * the atlas geometry from the render manifest. Returns the part groups so a
 * caller can key picking or highlighting off the same grouping.
 */
export function dressModel(root, { parts, textures, plank, atlas }) {
  const { corrugation } = textures;
  const cache = new Map();
  const baseFor = (role, planked = false) => {
    const cacheKey = `${role}:${planked}`;
    if (cache.has(cacheKey)) return cache.get(cacheKey);
    const spec = MATERIALS[role] ?? MATERIALS.wood;
    const metal = (spec.metalness ?? 0) > 0.5;
    const { map, normalMap, roughnessMap } = planked ? plank : textures;
    const material = new THREE.MeshStandardMaterial({
      color: spec.tint,
      roughness: spec.roughness,
      metalness: spec.metalness ?? 0,
      map: metal ? null : map,
      normalMap: metal ? corrugation : normalMap,
      normalScale: metal ? new THREE.Vector2(1, 1) : new THREE.Vector2(0.12, 0.12),
      roughnessMap: metal ? null : roughnessMap,
      // Boarded panels carry a per-board tone in their vertex colours.
      vertexColors: planked,
      side: THREE.DoubleSide,
      shadowSide: THREE.DoubleSide,
    });
    cache.set(cacheKey, material);
    return material;
  };

  // Real timber is never uniform: nudge each part's tone and roughness a
  // little so butted boards read as separate pieces.
  const woodMaterialFor = (role, planked, seed) => {
    const base = baseFor(role, planked);
    const material = base.clone();
    const shift = (hash(`${seed}:tone`) - 0.5) * 0.14;
    material.color.copy(base.color).offsetHSL(
      (hash(`${seed}:hue`) - 0.5) * 0.02,
      (hash(`${seed}:sat`) - 0.5) * 0.10,
      shift * 0.5,
    );
    material.roughness = THREE.MathUtils.clamp(base.roughness + shift * 0.5, 0.35, 0.95);
    return material;
  };

  const groups = groupByPart(root, parts);
  for (const [key, group] of groups) {
    let frame = null;
    if (group.planked) {
      for (const mesh of group.meshes) {
        if (mesh.geometry.index) mesh.geometry = mesh.geometry.toNonIndexed();
      }
      frame = plankFrame(group);
    }
    const extent = group.box.getSize(new THREE.Vector3()).toArray();
    const grainAxis = extent.indexOf(Math.max(...extent));
    for (const mesh of group.meshes) {
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      if (group.role === 'metal roof') {
        mesh.material = baseFor(averageNormal(mesh).y > 0.5 ? 'roof top' : 'roof under');
        // Corrugations run down the slope (Z), so they ripple across the
        // width (X): one texture period per corrugation pitch.
        applyPlanarUVs(mesh, 2, 0, CORRUGATION_PITCH_MM * 8, CORRUGATION_PITCH_MM);
      } else if (group.role === 'metal') {
        mesh.material = baseFor('metal');
      } else if (group.planked) {
        mesh.material = woodMaterialFor(group.role, true, key);
        applyPlankUVs(mesh, frame, key, atlas);
      } else {
        mesh.material = woodMaterialFor(group.role, false, key);
        applyBoxUVs(mesh, grainAxis, key, WOOD_SPAN_MM.u * 0.34, WOOD_SPAN_MM.v * 0.34);
      }
    }
  }
  return groups;
}
