"""Coverage for the audit and overlay scripts under `scripts/`.

`scripts/` is not an installed package, so `import audit_cutlist` fails the way
`import build_web_assets` would. `dass.serve.staging` already reaches into
`scripts/build_web_assets.py` the same way these tests need to reach
`audit_cutlist.py`, `audit_fastening.py`, and `make_overlays.py`:
`importlib.util.spec_from_file_location` plus `module_from_spec` and
`exec_module`. That is chosen here over the alternative in
`test_deploy_cut_guide.py`, which only reads a shell script as text and never
runs it — these scripts must actually run to prove their behaviour.

Every script derives its own `ROOT` from `Path(__file__).resolve().parents[1]`
and writes relative to that, with no `argv` to redirect it. Loading a script
by path with `spec_from_file_location` leaves its module-level `OUTPUT` (and,
for `audit_cutlist`, `CSV_OUTPUT`) reassignable before `main()` runs, so
`monkeypatch.setattr(module, "OUTPUT", tmp_path / ...)` points every write at
`tmp_path` without touching the source.

That path only reaches lines executed while importing the module, so it never
runs the `if __name__ == "__main__": main()` guard at the bottom of each
script — the module's `__name__` is its own name, never `"__main__"`. Proving
that guard line real would otherwise mean running the script as a real
subprocess, which — because `ROOT` is derived only from the script's own
`__file__` — would write straight into the repository's `build/` or `docs/`,
exactly what this suite must never do. `run_entry_point` below avoids both:
it points a `SourceFileLoader` at the real `scripts/<name>.py` (so the code
object's filename, and so coverage, still credits the real file) but hands
`spec_from_file_location` a *different* location under `tmp_path` and the name
`"__main__"`. `module_from_spec` sets `__file__` and `__name__` from that
spec, not from the loader, so the executed script's own
`ROOT = Path(__file__).resolve().parents[1]` reads the `tmp_path` location and
its `if __name__ == "__main__":` guard fires — while every line still counts
against `scripts/<name>.py` for coverage.
"""

import csv
import importlib.machinery
import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import numpy as np
from PIL import Image

from dass import Design, Part, box_at
from dass.fastening import fastening_report

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

# A part's `.solid` is never read by any of these scripts; one cheap shared
# shape keeps the fake parts below valid `Part` instances without a build.
_SOLID = box_at(0, 0, 0, 10, 10, 10)


def load_script(name: str) -> ModuleType:
    """Load `scripts/<name>.py` by path, the way `dass.serve.staging` does."""
    source = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_entry_point(name: str, file_target: Path) -> None:
    """Run a script's own `if __name__ == "__main__":` guard for real.

    See the module docstring for why this reads from `scripts/<name>.py` but
    reports `file_target` as its location.
    """
    source = SCRIPTS / f"{name}.py"
    loader = importlib.machinery.SourceFileLoader("__main__", str(source))
    spec = importlib.util.spec_from_file_location(
        "__main__", str(file_target), loader=loader
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)


# audit_cutlist.py


def test_reconciled_cutlist_flags_the_modeled_mismatches(parts, tmp_path, monkeypatch):
    module = load_script("audit_cutlist")
    monkeypatch.setattr(module, "build", lambda design: (design, parts))
    report_path = tmp_path / "cutlist-audit.md"
    csv_path = tmp_path / "cutlist-side-by-side.csv"
    monkeypatch.setattr(module, "OUTPUT", report_path)
    monkeypatch.setattr(module, "CSV_OUTPUT", csv_path)

    module.main()

    # V1 is a quantity-and-length match; D1 keeps the reconciled quantity but
    # the exact geometry differs from the hand-transcribed length; HL2 has
    # more modeled parts than either reference table claims. Together they
    # exercise every branch of `matches` and both arms of `if not matches`.
    text = report_path.read_text()
    assert (
        "| V1 | 4 × 1150 | 4 × 1150 | 4 parts: 1150.0, 1150.0, 1150.0, 1150.0 | match |"
        in text
    )
    assert "| D1 | 2 × 1209 | 2 × 1209 | 2 parts: 1203.0, 1203.0 | ERROR |" in text
    assert (
        "| HL2 | 2 × 950 | 2 × 950 | 4 parts: 900.0, 900.0, 990.0, 990.0 | ERROR |"
        in text
    )
    assert "## Errors" in text
    assert "- D1: image=2 × 1209, drawing=2 × 1209, CAD=2 parts: 1203.0, 1203.0" in text
    assert "- No discrepancies" not in text

    with csv_path.open(newline="") as stream:
        rows = {row["part"]: row for row in csv.DictReader(stream)}
    assert rows["V1"]["result"] == "match"
    assert rows["D1"]["result"] == "ERROR"
    assert rows["HL2"]["cad_quantity"] == "4"


def test_reconciled_cutlist_reports_no_discrepancies_when_every_part_matches(
    tmp_path, monkeypatch
):
    module = load_script("audit_cutlist")
    clean_parts = [
        Part(f"{name}_{index}", name, _SOLID, length, 50, 50)
        for name, (quantity, length, _) in module.IMAGE_CUTLIST.items()
        for index in range(quantity)
    ]
    monkeypatch.setattr(module, "build", lambda design: (design, clean_parts))
    report_path = tmp_path / "cutlist-audit.md"
    monkeypatch.setattr(module, "OUTPUT", report_path)
    monkeypatch.setattr(module, "CSV_OUTPUT", tmp_path / "cutlist-side-by-side.csv")

    module.main()

    text = report_path.read_text()
    assert "ERROR" not in text
    assert "## Errors" not in text
    assert (
        "- No discrepancies were found among the eight labeled structural stock rows."
        in text
    )


def test_audit_cutlist_runs_as_a_script_and_writes_its_report(tmp_path, capsys):
    (tmp_path / "build").mkdir()

    run_entry_point("audit_cutlist", tmp_path / "scripts" / "audit_cutlist.py")

    report = (tmp_path / "build" / "cutlist-audit.md").read_text()
    assert report.startswith("# Cut-list audit")
    assert (tmp_path / "build" / "cutlist-side-by-side.csv").exists()
    assert "Wrote" in capsys.readouterr().out


# audit_fastening.py


def test_fastening_audit_writes_the_same_report_the_module_computes(
    design, tmp_path, monkeypatch
):
    module = load_script("audit_fastening")
    output_path = tmp_path / "fastening-audit.md"
    monkeypatch.setattr(module, "OUTPUT", output_path)

    module.main()

    assert output_path.read_text() == fastening_report(design)


def test_audit_fastening_runs_as_a_script_and_writes_its_report(tmp_path, capsys):
    run_entry_point("audit_fastening", tmp_path / "scripts" / "audit_fastening.py")

    output_path = tmp_path / "build" / "fastening-audit.md"
    assert output_path.read_text() == fastening_report(Design())
    assert "Wrote" in capsys.readouterr().out


# make_overlays.py

# Each render's overlay is composited only inside this (left, top, right,
# bottom) pixel box, read out of `scripts/make_overlays.py`'s own `main`.
_RENDER_OUTLINES = {
    "door-front": (50, 50, 685, 910),
    "seat-section": (50, 50, 670, 925),
}


def test_overlays_composite_red_lines_only_inside_each_render_outline(
    tmp_path, monkeypatch, capsys
):
    module = load_script("make_overlays")
    output_dir = tmp_path / "evolution"
    monkeypatch.setattr(module, "OUTPUT", output_dir)

    module.main()

    assert Image.open(output_dir / "drawing-door-front.png").size == (385, 475)
    assert Image.open(output_dir / "drawing-side-frame.png").size == (325, 495)
    assert Image.open(output_dir / "drawing-seat-section.png").size == (365, 490)

    for stem, (left, top, right, bottom) in _RENDER_OUTLINES.items():
        base = np.array(
            Image.open(output_dir / f"render-{stem}.png").convert("RGB")
        ).astype(int)
        composed = np.array(
            Image.open(output_dir / f"overlay-{stem}.png").convert("RGB")
        ).astype(int)
        assert base.shape == composed.shape

        outside = np.ones(base.shape[:2], dtype=bool)
        outside[top:bottom, left:right] = False
        # Nothing changes outside the render outline: the alpha channel the
        # red overlay was built from is zero everywhere off that box.
        assert np.array_equal(base[outside], composed[outside])
        # Inside it, the drawing's construction lines were actually painted.
        assert np.abs(base - composed)[top:bottom, left:right].max() > 0

    assert (
        f"Wrote drawing crops and overlays to {output_dir}" in capsys.readouterr().out
    )


def test_make_overlays_runs_as_a_script_and_writes_every_overlay(tmp_path, capsys):
    drawing_dir = tmp_path / "docs" / "original-drawing"
    drawing_dir.mkdir(parents=True)
    shutil.copy(
        ROOT / "docs" / "original-drawing" / "drawing-sides.png",
        drawing_dir / "drawing-sides.png",
    )

    run_entry_point("make_overlays", tmp_path / "scripts" / "make_overlays.py")

    output_dir = tmp_path / "docs" / "verification" / "evolution"
    assert (output_dir / "overlay-door-front.png").exists()
    assert (output_dir / "overlay-seat-section.png").exists()
    assert "Wrote drawing crops and overlays" in capsys.readouterr().out
