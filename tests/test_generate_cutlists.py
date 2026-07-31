import csv
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

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


class CutListTest(unittest.TestCase):
    def test_default_kerf_is_2_8_mm(self):
        self.assertEqual(DEFAULT_KERF, 2.8)

    def test_pack_stock_preserves_pieces_and_accounts_for_kerf(self):
        pieces = [
            CutPiece("a", 1200, 50, 50),
            CutPiece("b", 1198, 50, 50),
            CutPiece("c", 800, 50, 50),
        ]
        stocks = pack_stock(pieces, stock_length=2400, kerf=DEFAULT_KERF)

        self.assertEqual(
            Counter(piece.name for stock in stocks for piece in stock),
            Counter(piece.name for piece in pieces),
        )
        self.assertEqual(len(stocks), 2)
        for stock in stocks:
            used = sum(piece.length for piece in stock) + DEFAULT_KERF * len(stock)
            self.assertLessEqual(used, 2400)

    def test_rejects_impossible_or_invalid_stock_inputs(self):
        with self.assertRaises(ValueError):
            pack_stock([CutPiece("too_long", 2401, 50, 50)])
        with self.assertRaises(ValueError):
            pack_stock([], kerf=-1)
        with self.assertRaises(ValueError):
            panel_stock_plan(cladding_pieces(Design()), stock_limit=0)
        with self.assertRaisesRegex(ValueError, "three letters and two digits"):
            cladding_pieces(Design(width=12000))

    def test_dass_piece_schedules_include_roof_connector_and_cladding(self):
        design = Design()
        beams = beam_pieces(design)
        cladding = cladding_pieces(design)

        connector = next(piece for piece in beams if piece.name == "roof_middle")
        self.assertEqual((connector.length, connector.width, connector.thickness), (900, 45, 45))
        self.assertEqual(sum(piece.name.startswith("door_") for piece in cladding), 9)
        self.assertEqual(sum(piece.name.startswith("roof_") for piece in cladding), 0)
        self.assertEqual(sum(piece.name.startswith("left_wall_") for piece in cladding), 7)
        self.assertTrue(all(piece.length <= 4500 for piece in beams + cladding))

    def test_written_plan_never_exceeds_stock(self):
        pieces = cladding_pieces(Design())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.csv"
            write_stock_plan(
                [("cladding_120x23", pieces, 4500)],
                path,
                DEFAULT_KERF,
            )
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(float(row["used_mm"]) <= 4500 for row in rows))

    def test_variant_fits_requested_stock_options(self):
        design = Design(
            frame=45,
            cladding=23,
            roof_connector_width=45,
            roof_connector_thickness=45,
        )
        self.assertEqual(
            len(pack_stock(beam_pieces(design), 4200, DEFAULT_KERF)),
            8,
        )
        self.assertEqual(
            len(panel_stock_plan(cladding_pieces(design), 4500, DEFAULT_KERF)),
            12,
        )

    def test_45x45_120x23_variant_cut_pieces_use_requested_profiles(self):
        design = Design(
            frame=45,
            cladding=23,
            roof_connector_width=45,
            roof_connector_thickness=45,
        )
        self.assertEqual(
            {(piece.width, piece.thickness) for piece in beam_pieces(design)},
            {(45, 45)},
        )
        floor_bearers = {
            piece.name: piece.length
            for piece in beam_pieces(design)
            if piece.name.startswith("floor_")
        }
        self.assertEqual(
            floor_bearers,
            {
                "floor_back_support": design.interior_width,
                "floor_left_support": design.back_wall_front - 2 * design.frame,
                "floor_right_support": design.back_wall_front - 2 * design.frame,
            },
        )
        cladding = cladding_pieces(design)
        self.assertTrue(all(piece.thickness == 23 for piece in cladding))
        self.assertEqual({piece.width for piece in cladding}, {120})
        codes = [piece.code for piece in beam_pieces(design) + cladding]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(re.fullmatch(r"[A-Z]{1,3}\d{1,2}", code) for code in codes))

    def test_equal_beam_lengths_form_one_uninterrupted_run_across_stock(self):
        lengths = [
            round(piece.length, 1)
            for stock in pack_stock(beam_pieces(Design()), 4200, DEFAULT_KERF)
            for piece in stock
        ]
        for length in set(lengths):
            first = lengths.index(length)
            last = len(lengths) - 1 - lengths[::-1].index(length)
            self.assertEqual(lengths[first:last + 1], [length] * lengths.count(length))

    def test_panel_plan_reuses_only_shortest_batch_to_fit_twelve_stock_lengths(self):
        stocks = panel_stock_plan(
            cladding_pieces(Design()),
            4500,
            DEFAULT_KERF,
        )

        self.assertEqual(len(stocks), 12)
        self.assertEqual(
            [[piece.code for piece in stock if piece.length == 397] for stock in stocks],
            [["SFB1", "SFB2"], ["SFB3", "SFB4"], ["SFB5", "SFB6"]]
            + [[]] * 8
            + [["SFB7", "SFB8"]],
        )

    def test_raspont_coverage_leaves_trim_and_side_walls_are_gang_cut(self):
        design = Design()
        pieces = cladding_pieces(design)

        panel_spans = {
            "door": (design.width, 9),
            "back_wall": (design.interior_width, 8),
            "floor": (design.interior_width, 8),
            "seat_top": (design.interior_width, 8),
            "seat_front": (design.interior_width, 8),
            "left_wall": (design.plan_grid_depth, 7),
            "right_wall": (design.plan_grid_depth, 7),
        }
        for prefix, (span, count) in panel_spans.items():
            panel = [piece for piece in pieces if piece.name.startswith(prefix + "_")]
            self.assertEqual(len(panel), count)
            self.assertGreaterEqual(count * 110 + 10 - span, 10)
            self.assertEqual(
                {piece.panel_end_trim for piece in panel},
                {count * 110 + 10 - span},
            )

        for side in ("left_wall", "right_wall"):
            panel = [piece for piece in pieces if piece.gang_cut == side]
            self.assertEqual(len(panel), 7)
            self.assertEqual({piece.length for piece in panel}, {design.door_height})
            self.assertTrue(all(
                piece.finished_long > piece.finished_short for piece in panel
            ))


if __name__ == "__main__":
    unittest.main()
