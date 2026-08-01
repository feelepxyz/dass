import json
import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from dass import photo_render
from dass.photo_render import (
    _cloud,
    build_variants,
    synthesize_birch,
    write_corrugation_map,
    write_plank_atlas,
    write_relief_maps,
    write_texture_maps,
)


@pytest.fixture
def small_atlas(monkeypatch):
    """Shrink the plank atlas to 4 boards at a fraction of its default
    resolution. `write_plank_atlas` has no size argument of its own; the
    module constants are the only lever, and a full-size atlas otherwise
    costs a quarter of a second per call it does not need to pay in a test."""
    monkeypatch.setattr(photo_render, "PLANK_CELL_PX", (320, 64))
    monkeypatch.setattr(photo_render, "PLANK_CELLS", 4)


# _cloud


def test_cloud_returns_normalized_noise_with_correct_shape_and_dtype():
    rng = np.random.default_rng(0)

    field = _cloud(rng, (16, 32), beta=2.0)

    assert field.shape == (16, 32)
    assert field.dtype == np.float32
    assert field.min() == pytest.approx(0.0, abs=1e-6)
    assert field.max() == pytest.approx(1.0, abs=1e-6)


def test_cloud_stretch_smears_noise_into_bands_running_down_the_height_axis():
    def mean_row_step(field: np.ndarray) -> float:
        return float(np.abs(np.diff(field, axis=0)).mean())

    unstretched = _cloud(np.random.default_rng(3), (48, 96), beta=2.0, stretch=1.0)
    stretched = _cloud(np.random.default_rng(3), (48, 96), beta=2.0, stretch=20.0)

    # `stretch` divides the width-direction frequency before it feeds the
    # radius, so it amplifies the components that are constant down a column
    # far more than any other. In the birch panel this is what lets a growth
    # ring's whole cross-section shift together as one rigid band while
    # tracing out a cathedral arc along the board's length, instead of each
    # pixel jittering independently. The signature of that is adjacent rows
    # (same column, one step down) landing far closer together once stretched.
    assert mean_row_step(stretched) < 0.5 * mean_row_step(unstretched)


# synthesize_birch


def test_synthesize_birch_writes_a_deterministic_tileable_rgb_panel(tmp_path):
    first = tmp_path / "birch.png"
    synthesize_birch(first, size=(32, 24), seed=1)

    image = Image.open(first)
    assert image.size == (32, 24)
    assert image.mode == "RGB"
    pixels = np.asarray(image, dtype=np.float32)
    assert pixels.std() > 1.0  # the grain actually varies, not a flat fill

    # Same seed, same panel.
    again = tmp_path / "birch-again.png"
    synthesize_birch(again, size=(32, 24), seed=1)
    assert np.array_equal(np.asarray(Image.open(again)), pixels)

    # Different seed, different panel.
    other = tmp_path / "birch-other.png"
    synthesize_birch(other, size=(32, 24), seed=2)
    assert not np.array_equal(np.asarray(Image.open(other)), pixels)


# write_corrugation_map


def test_write_corrugation_map_encodes_unit_normals_for_one_sine_period(tmp_path):
    path = tmp_path / "corrugation.png"
    pitch = 16

    write_corrugation_map(path, pitch=pitch, depth_ratio=0.24)

    image = Image.open(path)
    assert image.size == (8, pitch)
    assert image.mode == "RGB"
    decoded = np.asarray(image, dtype=np.float32) / 255.0 * 2 - 1

    # All 8 columns repeat the single-pixel-wide profile.
    assert np.array_equal(decoded[:, 0], decoded[:, -1])
    # Every texel is a normalized vector once decoded back out of the map.
    assert np.allclose(np.linalg.norm(decoded, axis=-1), 1.0, atol=0.02)
    # A quarter of the way through the sine the slope is zero, so that row
    # faces straight out of the sheet.
    quarter = decoded[pitch // 4, 0]
    assert tuple(quarter.tolist()) == pytest.approx((0.0, 0.0, 1.0), abs=0.05)


# write_plank_atlas


def test_write_plank_atlas_stacks_the_source_bands_in_order(tmp_path, small_atlas):
    band_colours = [(220, 30, 30), (30, 220, 30), (30, 30, 220), (220, 220, 30)]
    cells = photo_render.PLANK_CELLS
    band_height = 40
    source = Image.new("RGB", (80, band_height * cells))
    for index, colour in enumerate(band_colours):
        source.paste(
            Image.new("RGB", (80, band_height), colour), (0, index * band_height)
        )
    source_path = tmp_path / "bands.png"
    source.save(source_path)

    atlas_path = tmp_path / "atlas.png"
    write_plank_atlas(source_path, atlas_path, seed=1)

    cell_height = photo_render.PLANK_CELL_PX[1]
    atlas = np.asarray(Image.open(atlas_path), dtype=np.float32)
    assert Image.open(atlas_path).size == (
        photo_render.PLANK_CELL_PX[0],
        cell_height * cells,
    )
    palette = np.array(band_colours, dtype=np.float32)
    for index in range(cells):
        centre = (
            atlas[
                index * cell_height + cell_height // 2 - 8 : index * cell_height
                + cell_height // 2
                + 8
            ]
            .reshape(-1, 3)
            .mean(axis=0)
        )
        # Each cell reads closest to its own source band, however the random
        # tone jitter and mirroring nudged it, and not to any other band.
        distances = np.linalg.norm(palette - centre, axis=1)
        assert int(np.argmin(distances)) == index


def test_write_plank_atlas_shades_the_lapped_joint_at_each_board_edge(
    tmp_path, small_atlas
):
    cells = photo_render.PLANK_CELLS
    source_path = tmp_path / "source.png"
    Image.new("RGB", (80, 40 * cells), (200, 200, 200)).save(source_path)

    atlas_path = tmp_path / "atlas.png"
    write_plank_atlas(source_path, atlas_path, seed=0)

    cell_height = photo_render.PLANK_CELL_PX[1]
    pixels = np.asarray(Image.open(atlas_path), dtype=np.float32)
    first_cell = pixels[:cell_height]

    # The lapped edge of a board sits under its neighbour and is darkened;
    # the middle of the board's face is not.
    assert first_cell[0].mean() < first_cell[cell_height // 2].mean()


# write_relief_maps


def test_write_relief_maps_derives_a_flat_normal_and_grain_linked_roughness(tmp_path):
    source = tmp_path / "wood.png"
    Image.new("L", (16, 16), 200).save(source)
    normal_path = tmp_path / "normal.png"
    roughness_path = tmp_path / "roughness.png"

    write_relief_maps(source, normal_path, roughness_path)

    # A perfectly flat grey field has zero gradient everywhere, so every
    # texel encodes a normal pointing straight out of the surface (0, 0, 1).
    normal = np.asarray(Image.open(normal_path), dtype=np.float32)
    assert Image.open(normal_path).mode == "RGB"
    assert np.allclose(normal[..., 0], 127.5, atol=1.0)
    assert np.allclose(normal[..., 1], 127.5, atol=1.0)
    assert np.allclose(normal[..., 2], 255.0, atol=1.0)

    roughness_image = Image.open(roughness_path)
    assert roughness_image.mode == "L"
    roughness = np.asarray(roughness_image, dtype=np.float32)
    expected = (0.60 + (1 - 200 / 255) * 0.22) * 255
    assert np.allclose(roughness, expected, atol=1.0)


def test_write_relief_maps_skips_regeneration_when_cached_maps_are_newer_than_the_source(
    tmp_path,
):
    source = tmp_path / "wood.png"
    Image.new("L", (8, 8), 100).save(source)
    normal_path = tmp_path / "normal.png"
    roughness_path = tmp_path / "roughness.png"
    normal_path.write_bytes(b"stale-normal")
    roughness_path.write_bytes(b"stale-roughness")
    future = source.stat().st_mtime + 10
    os.utime(normal_path, (future, future))
    os.utime(roughness_path, (future, future))

    write_relief_maps(source, normal_path, roughness_path)

    assert normal_path.read_bytes() == b"stale-normal"
    assert roughness_path.read_bytes() == b"stale-roughness"


# write_texture_maps


def test_write_texture_maps_builds_the_manifest_from_an_existing_photo(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()
    source = tmp_path / "wood.png"
    Image.new("RGB", (64, 64), (150, 120, 90)).save(source)

    manifest = write_texture_maps(source, output)

    assert manifest["color"] == "wood.png"
    assert manifest["normal"] == "renders/wood-normal.png"
    assert manifest["roughness"] == "renders/wood-roughness.png"
    assert manifest["corrugation"] == "renders/corrugation-normal.png"
    assert manifest["plank"] == {
        "color": "renders/plank-atlas.png",
        "normal": "renders/plank-normal.png",
        "roughness": "renders/plank-roughness.png",
        "cells": photo_render.PLANK_CELLS,
        "lengthMm": photo_render.PLANK_LENGTH_MM,
        "boardMm": photo_render.PLANK_BOARD_MM,
        "coverMm": photo_render.PLANK_COVER_MM,
    }
    for name in (
        "wood-normal.png",
        "wood-roughness.png",
        "corrugation-normal.png",
        "plank-atlas.png",
        "plank-normal.png",
        "plank-roughness.png",
    ):
        assert (output / name).exists()


def test_write_texture_maps_synthesizes_a_birch_photo_when_none_is_supplied(
    tmp_path, monkeypatch, small_atlas, capsys
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()
    missing_source = tmp_path / "no-such-photo.png"

    calls = []

    def fake_synthesize_birch(path, *args, **kwargs):
        calls.append(path)
        Image.new("RGB", (4, 4), (210, 190, 160)).save(path)

    monkeypatch.setattr(photo_render, "synthesize_birch", fake_synthesize_birch)

    manifest = write_texture_maps(missing_source, output)

    birch_path = output / "wood-birch.png"
    assert calls == [birch_path]
    assert f"synthesising birch into {birch_path}" in capsys.readouterr().out
    assert manifest["color"] == "renders/wood-birch.png"


def test_write_texture_maps_reuses_an_already_synthesized_birch_photo(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()
    missing_source = tmp_path / "no-such-photo.png"
    Image.new("RGB", (8, 8), (210, 190, 160)).save(output / "wood-birch.png")

    def boom(*args, **kwargs):
        raise AssertionError("should reuse the cached birch photo")

    monkeypatch.setattr(photo_render, "synthesize_birch", boom)

    manifest = write_texture_maps(missing_source, output)

    assert manifest["color"] == "renders/wood-birch.png"


def test_write_texture_maps_leaves_fresh_corrugation_and_atlas_maps_alone(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()
    source = tmp_path / "wood.png"
    Image.new("RGB", (64, 64), (150, 120, 90)).save(source)

    write_texture_maps(source, output)  # first call creates every map

    def boom(*args, **kwargs):
        raise AssertionError("should not regenerate an already-fresh map")

    monkeypatch.setattr(photo_render, "write_corrugation_map", boom)
    monkeypatch.setattr(photo_render, "write_plank_atlas", boom)

    write_texture_maps(source, output)  # second call must reuse both


def test_write_texture_maps_rebuilds_the_atlas_when_the_source_photo_changes(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()
    source = tmp_path / "wood.png"
    Image.new("RGB", (64, 64), (150, 120, 90)).save(source)
    write_texture_maps(source, output)

    atlas_path = output / "plank-atlas.png"
    before = atlas_path.read_bytes()

    Image.new("RGB", (64, 64), (10, 200, 30)).save(source)
    future = atlas_path.stat().st_mtime + 10
    os.utime(source, (future, future))

    write_texture_maps(source, output)

    assert atlas_path.read_bytes() != before


# build_variants


def test_build_variants_writes_both_glbs_and_records_every_parts_material(
    design, by_name, tmp_path, monkeypatch
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path)
    output = tmp_path / "renders"
    output.mkdir()

    manifest = build_variants(design, output, door_angle=105.0, roof_lift_angle=25.0)

    assert set(manifest["variants"]) == {"closed", "open"}
    for name, relative in manifest["variants"].items():
        glb = output / f"dass-{name}.glb"
        assert relative == str(glb.relative_to(tmp_path))
        assert glb.stat().st_size > 0

    for part_name, part in by_name.items():
        assert manifest["parts"][part_name] == {
            "material": part.material,
            "category": part.category,
        }


# main


def test_main_list_views_runs_the_renderer_and_returns_without_building(monkeypatch):
    calls = []

    def fake_run(command, cwd, check):
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(photo_render.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["render-photo", "--list-views"])

    photo_render.main()

    assert calls == [
        (
            ["node", "web/render/render.mjs", "--list-views", "1"],
            photo_render.ROOT,
            False,
        )
    ]


def test_main_wires_overrides_into_the_design_and_reports_the_renderer_exit_code(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path.resolve())
    output = tmp_path / "renders"
    texture = tmp_path / "wood.png"
    Image.new("RGB", (64, 64), (150, 120, 90)).save(texture)

    captured = {}

    def fake_build_variants(design, out, door_angle, roof_lift_angle):
        captured["design"] = design
        captured["door_angle"] = door_angle
        captured["roof_lift_angle"] = roof_lift_angle
        out.mkdir(parents=True, exist_ok=True)
        return {"variants": {"closed": "x", "open": "y"}, "parts": {}}

    monkeypatch.setattr(photo_render, "build_variants", fake_build_variants)

    run_calls = []

    def fake_run(command, cwd, check):
        run_calls.append(command)
        return subprocess.CompletedProcess(command, 5)

    monkeypatch.setattr(photo_render.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render-photo",
            "--output",
            str(output),
            "--texture",
            str(texture),
            "--photo",
            str(tmp_path / "missing.png"),
            "--door-angle",
            "40",
            "--roof-lift-angle",
            "12",
            "--set",
            "width=1000",
            "--views",
            "open-hero",
        ],
    )

    with pytest.raises(SystemExit) as caught:
        photo_render.main()

    assert caught.value.code == 5
    assert captured["design"].width == 1000
    assert captured["door_angle"] == 40.0
    assert captured["roof_lift_angle"] == 12.0

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["photo"] is None  # the backdrop path does not exist
    assert manifest["textures"]["plank"]["cells"] == photo_render.PLANK_CELLS

    [command] = run_calls
    assert command[:2] == ["node", "web/render/render.mjs"]
    assert command[command.index("--views") + 1] == "open-hero"


def test_main_skip_build_reuses_the_cached_manifest_and_keeps_the_backdrop_path(
    tmp_path, monkeypatch, small_atlas
):
    monkeypatch.setattr(photo_render, "ROOT", tmp_path.resolve())
    output = tmp_path / "renders"
    output.mkdir()
    cached = {"variants": {"closed": "renders/dass-closed.glb"}, "parts": {}}
    (output / "manifest.json").write_text(json.dumps(cached))

    texture = tmp_path / "wood.png"
    Image.new("RGB", (64, 64), (150, 120, 90)).save(texture)
    photo = tmp_path / "photo.png"
    Image.new("RGB", (4, 4), (0, 0, 0)).save(photo)

    def fake_run(command, cwd, check):
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(photo_render.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render-photo",
            "--output",
            str(output),
            "--texture",
            str(texture),
            "--photo",
            str(photo),
            "--skip-build",
        ],
    )

    with pytest.raises(SystemExit) as caught:
        photo_render.main()

    assert caught.value.code == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["variants"] == {
        "closed": "renders/dass-closed.glb"
    }  # reused, not rebuilt
    assert manifest["photo"] == "photo.png"


def test_main_set_with_an_unknown_parameter_name_exits_with_a_usage_error(
    monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["render-photo", "--set", "bogus=1"])

    with pytest.raises(SystemExit) as caught:
        photo_render.main()

    assert caught.value.code == 2
    error = capsys.readouterr().err
    assert "--set must be NAME=MM" in error
    assert "width" in error  # the message lists the valid parameter names
