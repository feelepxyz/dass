"""Parametric outdoor-toilet CAD model, renderer, and cut-list generator.

All dimensions are millimetres.  The elevations and reference cut list are the
authority for part sizes; the 900 x 800 plan dimensions are post-centre grid
dimensions within the 950 x 850 outside post envelope.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, fields, replace
from pathlib import Path

import cadquery as cq
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class Design:
    # Primary parameters
    width: float = 990
    depth: float = 815
    frame: float = 45
    cladding: float = 23
    front_post_height: float = 1150
    front_height: float = 1275
    back_height: float = 1150
    door_height: float = 1175
    seat_depth: float = 500
    seat_height: float = 420
    seat_hole_width: float = 270
    seat_hole_depth: float = 330
    seat_support: float = 45
    roof_overhang: float = 65
    roof_thickness: float = 1
    roof_beam_run: float = 803
    door_brace_rise: float = 850
    diagonal_end_setback: float = 0
    screw_length: float = 120
    diagonal_screw_angle: float = 10
    leg_extension: float = 100
    door_frame_height: float = 1050
    hinge_gap: float = 10
    hinge_pin_radius: float = 6
    hinge_leaf_thickness: float = 5
    roof_hinge_pin_radius: float = 8
    roof_connector_width: float = 45
    roof_connector_thickness: float = 45
    side_back_lift: float = 25

    @property
    def inner_width(self) -> float:
        return self.width - 2 * self.frame

    @property
    def inner_depth(self) -> float:
        return self.depth - 2 * self.frame

    @property
    def interior_width(self) -> float:
        return self.width - 2 * (self.frame + self.cladding)

    @property
    def interior_x(self) -> float:
        """Inner face of the left side cladding; everything fitted starts here."""
        return self.frame + self.cladding

    @property
    def back_wall_front(self) -> float:
        return self.depth - self.frame - self.cladding

    @property
    def plan_grid_width(self) -> float:
        return self.width - self.frame

    @property
    def plan_grid_depth(self) -> float:
        return self.depth - self.frame

    @property
    def side_back_top(self) -> float:
        """Top of the side cladding at the back, lifted clear of the frame."""
        return self.back_height + self.side_back_lift

    @property
    def side_fall(self) -> float:
        """Side cladding drop from front to back; shallower than the roof."""
        return self.front_height - self.side_back_top

    @property
    def roof_run(self) -> float:
        return self.roof_beam_run

    @property
    def roof_rise(self) -> float:
        return self.front_height - self.back_height

    @property
    def roof_angle(self) -> float:
        return math.degrees(math.atan2(self.roof_rise, self.roof_run))

    @property
    def door_bottom(self) -> float:
        return self.leg_extension

    @property
    def door_top(self) -> float:
        return self.door_bottom + self.door_height

    @property
    def roof_frame_depth(self) -> float:
        return self.roof_run + 2 * self.frame

    @property
    def roof_seat_angle(self) -> float:
        """Extra hinge rotation that seats the roof beams in the door notches."""
        slope_length = math.hypot(self.roof_run, self.roof_rise)
        pitch_rear_y = -self.cladding - self.hinge_gap + self.frame + self.roof_run
        hinge_top = self.back_height + self.frame
        flat_front = pitch_rear_y - self.frame - slope_length
        hinge_y = self.depth
        hinge_z = self.back_height + self.roof_hinge_pin_radius

        def rotate_yz(
            y: float,
            z: float,
            centre_y: float,
            centre_z: float,
            angle: float,
        ) -> tuple[float, float]:
            cosine = math.cos(angle)
            sine = math.sin(angle)
            return (
                centre_y + cosine * (y - centre_y) - sine * (z - centre_z),
                centre_z + sine * (y - centre_y) + cosine * (z - centre_z),
            )

        pitch = -math.radians(self.roof_angle)
        underside = (
            rotate_yz(flat_front, self.back_height, pitch_rear_y, hinge_top, pitch),
            rotate_yz(
                flat_front + slope_length,
                self.back_height,
                pitch_rear_y,
                hinge_top,
                pitch,
            ),
        )

        def underside_z(angle: float) -> float:
            first = rotate_yz(*underside[0], hinge_y, hinge_z, angle)
            second = rotate_yz(*underside[1], hinge_y, hinge_z, angle)
            target_y = -self.hinge_gap
            fraction = (target_y - first[0]) / (second[0] - first[0])
            return first[1] + fraction * (second[1] - first[1])

        target_z = self.door_top - self.frame
        low = math.radians(-15)
        high = math.radians(15)
        assert underside_z(low) >= target_z >= underside_z(high)
        for _ in range(60):
            middle = (low + high) / 2
            if underside_z(middle) > target_z:
                low = middle
            else:
                high = middle
        return math.degrees((low + high) / 2)

    def validate(self) -> None:
        assert self.frame > 0 and self.cladding > 0
        assert self.width > 2 * self.frame and self.depth > 2 * self.frame
        assert (
            self.front_height
            > self.back_height
            >= self.front_post_height
            > self.seat_height
        )
        assert 0 < self.seat_depth < self.inner_depth
        assert 0 < self.seat_hole_width < self.interior_width
        assert 0 < self.seat_hole_depth < self.seat_depth
        assert self.diagonal_end_setback >= 0
        assert self.screw_length > 0
        assert 0 < self.diagonal_screw_angle < 45
        assert 2 * self.diagonal_end_setback < min(
            self.front_post_height - self.leg_extension - 2 * self.frame,
            self.back_height - self.leg_extension - 2 * self.frame,
            self.door_frame_height - 2 * self.frame,
        )
        assert self.door_top == self.front_height

    def validate_reference(self) -> None:
        """Prove that defaults reproduce the dimensions repeated in the sources."""
        self.validate()
        assert self.width == 990, "door field is nine 110 mm råspont covers"
        assert self.plan_grid_depth == 770, "side fields are seven 110 mm covers"
        assert self.inner_width == 900
        assert self.inner_depth == 725
        assert self.door_height == 1175
        assert self.door_frame_height == 1050
        assert self.roof_run == 803 and self.roof_rise == 125
        assert self.seat_depth == 500 and self.seat_height - self.cladding == 397


@dataclass
class Part:
    name: str
    category: str
    solid: cq.Shape
    length: float
    width: float
    thickness: float
    material: str = "wood"


def box_at(x: float, y: float, z: float, dx: float, dy: float, dz: float) -> cq.Shape:
    # CadQuery types Workplane.val() as Vector | Location | Shape | Sketch. A
    # solid modelling stack only ever yields a Shape here, so every .val() in
    # this module narrows the same way.
    solid = (
        cq.Workplane("XY")
        .box(dx, dy, dz, centered=(False, False, False))
        .translate((x, y, z))
    )
    return solid.val()  # ty: ignore[invalid-return-type]


def beam_between(
    a: tuple[float, float, float], b: tuple[float, float, float], size: float
) -> cq.Shape:
    """Square beam whose long axis follows a→b."""
    va, vb = cq.Vector(*a), cq.Vector(*b)
    delta = vb - va
    length = delta.Length
    direction = delta.normalized()
    # Make a centred profile normal to the member axis, then extrude along it.
    plane = cq.Plane(origin=va, normal=direction)
    return cq.Workplane(plane).rect(size, size).extrude(length).val()  # ty: ignore[invalid-return-type]


def rotate_about(vector: cq.Vector, axis: cq.Vector, degrees: float) -> cq.Vector:
    """Rodrigues rotation of ``vector`` about ``axis``."""
    unit = axis.normalized()
    theta = math.radians(degrees)
    return (
        vector.multiply(math.cos(theta))
        + unit.cross(vector).multiply(math.sin(theta))
        + unit.multiply(unit.dot(vector) * (1 - math.cos(theta)))
    )


def single_cut_brace(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    size: float,
    plane_normal: tuple[float, float, float],
    opening: cq.Shape,
) -> cq.Shape:
    """Brace whose ends each take one angled saw cut.

    A bar centred on the corner-to-corner diagonal overshoots both boundaries
    at each corner, so clipping it leaves a notched point built from two faces.
    Tilting the bar by ``asin(size / span)`` puts one long face through each
    corner instead: a single plane then trims each end and the finished piece
    is a parallelogram that still fills the opening corner to corner.
    """
    va, vb = cq.Vector(*a), cq.Vector(*b)
    delta = vb - va
    tilt = math.degrees(math.asin(size / delta.Length))
    normal = cq.Vector(*plane_normal)
    diagonal = delta.normalized()
    # Take the shallower tilt. The receiving-member boundary then makes the
    # mitred end faces: x for the door/back frames and y for the side frames.
    # The long points still reach both rail corners, while the solid does not
    # extend through either vertical member.
    direction = max(
        (rotate_about(diagonal, normal, sign * tilt) for sign in (1, -1)),
        key=lambda candidate: -abs(candidate.z),
    )
    midpoint = va + delta.multiply(0.5)
    # Extend well past each receiving-member boundary so the final end is one
    # clean contact plane, even when the end is set back from a frame corner.
    reach = delta.dot(direction) / 2 + 2 * size
    start = midpoint - direction.multiply(reach)
    end = midpoint + direction.multiply(reach)
    bar = beam_between((start.x, start.y, start.z), (end.x, end.y, end.z), size)
    return bar.intersect(opening)


def cut_length(solid: cq.Shape) -> float:
    """Return the long-point diagonal between the two mitred end faces."""
    bbox = solid.BoundingBox()
    spans = sorted((bbox.xlen, bbox.ylen, bbox.zlen), reverse=True)
    return math.hypot(spans[0], spans[1])


def door_brace_endpoints(
    d: Design,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """D2 centreline joins the opposite vertical stile corners."""
    frame_bottom = d.door_bottom
    frame_top = frame_bottom + d.door_frame_height
    frame_center_y = -d.frame - d.cladding - d.hinge_gap + d.frame / 2
    end_setback = d.diagonal_end_setback
    return (
        (d.frame, frame_center_y, frame_top - d.frame - end_setback),
        (d.width - d.frame, frame_center_y, frame_bottom + d.frame + end_setback),
    )


def side_panel(d: Design, x: float, right: bool) -> cq.Shape:
    """Cladding wedge following the mono-pitch roof.

    The bottom front corner is notched around the front opening rail, which
    runs the full inner width and so crosses the side cladding's plane.
    """
    z0 = d.leg_extension
    notch_top = z0 + d.frame
    front_top = d.front_height
    back_top = d.side_back_top
    front_y = 0
    back_y = d.depth - d.frame
    profile = (
        cq.Workplane("YZ")
        .workplane(offset=x)
        .moveTo(d.frame, z0)
        .lineTo(back_y, z0)
        .lineTo(back_y, back_top)
        .lineTo(front_y, front_top)
        .lineTo(front_y, notch_top)
        .lineTo(d.frame, notch_top)
        .close()
        .extrude(d.cladding if not right else -d.cladding)
    )
    return profile.val()  # ty: ignore[invalid-return-type]


def door_cladding_panel(d: Design) -> cq.Shape:
    """Door cladding with top-corner notches around the roof side beams."""
    panel = box_at(
        0,
        -d.cladding - d.hinge_gap,
        d.door_bottom,
        d.width,
        d.cladding,
        d.door_height,
    )
    notch = d.frame
    notch_y = -d.cladding - d.hinge_gap - 1
    notch_z = d.door_top - notch
    for notch_x in (-1, d.width - notch):
        panel = panel.cut(
            box_at(
                notch_x,
                notch_y,
                notch_z,
                notch + 1,
                d.cladding + 2,
                notch + 1,
            )
        )
    return panel


def build(
    d: Design,
    door_angle: float = 0,
    roof_visible: bool = True,
    roof_lift_angle: float = 0,
) -> tuple[cq.Assembly, list[Part]]:
    d.validate()
    parts: list[Part] = []

    def add(
        name: str,
        category: str,
        solid: cq.Shape,
        dims: tuple[float, float, float],
        material: str = "wood",
    ) -> None:
        parts.append(Part(name, category, solid, *dims, material))

    # Bottom rails start 100 mm above the post bottoms. No wall, floor, or
    # framing member extends below that datum; only the four posts form legs.
    for side, x in (("left", 0), ("right", d.width - d.frame)):
        add(
            f"front_post_{side}",
            "V1",
            box_at(x, 0, 0, d.frame, d.frame, d.front_post_height),
            (d.front_post_height, d.frame, d.frame),
        )
        add(
            f"back_post_{side}",
            "V1",
            box_at(x, d.depth - d.frame, 0, d.frame, d.frame, d.back_height),
            (d.back_height, d.frame, d.frame),
        )

    # Horizontal frame around the wall bottoms and tops.
    for y, label in ((0, "front"), (d.depth - d.frame, "back")):
        z = d.leg_extension
        add(
            f"{label}_bottom",
            "front opening rail" if label == "front" else "HL1",
            box_at(d.frame, y, z, d.inner_width, d.frame, d.frame),
            (d.inner_width, d.frame, d.frame),
        )
    for x, label in ((0, "left"), (d.width - d.frame, "right")):
        add(
            f"{label}_bottom",
            "HK1",
            box_at(x, d.frame, d.leg_extension, d.frame, d.inner_depth, d.frame),
            (d.inner_depth, d.frame, d.frame),
        )
        add(
            f"{label}_top",
            "HK1",
            box_at(
                x,
                d.frame,
                d.front_post_height - d.frame,
                d.frame,
                d.inner_depth,
                d.frame,
            ),
            (d.inner_depth, d.frame, d.frame),
        )
    # The fixed rear support is distinct from the hinged roof frame.
    roof_slope_length = math.hypot(d.roof_run, d.roof_rise)
    roof_contact_y = -d.cladding - d.hinge_gap + d.frame
    roof_pitch_rear_y = roof_contact_y + d.roof_run
    roof_hinge_y = d.depth
    roof_hinge_top = d.back_height + d.frame
    roof_hinge_z = d.back_height + d.roof_hinge_pin_radius
    add(
        "back_top",
        "HL1",
        box_at(
            d.frame,
            d.depth - d.frame,
            d.back_height - d.frame,
            d.inner_width,
            d.frame,
            d.frame,
        ),
        (d.inner_width, d.frame, d.frame),
    )

    def pitch_roof_part(solid: cq.Shape) -> cq.Shape:
        return solid.rotate(
            (0, roof_pitch_rear_y, roof_hinge_top),
            (1, roof_pitch_rear_y, roof_hinge_top),
            -d.roof_angle,
        )

    def seat_roof_part(solid: cq.Shape) -> cq.Shape:
        return solid.rotate(
            (0, roof_hinge_y, roof_hinge_z),
            (1, roof_hinge_y, roof_hinge_z),
            d.roof_seat_angle,
        )

    def lift_roof_part(solid: cq.Shape) -> cq.Shape:
        if not roof_lift_angle:
            return solid
        return solid.rotate(
            (0, roof_hinge_y, roof_hinge_z),
            (1, roof_hinge_y, roof_hinge_z),
            -roof_lift_angle,
        )

    roof_flat_rear = roof_pitch_rear_y
    roof_flat_front = roof_flat_rear - d.frame - roof_slope_length
    roof_parts: list[tuple[str, str, cq.Shape, tuple[float, float, float], str]] = [
        (
            "roof_front",
            "HL2",
            box_at(
                0,
                roof_flat_front - d.frame,
                roof_hinge_top - d.frame,
                d.width,
                d.frame,
                d.frame,
            ),
            (d.width, d.frame, d.frame),
            "wood",
        ),
        (
            "roof_back",
            "HL2",
            box_at(
                0,
                roof_flat_rear - d.frame,
                roof_hinge_top - d.frame,
                d.width,
                d.frame,
                d.frame,
            ),
            (d.width, d.frame, d.frame),
            "wood",
        ),
        (
            "roof_left",
            "HK2",
            box_at(
                0,
                roof_flat_front,
                roof_hinge_top - d.frame,
                d.frame,
                roof_slope_length,
                d.frame,
            ),
            (roof_slope_length, d.frame, d.frame),
            "wood",
        ),
        (
            "roof_right",
            "HK2",
            box_at(
                d.width - d.frame,
                roof_flat_front,
                roof_hinge_top - d.frame,
                d.frame,
                roof_slope_length,
                d.frame,
            ),
            (roof_slope_length, d.frame, d.frame),
            "wood",
        ),
        (
            "roof_middle",
            "roof connector",
            box_at(
                d.frame,
                (roof_flat_front + roof_flat_rear) / 2 - d.roof_connector_width / 2,
                roof_hinge_top - d.roof_connector_thickness,
                d.inner_width,
                d.roof_connector_width,
                d.roof_connector_thickness,
            ),
            (
                d.inner_width,
                d.roof_connector_width,
                d.roof_connector_thickness,
            ),
            "wood",
        ),
    ]
    pitched_roof_parts = [pitch_roof_part(solid) for _, _, solid, _, _ in roof_parts]
    closed_roof_parts = [seat_roof_part(solid) for solid in pitched_roof_parts]
    closed_roof_by_name = {
        name: solid for (name, _, _, _, _), solid in zip(roof_parts, closed_roof_parts)
    }
    for (name, category, _, dims, material), solid in zip(
        roof_parts, closed_roof_parts
    ):
        add(name, category, lift_roof_part(solid), dims, material)

    # The metal sheet is centred over the roof frame before the complete unit
    # seats on its hinge. The frame and sheet then use the same two rotations.
    roof_width = 1050
    roof_depth = 1085
    roof_frame_box = cq.Compound.makeCompound(closed_roof_parts).BoundingBox()
    roof_center_x = (roof_frame_box.xmin + roof_frame_box.xmax) / 2
    roof_center_y = (roof_frame_box.ymin + roof_frame_box.ymax) / 2
    closed_roof_angle = math.radians(d.roof_seat_angle - d.roof_angle)
    roof_flat_depth = (
        roof_depth - d.roof_thickness * abs(math.sin(closed_roof_angle))
    ) / abs(math.cos(closed_roof_angle))
    roof_flat_center_y = (roof_flat_front + roof_flat_rear) / 2
    roof_blank = box_at(
        roof_center_x - roof_width / 2,
        roof_flat_center_y - roof_flat_depth / 2,
        roof_hinge_top,
        roof_width,
        roof_flat_depth,
        d.roof_thickness,
    )
    closed_roof = seat_roof_part(pitch_roof_part(roof_blank))
    sheet_box = closed_roof.BoundingBox()
    sheet_shift_y = roof_center_y - (sheet_box.ymin + sheet_box.ymax) / 2
    closed_roof = closed_roof.translate(
        (0, sheet_shift_y, math.tan(closed_roof_angle) * sheet_shift_y)
    )
    roof = lift_roof_part(closed_roof)

    # Tongue-and-groove wall fields. The lifted back edge rises past the
    # closed roof frame, so each panel is notched where that frame crosses it.
    # Cut the actual interferences separately. Subtracting the whole roof
    # compound leaves invalid sliver faces between the reliefs and rear edge.
    left_wall = side_panel(d, d.frame, False)
    right_wall = side_panel(d, d.width - d.frame, True)
    for relief in (
        closed_roof_by_name["roof_back"],
        closed_roof_by_name["roof_middle"],
        closed_roof,
    ):
        left_wall = left_wall.cut(relief)
        right_wall = right_wall.cut(relief)
    add(
        "left_wall",
        "side cladding",
        left_wall,
        (d.plan_grid_depth, d.door_height, d.cladding),
    )
    add(
        "right_wall",
        "side cladding",
        right_wall,
        (d.plan_grid_depth, d.door_height, d.cladding),
    )
    # The back field is fitted between the two side skins, not behind them.
    add(
        "back_wall",
        "back cladding",
        box_at(
            d.interior_x,
            d.back_wall_front,
            d.leg_extension,
            d.interior_width,
            d.cladding,
            d.back_height - d.leg_extension,
        ),
        (d.interior_width, d.back_height - d.leg_extension, d.cladding),
    )

    # Floor and toilet box fit between the 25 mm side-wall skins.
    interior_x = d.interior_x
    interior_width = d.interior_width
    back_wall_front = d.back_wall_front
    floor_width = interior_width
    floor_depth = back_wall_front
    floor_x = interior_x
    floor_bottom = d.leg_extension + d.frame
    floor_top = floor_bottom + d.cladding
    add(
        "floor",
        "floor",
        box_at(floor_x, 0, floor_bottom, floor_width, floor_depth, d.cladding),
        (floor_depth, floor_width, d.cladding),
        "dark wood",
    )
    add(
        "floor_back_support",
        "floor support",
        box_at(
            interior_x,
            back_wall_front - d.frame,
            d.leg_extension,
            interior_width,
            d.frame,
            d.frame,
        ),
        (interior_width, d.frame, d.frame),
    )
    # The floor boards run front to back, so the side bearers carry their long
    # edges between the front opening rail and the back support.
    floor_side_length = back_wall_front - 2 * d.frame
    for label, x in (
        ("left", interior_x),
        ("right", interior_x + interior_width - d.frame),
    ):
        add(
            f"floor_{label}_support",
            "floor support",
            box_at(x, d.frame, d.leg_extension, d.frame, floor_side_length, d.frame),
            (floor_side_length, d.frame, d.frame),
        )

    seat_width = interior_width
    seat_x = interior_x
    seat_back = back_wall_front
    seat_front_y = seat_back - d.seat_depth
    seat_top_bottom = floor_top + d.seat_height - d.cladding
    add(
        "seat_front",
        "seat side",
        box_at(
            seat_x,
            seat_front_y,
            floor_top,
            seat_width,
            d.cladding,
            d.seat_height - d.cladding,
        ),
        (d.seat_height - d.cladding, seat_width, d.cladding),
    )
    # Oval seat opening, centred in the seat box so the rails stay clear of it.
    seat_hole: cq.Shape = (  # ty: ignore[invalid-assignment]
        cq.Workplane("XY")
        .center(d.width / 2, seat_front_y + d.seat_depth / 2)
        .ellipse(d.seat_hole_width / 2, d.seat_hole_depth / 2)
        .extrude(d.cladding)
        .translate((0, 0, seat_top_bottom))
        .val()
    )
    add(
        "seat_top",
        "seat top",
        box_at(
            seat_x, seat_front_y, seat_top_bottom, seat_width, d.seat_depth, d.cladding
        ).cut(seat_hole),
        (d.seat_depth, seat_width, d.cladding),
    )
    # Both rails are concealed inside the seat box, immediately below its boards.
    for index, y in enumerate(
        (
            seat_front_y + d.cladding,
            seat_back - d.frame,
        )
    ):
        add(
            f"seat_rail_{index + 1}",
            "HL1",
            box_at(seat_x, y, seat_top_bottom - d.frame, seat_width, d.frame, d.frame),
            (seat_width, d.frame, d.frame),
        )
    add(
        "seat_lower_rail",
        "HL1",
        box_at(
            seat_x, seat_front_y + d.cladding, floor_top, seat_width, d.frame, d.frame
        ),
        (seat_width, d.frame, d.frame),
    )
    # The opening cuts the middle seat boards, so a bearer runs down each side
    # of it, fitted between the two seat rails and flush under the boards.
    seat_support_front = seat_front_y + d.cladding + d.frame
    seat_support_length = (seat_back - d.frame) - seat_support_front
    for label, x in (
        ("left", (d.width - d.seat_hole_width) / 2 - d.seat_support),
        ("right", (d.width + d.seat_hole_width) / 2),
    ):
        add(
            f"seat_support_{label}",
            "seat support",
            box_at(
                x,
                seat_support_front,
                seat_top_bottom - d.seat_support,
                d.seat_support,
                seat_support_length,
                d.seat_support,
            ),
            (seat_support_length, d.seat_support, d.seat_support),
        )
    # Side braces run corner to corner. Their mitred end faces are made by the
    # inner faces of the vertical members, so no stock extends into a post.
    for x, label in ((d.frame / 2, "left"), (d.width - d.frame / 2, "right")):
        bottom = (
            x,
            d.depth - d.frame,
            d.leg_extension + d.frame + d.diagonal_end_setback,
        )
        top = (
            x,
            d.frame,
            d.front_post_height - d.frame - d.diagonal_end_setback,
        )
        side_opening = box_at(
            x - d.frame / 2,
            d.frame,
            d.leg_extension + d.frame,
            d.frame,
            d.inner_depth,
            d.front_post_height - d.leg_extension - 2 * d.frame,
        )
        brace = single_cut_brace(bottom, top, d.frame, (1, 0, 0), side_opening)
        add(f"{label}_brace", "D1", brace, (cut_length(brace), d.frame, d.frame))

    # Back-wall brace. Its low end shares the rear-left corner with the left
    # side brace, so the bracing runs continuously around that corner. The
    # 850 x 950 opening matches the door frame, so this is a second D2 cut.
    back_brace_bottom = (
        d.frame,
        d.depth - d.frame / 2,
        d.leg_extension + d.frame + d.diagonal_end_setback,
    )
    back_brace_top = (
        d.width - d.frame,
        d.depth - d.frame / 2,
        d.back_height - d.frame - d.diagonal_end_setback,
    )
    back_opening = box_at(
        d.frame,
        d.depth - d.frame,
        d.leg_extension + d.frame,
        d.inner_width,
        d.frame,
        d.back_height - d.leg_extension - 2 * d.frame,
    )
    back_brace = single_cut_brace(
        back_brace_bottom, back_brace_top, d.frame, (0, 1, 0), back_opening
    )
    add("back_brace", "D2", back_brace, (cut_length(back_brace), d.frame, d.frame))

    if roof_visible:
        add(
            "roof",
            "metal roof",
            roof,
            (roof_depth, roof_width, d.roof_thickness),
            "metal roof",
        )

    roof_fixed_leaf = box_at(
        d.frame,
        d.depth,
        d.back_height - d.frame,
        d.inner_width,
        d.hinge_leaf_thickness,
        d.frame + d.roof_hinge_pin_radius,
    )
    roof_moving_leaf = seat_roof_part(
        pitch_roof_part(
            box_at(
                d.frame,
                roof_pitch_rear_y,
                roof_hinge_top - d.frame,
                d.inner_width,
                d.hinge_leaf_thickness,
                d.frame,
            )
        )
    )
    # Pitching swings the leaf's outer bottom corner below the fixed rear rail.
    # Relieve it there so the closed roof seats without fouling the rail.
    roof_moving_leaf = roof_moving_leaf.cut(
        box_at(0, 0, 0, d.width, d.depth, d.back_height)
    )
    roof_moving_leaf = lift_roof_part(roof_moving_leaf)
    roof_hinge_pin: cq.Shape = (  # ty: ignore[invalid-assignment]
        cq.Workplane("YZ")
        .center(roof_hinge_y, roof_hinge_z)
        .circle(d.roof_hinge_pin_radius)
        .extrude(d.inner_width)
        .translate((d.frame, 0, 0))
        .val()
    )
    add(
        "roof_hinge_fixed",
        "roof hinge leaf",
        roof_fixed_leaf,
        (d.inner_width, d.frame + d.roof_hinge_pin_radius, d.hinge_leaf_thickness),
        "metal",
    )
    add(
        "roof_hinge_moving",
        "roof hinge leaf",
        roof_moving_leaf,
        (d.inner_width, d.frame, d.hinge_leaf_thickness),
        "metal",
    )
    add(
        "roof_hinge_pin",
        "roof hinge pin",
        roof_hinge_pin,
        (d.inner_width, 2 * d.roof_hinge_pin_radius, 2 * d.roof_hinge_pin_radius),
        "metal",
    )

    # Door panel and frame rotate about a pin offset from the front-right post.
    # The gap keeps this separately manufactured moving assembly from merging
    # visually or geometrically into the fixed structure.
    hinge_x = d.width
    hinge_y = -d.hinge_gap / 2
    door_width = d.width
    door_height = d.door_height
    door_frame_bottom = d.door_bottom
    door_frame_top = door_frame_bottom + d.door_frame_height
    door_brace_top, door_brace_bottom = door_brace_endpoints(d)
    door_brace_solid = single_cut_brace(
        door_brace_bottom,
        door_brace_top,
        d.frame,
        (0, 1, 0),
        box_at(
            d.frame,
            -d.frame - d.cladding - d.hinge_gap,
            door_frame_bottom + d.frame,
            d.inner_width,
            d.frame,
            d.door_frame_height - 2 * d.frame,
        ),
    )
    door_parts: list[tuple[str, cq.Shape, tuple[float, float, float], str]] = [
        (
            "door_panel",
            door_cladding_panel(d),
            (door_height, door_width, d.cladding),
            "cladding",
        ),
        (
            "door_left",
            box_at(
                0,
                -d.frame - d.cladding - d.hinge_gap,
                door_frame_bottom,
                d.frame,
                d.frame,
                d.door_frame_height,
            ),
            (d.door_frame_height, d.frame, d.frame),
            "V2",
        ),
        (
            "door_right",
            box_at(
                d.width - d.frame,
                -d.frame - d.cladding - d.hinge_gap,
                door_frame_bottom,
                d.frame,
                d.frame,
                d.door_frame_height,
            ),
            (d.door_frame_height, d.frame, d.frame),
            "V2",
        ),
        # The stiles run the full frame height, so the rails fit between them.
        (
            "door_bottom",
            box_at(
                d.frame,
                -d.frame - d.cladding - d.hinge_gap,
                door_frame_bottom,
                d.inner_width,
                d.frame,
                d.frame,
            ),
            (d.inner_width, d.frame, d.frame),
            "HL2",
        ),
        (
            "door_top",
            box_at(
                d.frame,
                -d.frame - d.cladding - d.hinge_gap,
                door_frame_top - d.frame,
                d.inner_width,
                d.frame,
                d.frame,
            ),
            (d.inner_width, d.frame, d.frame),
            "HL2",
        ),
        (
            "door_brace",
            door_brace_solid,
            (cut_length(door_brace_solid), d.frame, d.frame),
            "D2",
        ),
    ]
    for name, solid, dims, category in door_parts:
        if door_angle:
            solid = solid.rotate(
                (hinge_x, hinge_y, d.door_bottom),
                (hinge_x, hinge_y, d.door_bottom + 1),
                door_angle,
            )
        add(name, category, solid, dims)
    for index, z in enumerate((225, 825), start=1):
        hinge_z = z + d.door_bottom
        fixed_leaf = box_at(
            d.width - d.frame,
            hinge_y,
            hinge_z,
            d.frame,
            d.hinge_leaf_thickness,
            150,
        )
        moving_leaf = box_at(
            d.width - d.hinge_leaf_thickness,
            -d.hinge_gap,
            hinge_z,
            d.hinge_leaf_thickness,
            d.hinge_gap / 2,
            150,
        )
        if door_angle:
            moving_leaf = moving_leaf.rotate(
                (hinge_x, hinge_y, d.door_bottom),
                (hinge_x, hinge_y, d.door_bottom + 1),
                door_angle,
            )
        pin: cq.Shape = (  # ty: ignore[invalid-assignment]
            cq.Workplane("XY")
            .center(hinge_x, hinge_y)
            .circle(d.hinge_pin_radius)
            .extrude(150)
            .translate((0, 0, hinge_z))
            .val()
        )
        add(
            f"hinge_fixed_{index}",
            "hinge leaf",
            fixed_leaf,
            (150, d.frame, d.hinge_leaf_thickness),
            "metal",
        )
        add(
            f"hinge_door_{index}",
            "hinge leaf",
            moving_leaf,
            (150, d.frame + d.hinge_gap / 2, d.hinge_leaf_thickness),
            "metal",
        )
        add(
            f"door_hinge_{index}",
            "hinge pin",
            pin,
            (150, 2 * d.hinge_pin_radius, 2 * d.hinge_pin_radius),
            "metal",
        )

    assembly = cq.Assembly(name="dass")
    colors = {
        "wood": cq.Color(0.72, 0.54, 0.32),
        "cladding": cq.Color(0.82, 0.69, 0.46),
        "dark wood": cq.Color(0.22, 0.15, 0.09),
        "roof": cq.Color(0.23, 0.27, 0.28),
        "metal roof": cq.Color(0.43, 0.48, 0.50),
        "metal": cq.Color(0.16, 0.17, 0.18),
    }
    for p in parts:
        assembly.add(p.solid, name=p.name, color=colors.get(p.material, colors["wood"]))
    return assembly, parts


def write_cutlist(parts: list[Part], path: Path) -> None:
    grouped: dict[tuple[str, float, float, float, str], int] = {}
    for p in parts:
        key = (
            p.category,
            round(p.length, 1),
            round(p.width, 1),
            round(p.thickness, 1),
            p.material,
        )
        grouped[key] = grouped.get(key, 0) + 1
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ("part", "quantity", "length_mm", "width_mm", "thickness_mm", "material")
        )
        for key, quantity in sorted(grouped.items()):
            category, length, width, thickness, material = key
            writer.writerow((category, quantity, length, width, thickness, material))


def render(
    parts: list[Part],
    design: Design,
    path: Path,
    size: tuple[int, int] = (1200, 900),
    eye: tuple[float, float, float] = (-1900, -2400, 1650),
    target: tuple[float, float, float] | None = None,
) -> None:
    """Deterministic orthographic triangle renderer with a depth buffer."""
    eye_vector = np.array(eye, dtype=float)
    target_vector = np.array(
        target or (design.width / 2, design.depth / 2, design.front_height / 2),
        dtype=float,
    )
    forward = target_vector - eye_vector
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array((0.0, 0.0, 1.0)))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    triangles: list[tuple[np.ndarray, str, float]] = []
    palette = {
        "wood": (184, 138, 82),
        "cladding": (209, 173, 115),
        "dark wood": (57, 39, 25),
        "roof": (72, 81, 86),
        "metal roof": (110, 122, 128),
        "metal": (42, 44, 46),
    }
    light = np.array((-0.35, -0.5, 0.79))
    for part in parts:
        vertices, faces = part.solid.tessellate(0.2, 0.1)
        xyz = np.array([[v.x, v.y, v.z] for v in vertices])
        for face in faces:
            tri = xyz[list(face)]
            normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            normal /= np.linalg.norm(normal)
            shade = 0.68 + 0.32 * abs(float(np.dot(normal, light)))
            triangles.append((tri, part.material, shade))

    projected = [
        np.column_stack((tri @ right, tri @ up, tri @ forward))
        for tri, _, _ in triangles
    ]
    cloud = np.concatenate(projected)
    lo, hi = cloud[:, :2].min(axis=0), cloud[:, :2].max(axis=0)
    margin = 50
    scale = min(
        (size[0] - 2 * margin) / (hi[0] - lo[0]),
        (size[1] - 2 * margin) / (hi[1] - lo[1]),
    )
    color = np.full((size[1], size[0], 3), 247, dtype=np.uint8)
    depth = np.full((size[1], size[0]), np.inf)

    for (_, material, shade), tri in zip(triangles, projected):
        px = (tri[:, 0] - lo[0]) * scale + margin
        py = size[1] - ((tri[:, 1] - lo[1]) * scale + margin)
        pz = tri[:, 2]
        xmin, xmax = max(0, int(px.min())), min(size[0] - 1, int(px.max()) + 1)
        ymin, ymax = max(0, int(py.min())), min(size[1] - 1, int(py.max()) + 1)
        if xmin > xmax or ymin > ymax:
            continue
        xx, yy = np.meshgrid(
            np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5
        )
        denominator = (py[1] - py[2]) * (px[0] - px[2]) + (px[2] - px[1]) * (
            py[0] - py[2]
        )
        if abs(denominator) < 1e-9:
            continue
        a = (
            (py[1] - py[2]) * (xx - px[2]) + (px[2] - px[1]) * (yy - py[2])
        ) / denominator
        b = (
            (py[2] - py[0]) * (xx - px[2]) + (px[0] - px[2]) * (yy - py[2])
        ) / denominator
        c = 1 - a - b
        inside = (a >= -1e-8) & (b >= -1e-8) & (c >= -1e-8)
        z = a * pz[0] + b * pz[1] + c * pz[2]
        local_depth = depth[ymin : ymax + 1, xmin : xmax + 1]
        visible = inside & (z < local_depth)
        local_depth[visible] = z[visible]
        rgb = np.array(
            [round(channel * shade) for channel in palette[material]], dtype=np.uint8
        )
        color[ymin : ymax + 1, xmin : xmax + 1][visible] = rgb
    Image.fromarray(color).save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument("--door-angle", type=float, default=105)
    parser.add_argument("--roof-lift-angle", type=float, default=25)
    parser.add_argument("--width", type=float)
    parser.add_argument("--depth", type=float)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=MM",
        help="override any numeric Design parameter; may be repeated",
    )
    args = parser.parse_args()
    overrides = {
        key: value
        for key, value in vars(args).items()
        if key in {"width", "depth"} and value is not None
    }
    parameter_names = {field.name for field in fields(Design)}
    for item in args.set:
        name, separator, value = item.partition("=")
        if not separator or name not in parameter_names:
            parser.error(
                f"--set must be NAME=MM where NAME is one of: {', '.join(sorted(parameter_names))}"
            )
        try:
            overrides[name] = float(value)
        except ValueError:
            parser.error(f"--set {name} requires a numeric value, got {value!r}")
    base = Design()
    design = replace(base, **overrides)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, door_angle, roof_lift_angle in (
        ("closed", 0, 0),
        ("open", args.door_angle, args.roof_lift_angle),
    ):
        assembly, parts = build(
            design,
            door_angle=door_angle,
            roof_visible=True,
            roof_lift_angle=roof_lift_angle,
        )
        assembly.export(str(args.output / f"dass-{name}.step"))
        assembly.export(str(args.output / f"dass-{name}.glb"))
        render(parts, design, args.output / f"dass-{name}.png")
    write_cutlist(parts, args.output / "cutlist.csv")
    print(f"Wrote CAD, renders, and cut list to {args.output}")


if __name__ == "__main__":
    main()
