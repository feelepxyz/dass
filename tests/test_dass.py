import unittest
from itertools import combinations

import cadquery as cq

from dass import Design, box_at, build, door_brace_endpoints, side_panel

# Hinge pins are modelled as continuous barrels running through the knuckles
# they pivot in, so they intentionally share volume with their leaves and with
# the members they are fastened between. Nothing else in the model may overlap.
PIN_CATEGORIES = {"hinge pin", "roof hinge pin"}


def clashes(parts, tolerance=1.0):
    """Return every overlapping part pair that is not hinge-pin hardware."""
    found = []
    for a, b in combinations(parts, 2):
        if a.category in PIN_CATEGORIES or b.category in PIN_CATEGORIES:
            continue
        first, second = a.solid.BoundingBox(), b.solid.BoundingBox()
        if (first.xmin >= second.xmax or second.xmin >= first.xmax
                or first.ymin >= second.ymax or second.ymin >= first.ymax
                or first.zmin >= second.zmax or second.zmin >= first.zmax):
            continue
        volume = a.solid.intersect(b.solid).Volume()
        if volume > tolerance:
            found.append((a.name, b.name, round(volume, 1)))
    return found


class DassModelTest(unittest.TestCase):
    def test_reference_dimensions_and_panels(self):
        design = Design()
        design.validate_reference()
        _, parts = build(design)
        panels = {(p.category, round(p.length), round(p.width)): 1 for p in parts}
        for expected in {
            ("side cladding", 770, 1175),
            ("back cladding", 854, 1050),
            ("cladding", 1175, 990),
            ("floor", 747, 854),
            ("seat top", 500, 854),
            ("seat side", 397, 854),
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
        self.assertIn(("HL1", 960), grouped)
        self.assertIn(("HL2", 1050), grouped)
        self.assertIn(
            ("D2", round(next(part.length for part in parts if part.name == "door_brace"))),
            grouped,
        )

    def test_45x45_120x23_variant_uses_requested_profiles_and_clearances(self):
        design = Design(
            frame=45,
            cladding=23,
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
        self.assertEqual(design.interior_width, 854)
        self.assertEqual(design.back_wall_front, 747)
        self.assertEqual(design.seat_height - design.cladding, 397)

    def test_floor_seat_and_hinge_follow_section_datums(self):
        design = Design()
        _, parts = build(design)
        by_name = {part.name: part for part in parts}

        floor = by_name["floor"].solid.BoundingBox()
        self.assertEqual(
            (floor.xmin, floor.xmax, floor.ymin, floor.ymax, floor.zmin, floor.zmax),
            (68, 922, 0, 747, 145, 168),
        )
        floor_support = by_name["floor_back_support"].solid.BoundingBox()
        self.assertEqual(
            (floor_support.xmin, floor_support.xmax,
             floor_support.ymin, floor_support.ymax, floor_support.zmax),
            (68, 922, 702, 747, floor.zmin),
        )
        self.assertNotIn("floor_diagonal", by_name)
        # Side bearers run under the floor's long edges, butting the front
        # opening rail and the back support without overlapping either.
        for name, xmin in (("floor_left_support", 68), ("floor_right_support", 877)):
            bearer = by_name[name].solid.BoundingBox()
            self.assertEqual(
                (bearer.xmin, bearer.xmax, bearer.ymin, bearer.ymax,
                 bearer.zmin, bearer.zmax),
                (xmin, xmin + 45, 45, 702, 100, floor.zmin),
            )
            self.assertEqual(by_name[name].length, 657)

        seat_front = by_name["seat_front"].solid.BoundingBox()
        seat_top = by_name["seat_top"].solid.BoundingBox()
        self.assertEqual((seat_front.zmin, seat_front.zmax), (168, 565))
        self.assertEqual((seat_top.zmin, seat_top.zmax), (565, 588))
        for name in ("seat_rail_1", "seat_rail_2"):
            rail = by_name[name].solid.BoundingBox()
            self.assertLessEqual(rail.zmax, seat_top.zmin)

        front_post = by_name["front_post_left"].solid.BoundingBox()
        self.assertEqual((front_post.zmin, front_post.zmax), (0, 1150))
        bottom_rail = by_name["front_bottom"].solid.BoundingBox()
        self.assertEqual(bottom_rail.zmin - front_post.zmin, design.leg_extension)
        for name in ("left_wall", "right_wall", "back_wall"):
            self.assertEqual(by_name[name].solid.BoundingBox().zmin, design.leg_extension)

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
        self.assertAlmostEqual(left.ymin, 0)
        self.assertAlmostEqual(left.ymax, design.plan_grid_depth)
        self.assertAlmostEqual(left.ymin, by_name["front_post_left"].solid.BoundingBox().ymin)

        for name in (
            "floor", "seat_front", "seat_top",
            "seat_rail_1", "seat_rail_2", "seat_lower_rail",
        ):
            # Boolean cuts leave sub-nanometre noise on the cladding faces.
            box = by_name[name].solid.BoundingBox()
            self.assertGreaterEqual(box.xmin, left.xmax - 1e-6)
            self.assertLessEqual(box.xmax, right.xmin + 1e-6)
            self.assertLessEqual(box.ymax, back.ymin + 1e-6)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["left_wall"].solid).Volume(), 0)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["right_wall"].solid).Volume(), 0)
            self.assertAlmostEqual(by_name[name].solid.intersect(by_name["back_wall"].solid).Volume(), 0)

    def test_hk1_rails_are_unique_and_frame_each_side_brace(self):
        design = Design()
        _, parts = build(design)
        rails = [part for part in parts if part.category == "HK1"]

        self.assertEqual(len(rails), 4)
        self.assertEqual({part.length for part in rails}, {design.inner_depth})
        self.assertEqual(
            {part.name for part in rails},
            {"left_bottom", "left_top", "right_bottom", "right_top"},
        )
        self.assertEqual(
            {(part.solid.BoundingBox().xmin, part.solid.BoundingBox().zmin) for part in rails},
            {(0, 100), (0, 1105), (945, 100), (945, 1105)},
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
        self.assertEqual((door_frame.xlen, door_frame.zlen), (design.width, 1050))
        self.assertEqual(door_frame.zmin, design.leg_extension)
        self.assertEqual(
            door_frame.zmin,
            by_name["front_bottom"].solid.BoundingBox().zmin,
        )

        panel = by_name["door_panel"].solid.BoundingBox()
        self.assertEqual((panel.xlen, panel.zlen), (design.width, 1175))
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
        self.assertAlmostEqual(roof_back.ymax, back_top.ymax, delta=3)
        self.assertGreaterEqual(roof_back.zmin, back_top.zmax)

        roof_frame = cq.Compound.makeCompound([
            by_name[name].solid
            for name in ("roof_front", "roof_back", "roof_left", "roof_right")
        ]).BoundingBox()
        self.assertAlmostEqual(roof_frame.xlen, design.width)
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
        self.assertEqual(design.roof_frame_depth, 893)
        self.assertEqual(design.roof_rise, 125)
        self.assertEqual(design.roof_run, 803)
        connector = by_name["roof_middle"]
        self.assertEqual(
            (connector.length, connector.width, connector.thickness),
            (design.inner_width, 45, design.roof_connector_thickness),
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

    def test_door_brace_ends_between_the_vertical_stiles(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        brace = by_name["door_brace"].solid.BoundingBox()
        bottom = by_name["door_bottom"].solid.BoundingBox()
        top = by_name["door_top"].solid.BoundingBox()
        left = by_name["door_left"].solid.BoundingBox()
        right = by_name["door_right"].solid.BoundingBox()
        self.assertAlmostEqual(brace.xmin, left.xmax)
        self.assertAlmostEqual(brace.xmax, right.xmin)
        self.assertAlmostEqual(brace.zmin, bottom.zmax)
        self.assertAlmostEqual(brace.zmax, top.zmin)
        top, bottom = door_brace_endpoints(design)
        self.assertAlmostEqual(
            sum((a - b) ** 2 for a, b in zip(top, bottom)) ** 0.5,
            (design.inner_width**2 + (960 - 2 * design.diagonal_end_setback) ** 2) ** 0.5,
        )

    def test_diagonal_braces_fit_corner_to_corner_without_extending_into_members(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}

        brace_pairs = (
            ("left_brace", "front_post_left", "back_post_left", "left_bottom", "left_top"),
            ("right_brace", "front_post_right", "back_post_right", "right_bottom", "right_top"),
            ("back_brace", "back_post_left", "back_post_right", "back_bottom", "back_top"),
            ("door_brace", "door_left", "door_right", "door_bottom", "door_top"),
        )
        for brace_name, first_post, second_post, bottom_rail, top_rail in brace_pairs:
            with self.subTest(brace=brace_name):
                brace = by_name[brace_name].solid.BoundingBox()
                first = by_name[first_post].solid.BoundingBox()
                second = by_name[second_post].solid.BoundingBox()
                low = by_name[bottom_rail].solid.BoundingBox()
                high = by_name[top_rail].solid.BoundingBox()

                self.assertAlmostEqual(brace.zmin, low.zmax)
                self.assertAlmostEqual(brace.zmax, high.zmin)
                if brace_name in {"left_brace", "right_brace"}:
                    self.assertAlmostEqual(brace.ymin, first.ymax)
                    self.assertAlmostEqual(brace.ymax, second.ymin)
                    end_axis = "y"
                else:
                    self.assertAlmostEqual(brace.xmin, first.xmax)
                    self.assertAlmostEqual(brace.xmax, second.xmin)
                    end_axis = "x"

                solid = by_name[brace_name].solid
                end_faces = [
                    face for face in solid.Faces()
                    if getattr(face.BoundingBox(), f"{end_axis}len") < 1e-6
                    and face.Area() > design.frame**2
                ]
                rail_faces = [
                    face for face in solid.Faces()
                    if face.BoundingBox().zlen < 1e-6
                    and face.Area() > design.frame**2
                ]
                self.assertEqual(len(end_faces), 2)
                self.assertEqual(rail_faces, [])

    def test_side_braces_end_at_the_vertical_post_corners(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        for name in ("left_brace", "right_brace"):
            brace = by_name[name].solid.BoundingBox()
            side = "left" if name == "left_brace" else "right"
            self.assertAlmostEqual(brace.ymin, by_name[f"front_post_{side}"].solid.BoundingBox().ymax)
            self.assertAlmostEqual(brace.ymax, by_name[f"back_post_{side}"].solid.BoundingBox().ymin)
            self.assertAlmostEqual(brace.zmin, by_name[f"{side}_bottom"].solid.BoundingBox().zmax)
            self.assertAlmostEqual(brace.zmax, by_name[f"{side}_top"].solid.BoundingBox().zmin)

    def test_braces_take_one_angled_cut_at_each_end(self):
        """Each diagonal remains one valid square-stock solid with clean ends."""
        for design in (
            Design(),
            Design(frame=45, cladding=23,
                   roof_connector_width=45, roof_connector_thickness=45),
        ):
            by_name = {part.name: part for part in build(design)[1]}
            openings = {
                "left_brace": (design.inner_depth, design.front_post_height
                               - design.leg_extension - 2 * design.frame),
                "right_brace": (design.inner_depth, design.front_post_height
                                - design.leg_extension - 2 * design.frame),
                "back_brace": (design.inner_width, design.back_height
                               - design.leg_extension - 2 * design.frame),
                "door_brace": (design.inner_width,
                               design.door_frame_height - 2 * design.frame),
            }
            for name, (span, rise) in openings.items():
                with self.subTest(frame=design.frame, brace=name):
                    solid = by_name[name].solid
                    self.assertEqual(len(solid.Faces()), 6)
                    self.assertEqual(len(solid.Solids()), 1)
                    diagonal = (span**2 + (rise - 2 * design.diagonal_end_setback) ** 2) ** 0.5
                    self.assertAlmostEqual(
                        by_name[name].length,
                        diagonal,
                        places=6,
                    )

    def test_side_cladding_lifts_at_the_back_and_clears_the_roof(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        panel = by_name["left_wall"].solid

        for name in ("left_wall", "right_wall"):
            with self.subTest(panel=name):
                self.assertTrue(by_name[name].solid.isValid())
                self.assertEqual(len(by_name[name].solid.Solids()), 1)

        self.assertEqual(design.side_back_top, design.back_height + 25)
        self.assertEqual(design.side_fall, 100)
        # The nominal front edge stays within the 1 mm roof-sheet relief; the
        # back edge carries the full lift.
        front = [v.toTuple() for v in panel.Vertices() if abs(v.toTuple()[1]) < 1e-6]
        self.assertLessEqual(max(z for _, _, z in front), design.front_height)
        self.assertGreaterEqual(
            max(z for _, _, z in front),
            design.front_height - design.roof_thickness,
        )
        self.assertLessEqual(panel.BoundingBox().zmax, design.front_height)
        self.assertGreaterEqual(
            panel.BoundingBox().zmax,
            design.front_height - design.roof_thickness,
        )
        self.assertEqual(panel.BoundingBox().zmin, design.leg_extension)

        # The lifted back rises past the closed roof frame, so it is notched
        # there; the notch is the only thing keeping the two apart.
        raw = side_panel(design, design.frame, False)
        self.assertGreater(
            raw.intersect(by_name["roof_back"].solid).Volume(), 0
        )
        self.assertAlmostEqual(
            panel.intersect(by_name["roof_back"].solid).Volume(), 0
        )

    def test_door_cladding_has_roof_beam_notches_in_both_top_corners(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        panel = by_name["door_panel"].solid
        panel_y = -design.cladding - design.hinge_gap
        notch_z = design.door_top - design.frame

        self.assertTrue(panel.isValid())
        self.assertEqual(len(panel.Solids()), 1)
        self.assertAlmostEqual(
            design.width * design.door_height * design.cladding - panel.Volume(),
            2 * design.frame**2 * design.cladding,
        )
        for notch_x in (0, design.width - design.frame):
            with self.subTest(x=notch_x):
                notch = box_at(
                    notch_x,
                    panel_y,
                    notch_z,
                    design.frame,
                    design.cladding,
                    design.frame,
                )
                self.assertAlmostEqual(panel.intersect(notch).Volume(), 0)

        # The field remains full height between the two 45 mm roof-beam seats.
        top_center = box_at(
            design.frame,
            panel_y,
            design.door_top - 1,
            design.inner_width,
            design.cladding,
            1,
        )
        self.assertAlmostEqual(
            panel.intersect(top_center).Volume(),
            top_center.Volume(),
        )
        # In the closed position, each side beam bears on its notch without
        # cutting into the door field.
        for beam in ("roof_left", "roof_right"):
            with self.subTest(beam=beam):
                self.assertAlmostEqual(
                    by_name[beam].solid.distance(panel),
                    0,
                    places=6,
                )
                self.assertAlmostEqual(
                    by_name[beam].solid.intersect(panel).Volume(),
                    0,
                    places=6,
                )

    def test_seat_supports_flank_the_opening_between_the_rails(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        seat_top = by_name["seat_top"].solid.BoundingBox()

        hole_left = (design.width - design.seat_hole_width) / 2
        hole_right = (design.width + design.seat_hole_width) / 2
        for name, xmin in (
            ("seat_support_left", hole_left - design.seat_support),
            ("seat_support_right", hole_right),
        ):
            part = by_name[name]
            box = part.solid.BoundingBox()
            self.assertEqual(part.width, design.seat_support)
            self.assertEqual(part.thickness, design.seat_support)
            self.assertEqual((box.xmin, box.xmax), (xmin, xmin + design.seat_support))
            # Flush under the seat boards, fitted between the two seat rails.
            self.assertEqual(box.zmax, seat_top.zmin)
            self.assertEqual(box.ymin, by_name["seat_rail_1"].solid.BoundingBox().ymax)
            self.assertEqual(box.ymax, by_name["seat_rail_2"].solid.BoundingBox().ymin)

    def test_back_brace_matches_side_brace_corners_and_d2_cut(self):
        design = Design()
        _, parts = build(design)
        by_name = {part.name: part for part in parts}
        brace = by_name["back_brace"]

        # Same side-to-side opening as the door frame, so it is a second D2 cut.
        self.assertEqual(brace.category, "D2")
        self.assertAlmostEqual(
            brace.length,
            by_name["door_brace"].length,
        )
        self.assertAlmostEqual(
            brace.length,
            by_name["door_brace"].length,
        )

        box = brace.solid.BoundingBox()
        self.assertAlmostEqual(box.xmin, design.frame)
        self.assertAlmostEqual(box.xmax, design.width - design.frame)
        self.assertAlmostEqual(box.ymin, design.depth - design.frame)
        self.assertAlmostEqual(box.ymax, design.depth)
        self.assertAlmostEqual(box.zmin, by_name["back_bottom"].solid.BoundingBox().zmax)
        self.assertAlmostEqual(box.zmax, by_name["back_top"].solid.BoundingBox().zmin)
        # Its low end shares the rear-left post with the left side brace.
        left_brace = by_name["left_brace"].solid.BoundingBox()
        self.assertAlmostEqual(left_brace.ymax, box.ymin, places=6)
        self.assertAlmostEqual(box.zmin, by_name["back_bottom"].solid.BoundingBox().zmax)
        # It sits in the frame plane, outside the back cladding.
        self.assertGreaterEqual(box.ymin, by_name["back_wall"].solid.BoundingBox().ymax)

    def test_seat_top_has_oval_opening_clear_of_the_rails(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        seat_top = by_name["seat_top"].solid

        solid_volume = design.interior_width * design.seat_depth * design.cladding
        hole_area = 3.141592653589793 * (design.seat_hole_width / 2) * (design.seat_hole_depth / 2)
        self.assertAlmostEqual(
            seat_top.Volume(),
            solid_volume - hole_area * design.cladding,
            delta=1.0,
        )

        # The opening is centred in the seat box and clears both rails below.
        opening = max(seat_top.Faces(), key=lambda face: face.Area()).innerWires()
        self.assertEqual(len(opening), 1)
        hole = opening[0].BoundingBox()
        self.assertAlmostEqual(hole.xlen, design.seat_hole_width, places=6)
        self.assertAlmostEqual(hole.ylen, design.seat_hole_depth, places=6)
        self.assertAlmostEqual((hole.xmin + hole.xmax) / 2, design.width / 2)
        for name in ("seat_rail_1", "seat_rail_2"):
            rail = by_name[name].solid.BoundingBox()
            self.assertFalse(rail.ymin < hole.ymax and hole.ymin < rail.ymax)

    def test_cladding_fields_meet_without_overlapping(self):
        design = Design()
        by_name = {part.name: part for part in build(design)[1]}
        left = by_name["left_wall"].solid.BoundingBox()
        right = by_name["right_wall"].solid.BoundingBox()
        back = by_name["back_wall"].solid.BoundingBox()

        # The back field is fitted between the side skins, not behind them.
        self.assertAlmostEqual(back.xmin, left.xmax)
        self.assertAlmostEqual(back.xmax, right.xmin)
        self.assertEqual(back.xlen, design.interior_width)
        # The side skins still close the corner the back field no longer covers.
        self.assertEqual(left.ymax, back.ymax)

        # Both side skins are notched around the front opening rail.
        rail = by_name["front_bottom"].solid
        for name in ("left_wall", "right_wall"):
            panel = by_name[name].solid
            self.assertAlmostEqual(panel.intersect(rail).Volume(), 0)
            notch = box_at(
                design.frame, 0, design.leg_extension,
                design.width - 2 * design.frame, design.frame, design.frame,
            )
            self.assertAlmostEqual(panel.intersect(notch).Volume(), 0)

    def test_no_part_overlaps_another_except_hinge_pins(self):
        variants = {
            "default": Design(),
            "wide": Design(width=1050, seat_depth=550),
            "45x45": Design(
                frame=45, cladding=23,
                roof_connector_width=45, roof_connector_thickness=45,
            ),
        }
        for label, design in variants.items():
            for state, door_angle, roof_lift_angle in (
                ("closed", 0, 0),
                ("open", 105, 25),
            ):
                with self.subTest(variant=label, state=state):
                    _, parts = build(
                        design,
                        door_angle=door_angle,
                        roof_lift_angle=roof_lift_angle,
                    )
                    self.assertEqual(clashes(parts), [])


if __name__ == "__main__":
    unittest.main()
