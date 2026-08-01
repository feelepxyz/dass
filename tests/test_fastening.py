import math

import pytest

from dass import Design
from dass.fastening import (
    Connection,
    ScrewMark,
    ScrewPath,
    _diagonal_station,
    _find_overlaps,
    analyze_frame_fastening,
    fastening_report,
    find_screw_path_collisions,
)
from tests.helpers import almost


@pytest.fixture(scope="module")
def analysis(design):
    return analyze_frame_fastening(design)


def test_every_screw_connects_two_modeled_frame_beams(analysis, parts):
    beam_names = {
        part.name
        for part in parts
        if part.material == "wood"
        and part.category not in {"side cladding", "back cladding"}
    }

    assert len(analysis.screws) > 0
    assert all(
        screw.from_beam in beam_names and screw.into_beam in beam_names
        for screw in analysis.screws
    )
    assert analysis.overlaps == ()


def test_diagonal_screws_are_angled_from_the_vertical_members(analysis, design):
    diagonal = [screw for screw in analysis.screws if screw.diagonal]
    assert diagonal
    assert min(screw.source_station_mm for screw in diagonal) >= design.frame
    assert (
        "Drive the 6 × 120 mm diagonal screws from the vertical members at a slight angle"
        in analysis.recommendations
    )
    assert all(
        path.source_exit_mm == design.frame
        for path in analysis.screw_paths
        if path.into_beam.endswith("brace")
    )


def test_diagonal_connections_run_from_vertical_members_and_clear_paths(analysis):
    diagonal_connections = {
        (screw.from_beam, screw.into_beam)
        for screw in analysis.screws
        if screw.diagonal
    }

    assert diagonal_connections == {
        ("front_post_left", "left_brace"),
        ("back_post_left", "left_brace"),
        ("front_post_right", "right_brace"),
        ("back_post_right", "right_brace"),
        ("back_post_left", "back_brace"),
        ("back_post_right", "back_brace"),
        ("door_left", "door_brace"),
        ("door_right", "door_brace"),
    }
    assert len(analysis.screw_paths) == 52
    assert analysis.path_collisions == ()


def test_screw_path_detector_catches_intersecting_centerlines():
    paths = (
        ScrewPath("A", "post", "rail", (0, 0, 0), (120, 0, 0), "x"),
        ScrewPath("B", "post", "brace", (60, -60, 0), (60, 60, 0), "y"),
    )

    assert find_screw_path_collisions(paths) == (("A", "B", 0.0),)
    assert find_screw_path_collisions(
        (
            paths[0],
            ScrewPath("C", "rail", "brace", (60, 0, 0), (180, 0, 0), "x"),
        )
    ) == (("A", "C", 0.0),)


def test_angles_keep_drawing_and_model_values_visible(analysis):
    angles = {check.code: check for check in analysis.angles}

    assert angles["SIDE-PITCH"].model_degrees == almost(7.4, 1)
    assert angles["ROOF-PITCH"].model_degrees == almost(8.8, 1)
    assert angles["D1"].drawing_degrees == almost(36.0, 1)
    assert angles["D2"].drawing_degrees == almost(40.0, 1)
    assert angles["D1"].drawing_degrees != angles["D1"].model_degrees


def test_report_records_collision_result_and_angle_check(design):
    report = fastening_report(design)

    assert "Screw-mark overlaps: 0" in report
    assert "Screw-path collisions: 0" in report
    assert "LSD1" in report
    assert "Measure the finished frame" in report
    assert "6 × 120 mm sunk wood screws" in report
    assert "6 × 90 mm sunk wood screws" in report
    assert "2.8 × 60 mm nails or 6 × 60 mm sunk wood screws" in report
    assert "Do not use the cladding fastener pattern" in report


def test_a_diagonal_the_schedule_cannot_place_names_itself(design):
    # Every diagonal gets its station from an explicit brace-by-brace rule. A
    # new brace added to CONNECTIONS without a matching rule would otherwise
    # take whichever station fell through, and be off by the setback.
    unplaceable = Connection("front_post_left", "roof_brace", "y", 0.0, diagonal=True)

    with pytest.raises(ValueError, match="unknown diagonal connection"):
        _diagonal_station(design, unplaceable)


def test_two_marks_closer_than_the_spacing_minimum_are_reported_as_one_overlap():
    # Same beam pair and same face, 12 mm apart across the station and lane
    # axes together, which is inside the 20 mm minimum.
    def mark(code: str, station: float, lane: float) -> ScrewMark:
        return ScrewMark(
            code, "front_post_left", "left_bottom", "y", station, 0.0, lane
        )

    crowded = (mark("A", 100.0, 0.0), mark("B", 109.0, 8.0))

    assert _find_overlaps(crowded) == (("A", "B", almost(math.hypot(9.0, 8.0))),)
    # A mark on a different face at the same station is a different joint.
    apart = (
        mark("A", 100.0, 0.0),
        ScrewMark("C", "front_post_left", "left_bottom", "z", 100.0, 0.0, 0.0),
    )
    assert _find_overlaps(apart) == ()


def test_a_schedule_naming_a_beam_the_model_does_not_build_is_rejected(monkeypatch):
    # The schedule is written by hand against the model's beam names, so a
    # rename in model.py must fail loudly here rather than silently drop screws.
    monkeypatch.setattr(
        "dass.fastening.CONNECTIONS",
        (Connection("front_post_left", "no_such_beam", "y", 100.0),),
    )

    with pytest.raises(ValueError, match=r"missing frame beams: \['no_such_beam'\]"):
        analyze_frame_fastening(Design())
