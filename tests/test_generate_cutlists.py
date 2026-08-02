import csv
import re
from collections import Counter
from dataclasses import replace

import pytest

from dass import Design
from dass.cutlists import (
    DEFAULT_KERF,
    CutPiece,
    beam_pieces,
    cladding_pieces,
    pack_stock,
    panel_stock_plan,
    write_stock_plan,
)


def test_default_kerf_is_2_8_mm():
    assert DEFAULT_KERF == 2.8


def test_pack_stock_preserves_pieces_and_accounts_for_kerf():
    pieces = [
        CutPiece("a", 1200, 50, 50),
        CutPiece("b", 1198, 50, 50),
        CutPiece("c", 800, 50, 50),
    ]
    stocks = pack_stock(pieces, stock_length=2400, kerf=DEFAULT_KERF)

    assert Counter(piece.name for stock in stocks for piece in stock) == Counter(
        piece.name for piece in pieces
    )
    assert len(stocks) == 2
    for stock in stocks:
        used = sum(piece.length for piece in stock) + DEFAULT_KERF * len(stock)
        assert used <= 2400


def test_rejects_impossible_or_invalid_stock_inputs(boards):
    with pytest.raises(ValueError):
        pack_stock([CutPiece("too_long", 2401, 50, 50)])
    with pytest.raises(ValueError):
        pack_stock([], kerf=-1)
    with pytest.raises(ValueError):
        panel_stock_plan(boards, stock_limit=0)
    with pytest.raises(ValueError, match="three letters and two digits"):
        cladding_pieces(Design(width=12000))


def test_dass_piece_schedules_include_roof_connector_and_cladding(beams, boards):
    connector = next(piece for piece in beams if piece.name == "roof_middle")
    assert (connector.length, connector.width, connector.thickness) == (900, 45, 45)
    assert sum(piece.name.startswith("door_") for piece in boards) == 9
    assert sum(piece.name.startswith("roof_") for piece in boards) == 0
    assert sum(piece.name.startswith("left_wall_") for piece in boards) == 7
    assert all(piece.length <= 4500 for piece in beams + boards)


def test_written_plan_never_exceeds_stock(boards, tmp_path):
    path = tmp_path / "plan.csv"
    write_stock_plan(
        [("cladding_120x23", boards, 4500)],
        path,
        DEFAULT_KERF,
    )
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 12
    assert all(float(row["used_mm"]) <= 4500 for row in rows)


def test_variant_fits_requested_stock_options():
    design = Design(
        frame=45,
        cladding=23,
        roof_connector_width=45,
        roof_connector_thickness=45,
    )
    assert len(pack_stock(beam_pieces(design), 4200, DEFAULT_KERF)) == 9
    assert len(panel_stock_plan(cladding_pieces(design), 4500, DEFAULT_KERF)) == 12


def test_45x45_120x23_variant_cut_pieces_use_requested_profiles():
    design = Design(
        frame=45,
        cladding=23,
        roof_connector_width=45,
        roof_connector_thickness=45,
    )
    assert {(piece.width, piece.thickness) for piece in beam_pieces(design)} == {
        (45, 45)
    }
    floor_bearers = {
        piece.name: piece.length
        for piece in beam_pieces(design)
        if piece.name.startswith("floor_")
    }
    assert floor_bearers == {
        "floor_back_support": design.interior_width,
        "floor_left_support": design.back_wall_front - 2 * design.frame,
        "floor_right_support": design.back_wall_front - 2 * design.frame,
    }
    seat_bearers = {
        piece.name: piece.length
        for piece in beam_pieces(design)
        if piece.name.startswith("seat_box_support_")
    }
    assert seat_bearers == {
        "seat_box_support_front": design.interior_width,
        "seat_box_support_rear": design.interior_width,
    }
    outer_seat_bearers = {
        piece.name: piece.length
        for piece in beam_pieces(design)
        if piece.name.startswith("seat_support_outer_")
    }
    assert outer_seat_bearers == {
        "seat_support_outer_left": design.seat_support_length,
        "seat_support_outer_right": design.seat_support_length,
    }
    cladding = cladding_pieces(design)
    assert all(piece.thickness == 23 for piece in cladding)
    assert {piece.width for piece in cladding} == {120}
    codes = [piece.code for piece in beam_pieces(design) + cladding]
    assert len(codes) == len(set(codes))
    assert all(re.fullmatch(r"[A-Z]{1,3}\d{1,2}", code) for code in codes)


def test_equal_beam_lengths_form_one_uninterrupted_run_across_stock(beams):
    lengths = [
        round(piece.length, 1)
        for stock in pack_stock(beams, 4200, DEFAULT_KERF)
        for piece in stock
    ]
    for length in set(lengths):
        first = lengths.index(length)
        last = len(lengths) - 1 - lengths[::-1].index(length)
        assert lengths[first : last + 1] == [length] * lengths.count(length)


def test_panel_plan_reuses_only_shortest_batch_to_fit_twelve_stock_lengths(boards):
    stocks = panel_stock_plan(
        boards,
        4500,
        DEFAULT_KERF,
    )

    assert len(stocks) == 12
    assert [
        [piece.code for piece in stock if piece.length == 397] for stock in stocks
    ] == [["SFB1", "SFB2"], ["SFB3", "SFB4"], ["SFB5", "SFB6"]] + [[]] * 6 + [
        ["SFB7"],
        ["SFB8"],
        [],
    ]


def test_raspont_coverage_leaves_trim_and_side_walls_are_gang_cut(design, boards):
    panel_spans = {
        "door": (design.width, 9),
        "back_wall": (design.interior_width, 8),
        "floor": (design.interior_width, 8),
        "seat_top": (design.seat_depth, 5),
        "seat_front": (design.interior_width, 8),
        "left_wall": (design.plan_grid_depth, 7),
        "right_wall": (design.plan_grid_depth, 7),
    }
    for prefix, (span, count) in panel_spans.items():
        panel = [piece for piece in boards if piece.name.startswith(prefix + "_")]
        assert len(panel) == count
        assert count * 110 + 10 - span >= 10
        assert {piece.panel_end_trim for piece in panel} == {count * 110 + 10 - span}

    seat_top = [piece for piece in boards if piece.name.startswith("seat_top_")]
    assert {piece.length for piece in seat_top} == {design.seat_box_width}
    assert {piece.panel_end_trim for piece in seat_top} == {60.0}

    for side in ("left_wall", "right_wall"):
        panel = [piece for piece in boards if piece.gang_cut == side]
        assert len(panel) == 7
        assert {piece.length for piece in panel} == {design.door_height}
        assert all(
            piece.finished_long is not None
            and piece.finished_short is not None
            and piece.finished_long > piece.finished_short
            for piece in panel
        )


def test_profile_reads_as_a_stock_profile_label():
    assert CutPiece("beam", 1000, 45, 45).profile == "45x45"
    assert CutPiece("board", 1000, 120, 23).profile == "120x23"


def test_panel_stock_plan_rejects_pieces_without_two_equal_gang_cut_sets():
    with pytest.raises(ValueError, match="two equal side-panel sets"):
        panel_stock_plan([CutPiece("square", 900, 45, 45)])


def test_panel_stock_plan_rejects_gang_cut_blanks_of_different_lengths():
    pieces = [
        CutPiece("l1", 100, 120, 23, gang_cut="left_wall", code="L1"),
        CutPiece("l2", 100, 120, 23, gang_cut="left_wall", code="L2"),
        CutPiece("r1", 200, 120, 23, gang_cut="right_wall", code="R1"),
        CutPiece("r2", 200, 120, 23, gang_cut="right_wall", code="R2"),
    ]
    with pytest.raises(ValueError, match="must share one length"):
        panel_stock_plan(pieces)


def test_panel_stock_plan_rejects_a_batch_that_cannot_be_compacted_to_fit(boards):
    # Every side board is close to the 1175 mm door height, so a stock only
    # just longer than one board leaves no room to compact a dozen of them
    # down to a single length.
    with pytest.raises(ValueError, match="do not fit 1 stock lengths"):
        panel_stock_plan(boards, stock_length=1200, stock_limit=1)


def test_board_count_corrects_a_float_rounding_shortfall_at_extreme_scale():
    """`board_count` proves, by construction, that its naive board count
    always leaves at least `minimum_end_trim`; the `+ 1` correction exists
    only to guard against float64 rounding noise in that proof, which needs
    values far outside any real råspont job to actually surface. At the
    literal defaults (mm-scale spans), the correction is unreachable; at
    these extreme magnitudes it fires, and this is that one case."""
    cover_width = 897197477.5240914
    board_width = 1026241448.6234032
    minimum_end_trim = 139895398.22695148
    span = 76250934162.42014
    design = replace(Design(), width=span)

    pieces = cladding_pieces(
        design,
        board_width=board_width,
        cover_width=cover_width,
        minimum_end_trim=minimum_end_trim,
    )

    door = [piece for piece in pieces if piece.name.startswith("door_")]
    # The naive ceil() count for this span leaves a trim a hair under the
    # minimum once rounded in float64; without the correction this would be
    # 85 boards and would violate `minimum_end_trim`.
    assert len(door) == 86
    trim = door[0].panel_end_trim
    assert trim is not None
    assert trim >= minimum_end_trim
