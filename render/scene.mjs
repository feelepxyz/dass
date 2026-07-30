// Browser half of the photoreal renderer.  Node (render.mjs) drives this page
// through Playwright: `loadModel` once per variant, then `renderView` per shot.
//
// The CAD exporter writes the glTF Y-up convention, so the model arrives
// upright with its door facing +Z.  Camera angles are given as azimuth
// (0 = looking at the door, +90 = from the right) and elevation, in degrees.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { Sky } from 'three/addons/objects/Sky.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
// The timber pipeline is shared with the cut guide's model viewer.
import { dressModel, loadTexture } from './materials.mjs';

const DEG = Math.PI / 180;

const state = {};

function makeGroundTexture() {
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext('2d');
  context.fillStyle = '#8b8478';
  context.fillRect(0, 0, size, size);

  // Blotches at a few scales stop the ground reading as flat paper.
  let seed = 20260730;
  const random = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (seed >>> 8) / 8388608;
  };
  for (const [count, radius, alpha] of [[70, 70, 0.035], [400, 18, 0.045], [6000, 3, 0.07]]) {
    for (let i = 0; i < count; i += 1) {
      const tone = 90 + random() * 90;
      context.fillStyle = `rgba(${tone | 0}, ${(tone * 0.97) | 0}, ${(tone * 0.9) | 0}, ${alpha})`;
      context.beginPath();
      context.arc(random() * size, random() * size, radius * (0.4 + random()), 0, Math.PI * 2);
      context.fill();
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(9, 9);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

async function boot(config) {
  const canvas = document.createElement('canvas');
  document.body.append(canvas);
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    preserveDrawingBuffer: true,
    alpha: true,
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  state.renderer = renderer;

  state.composerTarget = new THREE.WebGLRenderTarget(1, 1, {
    type: THREE.HalfFloatType,
    colorSpace: THREE.LinearSRGBColorSpace,
    samples: 4,
  });

  state.pmrem = new THREE.PMREMGenerator(renderer);
  state.pmrem.compileEquirectangularShader();

  const scene = new THREE.Scene();
  state.scene = scene;

  const sky = new Sky();
  sky.scale.setScalar(450000);
  sky.material.uniforms.turbidity.value = 5;
  sky.material.uniforms.rayleigh.value = 2.6;
  sky.material.uniforms.mieCoefficient.value = 0.004;
  sky.material.uniforms.mieDirectionalG.value = 0.8;
  state.sky = sky;
  state.skyScene = new THREE.Scene();
  state.skyScene.add(sky);

  const sun = new THREE.DirectionalLight(0xffeed0, 6.5);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.radius = 2.5;
  sun.shadow.bias = -0.0004;
  sun.shadow.normalBias = 2;
  scene.add(sun);
  scene.add(sun.target);
  state.sun = sun;

  // Follows the camera on the orthographic elevations so faces the sun misses
  // (undersides, the back) still read as shaped rather than flat.
  const headlight = new THREE.DirectionalLight(0xf2f6ff, 0);
  scene.add(headlight);
  scene.add(headlight.target);
  state.headlight = headlight;

  state.groundMaterial = new THREE.MeshStandardMaterial({
    map: makeGroundTexture(), roughness: 1.0, metalness: 0,
  });
  state.shadowMaterial = new THREE.ShadowMaterial({ opacity: 0.55 });
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), state.groundMaterial);
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  ground.renderOrder = -1;
  scene.add(ground);
  state.ground = ground;

  const anisotropy = state.renderer.capabilities.getMaxAnisotropy();
  const [map, normalMap, roughnessMap, corrugation] = await Promise.all([
    loadTexture(config.woodColor, THREE.SRGBColorSpace, { anisotropy }),
    loadTexture(config.woodNormal, THREE.NoColorSpace, { anisotropy }),
    loadTexture(config.woodRoughness, THREE.NoColorSpace, { anisotropy }),
    loadTexture(config.corrugation, THREE.NoColorSpace, { anisotropy }),
  ]);
  state.textures = { map, normalMap, roughnessMap, corrugation };

  // The atlas stacks one board per cell, so v must stay inside the cell it was
  // given.  A board longer than a cell mirrors rather than showing a seam.
  const plankWrap = {
    wrapS: THREE.MirroredRepeatWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
    anisotropy,
  };
  const [plankMap, plankNormal, plankRoughness] = await Promise.all([
    loadTexture(config.plankColor, THREE.SRGBColorSpace, plankWrap),
    loadTexture(config.plankNormal, THREE.NoColorSpace, plankWrap),
    loadTexture(config.plankRoughness, THREE.NoColorSpace, plankWrap),
  ]);
  state.plank = { map: plankMap, normalMap: plankNormal, roughnessMap: plankRoughness };
  state.plankAtlas = config.plankAtlas;

  if (config.photo) {
    state.photoUrl = config.photo;
    const photo = await loadTexture(config.photo, THREE.SRGBColorSpace, { anisotropy });
    photo.mapping = THREE.EquirectangularReflectionMapping;
    // Not a real panorama, but it lends the model the plate's green bounce.
    state.photoEnv = state.pmrem.fromEquirectangular(photo).texture;
  }
}

async function loadModel(config) {
  if (state.root) {
    state.scene.remove(state.root);
    state.root.traverse((child) => {
      if (child.isMesh) child.geometry.dispose();
    });
  }
  const gltf = await new GLTFLoader().loadAsync(config.model);
  const root = gltf.scene;
  root.updateMatrixWorld(true);

  const groups = dressModel(root, {
    parts: config.parts,
    textures: state.textures,
    plank: state.plank,
    atlas: state.plankAtlas,
  });
  const roles = {};
  for (const group of groups.values()) {
    roles[group.role] = (roles[group.role] ?? 0) + 1;
  }

  state.scene.add(root);
  state.root = root;

  const box = new THREE.Box3().setFromObject(root);
  const center = box.getCenter(new THREE.Vector3());
  const sphere = box.getBoundingSphere(new THREE.Sphere());
  state.bounds = { box, center, radius: sphere.radius };
  state.ground.position.y = box.min.y;
  state.fog = new THREE.Fog(0xc6d3de, sphere.radius * 5, sphere.radius * 26);
  return {
    parts: groups.size,
    roles,
    min: box.min.toArray(),
    max: box.max.toArray(),
    radius: sphere.radius,
  };
}

function directionFrom(azimuthDeg, elevationDeg) {
  const azimuth = azimuthDeg * DEG;
  const elevation = elevationDeg * DEG;
  return new THREE.Vector3(
    Math.sin(azimuth) * Math.cos(elevation),
    Math.sin(elevation),
    Math.cos(azimuth) * Math.cos(elevation),
  );
}

function updateSun(view) {
  const azimuth = view.sunAzimuth ?? (view.azimuth ?? 0) - 42;
  const elevation = view.sunElevation ?? 48;
  const direction = directionFrom(azimuth, elevation);
  const { center, radius } = state.bounds;

  if (view.photo) {
    state.scene.environment = state.photoEnv;
  } else {
    state.sky.material.uniforms.sunPosition.value.copy(direction);
    if (state.envRT) state.envRT.dispose();
    state.envRT = state.pmrem.fromScene(state.skyScene);
    state.scene.environment = state.envRT.texture;
  }
  state.scene.environmentIntensity = view.envIntensity ?? (view.photo ? 0.55 : 0.40);

  const sun = state.sun;
  sun.position.copy(center).addScaledVector(direction, radius * 4);
  sun.target.position.copy(center);
  sun.target.updateMatrixWorld();
  sun.intensity = view.sunIntensity ?? 6.5;
  const extent = radius * 1.35;
  Object.assign(sun.shadow.camera, {
    left: -extent, right: extent, top: extent, bottom: -extent,
    near: radius * 0.5, far: radius * 8,
  });
  sun.shadow.camera.updateProjectionMatrix();
}

function fitOrthographic(camera, margin) {
  const corners = [];
  const { box } = state.bounds;
  for (const x of [box.min.x, box.max.x]) {
    for (const y of [box.min.y, box.max.y]) {
      for (const z of [box.min.z, box.max.z]) {
        corners.push(new THREE.Vector3(x, y, z).applyMatrix4(camera.matrixWorldInverse));
      }
    }
  }
  const halfWidth = Math.max(...corners.map((c) => Math.abs(c.x))) * margin;
  const halfHeight = Math.max(...corners.map((c) => Math.abs(c.y))) * margin;
  const aspect = camera.userData.aspect;
  const half = Math.max(halfWidth / aspect, halfHeight);
  camera.left = -half * aspect;
  camera.right = half * aspect;
  camera.top = half;
  camera.bottom = -half;
  camera.updateProjectionMatrix();
}

/**
 * Camera for a shot composited into a photograph: held level at a person's
 * height, far enough back that `frameWidth` millimetres of the scene fill the
 * frame.  That is what gives the model its scale against the real place.
 */
function photoCamera(view, aspect) {
  const { box, center } = state.bounds;
  const horizontal = 2 * Math.atan(view.frameWidth / 2 / view.distance);
  const fov = 2 * Math.atan(Math.tan(horizontal / 2) / aspect);
  const camera = new THREE.PerspectiveCamera(fov / DEG, aspect, 10, 400000);

  const direction = directionFrom(view.azimuth ?? 0, 0);
  const anchor = new THREE.Vector3(
    view.anchorX ?? center.x,
    (view.anchorY ?? box.min.y) + view.cameraHeight,
    view.anchorZ ?? center.z,
  );
  camera.position.copy(anchor).addScaledVector(direction, view.distance);

  // Look level, yawed and pitched only enough to place the model in frame.
  const target = anchor.clone();
  const lateral = new THREE.Vector3(-direction.z, 0, direction.x)
    .multiplyScalar((view.offsetX ?? 0) * view.frameWidth);
  target.add(lateral);
  target.y += (view.offsetY ?? 0) * view.frameWidth;
  camera.lookAt(target);
  return camera;
}

/**
 * Screen-space ambient occlusion does most of the work of making the joinery
 * read: without it, butted timbers of the same colour dissolve into each other.
 */
function renderComposed(camera, width, height, view) {
  const { renderer, scene } = state;
  if (!state.composer) {
    state.composer = new EffectComposer(renderer, state.composerTarget);
    state.renderPass = new RenderPass(scene, camera);
    state.gtao = new GTAOPass(scene, camera, width, height);
    state.gtao.output = GTAOPass.OUTPUT.Default;
    state.composer.addPass(state.renderPass);
    state.composer.addPass(state.gtao);
    state.composer.addPass(new OutputPass());
  }
  state.renderPass.camera = camera;
  state.renderPass.clearAlpha = view.photo ? 0 : 1;
  state.gtao.camera = camera;
  state.gtao.updateGtaoMaterial({
    radius: view.aoRadius ?? 90,
    distanceExponent: 1.4,
    thickness: 120,
    scale: view.aoScale ?? 1.4,
    samples: 16,
    screenSpaceRadius: false,
  });
  state.composer.setSize(width, height);
  state.gtao.setSize(width, height);
  state.composer.render();
}

/** A touch of vignette and sensor grain; enough to read as a photograph. */
function applyFilmLook(context, size, strength = 1) {
  const frame = context.getImageData(0, 0, size.width, size.height);
  const data = frame.data;
  const cx = size.width / 2;
  const cy = size.height / 2;
  const maxRadius = Math.hypot(cx, cy);
  let seed = 987654321;
  for (let y = 0; y < size.height; y += 1) {
    for (let x = 0; x < size.width; x += 1) {
      const i = (y * size.width + x) * 4;
      const falloff = 1 - 0.22 * strength * (Math.hypot(x - cx, y - cy) / maxRadius) ** 2.4;
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      const grain = ((seed >>> 12) % 255) / 255 - 0.5;
      for (let c = 0; c < 3; c += 1) {
        data[i + c] = Math.max(0, Math.min(255, data[i + c] * falloff + grain * 4.5 * strength));
      }
    }
  }
  context.putImageData(frame, 0, 0);
}

/** Draw the background photograph, cropped to fill the frame. */
async function drawPlate(context, size) {
  if (!state.plate) {
    state.plate = await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = state.photoUrl;
    });
  }
  const image = state.plate;
  const scale = Math.max(size.width / image.width, size.height / image.height);
  const width = image.width * scale;
  const height = image.height * scale;
  context.drawImage(image, (size.width - width) / 2, (size.height - height) / 2, width, height);
}

async function renderView(view, size) {
  const { renderer, scene, bounds } = state;
  const width = size.width * size.supersample;
  const height = size.height * size.supersample;
  renderer.setSize(width, height, false);
  renderer.toneMappingExposure = view.exposure ?? 0.44;

  const aspect = width / height;
  const orthographic = view.projection === 'orthographic';
  const target = bounds.center.clone();
  if (view.targetLift) target.y += bounds.radius * view.targetLift;
  const direction = directionFrom(view.azimuth ?? 0, view.elevation ?? 0);

  let camera;
  if (orthographic) {
    camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, bounds.radius * 40);
    camera.userData.aspect = aspect;
    camera.position.copy(target).addScaledVector(direction, bounds.radius * 6);
    camera.up.set(0, 1, 0);
    if (Math.abs(view.elevation ?? 0) > 89) camera.up.set(0, 0, -Math.sign(view.elevation));
    camera.lookAt(target);
    camera.updateMatrixWorld(true);
    camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
    fitOrthographic(camera, view.margin ?? 1.06);
  } else if (view.photo) {
    camera = photoCamera(view, aspect);
  } else {
    const fov = view.fov ?? 32;
    camera = new THREE.PerspectiveCamera(fov, aspect, bounds.radius * 0.05, bounds.radius * 60);
    const distance = (bounds.radius / Math.sin(fov * DEG * 0.5)) * (view.distance ?? 1.0);
    camera.position.copy(target).addScaledVector(direction, distance);
    camera.lookAt(target);
  }
  camera.updateMatrixWorld(true);

  updateSun(view);
  state.headlight.intensity = orthographic ? (view.headlight ?? 1.1) : 0;
  state.headlight.position.copy(target).addScaledVector(direction, bounds.radius * 4);
  state.headlight.target.position.copy(target);
  state.headlight.target.updateMatrixWorld();

  // In a photo composite the ground only catches the shadow; the plate supplies
  // everything else, so the render is made over transparent black.
  state.ground.visible = view.ground ?? !orthographic;
  state.ground.material = view.photo ? state.shadowMaterial : state.groundMaterial;
  state.shadowMaterial.opacity = view.shadowOpacity ?? 0.55;
  scene.fog = view.photo || orthographic ? null : state.fog;
  if (orthographic) scene.background = new THREE.Color(view.background ?? 0xf2f0ec);
  else scene.background = view.photo ? null : state.envRT.texture;
  renderer.setClearAlpha(view.photo ? 0 : 1);

  renderComposed(camera, width, height, view);

  const canvas = document.createElement('canvas');
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext('2d');
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = 'high';
  if (view.photo) await drawPlate(context, size);
  context.drawImage(renderer.domElement, 0, 0, size.width, size.height);
  if (!orthographic) applyFilmLook(context, size, view.photo ? 0.4 : 1);
  return canvas.toDataURL('image/png');
}

window.dass = { boot, loadModel, renderView };
window.dispatchEvent(new Event('dass-ready'));
