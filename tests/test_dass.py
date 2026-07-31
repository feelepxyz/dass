from itertools import combinations

import cadquery as cq
import pytest

from dass import Design, box_at, build, door_brace_endpoints, side_panel
from tests.helpers import almost

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
        if (
            first.xmin >= second.xmax
            or second.xmin >= first.xmax
            or first.ymin >= second.ymax
            or second.ymin >= first.ymax
            or first.zmin >= second.zmax
            or second.zmin >= first.zmax
        ):
            continue
        volume = a.solid.intersect(b.solid).Volume()
        if volume > tolerance:
            found.append((a.name, b.name, round(volume, 1)))
    return found


def test_reference_dimensions_and_panels(design, parts):
    design.validate_reference()
    panels = {(p.category, round(p.length), round(p.width)): 1 for p in parts}
    for expected in {
        ("side cladding", 770, 1175),
        ("back cladding", 854, 1050),
        ("cladding", 1175, 990),
        ("floor", 747, 854),
        ("seat top", 500, 854),
        ("seat side", 397, 854),
    }:
        assert expected in panels
    assert (
        sorted(
            (part.category, part.length)
            for part in parts
            if part.category in {"V1", "V2"}
        )
        == [("V1", 1150)] * 4 + [("V2", 1050)] * 2
    )


def test_width_variant_updates_geometry_and_cut_lengths():
    design = Design(width=1050)
    _, parts = build(design)
    grouped = {(p.category, round(p.length)) for p in parts}
    assert ("HL1", 960) in grouped
    assert ("HL2", 1050) in grouped
    assert (
        "D2",
        round(next(part.length for part in parts if part.name == "door_brace")),
    ) in grouped


def test_45x45_120x23_variant_uses_requested_profiles_and_clearances():
    design = Design(
        frame=45,
        cladding=23,
        roof_connector_width=45,
        roof_connector_thickness=45,
    )
    _, parts = build(design)
    structural = [
        part
        for part in parts
        if part.material == "wood" and part.thickness != design.cladding
    ]
    assert structural
    assert {(part.width, part.thickness) for part in structural} == {(45, 45)}
    assert design.interior_width == 854
    assert design.back_wall_front == 747
    assert design.seat_height - design.cladding == 397


def test_floor_seat_and_hinge_follow_section_datums(design, by_name):
    floor = by_name["floor"].solid.BoundingBox()
    assert (
        floor.xmin,
        floor.xmax,
        floor.ymin,
        floor.ymax,
        floor.zmin,
        floor.zmax,
    ) == (68, 922, 0, 747, 145, 168)
    floor_support = by_name["floor_back_support"].solid.BoundingBox()
    assert (
        floor_support.xmin,
        floor_support.xmax,
        floor_support.ymin,
        floor_support.ymax,
        floor_support.zmax,
    ) == (68, 922, 702, 747, floor.zmin)
    assert "floor_diagonal" not in by_name
    # Side bearers run under the floor's long edges, butting the front
    # opening rail and the back support without overlapping either.
    for name, xmin in (("floor_left_support", 68), ("floor_right_support", 877)):
        bearer = by_name[name].solid.BoundingBox()
        assert (
            bearer.xmin,
            bearer.xmax,
            bearer.ymin,
            bearer.ymax,
            bearer.zmin,
            bearer.zmax,
        ) == (xmin, xmin + 45, 45, 702, 100, floor.zmin)
        assert by_name[name].length == 657

    seat_front = by_name["seat_front"].solid.BoundingBox()
    seat_top = by_name["seat_top"].solid.BoundingBox()
    assert (seat_front.zmin, seat_front.zmax) == (168, 565)
    assert (seat_top.zmin, seat_top.zmax) == (565, 588)
    for name in ("seat_rail_1", "seat_rail_2"):
        rail = by_name[name].solid.BoundingBox()
        assert rail.zmax <= seat_top.zmin

    front_post = by_name["front_post_left"].solid.BoundingBox()
    assert (front_post.zmin, front_post.zmax) == (0, 1150)
    bottom_rail = by_name["front_bottom"].solid.BoundingBox()
    assert bottom_rail.zmin - front_post.zmin == design.leg_extension
    for name in ("left_wall", "right_wall", "back_wall"):
        assert by_name[name].solid.BoundingBox().zmin == design.leg_extension

    door = by_name["door_right"].solid.BoundingBox()
    door_panel = by_name["door_panel"].solid.BoundingBox()
    assert (door.zmin, door.zmax) == (100, 1150)
    assert (door_panel.zmin, door_panel.zmax) == (100, 1275)
    assert door_panel.zmin == by_name["door_bottom"].solid.BoundingBox().zmin
    assert door_panel.ymin == door.ymax
    structure = by_name["front_post_right"].solid.BoundingBox()
    assert door.ymax <= structure.ymin - design.hinge_gap
    assert "door_hinge_1" in by_name
    assert "door_hinge_2" in by_name


def test_wall_seat_and_floor_clearances_follow_panel_faces(design, by_name):
    left = by_name["left_wall"].solid.BoundingBox()
    right = by_name["right_wall"].solid.BoundingBox()
    back = by_name["back_wall"].solid.BoundingBox()
    assert left.ymin == almost(0)
    assert left.ymax == almost(design.plan_grid_depth)
    assert left.ymin == almost(by_name["front_post_left"].solid.BoundingBox().ymin)

    for name in (
        "floor",
        "seat_front",
        "seat_top",
        "seat_rail_1",
        "seat_rail_2",
        "seat_lower_rail",
    ):
        # Boolean cuts leave sub-nanometre noise on the cladding faces.
        box = by_name[name].solid.BoundingBox()
        assert box.xmin >= left.xmax - 1e-6
        assert box.xmax <= right.xmin + 1e-6
        assert box.ymax <= back.ymin + 1e-6
        assert by_name[name].solid.intersect(
            by_name["left_wall"].solid
        ).Volume() == almost(0)
        assert by_name[name].solid.intersect(
            by_name["right_wall"].solid
        ).Volume() == almost(0)
        assert by_name[name].solid.intersect(
            by_name["back_wall"].solid
        ).Volume() == almost(0)


def test_hk1_rails_are_unique_and_frame_each_side_brace(design, parts):
    rails = [part for part in parts if part.category == "HK1"]

    assert len(rails) == 4
    assert {part.length for part in rails} == {design.inner_depth}
    assert {part.name for part in rails} == {
        "left_bottom",
        "left_top",
        "right_bottom",
        "right_top",
    }
    assert {
        (part.solid.BoundingBox().xmin, part.solid.BoundingBox().zmin) for part in rails
    } == {(0, 100), (0, 1105), (945, 100), (945, 1105)}


def test_door_is_clear_of_structure_and_connected_by_hinges(design, by_name):
    for angle in (0, 105):
        _, parts = build(design, door_angle=angle)
        angled = {part.name: part for part in parts}
        door = cq.Compound.makeCompound(
            [
                angled[name].solid
                for name in (
                    "door_panel",
                    "door_left",
                    "door_right",
                    "door_bottom",
                    "door_top",
                    "door_brace",
                )
            ]
        )
        structure = cq.Compound.makeCompound(
            [
                angled[name].solid
                for name in ("front_post_left", "front_post_right", "front_bottom")
            ]
        )
        assert door.intersect(structure).Volume() == almost(0)

    # door_angle=0 is the default build, already available from the shared fixture.
    closed = by_name
    door_face = closed["door_panel"].solid.BoundingBox().ymax
    structure_face = closed["front_post_right"].solid.BoundingBox().ymin
    assert structure_face - door_face == design.hinge_gap
    assert (
        closed["hinge_door_1"].solid.BoundingBox().ymin
        == closed["door_panel"].solid.BoundingBox().ymax
    )
    assert closed["hinge_fixed_1"].solid.BoundingBox().ymax == structure_face
    assert (
        closed["door_hinge_1"].solid.intersect(closed["hinge_door_1"].solid).Volume()
        > 0
    )
    assert (
        closed["door_hinge_1"].solid.intersect(closed["hinge_fixed_1"].solid).Volume()
        > 0
    )


def test_roof_pitch_frame_and_door_alignment(design, by_name):
    door_frame = cq.Compound.makeCompound(
        [
            by_name[name].solid
            for name in ("door_left", "door_right", "door_bottom", "door_top")
        ]
    ).BoundingBox()
    assert (door_frame.xlen, door_frame.zlen) == (design.width, 1050)
    assert door_frame.zmin == design.leg_extension
    assert door_frame.zmin == by_name["front_bottom"].solid.BoundingBox().zmin

    panel = by_name["door_panel"].solid.BoundingBox()
    assert (panel.xlen, panel.zlen) == (design.width, 1175)
    assert panel.zmax == design.door_bottom + design.door_height
    back_wall = by_name["back_wall"].solid.BoundingBox()
    assert (back_wall.zmin, back_wall.zlen) == (100, 1050)

    assert by_name["roof"].solid.intersect(
        by_name["door_panel"].solid
    ).Volume() == almost(0)

    back_post = by_name["back_post_left"].solid.BoundingBox()
    back_top = by_name["back_top"].solid.BoundingBox()
    fixed_hinge = by_name["roof_hinge_fixed"].solid.BoundingBox()
    roof_back = by_name["roof_back"].solid.BoundingBox()
    assert back_top.zmax == back_post.zmax
    assert fixed_hinge.ymin == back_top.ymax
    assert fixed_hinge.zmax == back_post.zmax + design.roof_hinge_pin_radius
    assert (
        by_name["roof_hinge_pin"]
        .solid.intersect(by_name["roof_hinge_fixed"].solid)
        .Volume()
        > 0
    )
    assert (
        by_name["roof_hinge_pin"]
        .solid.intersect(by_name["roof_hinge_moving"].solid)
        .Volume()
        > 0
    )
    assert roof_back.ymax == pytest.approx(back_top.ymax, abs=3)
    assert roof_back.zmin >= back_top.zmax

    roof_frame = cq.Compound.makeCompound(
        [
            by_name[name].solid
            for name in ("roof_front", "roof_back", "roof_left", "roof_right")
        ]
    ).BoundingBox()
    assert roof_frame.xlen == almost(design.width)
    roof = by_name["roof"].solid.BoundingBox()
    assert roof.xlen == almost(1050, 6)
    assert roof.ylen == almost(1085, 6)
    assert (roof.xmin + roof.xmax) / 2 == almost(
        (roof_frame.xmin + roof_frame.xmax) / 2, 6
    )
    assert (roof.ymin + roof.ymax) / 2 == almost(
        (roof_frame.ymin + roof_frame.ymax) / 2, 6
    )
    assert by_name["roof"].material == "metal roof"
    assert design.roof_frame_depth == 893
    assert design.roof_rise == 125
    assert design.roof_run == 803
    connector = by_name["roof_middle"]
    assert (connector.length, connector.width, connector.thickness) == (
        design.inner_width,
        45,
        design.roof_connector_thickness,
    )

    roof_normal = max(
        (face.normalAt() for face in by_name["roof"].solid.Faces()),
        key=lambda normal: normal.z,
    )
    for name in (
        "roof_front",
        "roof_back",
        "roof_left",
        "roof_right",
        "roof_middle",
    ):
        beam_normal = max(
            (face.normalAt() for face in by_name[name].solid.Faces()),
            key=lambda normal: normal.z,
        )
        assert beam_normal.dot(roof_normal) == almost(1, 6)

    assert by_name["roof_back"].solid.intersect(
        by_name["back_top"].solid
    ).Volume() == almost(0)


def test_roof_lifts_as_one_hinged_assembly(design, by_name):
    # roof_lift_angle=0 is the default build, already available from the shared fixture.
    closed = by_name
    lifted = {part.name: part for part in build(design, roof_lift_angle=25)[1]}

    moving = (
        "roof",
        "roof_front",
        "roof_back",
        "roof_left",
        "roof_right",
        "roof_middle",
    )
    for name in moving:
        assert lifted[name].solid.Center().z > closed[name].solid.Center().z
    lifted_pin = lifted["roof_hinge_pin"].solid.BoundingBox()
    closed_pin = closed["roof_hinge_pin"].solid.BoundingBox()
    assert (
        lifted_pin.xmin,
        lifted_pin.ymin,
        lifted_pin.zmin,
        lifted_pin.xmax,
        lifted_pin.ymax,
        lifted_pin.zmax,
    ) == (
        closed_pin.xmin,
        closed_pin.ymin,
        closed_pin.zmin,
        closed_pin.xmax,
        closed_pin.ymax,
        closed_pin.zmax,
    )
    assert lifted["roof"].solid.intersect(lifted["back_top"].solid).Volume() == almost(
        0
    )


def test_door_brace_ends_between_the_vertical_stiles(design, by_name):
    brace = by_name["door_brace"].solid.BoundingBox()
    bottom = by_name["door_bottom"].solid.BoundingBox()
    top = by_name["door_top"].solid.BoundingBox()
    left = by_name["door_left"].solid.BoundingBox()
    right = by_name["door_right"].solid.BoundingBox()
    assert brace.xmin == almost(left.xmax)
    assert brace.xmax == almost(right.xmin)
    assert brace.zmin == almost(bottom.zmax)
    assert brace.zmax == almost(top.zmin)
    top, bottom = door_brace_endpoints(design)
    assert sum((a - b) ** 2 for a, b in zip(top, bottom)) ** 0.5 == almost(
        (design.inner_width**2 + (960 - 2 * design.diagonal_end_setback) ** 2) ** 0.5
    )


@pytest.mark.parametrize(
    "brace_name, first_post, second_post, bottom_rail, top_rail",
    [
        ("left_brace", "front_post_left", "back_post_left", "left_bottom", "left_top"),
        (
            "right_brace",
            "front_post_right",
            "back_post_right",
            "right_bottom",
            "right_top",
        ),
        ("back_brace", "back_post_left", "back_post_right", "back_bottom", "back_top"),
        ("door_brace", "door_left", "door_right", "door_bottom", "door_top"),
    ],
    ids=["left_brace", "right_brace", "back_brace", "door_brace"],
)
def test_diagonal_braces_fit_corner_to_corner_without_extending_into_members(
    design, by_name, brace_name, first_post, second_post, bottom_rail, top_rail
):
    brace = by_name[brace_name].solid.BoundingBox()
    first = by_name[first_post].solid.BoundingBox()
    second = by_name[second_post].solid.BoundingBox()
    low = by_name[bottom_rail].solid.BoundingBox()
    high = by_name[top_rail].solid.BoundingBox()

    assert brace.zmin == almost(low.zmax)
    assert brace.zmax == almost(high.zmin)
    if brace_name in {"left_brace", "right_brace"}:
        assert brace.ymin == almost(first.ymax)
        assert brace.ymax == almost(second.ymin)
        end_axis = "y"
    else:
        assert brace.xmin == almost(first.xmax)
        assert brace.xmax == almost(second.xmin)
        end_axis = "x"

    solid = by_name[brace_name].solid
    end_faces = [
        face
        for face in solid.Faces()
        if getattr(face.BoundingBox(), f"{end_axis}len") < 1e-6
        and face.Area() > design.frame**2
    ]
    rail_faces = [
        face
        for face in solid.Faces()
        if face.BoundingBox().zlen < 1e-6 and face.Area() > design.frame**2
    ]
    assert len(end_faces) == 2
    assert rail_faces == []


def test_side_braces_end_at_the_vertical_post_corners(design, by_name):
    for name in ("left_brace", "right_brace"):
        brace = by_name[name].solid.BoundingBox()
        side = "left" if name == "left_brace" else "right"
        assert brace.ymin == almost(
            by_name[f"front_post_{side}"].solid.BoundingBox().ymax
        )
        assert brace.ymax == almost(
            by_name[f"back_post_{side}"].solid.BoundingBox().ymin
        )
        assert brace.zmin == almost(by_name[f"{side}_bottom"].solid.BoundingBox().zmax)
        assert brace.zmax == almost(by_name[f"{side}_top"].solid.BoundingBox().zmin)


# Covers the default profiles and the 45x45/120x23 variant profiles.
BRACE_TEST_DESIGNS = (
    Design(),
    Design(
        frame=45,
        cladding=23,
        roof_connector_width=45,
        roof_connector_thickness=45,
    ),
)


@pytest.mark.parametrize(
    "name", ["left_brace", "right_brace", "back_brace", "door_brace"]
)
def test_braces_take_one_angled_cut_at_each_end(name):
    """Each diagonal remains one valid square-stock solid with clean ends."""
    for design in BRACE_TEST_DESIGNS:
        by_name = {part.name: part for part in build(design)[1]}
        openings = {
            "left_brace": (
                design.inner_depth,
                design.front_post_height - design.leg_extension - 2 * design.frame,
            ),
            "right_brace": (
                design.inner_depth,
                design.front_post_height - design.leg_extension - 2 * design.frame,
            ),
            "back_brace": (
                design.inner_width,
                design.back_height - design.leg_extension - 2 * design.frame,
            ),
            "door_brace": (
                design.inner_width,
                design.door_frame_height - 2 * design.frame,
            ),
        }
        span, rise = openings[name]
        solid = by_name[name].solid
        assert len(solid.Faces()) == 6
        assert len(solid.Solids()) == 1
        diagonal = (span**2 + (rise - 2 * design.diagonal_end_setback) ** 2) ** 0.5
        assert by_name[name].length == almost(diagonal, 6)


@pytest.mark.parametrize("name", ["left_wall", "right_wall"])
def test_side_cladding_lifts_at_the_back_and_clears_the_roof_panel_is_one_valid_solid(
    by_name, name
):
    assert by_name[name].solid.isValid()
    assert len(by_name[name].solid.Solids()) == 1


def test_side_cladding_lifts_at_the_back_and_clears_the_roof(design, by_name):
    panel = by_name["left_wall"].solid

    assert design.side_back_top == design.back_height + 25
    assert design.side_fall == 100
    # The nominal front edge stays within the 1 mm roof-sheet relief; the
    # back edge carries the full lift.
    front = [v.toTuple() for v in panel.Vertices() if abs(v.toTuple()[1]) < 1e-6]
    assert max(z for _, _, z in front) <= design.front_height
    assert max(z for _, _, z in front) >= design.front_height - design.roof_thickness
    assert panel.BoundingBox().zmax <= design.front_height
    assert panel.BoundingBox().zmax >= design.front_height - design.roof_thickness
    assert panel.BoundingBox().zmin == design.leg_extension

    # The lifted back rises past the closed roof frame, so it is notched
    # there; the notch is the only thing keeping the two apart.
    raw = side_panel(design, design.frame, False)
    assert raw.intersect(by_name["roof_back"].solid).Volume() > 0
    assert panel.intersect(by_name["roof_back"].solid).Volume() == almost(0)


def test_door_cladding_has_roof_beam_notches_in_both_top_corners(design, by_name):
    panel = by_name["door_panel"].solid

    assert panel.isValid()
    assert len(panel.Solids()) == 1
    assert (
        design.width * design.door_height * design.cladding - panel.Volume()
        == almost(2 * design.frame**2 * design.cladding)
    )

    # The field remains full height between the two 45 mm roof-beam seats.
    panel_y = -design.cladding - design.hinge_gap
    top_center = box_at(
        design.frame,
        panel_y,
        design.door_top - 1,
        design.inner_width,
        design.cladding,
        1,
    )
    assert panel.intersect(top_center).Volume() == almost(top_center.Volume())


@pytest.mark.parametrize("corner", ["left", "right"])
def test_door_cladding_has_roof_beam_notches_in_both_top_corners_notch_is_clear(
    design, by_name, corner
):
    panel = by_name["door_panel"].solid
    panel_y = -design.cladding - design.hinge_gap
    notch_z = design.door_top - design.frame
    notch_x = 0 if corner == "left" else design.width - design.frame
    notch = box_at(
        notch_x, panel_y, notch_z, design.frame, design.cladding, design.frame
    )
    assert panel.intersect(notch).Volume() == almost(0)


@pytest.mark.parametrize("beam", ["roof_left", "roof_right"])
def test_door_cladding_has_roof_beam_notches_in_both_top_corners_beam_seat_is_clear(
    by_name, beam
):
    # In the closed position, each side beam bears on its notch without
    # cutting into the door field.
    panel = by_name["door_panel"].solid
    assert by_name[beam].solid.distance(panel) == almost(0, 6)
    assert by_name[beam].solid.intersect(panel).Volume() == almost(0, 6)


def test_seat_supports_flank_the_opening_between_the_rails(design, by_name):
    seat_top = by_name["seat_top"].solid.BoundingBox()

    hole_left = (design.width - design.seat_hole_width) / 2
    hole_right = (design.width + design.seat_hole_width) / 2
    for name, xmin in (
        ("seat_support_left", hole_left - design.seat_support),
        ("seat_support_right", hole_right),
    ):
        part = by_name[name]
        box = part.solid.BoundingBox()
        assert part.width == design.seat_support
        assert part.thickness == design.seat_support
        assert (box.xmin, box.xmax) == (xmin, xmin + design.seat_support)
        # Flush under the seat boards, fitted between the two seat rails.
        assert box.zmax == seat_top.zmin
        assert box.ymin == by_name["seat_rail_1"].solid.BoundingBox().ymax
        assert box.ymax == by_name["seat_rail_2"].solid.BoundingBox().ymin


def test_back_brace_matches_side_brace_corners_and_d2_cut(design, by_name):
    brace = by_name["back_brace"]

    # Same side-to-side opening as the door frame, so it is a second D2 cut.
    assert brace.category == "D2"
    assert brace.length == almost(by_name["door_brace"].length)
    assert brace.length == almost(by_name["door_brace"].length)

    box = brace.solid.BoundingBox()
    assert box.xmin == almost(design.frame)
    assert box.xmax == almost(design.width - design.frame)
    assert box.ymin == almost(design.depth - design.frame)
    assert box.ymax == almost(design.depth)
    assert box.zmin == almost(by_name["back_bottom"].solid.BoundingBox().zmax)
    assert box.zmax == almost(by_name["back_top"].solid.BoundingBox().zmin)
    # Its low end shares the rear-left post with the left side brace.
    left_brace = by_name["left_brace"].solid.BoundingBox()
    assert left_brace.ymax == almost(box.ymin, 6)
    assert box.zmin == almost(by_name["back_bottom"].solid.BoundingBox().zmax)
    # It sits in the frame plane, outside the back cladding.
    assert box.ymin >= by_name["back_wall"].solid.BoundingBox().ymax


def test_seat_top_has_oval_opening_clear_of_the_rails(design, by_name):
    seat_top = by_name["seat_top"].solid

    solid_volume = design.interior_width * design.seat_depth * design.cladding
    hole_area = (
        3.141592653589793 * (design.seat_hole_width / 2) * (design.seat_hole_depth / 2)
    )
    assert seat_top.Volume() == pytest.approx(
        solid_volume - hole_area * design.cladding, abs=1.0
    )

    # The opening is centred in the seat box and clears both rails below.
    opening = max(seat_top.Faces(), key=lambda face: face.Area()).innerWires()
    assert len(opening) == 1
    hole = opening[0].BoundingBox()
    assert hole.xlen == almost(design.seat_hole_width, 6)
    assert hole.ylen == almost(design.seat_hole_depth, 6)
    assert (hole.xmin + hole.xmax) / 2 == almost(design.width / 2)
    for name in ("seat_rail_1", "seat_rail_2"):
        rail = by_name[name].solid.BoundingBox()
        assert not (rail.ymin < hole.ymax and hole.ymin < rail.ymax)


def test_cladding_fields_meet_without_overlapping(design, by_name):
    left = by_name["left_wall"].solid.BoundingBox()
    right = by_name["right_wall"].solid.BoundingBox()
    back = by_name["back_wall"].solid.BoundingBox()

    # The back field is fitted between the side skins, not behind them.
    assert back.xmin == almost(left.xmax)
    assert back.xmax == almost(right.xmin)
    assert back.xlen == design.interior_width
    # The side skins still close the corner the back field no longer covers.
    assert left.ymax == back.ymax

    # Both side skins are notched around the front opening rail.
    rail = by_name["front_bottom"].solid
    for name in ("left_wall", "right_wall"):
        panel = by_name[name].solid
        assert panel.intersect(rail).Volume() == almost(0)
        notch = box_at(
            design.frame,
            0,
            design.leg_extension,
            design.width - 2 * design.frame,
            design.frame,
            design.frame,
        )
        assert panel.intersect(notch).Volume() == almost(0)


# Covers the default profile, the wide variant, and the 45x45/120x23 variant.
VARIANT_DESIGNS = {
    "default": Design(),
    "wide": Design(width=1050, seat_depth=550),
    "45x45": Design(
        frame=45,
        cladding=23,
        roof_connector_width=45,
        roof_connector_thickness=45,
    ),
}


@pytest.mark.parametrize(
    "door_angle, roof_lift_angle", [(0, 0), (105, 25)], ids=["closed", "open"]
)
def test_no_part_overlaps_another_except_hinge_pins(door_angle, roof_lift_angle):
    for design in VARIANT_DESIGNS.values():
        _, parts = build(design, door_angle=door_angle, roof_lift_angle=roof_lift_angle)
        assert clashes(parts) == []
