import unittest

from dass import Design, build
from dass.fastening import (
    ScrewPath,
    analyze_frame_fastening,
    fastening_report,
    find_screw_path_collisions,
)


class FrameFasteningTest(unittest.TestCase):
    def test_every_screw_connects_two_modeled_frame_beams(self):
        design = Design()
        analysis = analyze_frame_fastening(design)
        _, parts = build(design)
        beam_names = {
            part.name
            for part in parts
            if part.material == "wood"
            and part.category not in {"side cladding", "back cladding"}
        }

        self.assertGreater(len(analysis.screws), 0)
        self.assertTrue(
            all(
                screw.from_beam in beam_names and screw.into_beam in beam_names
                for screw in analysis.screws
            )
        )
        self.assertEqual(analysis.overlaps, ())

    def test_diagonal_screws_are_angled_from_the_vertical_members(self):
        analysis = analyze_frame_fastening(Design())

        diagonal = [screw for screw in analysis.screws if screw.diagonal]
        self.assertTrue(diagonal)
        self.assertGreaterEqual(
            min(screw.source_station_mm for screw in diagonal),
            Design().frame,
        )
        self.assertIn(
            "Drive the 6 × 120 mm diagonal screws from the vertical members at a slight angle",
            analysis.recommendations,
        )
        self.assertTrue(
            all(
                path.source_exit_mm == Design().frame
                for path in analysis.screw_paths
                if path.into_beam.endswith("brace")
            )
        )

    def test_diagonal_connections_run_from_vertical_members_and_clear_paths(self):
        analysis = analyze_frame_fastening(Design())
        diagonal_connections = {
            (screw.from_beam, screw.into_beam)
            for screw in analysis.screws
            if screw.diagonal
        }

        self.assertEqual(
            diagonal_connections,
            {
                ("front_post_left", "left_brace"),
                ("back_post_left", "left_brace"),
                ("front_post_right", "right_brace"),
                ("back_post_right", "right_brace"),
                ("back_post_left", "back_brace"),
                ("back_post_right", "back_brace"),
                ("door_left", "door_brace"),
                ("door_right", "door_brace"),
            },
        )
        self.assertEqual(len(analysis.screw_paths), 52)
        self.assertEqual(analysis.path_collisions, ())

    def test_screw_path_detector_catches_intersecting_centerlines(self):
        paths = (
            ScrewPath("A", "post", "rail", (0, 0, 0), (120, 0, 0), "x"),
            ScrewPath("B", "post", "brace", (60, -60, 0), (60, 60, 0), "y"),
        )

        self.assertEqual(find_screw_path_collisions(paths), (("A", "B", 0.0),))
        self.assertEqual(
            find_screw_path_collisions(
                (
                    paths[0],
                    ScrewPath("C", "rail", "brace", (60, 0, 0), (180, 0, 0), "x"),
                )
            ),
            (("A", "C", 0.0),),
        )

    def test_angles_keep_drawing_and_model_values_visible(self):
        analysis = analyze_frame_fastening(Design())
        angles = {check.code: check for check in analysis.angles}

        self.assertAlmostEqual(angles["SIDE-PITCH"].model_degrees, 7.4, places=1)
        self.assertAlmostEqual(angles["ROOF-PITCH"].model_degrees, 8.8, places=1)
        self.assertAlmostEqual(angles["D1"].drawing_degrees, 36.0, places=1)
        self.assertAlmostEqual(angles["D2"].drawing_degrees, 40.0, places=1)
        self.assertNotEqual(angles["D1"].drawing_degrees, angles["D1"].model_degrees)

    def test_report_records_collision_result_and_angle_check(self):
        report = fastening_report(Design())

        self.assertIn("Screw-mark overlaps: 0", report)
        self.assertIn("Screw-path collisions: 0", report)
        self.assertIn("LSD1", report)
        self.assertIn("Measure the finished frame", report)
        self.assertIn("6 × 120 mm sunk wood screws", report)
        self.assertIn("6 × 90 mm sunk wood screws", report)
        self.assertIn("2.8 × 60 mm nails or 6 × 60 mm sunk wood screws", report)
        self.assertIn("Do not use the cladding fastener pattern", report)


if __name__ == "__main__":
    unittest.main()
