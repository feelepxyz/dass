"""CLI entry points and file writers: the code that only runs when the
workshop actually calls `dass`, `generate-cutlists`, or `generate-build-guide`.

Every `main()` here defaults to writing into `build/`, so every test below
redirects it into `tmp_path` instead; nothing here writes into the real
`build/` directory.
"""

import csv
import runpy
import subprocess
import sys
import warnings

import numpy as np
import pytest
from PIL import Image

from dass.cutlists import (
    DEFAULT_KERF,
    CutPiece,
    panel_stock_plan,
    write_schedule,
    write_stock_summary,
)
from dass.cutlists import main as cutlists_main
from dass.model import main as model_main
from dass.model import render, write_cutlist


def _run_as_script(module: str) -> None:
    """Execute *module* the way `python -m` would.

    Every module exercised here is already imported (the suite imports
    `dass` for its fixtures), so `runpy` warns that re-running one as
    `__main__` may behave unpredictably across two copies of its classes.
    Nothing in these modules keys off object identity across that boundary,
    so the warning is expected and silenced rather than left to print over
    other tests' output.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module(module, run_name="__main__")


# dass.model -------------------------------------------------------------


def test_write_cutlist_groups_identical_profiles_and_rounds_dimensions(parts, tmp_path):
    path = tmp_path / "cutlist.csv"
    write_cutlist(parts, path)

    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert list(rows[0].keys()) == [
        "part",
        "quantity",
        "length_mm",
        "width_mm",
        "thickness_mm",
        "material",
    ]
    # The four posts share one profile (front/back height are both 1150 by
    # default), so they collapse into a single grouped row.
    v1 = next(row for row in rows if row["part"] == "V1")
    assert (v1["quantity"], v1["length_mm"], v1["width_mm"], v1["thickness_mm"]) == (
        "4",
        "1150",
        "45",
        "45",
    )
    assert sum(int(row["quantity"]) for row in rows) == len(parts)


def test_render_draws_the_model_within_the_requested_image_size(
    design, by_name, tmp_path
):
    path = tmp_path / "roof.png"
    render([by_name["roof"]], design, path, size=(100, 80))

    image = Image.open(path)
    assert image.size == (100, 80)
    colors = {tuple(pixel) for row in np.array(image) for pixel in row}

    background = (247, 247, 247)
    assert background in colors
    drawn = colors - {background}
    assert drawn
    # The roof is a flat "metal roof" palette colour (110, 122, 128) with
    # Lambertian shading in [0.68, 1.0]; every drawn pixel should land there.
    for r, g, b in drawn:
        assert 75 <= r <= 110
        assert 83 <= g <= 122
        assert 87 <= b <= 128


def test_model_main_rejects_an_unknown_set_name(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["dass", "--output", str(tmp_path), "--set", "bogus=1"]
    )

    with pytest.raises(SystemExit) as excinfo:
        model_main()

    assert excinfo.value.code == 2
    assert "--set must be NAME=MM" in capsys.readouterr().err


def test_model_main_rejects_a_non_numeric_set_value(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["dass", "--output", str(tmp_path), "--set", "width=abc"]
    )

    with pytest.raises(SystemExit):
        model_main()

    assert "requires a numeric value, got 'abc'" in capsys.readouterr().err


def test_model_main_writes_both_variants_and_a_cutlist_when_run_as_a_script(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        sys, "argv", ["dass", "--output", str(tmp_path), "--set", "width=1000"]
    )

    _run_as_script("dass.model")  # also proves the `__main__` guard calls main()

    for name in (
        "dass-closed.step",
        "dass-closed.glb",
        "dass-closed.png",
        "dass-open.step",
        "dass-open.glb",
        "dass-open.png",
        "cutlist.csv",
    ):
        assert (tmp_path / name).stat().st_size > 0

    with (tmp_path / "cutlist.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rail = next(row for row in rows if row["part"] == "front opening rail")
    # inner_width for the --set-overridden 990 -> 1000 mm width.
    assert rail["length_mm"] == "910.0"

    assert f"Wrote CAD, renders, and cut list to {tmp_path}" in capsys.readouterr().out


# dass.cutlists ------------------------------------------------------------


def test_write_schedule_writes_the_header_and_blanks_missing_finish_fields(tmp_path):
    pieces = [
        CutPiece("door_1", 1175.04, 120, 23, 1175.0, 1175.0, "", 4.96, "DCB1"),
        CutPiece("plain_1", 900, 45, 45),
    ]
    path = tmp_path / "schedule.csv"
    write_schedule(pieces, path)

    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert list(rows[0].keys()) == [
        "code",
        "piece",
        "blank_length_mm",
        "finished_long_mm",
        "finished_short_mm",
        "width_mm",
        "thickness_mm",
        "gang_cut",
        "panel_end_trim_mm",
    ]
    assert rows[0] == {
        "code": "DCB1",
        "piece": "door_1",
        "blank_length_mm": "1175.0",
        "finished_long_mm": "1175.0",
        "finished_short_mm": "1175.0",
        "width_mm": "120",
        "thickness_mm": "23",
        "gang_cut": "",
        "panel_end_trim_mm": "5.0",
    }
    # A piece with no finish or code data leaves those fields blank, not "0".
    assert rows[1]["code"] == ""
    assert rows[1]["finished_long_mm"] == ""
    assert rows[1]["panel_end_trim_mm"] == ""


def test_write_stock_summary_totals_each_material_batch(boards, tmp_path):
    path = tmp_path / "summary.csv"
    beams = [
        CutPiece("beam1", 1000, 45, 45, code="B1"),
        CutPiece("beam2", 1000, 45, 45, code="B2"),
    ]
    write_stock_summary(
        [("beam_45x45", beams, 2400.0), ("cladding_120x23", boards, 4500.0)],
        path,
        DEFAULT_KERF,
    )

    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))

    beam_row, cladding_row = rows
    assert (beam_row["stock_quantity"], beam_row["stock_length_mm"]) == ("1", "2400.0")
    # Both 1000 mm beams share one stock: 2400 - 2 * (1000 + kerf) waste.
    assert beam_row["total_waste_mm"] == "394.4"

    # The cladding batch runs through the gang-cut planner, not pack_stock.
    stocks = panel_stock_plan(boards, 4500.0, DEFAULT_KERF)
    assert cladding_row["stock_quantity"] == str(len(stocks))


def test_cutlists_main_writes_piece_schedules_and_stock_plans_when_run_as_a_script(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(sys, "argv", ["generate-cutlists", "--output", str(tmp_path)])

    _run_as_script("dass.cutlists")  # also proves the `__main__` guard calls main()

    for name in (
        "beam-pieces.csv",
        "cladding-pieces.csv",
        "stock-cut-plan.csv",
        "stock-summary.csv",
    ):
        assert (tmp_path / name).stat().st_size > 0

    assert (
        f"Wrote piece schedules and stock plan to {tmp_path}" in capsys.readouterr().out
    )


def test_cutlists_main_legacy_stock_length_overrides_both_material_groups(
    monkeypatch, tmp_path
):
    # 4500 is the cladding default but not the beam default (4200), so seeing
    # it on every row, beam and cladding alike, proves the single legacy flag
    # reached both groups.
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate-cutlists", "--output", str(tmp_path), "--stock-length", "4500"],
    )

    cutlists_main()

    with (tmp_path / "stock-cut-plan.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert {row["stock_length_mm"] for row in rows} == {"4500.0"}
    assert any(row["material"].startswith("beam_") for row in rows)
    assert any(row["material"].startswith("cladding_") for row in rows)


def test_cutlists_main_rejects_an_unknown_set_name(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate-cutlists", "--output", str(tmp_path), "--set", "bogus=1"],
    )

    with pytest.raises(SystemExit):
        cutlists_main()

    assert "--set must be NAME=MM" in capsys.readouterr().err


def test_cutlists_main_rejects_a_non_numeric_set_value(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate-cutlists", "--output", str(tmp_path), "--set", "frame=abc"],
    )

    with pytest.raises(SystemExit):
        cutlists_main()

    assert "requires a numeric value, got 'abc'" in capsys.readouterr().err


# dass.build_guide -----------------------------------------------------------


def test_build_guide_main_writes_the_guide_and_story_pages_when_run_as_a_script(
    monkeypatch, tmp_path, capsys
):
    output = tmp_path / "cut-guide.html"
    monkeypatch.setattr(sys, "argv", ["generate-build-guide", "--output", str(output)])

    _run_as_script("dass.build_guide")  # also proves the `__main__` guard calls main()

    assert "<h1>Can AI build a toilet yet?</h1>" in output.read_text()
    assert "<h2>How it started</h2>" in (tmp_path / "how-it-started.html").read_text()
    assert "<h2>How it's going</h2>" in (tmp_path / "how-its-going.html").read_text()
    assert f"Wrote {output}" in capsys.readouterr().out


# dass.photo_render ----------------------------------------------------------


def test_photo_render_lists_its_views_when_run_as_a_script(monkeypatch):
    # `--list-views` returns before any render, so this reaches the entry point
    # without building the model. It still asks the renderer for the names, so
    # the child process is stubbed rather than run: node is not a test
    # dependency, and CI never installs the render tree.
    commands = []

    def fake_run(command, **_):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(sys, "argv", ["render-photo", "--list-views"])
    monkeypatch.setattr(subprocess, "run", fake_run)

    _run_as_script("dass.photo_render")  # also proves the `__main__` guard calls main()

    assert commands == [["node", "web/render/render.mjs", "--list-views", "1"]]


# dass.serve -----------------------------------------------------------------


def test_serve_exits_clean_when_run_as_a_script_with_nothing_to_build(monkeypatch):
    # `--build` naming no stage runs no stage, which reaches main()'s exit
    # without binding a port, installing the renderer, or watching for saves.
    monkeypatch.setattr(sys, "argv", ["serve-guide", "--build"])

    with pytest.raises(SystemExit) as stop:
        _run_as_script("dass.serve")  # also proves the `__main__` guard calls main()

    assert stop.value.code == 0
