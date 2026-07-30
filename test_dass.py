import unittest

import cadquery as cq

from dass import Design, box_at, build, door_brace_endpoints


class DassModelTest(unittest.TestCase):
    def test_reference_dimensions_and_panels(self):
        design = Design()
        design.validate_reference()
        _, parts = build(design)
        panels = {(p.category, round(p.length), round(p.width)): 1 for p in parts}
        for expected in {
            ("side cladding", 800, 1175),
            ("back cladding", 850, 1050),
            ("cladding", 1175, 950),
            ("floor", 775, 800),
            ("seat top", 500, 800),
            ("seat side", 395, 800),
        }:
            self.assertIn(expected, panels)
        self.assertEqual(
            sorted((part.category, part.length) for part in parts if part.category in {"V1", "V2"}),
            [("V1", 1150)] * 4 + [("V2", 1050)] * 2,
        )

    def test_width_variant_updates_geometry_and_cut_lengths(self):
        design = Design(width=1050)
        _, parts = build(design)
        grouped = {(p.category, round(p.length)) for p in parts}
        self.assertIn(("HL1", 950), grouped)
        self.assertIn(("HL2", 1050), grouped)
        self.assertIn(("D2", round(((1050 - 100) ** 2 + 950**2) ** 0.5)), grouped)

    def test_45x45_120x20_variant_uses_requested_profiles(self):
        design = Design(
            frame=45,
            cladding=20,
            roof_connector_width=45,
            roof_connector_thickness=45,
        )
        _, parts = build(design)
        structural = [
            part for part in parts
            if part.material == "wood" and part.thickness != design.cladding
        ]
        self.assertTrue(structural)
        self.assertEqual(
            {(part.width, part.thickness) for part in structural},
            {(45, 45)},
        )

    def test_floor_seat_and_hinge_follow_section_datums(self):
        design = Design()
        _, parts = build(design)
        by_name = {part.name: part for part in parts}

        floor = by_name["floor"].solid.BoundingBox()
        self.assertEqual(
            (floor.xmin, floor.xmax, floor.ymin, floor.ymax, floor.zmin, floor.zmax),
            (75, 875, 0, 775, 150, 175),
        )
        floor_support = by_name["floor_back_support"].solid.BoundingBox()
        self.assertEqual(
            (floor_support.xmin, floor_support.xmax,
             floor_support.ymin, floor_support.ymax, floor_support.zmax),
            (75, 875, 725, 775, floor.zmin),
        )

        seat_front = by_name["seat_front"].solid.BoundingBox()
        seat_top = by_name["seat_top"].solid.BoundingBox()
        self.assertEqual((seat_front.zmin, seat_front.zmax), (175, 570))
        self.assertEqual((seat_top.zmin, seat_top.zmax), (570, 595))
        for name in ("seat_rail_1", "seat_rail_2"):
            rail = by_name[name].solid.BoundingBox()
            self.assertLessEqual(rail.zmax, seat_top.zmin)

        front_post = by_name["front_post_left"].solid.BoundingBox()
        self.assertEqual((front_post.zmin, front_post.zmax), (0, 1150))
        bottom_rail = by_name["front_bottom"].solid.BoundingBox()
        self.assertEqual(bottom_rail.zmin - front_post.zmin, design.leg_extension)
        for name in ("left_wall", "right_wall", "back_wall"):
            self.assertEqual(by_name[name].solid.BoundingBox().zmin, design.leg_extension)
        self.assertNotIn("back_brace", by_name)

        door = by_name["door_right"].solid.BoundingBox()
        door_panel = by_name["door_panel"].solid.BoundingBox()
        self.assertEqual((door.zmin, door.zmax), (100, 1150))
        self.assertEqual((door_panel.zmin, door_panel.zmax), (100, 1275))
        self.assertEqual(door_panel.zmin, by_name["door_bottom"].solid.BoundingBox().zmin)
        self.assertEqual(door_panel.ymin, door.ymax)
        structure = by_name["front_post_right"].solid.BoundingBox()
        self.assertLessEqual(door.ymax, structure.ymin - design.hinge_gap)
        self.assertIn("door_hinge_1", by_name)
        self.assertIn("door_hinge_2", by_name)

    def test_wall_seat_and_floor_clearances_follow_panel_faces(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}

        left = by_name["left_wall"].solid.BoundingBox()
        right = by_name["right_wall"].solid.BoundingBox()
        back = by_name["back_wall"].solid.BoundingBox()
        self.assertEqual((left.ymin, left.ymax), (0, 800))
        self.assertEqual(left.ymin, by_name["front_post_left"].solid.BoundingBox().ymin)

        for name in (
            "floor", "seat_front", "seat_top",
            "seat_rail_1", "seat_rail_2", "seat_lower_rail",
        ):
            box = by_name[name].solid.BoundingBox()
            self.assertGreaterEqual(box.xmin, left.xmax)
            self.assertLessEqual(box.xmax, right.xmin)
            self.assertLessEqual(box.ymax, back.ymin)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["left_wall"].solid).Volume(), 0)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["right_wall"].solid).Volume(), 0)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["back_wall"].solid).Volume(), 0)

    def test_hk1_rails_are_unique_and_frame_each_side_brace(self):
        design = Design()
        _, parts = build(design)
        rails = [part for part in parts if part.category == "HK1"]

        self.assertEqual(len(rails), 4)
        self.assertEqual({part.length for part in rails}, {750})
        self.assertEqual(
            {part.name for part in rails},
            {"left_bottom", "left_top", "right_bottom", "right_top"},
        )
        self.assertEqual(
            {(part.solid.BoundingBox().xmin, part.solid.BoundingBox().zmin) for part in rails},
            {(0, 100), (0, 1100), (900, 100), (900, 1100)},
        )

    def test_door_is_clear_of_structure_and_connected_by_hinges(self):
        design = Design()
        for angle in (0, 105):
            _, parts = build(design, door_angle=angle)
            by_name = {part.name: part for part in parts}
            door = cq.Compound.makeCompound([
                by_name[name].solid
                for name in (
                    "door_panel", "door_left", "door_right",
                    "door_bottom", "door_top", "door_brace",
                )
            ])
            structure = cq.Compound.makeCompound([
                by_name[name].solid
                for name in ("front_post_left", "front_post_right", "front_bottom")
            ])
            self.assertAlmostEqual(door.intersect(structure).Volume(), 0)

        closed = {part.name: part for part in build(design, door_angle=0)[1]}
        door_face = closed["door_panel"].solid.BoundingBox().ymax
        structure_face = closed["front_post_right"].solid.BoundingBox().ymin
        self.assertEqual(structure_face - door_face, design.hinge_gap)
        self.assertEqual(
            closed["hinge_door_1"].solid.BoundingBox().ymin,
            closed["door_panel"].solid.BoundingBox().ymax,
        )
        self.assertEqual(closed["hinge_fixed_1"].solid.BoundingBox().ymax, structure_face)
        self.assertGreater(
            closed["door_hinge_1"].solid.intersect(closed["hinge_door_1"].solid).Volume(),
            0,
        )
        self.assertGreater(
            closed["door_hinge_1"].solid.intersect(closed["hinge_fixed_1"].solid).Volume(),
            0,
        )

    def test_roof_pitch_frame_and_door_alignment(self):
        design = Design()
        _, parts = build(design)
        by_name = {part.name: part for part in parts}

        door_frame = cq.Compound.makeCompound([
            by_name[name].solid
            for name in ("door_left", "door_right", "door_bottom", "door_top")
        ]).BoundingBox()
        self.assertEqual((door_frame.xlen, door_frame.zlen), (950, 1050))
        self.assertEqual(door_frame.zmin, design.leg_extension)
        self.assertEqual(
            door_frame.zmin,
            by_name["front_bottom"].solid.BoundingBox().zmin,
        )

        panel = by_name["door_panel"].solid.BoundingBox()
        self.assertEqual((panel.xlen, panel.zlen), (950, 1175))
        self.assertEqual(panel.zmax, design.door_bottom + design.door_height)
        back_wall = by_name["back_wall"].solid.BoundingBox()
        self.assertEqual((back_wall.zmin, back_wall.zlen), (100, 1050))

        self.assertAlmostEqual(
            by_name["roof"].solid.intersect(by_name["door_panel"].solid).Volume(),
            0,
        )

        back_post = by_name["back_post_left"].solid.BoundingBox()
        back_top = by_name["back_top"].solid.BoundingBox()
        fixed_hinge = by_name["roof_hinge_fixed"].solid.BoundingBox()
        roof_back = by_name["roof_back"].solid.BoundingBox()
        self.assertEqual(back_top.zmax, back_post.zmax)
        self.assertEqual(fixed_hinge.ymin, back_top.ymax)
        self.assertEqual(fixed_hinge.zmax, back_post.zmax + design.roof_hinge_pin_radius)
        self.assertGreater(
            by_name["roof_hinge_pin"].solid.intersect(by_name["roof_hinge_fixed"].solid).Volume(),
            0,
        )
        self.assertGreater(
            by_name["roof_hinge_pin"].solid.intersect(by_name["roof_hinge_moving"].solid).Volume(),
            0,
        )
        self.assertAlmostEqual(roof_back.ymax, back_top.ymax, delta=2)
        self.assertGreaterEqual(roof_back.zmin, back_top.zmax)

        roof_frame = cq.Compound.makeCompound([
            by_name[name].solid
            for name in ("roof_front", "roof_back", "roof_left", "roof_right")
        ]).BoundingBox()
        self.assertAlmostEqual(roof_frame.xlen, 950)
        roof = by_name["roof"].solid.BoundingBox()
        self.assertAlmostEqual(roof.xlen, 1050, places=6)
        self.assertAlmostEqual(roof.ylen, 1085, places=6)
        self.assertAlmostEqual(
            (roof.xmin + roof.xmax) / 2,
            (roof_frame.xmin + roof_frame.xmax) / 2,
            places=6,
        )
        self.assertAlmostEqual(
            (roof.ymin + roof.ymax) / 2,
            (roof_frame.ymin + roof_frame.ymax) / 2,
            places=6,
        )
        self.assertEqual(by_name["roof"].material, "metal roof")
        self.assertEqual(design.roof_frame_depth, 933)
        self.assertEqual(design.roof_rise, 125)
        self.assertEqual(design.roof_run, 833)
        connector = by_name["roof_middle"]
        self.assertEqual(
            (connector.length, connector.width, connector.thickness),
            (850, 65, 25),
        )

        roof_normal = max(
            (face.normalAt() for face in by_name["roof"].solid.Faces()),
            key=lambda normal: normal.z,
        )
        for name in ("roof_front", "roof_back", "roof_left", "roof_right", "roof_middle"):
            beam_normal = max(
                (face.normalAt() for face in by_name[name].solid.Faces()),
                key=lambda normal: normal.z,
            )
            self.assertAlmostEqual(beam_normal.dot(roof_normal), 1, places=6)

        self.assertAlmostEqual(
            by_name["roof_back"].solid.intersect(by_name["back_top"].solid).Volume(),
            0,
        )

    def test_roof_lifts_as_one_hinged_assembly(self):
        design = Design()
        closed = {part.name: part for part in build(design, roof_lift_angle=0)[1]}
        lifted = {part.name: part for part in build(design, roof_lift_angle=25)[1]}

        moving = ("roof", "roof_front", "roof_back", "roof_left", "roof_right", "roof_middle")
        for name in moving:
            self.assertGreater(
                lifted[name].solid.Center().z,
                closed[name].solid.Center().z,
            )
        lifted_pin = lifted["roof_hinge_pin"].solid.BoundingBox()
        closed_pin = closed["roof_hinge_pin"].solid.BoundingBox()
        self.assertEqual(
            (lifted_pin.xmin, lifted_pin.ymin, lifted_pin.zmin,
             lifted_pin.xmax, lifted_pin.ymax, lifted_pin.zmax),
            (closed_pin.xmin, closed_pin.ymin, closed_pin.zmin,
             closed_pin.xmax, closed_pin.ymax, closed_pin.zmax),
        )
        self.assertAlmostEqual(
            lifted["roof"].solid.intersect(lifted["back_top"].solid).Volume(),
            0,
        )

    def test_door_brace_reaches_inside_frame_corners(self):
        design = Design()
        _, parts = build(design)
        brace = next(part for part in parts if part.name == "door_brace").solid.BoundingBox()
        self.assertLessEqual(brace.xmin, design.frame)
        self.assertGreaterEqual(brace.xmax, design.width - design.frame)
        self.assertLessEqual(brace.zmin, design.door_bottom + design.frame)
        self.assertGreaterEqual(
            brace.zmax,
            design.door_bottom + design.door_frame_height - design.frame,
        )
        top, bottom = door_brace_endpoints(design)
        self.assertAlmostEqual(
            sum((a - b) ** 2 for a, b in zip(top, bottom)) ** 0.5,
            (850**2 + 950**2) ** 0.5,
        )

    def test_side_braces_join_frame_corners(self):
        design = Design()
        _, parts = build(design)
        for name in ("left_brace", "right_brace"):
            part = next(part for part in parts if part.name == name)
            self.assertAlmostEqual(part.length, (750**2 + 950**2) ** 0.5)


if __name__ == "__main__":
    unittest.main()
