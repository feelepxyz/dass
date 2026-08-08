"""Stage the browser-side assets the cut guide loads beside itself.

The guide is a single offline page, so nothing it needs may come from a CDN:
the renders are re-encoded small enough to carry, and three.js is vendored out
of the renderer's own node_modules so the page and the renders stay on one
version of the library.

    uv run scripts/build_web_assets.py
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

# A large progressive/optimized JPEG can outgrow Pillow's default encode buffer,
# which surfaces as "broken data stream" rather than as a size error.
# Pillow types MAXBLOCK as the literal of its own default, so any override
# reads as an invalid assignment.
ImageFile.MAXBLOCK = 16 * 1024 * 1024  # ty: ignore[invalid-assignment]

from dass.build_guide import (
    CLOUDFLARE_STREAM_PLAYER_URL,
    GALLERY,
    IN_SITU_CROP_FOCUS,
    PROGRESS_GALLERY,
    PROGRESS_VIDEO,
    STARTED_GALLERY,
    SVG_RENDERS,
)

ROOT = Path(__file__).resolve().parent.parent
LONG_EDGE = 1400
QUALITY = 80

# Module specifier -> file, resolved through the page's import map.
VENDOR = {
    "three.module.min.js": "build/three.module.min.js",
    # three.module.min.js imports this one beside itself.
    "three.core.min.js": "build/three.core.min.js",
    "addons/loaders/GLTFLoader.js": "examples/jsm/loaders/GLTFLoader.js",
    "addons/controls/OrbitControls.js": "examples/jsm/controls/OrbitControls.js",
    "addons/utils/BufferGeometryUtils.js": "examples/jsm/utils/BufferGeometryUtils.js",
    "addons/utils/SkeletonUtils.js": "examples/jsm/utils/SkeletonUtils.js",
    # Screen-space line quads, so the viewer draws the plate weights rather
    # than the one device pixel a GL line is fixed at. These three import each
    # other by relative path, so they stage into one directory together.
    "addons/lines/LineSegments2.js": "examples/jsm/lines/LineSegments2.js",
    "addons/lines/LineSegmentsGeometry.js": "examples/jsm/lines/LineSegmentsGeometry.js",
    "addons/lines/LineMaterial.js": "examples/jsm/lines/LineMaterial.js",
}


def square_crop(image: Image.Image, focus: float = IN_SITU_CROP_FOCUS) -> Image.Image:
    """Centre a portrait or landscape plate on the square the page shows.

    The in-situ composites are shot portrait, over a portrait backplate, so a
    square frame would otherwise letterbox them to a third of its width. `focus`
    is where the kept band sits down the long edge. The lower crop keeps the
    building centered at the same scale as the model beside it.
    """
    side = min(image.size)
    if image.height > image.width:
        top = round((image.height - side) * focus)
        return image.crop((0, top, side, top + side))
    left = round((image.width - side) / 2)
    return image.crop((left, 0, left + side, image.height))


def stage_renders(source: Path, target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    # The drawing renders underlay the model viewer and print with it, so they
    # are staged whether or not the gallery beside them lists them.
    for name in SVG_RENDERS:
        original = source / f"{name}.svg"
        if not original.exists():
            raise SystemExit(
                f"missing render {original}; run `node scripts/render-drawing.mjs` first"
            )
        out = target / original.name
        shutil.copyfile(original, out)
        written.append(out)
    for group, views in GALLERY:
        for name, _, _ in views:
            original = source / f"{name}.png"
            if not original.exists():
                raise SystemExit(
                    f"missing render {original}; run `uv run render-photo` first"
                )
            image = Image.open(original).convert("RGB")
            # Only the in-situ plates fill their frame; the renders and the flat
            # elevations must stay whole, so they are never cropped.
            if group == "In situ":
                image = square_crop(image)
            scale = LONG_EDGE / max(image.size)
            if scale < 1:
                image = image.resize(
                    (round(image.width * scale), round(image.height * scale)),
                    Image.Resampling.LANCZOS,
                )
            out = target / f"{name}.jpg"
            image.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
            written.append(out)
    return written


def stage_progress(target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for output_name, source_name, _title, _caption in PROGRESS_GALLERY:
        original = ROOT / "web/media/progress" / source_name
        if not original.exists():
            raise SystemExit(f"missing progress photo {original}")
        image = ImageOps.exif_transpose(Image.open(original)).convert("RGB")
        scale = LONG_EDGE / max(image.size)
        if scale < 1:
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        out = target / output_name
        image.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        written.append(out)
    return written


def stage_progress_video(target: Path) -> list[Path]:
    """Copy the browser-ready video pair without loading either into Python."""
    if CLOUDFLARE_STREAM_PLAYER_URL:
        for asset in PROGRESS_VIDEO[:2]:
            (target / asset).unlink(missing_ok=True)
        return []
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for asset in PROGRESS_VIDEO[:2]:
        original = ROOT / "web/media/progress" / asset
        if not original.exists():
            raise SystemExit(f"missing progress video asset {original}")
        out = target / asset
        shutil.copyfile(original, out)
        written.append(out)
    return written


def stage_started(target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for output_name, source_name, _title, _width, _height in STARTED_GALLERY:
        original = ROOT / source_name
        if not original.exists():
            raise SystemExit(f"missing story image {original}")
        image = ImageOps.exif_transpose(Image.open(original)).convert("RGB")
        scale = LONG_EDGE / max(image.size)
        if scale < 1:
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        out = target / output_name
        image.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        written.append(out)
    return written


# What the model viewer needs to show real timber, and how far each map can be
# reduced before the viewer canvas can tell. Normal maps keep full chroma, so
# their encoding never invents a slope that is not in the surface.
WEB_TEXTURES = (
    ("wood-color.jpg", "web/media/textures/plywood_diff_4k.jpg", 1024, 82, True),
    ("wood-normal.jpg", "build/renders/wood-normal.png", 1024, 84, False),
    ("wood-roughness.jpg", "build/renders/wood-roughness.png", 1024, 80, True),
    ("plank-atlas.jpg", "build/renders/plank-atlas.png", 1400, 82, True),
    ("plank-normal.jpg", "build/renders/plank-normal.png", 1100, 84, False),
    ("plank-roughness.jpg", "build/renders/plank-roughness.png", 1024, 80, True),
)


def stage_textures(target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for name, relative, long_edge, quality, subsample in WEB_TEXTURES:
        original = ROOT / relative
        if not original.exists():
            raise SystemExit(
                f"missing texture {original}; run `uv run render-photo` first"
            )
        image = Image.open(original)
        image = image.convert("L" if image.mode == "L" else "RGB")
        scale = long_edge / max(image.size)
        if scale < 1:
            image = image.resize(
                (round(image.width * scale), round(image.height * scale)),
                Image.Resampling.LANCZOS,
            )
        out = target / name
        image.save(
            out,
            "JPEG",
            quality=quality,
            optimize=True,
            subsampling=2 if subsample else 0,
        )
        written.append(out)
    # The corrugation ripple is 8 x 256 and exact; resampling it would soften
    # the very edge it exists to carry.
    ripple = target / "corrugation-normal.png"
    shutil.copyfile(ROOT / "build/renders/corrugation-normal.png", ripple)
    written.append(ripple)
    return written


def stage_fonts(target: Path) -> list[Path]:
    target.mkdir(parents=True, exist_ok=True)
    out = target / "InputMono-Regular.woff2"
    shutil.copyfile(ROOT / "web/media/fonts/InputMono-Regular.woff2", out)
    return [out]


def stage_vendor(target: Path) -> list[Path]:
    three = ROOT / "web/render/node_modules/three"
    if not three.exists():
        raise SystemExit(
            "web/render/node_modules/three is missing; run npm install in web/render/"
        )
    written = []
    for name, relative in VENDOR.items():
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(three / relative, out)
        written.append(out)
    # The viewer and the photoreal renderer share one timber pipeline.
    materials = target / "materials.mjs"
    shutil.copyfile(ROOT / "web/render/materials.mjs", materials)
    written.append(materials)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build")
    parser.add_argument("--renders", type=Path, default=ROOT / "build/renders")
    args = parser.parse_args()
    shots = stage_renders(args.renders, args.output / "web-renders")
    started = stage_started(args.output / "started")
    progress = stage_progress(args.output / "progress")
    progress_video = stage_progress_video(args.output / "progress")
    vendor = stage_vendor(args.output / "vendor")
    textures = stage_textures(args.output / "textures")
    fonts = stage_fonts(args.output / "fonts")
    weigh = lambda paths: sum(path.stat().st_size for path in paths) / 1e6
    video_summary = (
        "Cloudflare Stream video"
        if CLOUDFLARE_STREAM_PLAYER_URL
        else f"{len(progress_video) // 2} progress video"
    )
    print(
        f"Wrote {len(shots)} web renders ({weigh(shots):.1f} MB), "
        f"{len(started)} starting-point images ({weigh(started):.1f} MB), "
        f"{len(progress)} progress photos ({weigh(progress):.1f} MB), "
        f"{video_summary}, "
        f"{len(textures)} textures ({weigh(textures):.1f} MB), "
        f"{len(vendor)} vendored modules, {len(fonts)} font"
    )


if __name__ == "__main__":
    main()
