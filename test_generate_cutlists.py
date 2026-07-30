import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from dass import Design
from generate_cutlists import (
    CutPiece,
    beam_pieces,
    cladding_pieces,
    pack_stock,
    write_stock_plan,
)


class CutListTest(unittest.TestCase):
    def test_pack_stock_preserves_pieces_and_accounts_for_kerf(self):
        pieces = [
            CutPiece("a", 1200, 50, 50),
            CutPiece("b", 1198, 50, 50),
            CutPiece("c", 800, 50, 50),
        ]
        stocks = pack_stock(pieces, stock_length=2400, kerf=2)

        self.assertEqual(
            Counter(piece.name for stock in stocks for piece in stock),
            Counter(piece.name for piece in pieces),
        )
        self.assertEqual(len(stocks), 2)
        for stock in stocks:
            used = sum(piece.length for piece in stock) + 2 * (len(stock) - 1)
            self.assertLessEqual(used, 2400)

    def test_rejects_impossible_or_invalid_stock_inputs(self):
        with self.assertRaises(ValueError):
            pack_stock([CutPiece("too_long", 2401, 50, 50)])
        with self.assertRaises(ValueError):
            pack_stock([], kerf=-1)

    def test_dass_piece_schedules_include_roof_connector_and_cladding(self):
        design = Design()
        beams = beam_pieces(design)
        cladding = cladding_pieces(design)

        connector = next(piece for piece in beams if piece.name == "roof_middle")
        self.assertEqual((connector.length, connector.width, connector.thickness), (850, 65, 23))
        self.assertEqual(sum(piece.name.startswith("door_") for piece in cladding), 8)
        self.assertEqual(sum(piece.name.startswith("roof_") for piece in cladding), 0)
        self.assertEqual(sum(piece.name.startswith("left_wall_") for piece in cladding), 7)
        self.assertTrue(all(piece.length <= 2400 for piece in beams + cladding))

    def test_written_plan_never_exceeds_stock(self):
        pieces = cladding_pieces(Design())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.csv"
            write_stock_plan([("cladding", pieces)], path, 2400, 2)
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertTrue(rows)
        self.assertTrue(all(float(row["used_mm"]) <= 2400 for row in rows))

    def test_variant_fits_requested_stock_options(self):
        design = Design(
            frame=45,
            cladding=23,
            roof_connector_width=45,
            roof_connector_thickness=45,
        )
        self.assertEqual(len(pack_stock(beam_pieces(design), 2400, 2)), 13)
        self.assertEqual(len(pack_stock(beam_pieces(design), 3600, 2)), 9)
        self.assertEqual(
            [len(pack_stock(cladding_pieces(design), length, 2))
             for length in (3600, 4200, 5400)],
            [13, 11, 9],
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
        self.assertTrue(all(0 < piece.width <= 120 for piece in cladding))
        self.assertIn(120, {piece.width for piece in cladding})


if __name__ == "__main__":
    unittest.main()
