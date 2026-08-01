"""`scripts/build_web_assets.py` is a plain module, not part of the installed
package, so it is loaded by path, the same way `dass.serve.staging` loads it
to run the real guide server.

Its own `if __name__ == "__main__": main()` guard only fires when the
module's `__name__` is `"__main__"`, which never happens for a module loaded
under its own name. `_run_entry_point` below runs that guard for real without
a subprocess: a `SourceFileLoader` reads the real `scripts/build_web_assets.py`
(so the executed lines still count against that file for coverage), while
`spec_from_file_location` reports a *different* location under `tmp_path` and
the name `"__main__"`. `module_from_spec` sets `__file__` and `__name__` from
that spec, not from the loader, so the script's own
`ROOT = Path(__file__).resolve().parent.parent` lands under `tmp_path` and the
guard fires there — without ever touching the real `build/`, `web/media/`, or
`web/render/`.
"""

import importlib.machinery
import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE = REPO / "scripts" / "build_web_assets.py"


def _load_build_web_assets():
    spec = importlib.util.spec_from_file_location("build_web_assets", SCRIPT_SOURCE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_web_assets = _load_build_web_assets()


def _run_entry_point(file_target: Path) -> None:
    """Run the script's own `if __name__ == "__main__":` guard for real.

    See the module docstring for why this reads from the real
    `scripts/build_web_assets.py` but reports `file_target` as its location.
    """
    loader = importlib.machinery.SourceFileLoader("__main__", str(SCRIPT_SOURCE))
    spec = importlib.util.spec_from_file_location(
        "__main__", str(file_target), loader=loader
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)


def _write_placeholder_image(path: Path, size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)


# Square crop


def test_square_crop_keeps_a_focused_band_down_a_portrait_plate():
    width, height = 10, 20
    image = Image.new("L", (width, height))
    image.putdata([y for y in range(height) for _ in range(width)])

    cropped = build_web_assets.square_crop(image, focus=0.3)

    # side = 10, top = round((20 - 10) * 0.3) = 3, so rows 3..12 are kept.
    assert cropped.size == (10, 10)
    assert cropped.getpixel((0, 0)) == 3
    assert cropped.getpixel((0, cropped.height - 1)) == 12


def test_square_crop_centers_a_landscape_plate_regardless_of_focus():
    width, height = 20, 10
    image = Image.new("L", (width, height))
    image.putdata([x for _ in range(height) for x in range(width)])

    cropped = build_web_assets.square_crop(image)

    # side = 10, left = round((20 - 10) / 2) = 5, so columns 5..14 are kept.
    assert cropped.size == (10, 10)
    assert cropped.getpixel((0, 0)) == 5
    assert cropped.getpixel((cropped.width - 1, 0)) == 14


# Stage renders


def test_stage_renders_crops_only_in_situ_plates_before_downscaling(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(build_web_assets, "LONG_EDGE", 40)
    monkeypatch.setattr(
        build_web_assets,
        "GALLERY",
        (
            ("In situ", (("plate", "Plate", ""),)),
            ("Render", (("shot", "Shot", ""),)),
        ),
    )
    source = tmp_path / "renders"
    source.mkdir()
    Image.new("RGB", (60, 100), "red").save(source / "plate.png")
    Image.new("RGB", (30, 20), "blue").save(source / "shot.png")
    target = tmp_path / "web-renders"

    written = build_web_assets.stage_renders(source, target)

    assert [path.name for path in written] == ["plate.jpg", "shot.jpg"]
    with Image.open(target / "plate.jpg") as staged:
        # Cropped to a 60x60 square, then downscaled under the 40px long edge.
        assert staged.size == (40, 40)
    with Image.open(target / "shot.jpg") as staged:
        # Not an "In situ" plate, so it is kept whole; already under the long
        # edge, so it is left at its native size.
        assert staged.size == (30, 20)


def test_stage_renders_names_the_missing_render(tmp_path, monkeypatch):
    monkeypatch.setattr(
        build_web_assets, "GALLERY", (("Render", (("absent", "Absent", ""),)),)
    )

    with pytest.raises(SystemExit) as caught:
        build_web_assets.stage_renders(tmp_path / "renders", tmp_path / "out")

    assert "missing render" in str(caught.value)
    assert "absent.png" in str(caught.value)


# Stage progress


def test_stage_progress_downscales_only_photos_over_the_long_edge(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(build_web_assets, "LONG_EDGE", 40)
    progress_dir = tmp_path / "web/media/progress"
    progress_dir.mkdir(parents=True)
    Image.new("RGB", (80, 20), "green").save(progress_dir / "big.jpg")
    Image.new("RGB", (20, 10), "green").save(progress_dir / "small.jpg")
    monkeypatch.setattr(
        build_web_assets,
        "PROGRESS_GALLERY",
        (
            ("big-out.jpg", "big.jpg", "Big", "cap"),
            ("small-out.jpg", "small.jpg", "Small", "cap"),
        ),
    )
    target = tmp_path / "progress"

    written = build_web_assets.stage_progress(target)

    assert [path.name for path in written] == ["big-out.jpg", "small-out.jpg"]
    with Image.open(target / "big-out.jpg") as staged:
        assert staged.size == (40, 10)
    with Image.open(target / "small-out.jpg") as staged:
        assert staged.size == (20, 10)


def test_stage_progress_names_the_missing_photo(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(
        build_web_assets, "PROGRESS_GALLERY", (("out.jpg", "absent.jpg", "T", "C"),)
    )

    with pytest.raises(SystemExit) as caught:
        build_web_assets.stage_progress(tmp_path / "out")

    assert "missing progress photo" in str(caught.value)
    assert "absent.jpg" in str(caught.value)


# Stage started


def test_stage_started_downscales_only_images_over_the_long_edge(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(build_web_assets, "LONG_EDGE", 40)
    story = tmp_path / "story"
    story.mkdir()
    Image.new("RGB", (80, 20), "purple").save(story / "big.jpg")
    Image.new("RGB", (20, 10), "purple").save(story / "small.jpg")
    monkeypatch.setattr(
        build_web_assets,
        "STARTED_GALLERY",
        (
            ("big-out.jpg", "story/big.jpg", "Big", 80, 20),
            ("small-out.jpg", "story/small.jpg", "Small", 20, 10),
        ),
    )
    target = tmp_path / "started"

    written = build_web_assets.stage_started(target)

    assert [path.name for path in written] == ["big-out.jpg", "small-out.jpg"]
    with Image.open(target / "big-out.jpg") as staged:
        assert staged.size == (40, 10)
    with Image.open(target / "small-out.jpg") as staged:
        assert staged.size == (20, 10)


def test_stage_started_names_the_missing_image(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(
        build_web_assets, "STARTED_GALLERY", (("out.jpg", "absent.jpg", "T", 10, 10),)
    )

    with pytest.raises(SystemExit) as caught:
        build_web_assets.stage_started(tmp_path / "out")

    assert "missing story image" in str(caught.value)
    assert "absent.jpg" in str(caught.value)


# Stage textures


def test_stage_textures_resizes_by_its_own_long_edge_and_keeps_masks_grayscale(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    Image.new("RGB", (80, 20), "orange").save(tmp_path / "color.jpg")
    Image.new("L", (10, 10)).save(tmp_path / "mask.png")
    monkeypatch.setattr(
        build_web_assets,
        "WEB_TEXTURES",
        (
            ("color.jpg", "color.jpg", 40, 82, True),
            ("mask.jpg", "mask.png", 40, 80, False),
        ),
    )
    renders_dir = tmp_path / "build/renders"
    renders_dir.mkdir(parents=True)
    ripple_bytes = b"corrugation ripple, copied verbatim"
    (renders_dir / "corrugation-normal.png").write_bytes(ripple_bytes)
    target = tmp_path / "textures-out"

    written = build_web_assets.stage_textures(target)

    assert [path.name for path in written] == [
        "color.jpg",
        "mask.jpg",
        "corrugation-normal.png",
    ]
    with Image.open(target / "color.jpg") as staged:
        # 80x20 downscaled under the 40px long edge, kept in colour.
        assert staged.size == (40, 10)
        assert staged.mode == "RGB"
    with Image.open(target / "mask.jpg") as staged:
        # Already under the long edge, so left native; single channel is kept
        # rather than expanded to RGB.
        assert staged.size == (10, 10)
        assert staged.mode == "L"
    # The ripple is copied byte-for-byte, never resampled.
    assert (target / "corrugation-normal.png").read_bytes() == ripple_bytes


def test_stage_textures_names_the_missing_map(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(
        build_web_assets,
        "WEB_TEXTURES",
        (("out.jpg", "absent.jpg", 100, 80, True),),
    )

    with pytest.raises(SystemExit) as caught:
        build_web_assets.stage_textures(tmp_path / "out")

    assert "missing texture" in str(caught.value)
    assert "absent.jpg" in str(caught.value)


# Stage fonts


def test_stage_fonts_copies_the_vendored_woff2(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    fonts_dir = tmp_path / "web/media/fonts"
    fonts_dir.mkdir(parents=True)
    payload = b"woff2-bytes"
    (fonts_dir / "InputMono-Regular.woff2").write_bytes(payload)

    written = build_web_assets.stage_fonts(tmp_path / "fonts")

    assert [path.name for path in written] == ["InputMono-Regular.woff2"]
    assert written[0].read_bytes() == payload


# Stage vendor


def test_stage_vendor_copies_three_and_the_shared_materials_module(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    three = tmp_path / "web/render/node_modules/three"
    for relative in build_web_assets.VENDOR.values():
        path = three / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"// {relative}")
    (tmp_path / "web/render/materials.mjs").write_text("// materials")
    target = tmp_path / "vendor"

    written = build_web_assets.stage_vendor(target)

    assert {path.relative_to(target).as_posix() for path in written} == set(
        build_web_assets.VENDOR
    ) | {"materials.mjs"}
    # A nested module specifier lands at the matching nested path, and the
    # bytes travelled rather than a same-named placeholder.
    assert (
        target / "three.module.min.js"
    ).read_text() == "// build/three.module.min.js"
    assert (
        target / "addons/loaders/GLTFLoader.js"
    ).read_text() == "// examples/jsm/loaders/GLTFLoader.js"


def test_stage_vendor_names_the_missing_node_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)

    with pytest.raises(SystemExit) as caught:
        build_web_assets.stage_vendor(tmp_path / "out")

    assert "npm install" in str(caught.value)
    assert "node_modules/three" in str(caught.value)


@pytest.mark.skipif(
    not (REPO / "web/render/node_modules/three").is_dir(),
    reason="the render dependencies are not installed; run `npm ci` in web/render",
)
def test_every_vendored_module_exists_in_the_installed_three_package():
    """`VENDOR` hard-codes paths inside the `three` package.

    Every other test here builds its own tree, so none of them would notice
    three.js moving a file between releases -- the viewer would simply ship
    without it. This is the one check that reads the real installed package,
    which is why CI installs it.
    """
    three = REPO / "web/render/node_modules/three"

    missing = [
        relative
        for relative in build_web_assets.VENDOR.values()
        if not (three / relative).is_file()
    ]

    assert missing == []
    assert (REPO / "web/render/materials.mjs").is_file()


# Main


def test_main_stages_every_asset_group_under_the_given_flags_and_reports_a_summary(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(build_web_assets, "ROOT", tmp_path)
    monkeypatch.setattr(build_web_assets, "LONG_EDGE", 40)
    monkeypatch.setattr(
        build_web_assets, "GALLERY", (("Render", (("shot", "Shot", ""),)),)
    )
    monkeypatch.setattr(
        build_web_assets,
        "PROGRESS_GALLERY",
        (("progress-out.jpg", "progress-in.jpg", "T", "C"),),
    )
    monkeypatch.setattr(
        build_web_assets,
        "STARTED_GALLERY",
        (("started-out.jpg", "started-in.jpg", "T", 20, 10),),
    )
    monkeypatch.setattr(
        build_web_assets,
        "WEB_TEXTURES",
        (("texture-out.jpg", "texture-in.jpg", 40, 80, True),),
    )

    renders_source = tmp_path / "renders"
    renders_source.mkdir()
    Image.new("RGB", (20, 10), "red").save(renders_source / "shot.png")

    build_renders = tmp_path / "build/renders"
    build_renders.mkdir(parents=True)
    (build_renders / "corrugation-normal.png").write_bytes(b"ripple")

    (tmp_path / "web/media/progress").mkdir(parents=True)
    Image.new("RGB", (20, 10), "green").save(
        tmp_path / "web/media/progress/progress-in.jpg"
    )
    Image.new("RGB", (20, 10), "purple").save(tmp_path / "started-in.jpg")
    Image.new("RGB", (20, 10), "blue").save(tmp_path / "texture-in.jpg")

    (tmp_path / "web/media/fonts").mkdir(parents=True)
    (tmp_path / "web/media/fonts/InputMono-Regular.woff2").write_bytes(b"font")

    three = tmp_path / "web/render/node_modules/three"
    for relative in build_web_assets.VENDOR.values():
        path = three / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// vendor")
    (tmp_path / "web/render/materials.mjs").write_text("// materials")

    output = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_web_assets.py",
            "--output",
            str(output),
            "--renders",
            str(renders_source),
        ],
    )

    build_web_assets.main()

    assert (output / "web-renders/shot.jpg").exists()
    assert (output / "started/started-out.jpg").exists()
    assert (output / "progress/progress-out.jpg").exists()
    assert (output / "vendor/three.module.min.js").exists()
    assert (output / "textures/texture-out.jpg").exists()
    assert (output / "textures/corrugation-normal.png").exists()
    assert (output / "fonts/InputMono-Regular.woff2").exists()

    summary = capsys.readouterr().out
    assert summary.startswith("Wrote 1 web renders (")
    assert "1 starting-point images (" in summary
    assert "1 progress photos (" in summary
    assert "2 textures (" in summary
    assert "7 vendored modules, 1 font" in summary


# Entry point


def test_running_as_a_script_fires_the_main_guard_without_touching_the_real_repo(
    tmp_path, monkeypatch, capsys
):
    # The fresh module exec re-reads the real GALLERY, PROGRESS_GALLERY,
    # STARTED_GALLERY, WEB_TEXTURES, and VENDOR from their own top-level
    # import, so every entry they name is satisfied under `tmp_path` here
    # rather than in the repository's own `build/`, `web/media/`, or
    # `web/render/`.
    for _, views in build_web_assets.GALLERY:
        for name, _, _ in views:
            _write_placeholder_image(tmp_path / "build/renders" / f"{name}.png")
    for _, source_name, _, _ in build_web_assets.PROGRESS_GALLERY:
        _write_placeholder_image(tmp_path / "web/media/progress" / source_name)
    for _, source_name, _, _, _ in build_web_assets.STARTED_GALLERY:
        _write_placeholder_image(tmp_path / source_name)
    for _, relative, _, _, _ in build_web_assets.WEB_TEXTURES:
        _write_placeholder_image(tmp_path / relative)
    ripple = tmp_path / "build/renders/corrugation-normal.png"
    ripple.parent.mkdir(parents=True, exist_ok=True)
    ripple.write_bytes(b"ripple")
    three = tmp_path / "web/render/node_modules/three"
    for relative in build_web_assets.VENDOR.values():
        path = three / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"// {relative}")
    (tmp_path / "web/render/materials.mjs").write_text("// materials")
    fonts_dir = tmp_path / "web/media/fonts"
    fonts_dir.mkdir(parents=True)
    (fonts_dir / "InputMono-Regular.woff2").write_bytes(b"font")

    render_count = sum(len(views) for _, views in build_web_assets.GALLERY)
    started_count = len(build_web_assets.STARTED_GALLERY)
    progress_count = len(build_web_assets.PROGRESS_GALLERY)
    texture_count = len(build_web_assets.WEB_TEXTURES) + 1  # + the ripple copy
    vendor_count = len(build_web_assets.VENDOR) + 1  # + materials.mjs
    first_view = build_web_assets.GALLERY[0][1][0][0]

    # `main`'s `--output`/`--renders` default to paths under its own `ROOT`,
    # which `_run_entry_point` lands under `tmp_path`; no CLI args are needed.
    monkeypatch.setattr(sys, "argv", ["build_web_assets.py"])

    _run_entry_point(tmp_path / "scripts" / "build_web_assets.py")

    output = tmp_path / "build"
    assert (output / "web-renders" / f"{first_view}.jpg").exists()
    assert (output / "vendor/three.module.min.js").exists()
    assert (output / "fonts/InputMono-Regular.woff2").exists()

    summary = capsys.readouterr().out
    assert summary.startswith(f"Wrote {render_count} web renders (")
    assert f"{started_count} starting-point images (" in summary
    assert f"{progress_count} progress photos (" in summary
    assert f"{texture_count} textures (" in summary
    assert f"{vendor_count} vendored modules, 1 font" in summary
