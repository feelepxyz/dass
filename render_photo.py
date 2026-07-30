"""Photo-realistic renders of the dass model with board-on-board cladding.

Builds the GLB for each variant, derives normal/roughness maps and a per-board
texture atlas from ``textures/plywood_diff_4k.jpg``, then hands them all to
``render/render.mjs``, which lights and photographs the model in headless
Chromium (three.js, sky IBL, soft sun shadows).

    uv run python render_photo.py                        # every view
    uv run python render_photo.py --views open-hero      # one view, fast
    uv run python render_photo.py --width 2400 --height 1800

View names are listed by ``--list-views``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
from PIL import Image

import dass

ROOT = Path(__file__).resolve().parent

# The cladding fields are råspont: 120 mm boards lapped to a 110 mm cover, the
# same numbers generate_cutlists.cladding_pieces() cuts to.  The atlas holds one
# whole board per cell, long enough that the tallest field never has to repeat.
PLANK_CELLS = 8
PLANK_BOARD_MM = 120.0
PLANK_COVER_MM = 110.0
PLANK_LENGTH_MM = 1200.0
PLANK_CELL_PX = (2560, 256)
PLANK_JOINT_MM = 4.0
PLANK_JOINT_SHADE = 0.5


def _cloud(rng: np.random.Generator, shape: tuple[int, int], beta: float, stretch: float = 1.0) -> np.ndarray:
    """Tiling cloud noise: white noise shaped by a 1/f**beta spectrum.

    Built in the frequency domain, so the result wraps exactly at both edges;
    `stretch` above 1 smears it along the u axis the way grain runs a board.
    """
    height, width = shape
    spectrum = np.fft.fft2(rng.normal(size=shape))
    fy = np.fft.fftfreq(height)[:, None]
    fx = np.fft.fftfreq(width)[None, :] / stretch
    radius = np.hypot(fx, fy)
    radius[0, 0] = 1.0
    field = np.real(np.fft.ifft2(spectrum / radius ** beta))
    field -= field.min()
    return (field / field.max()).astype(np.float32)


def synthesize_birch(path: Path, size: tuple[int, int] = (2048, 1152), seed: int = 11) -> None:
    """Draw a pale birch panel: cathedral figure over fine straight grain.

    Used when no wood photo is supplied.  Every layer is periodic, so the sheet
    tiles seamlessly and large panels show no repeat seam.
    """
    width, height = size
    rng = np.random.default_rng(seed)
    _, yy = np.meshgrid(np.linspace(0, 1, width, endpoint=False),
                        np.linspace(0, 1, height, endpoint=False))
    drift = _cloud(rng, (height, width), beta=3.0, stretch=20.0)
    sway = _cloud(rng, (height, width), beta=2.0, stretch=10.0)
    chatter = _cloud(rng, (height, width), beta=1.4, stretch=9.0)

    # Growth rings run along the board.  The large drift term both bends them
    # into cathedral arcs and varies their spacing, which is what stops the
    # pattern reading as corrugation.
    phase = 5 * yy + 9.0 * (drift - 0.5) + 2.2 * (sway - 0.5)
    figure = (0.5 + 0.5 * np.cos(2 * np.pi * phase)) ** 2.6
    lines = (0.5 + 0.5 * np.cos(2 * np.pi * (150 * yy + 7.0 * (chatter - 0.5)))) ** 2.0

    value = np.clip(0.56 * figure + 0.24 * lines + 0.20 * (1 - drift), 0, 1)
    base_colour = np.array([247, 236, 216], dtype=np.float32)
    grain_colour = np.array([186, 142, 92], dtype=np.float32)
    blend = (0.30 * value)[..., None]
    image = base_colour * (1 - blend) + grain_colour * blend
    image += rng.normal(0, 2.0, (height, width, 1)).astype(np.float32)
    Image.fromarray(np.clip(image, 0, 255).astype(np.uint8)).save(path)


def write_corrugation_map(path: Path, pitch: int = 256, depth_ratio: float = 0.24) -> None:
    """Tangent-space normal map for one period of corrugated sheet.

    The profile is a sine across v; `depth_ratio` is corrugation depth over
    pitch, which for common roofing sheet is about 18 mm in 76 mm.
    """
    v = np.linspace(0, 1, pitch, endpoint=False, dtype=np.float32)
    slope = 2 * np.pi * depth_ratio * np.cos(2 * np.pi * v)
    normal = np.stack((np.zeros_like(slope), -slope, np.ones_like(slope)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    row = ((normal * 0.5 + 0.5) * 255).astype(np.uint8)
    Image.fromarray(np.repeat(row[:, None, :], 8, axis=1)).save(path)


def write_plank_atlas(source: Path, path: Path, seed: int = 7) -> None:
    """Cut the wood photo into `PLANK_CELLS` distinct board strips, stacked in v.

    Every cladding field is one solid panel in CAD, but it is built from råspont
    boards, and a wall of boards all sampling the same sheet reads as a single
    sheet.  Each cell here is one whole 120 x 1200 mm board, taken from its own
    band of the photo and then mirrored and re-toned, so the renderer can hand
    neighbouring boards figure that never lines up.
    """
    photo = Image.open(source).convert("RGB")
    width, height = photo.size
    cell_width, cell_height = PLANK_CELL_PX
    band = height // PLANK_CELLS
    # Each board is laid over its neighbour's lip, and that step throws a thin
    # shadow down the joint.  Darkening both edges of the cell puts half of it
    # on each board, so a joint reads as one line however the boards are laid.
    rows = (np.arange(cell_height, dtype=np.float32) + 0.5) / cell_height
    inset = (1 - PLANK_COVER_MM / PLANK_BOARD_MM) / 2
    edge = PLANK_JOINT_MM / PLANK_BOARD_MM
    near = np.clip(np.minimum(rows - inset, 1 - inset - rows), 0, edge) / edge
    joint = (1 - PLANK_JOINT_SHADE * (1 - near) ** 2)[:, None, None]
    # Take the strip at the board's own aspect, so the grain is never squashed.
    crop = min(band, round(width * cell_height / cell_width))
    rng = np.random.default_rng(seed)
    atlas = Image.new("RGB", (cell_width, cell_height * PLANK_CELLS))
    for index in range(PLANK_CELLS):
        top = index * band + (band - crop) // 2
        strip = photo.crop((0, top, width, top + crop))
        strip = strip.resize((cell_width, cell_height), Image.LANCZOS)
        # Mirroring either way covers all four rotations of the same crop.
        if rng.random() < 0.5:
            strip = strip.transpose(Image.FLIP_LEFT_RIGHT)
        if rng.random() < 0.5:
            strip = strip.transpose(Image.FLIP_TOP_BOTTOM)
        # No two boards off the same pack are quite the same colour.
        warm = 1.0 + (rng.random() - 0.5) * 0.07
        gain = (1.0 + (rng.random() - 0.5) * 0.18) * np.array([warm, 1.0, 2.0 - warm], np.float32)
        toned = np.clip(np.asarray(strip, dtype=np.float32) * gain * joint, 0, 255)
        atlas.paste(Image.fromarray(toned.astype(np.uint8)), (0, index * cell_height))
    atlas.save(path)


def write_relief_maps(source: Path, normal_path: Path, roughness_path: Path) -> None:
    """Derive a normal and roughness map from a wood image (cached by mtime)."""
    if (normal_path.exists() and roughness_path.exists()
            and min(normal_path.stat().st_mtime, roughness_path.stat().st_mtime)
            > source.stat().st_mtime):
        return
    grey = np.asarray(Image.open(source).convert("L"), dtype=np.float32) / 255.0
    # Sobel gradients of the grain give a believable surface relief.
    dx = np.gradient(grey, axis=1) * 8.0
    dy = np.gradient(grey, axis=0) * 8.0
    normal = np.dstack((-dx, dy, np.ones_like(grey)))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    Image.fromarray(((normal * 0.5 + 0.5) * 255).astype(np.uint8)).save(normal_path)

    # Darker grain reads as very slightly rougher than the pale sanded face.
    roughness = 0.60 + (1.0 - grey) * 0.22
    Image.fromarray((roughness * 255).astype(np.uint8), mode="L").save(roughness_path)


def write_texture_maps(source: Path, output: Path) -> dict:
    """Build every map the renderer needs: framing sheet, board atlas, roofing."""
    if not source.exists():
        source = output / "wood-birch.png"
        if not source.exists():
            print(f"no wood photo found; synthesising birch into {source}")
            synthesize_birch(source)
    corrugation_path = output / "corrugation-normal.png"
    if not corrugation_path.exists():
        write_corrugation_map(corrugation_path)

    write_relief_maps(source, output / "wood-normal.png", output / "wood-roughness.png")
    atlas_path = output / "plank-atlas.png"
    if not atlas_path.exists() or atlas_path.stat().st_mtime < source.stat().st_mtime:
        write_plank_atlas(source, atlas_path)
    write_relief_maps(atlas_path, output / "plank-normal.png", output / "plank-roughness.png")

    def relative(name: str) -> str:
        return str((output / name).relative_to(ROOT))

    return {
        "color": str(source.relative_to(ROOT)),
        "normal": relative("wood-normal.png"),
        "roughness": relative("wood-roughness.png"),
        "corrugation": relative("corrugation-normal.png"),
        "plank": {
            "color": relative("plank-atlas.png"),
            "normal": relative("plank-normal.png"),
            "roughness": relative("plank-roughness.png"),
            "cells": PLANK_CELLS,
            "lengthMm": PLANK_LENGTH_MM,
            "boardMm": PLANK_BOARD_MM,
            "coverMm": PLANK_COVER_MM,
        },
    }


def build_variants(design: dass.Design, output: Path, door_angle: float, roof_lift_angle: float) -> dict:
    variants: dict[str, str] = {}
    parts: dict[str, dict[str, str]] = {}
    for name, angle, lift in (("closed", 0.0, 0.0), ("open", door_angle, roof_lift_angle)):
        assembly, built = dass.build(design, door_angle=angle, roof_visible=True, roof_lift_angle=lift)
        path = output / f"dass-{name}.glb"
        assembly.export(str(path))
        variants[name] = str(path.relative_to(ROOT))
        for part in built:
            parts[part.name] = {"material": part.material, "category": part.category}
    return {"variants": variants, "parts": parts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=ROOT / "build/renders")
    parser.add_argument("--texture", type=Path, default=ROOT / "textures/plywood_diff_4k.jpg")
    parser.add_argument("--photo", type=Path, default=ROOT / "background.jpg",
                        help="backdrop photograph for the in-situ views")
    parser.add_argument("--views", help="comma-separated view names (default: all)")
    parser.add_argument("--list-views", action="store_true", help="print the view names and exit")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--supersample", type=int, default=2, help="render scale before downsampling")
    parser.add_argument("--door-angle", type=float, default=105)
    parser.add_argument("--roof-lift-angle", type=float, default=25)
    parser.add_argument("--skip-build", action="store_true", help="reuse the GLBs already in --output")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=MM",
                        help="override any numeric Design parameter; may be repeated")
    args = parser.parse_args()

    if args.list_views:
        subprocess.run(["node", "render/render.mjs", "--list-views", "1"], cwd=ROOT, check=False)
        return

    parameter_names = {field.name for field in fields(dass.Design)}
    overrides: dict[str, float] = {}
    for item in args.set:
        name, separator, value = item.partition("=")
        if not separator or name not in parameter_names:
            parser.error(f"--set must be NAME=MM where NAME is one of: {', '.join(sorted(parameter_names))}")
        overrides[name] = float(value)
    design = replace(dass.Design(), **overrides)

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"

    if args.skip_build and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        print("building GLB variants ...")
        manifest = build_variants(design, output, args.door_angle, args.roof_lift_angle)
    manifest["textures"] = write_texture_maps(args.texture.resolve(), output)
    photo = args.photo.resolve()
    manifest["photo"] = str(photo.relative_to(ROOT)) if photo.exists() else None
    manifest_path.write_text(json.dumps(manifest, indent=1))

    command = [
        "node", "render/render.mjs",
        "--manifest", str(manifest_path),
        "--out", str(output),
        "--width", str(args.width),
        "--height", str(args.height),
        "--supersample", str(args.supersample),
    ]
    if args.views:
        command += ["--views", args.views]
    sys.exit(subprocess.run(command, cwd=ROOT).returncode)


if __name__ == "__main__":
    main()
