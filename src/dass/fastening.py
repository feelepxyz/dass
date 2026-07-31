"""Model-derived frame screw layout and angle checks.

This is a collision and workshop-layout check, not a structural screw-sizing
calculation. Cladding remains outside this schedule because it is nailed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .cutlists import BEAM_CODES
from .model import Design, Part, build

MINIMUM_SCREW_SPACING_MM = 20.0
SCREW_LANES_MM = (12.0, 33.0)
SCREW_PATH_CLEARANCE_MM = 5.0


@dataclass(frozen=True)
class Connection:
    from_beam: str
    into_beam: str
    face: str
    target_station_mm: float
    diagonal: bool = False


@dataclass(frozen=True)
class ScrewMark:
    code: str
    from_beam: str
    into_beam: str
    target_face: str
    target_station_mm: float
    source_station_mm: float
    lane_mm: float
    diagonal: bool = False


@dataclass(frozen=True)
class ScrewPath:
    code: str
    from_beam: str
    into_beam: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    axis: str
    source_exit_mm: float = 0.0


@dataclass(frozen=True)
class AngleCheck:
    code: str
    description: str
    run_mm: float
    rise_mm: float
    drawing_degrees: float
    model_degrees: float


@dataclass(frozen=True)
class FasteningAnalysis:
    screws: tuple[ScrewMark, ...]
    overlaps: tuple[tuple[str, str, float], ...]
    screw_paths: tuple[ScrewPath, ...]
    path_collisions: tuple[tuple[str, str, float], ...]
    angles: tuple[AngleCheck, ...]
    recommendations: tuple[str, ...]


# Each entry is one beam-to-beam connection. Two marks share a connection but
# use separate lanes across the 45 mm face. Target stations are world-frame z
# stations for the upright/rail joints; diagonal stations come from the model's
# set-back endpoints.
CONNECTIONS = (
    # Fixed shell frame.
    Connection("front_post_left", "front_bottom", "front", 122.5),
    Connection("front_post_right", "front_bottom", "front", 122.5),
    Connection("back_post_left", "back_bottom", "rear", 122.5),
    Connection("back_post_right", "back_bottom", "rear", 122.5),
    Connection("back_post_left", "back_top", "rear", 1127.5),
    Connection("back_post_right", "back_top", "rear", 1127.5),
    Connection("front_post_left", "left_bottom", "side", 122.5),
    Connection("back_post_left", "left_bottom", "side", 122.5),
    Connection("front_post_left", "left_top", "side", 1127.5),
    Connection("back_post_left", "left_top", "side", 1127.5),
    Connection("front_post_right", "right_bottom", "side", 122.5),
    Connection("back_post_right", "right_bottom", "side", 122.5),
    Connection("front_post_right", "right_top", "side", 1127.5),
    Connection("back_post_right", "right_top", "side", 1127.5),
    # Diagonals end on the vertical members between the rail rows. Their
    # screws therefore start at the same post as the rail screws.
    Connection("front_post_left", "left_brace", "side", 1010, True),
    Connection("back_post_left", "left_brace", "side", 190, True),
    Connection("front_post_right", "right_brace", "side", 1010, True),
    Connection("back_post_right", "right_brace", "side", 190, True),
    Connection("back_post_left", "back_brace", "rear", 190, True),
    Connection("back_post_right", "back_brace", "rear", 1010, True),
    # Roof frame.
    Connection("roof_front", "roof_left", "slope-front", 45),
    Connection("roof_front", "roof_right", "slope-front", 45),
    Connection("roof_back", "roof_left", "slope-rear", 768),
    Connection("roof_back", "roof_right", "slope-rear", 768),
    Connection("roof_middle", "roof_left", "slope-middle", 406),
    Connection("roof_middle", "roof_right", "slope-middle", 406),
    # Floor bearers.
    Connection("floor_back_support", "floor_left_support", "top", 612),
    Connection("floor_back_support", "floor_right_support", "top", 612),
    Connection("floor_left_support", "front_bottom", "underside", 90),
    Connection("floor_right_support", "front_bottom", "underside", 810),
    Connection("floor_left_support", "floor_back_support", "underside", 90),
    Connection("floor_right_support", "floor_back_support", "underside", 810),
    # Seat box frame. The lower front rail is not in this beam-to-beam schedule;
    # the seat side that fixes it is cladding and remains nailed.
    Connection("seat_support_left", "seat_rail_1", "underside", 270),
    Connection("seat_support_left", "seat_rail_2", "underside", 270),
    Connection("seat_support_right", "seat_rail_1", "underside", 585),
    Connection("seat_support_right", "seat_rail_2", "underside", 585),
    # Door frame.
    Connection("door_left", "door_bottom", "door", 122.5),
    Connection("door_right", "door_bottom", "door", 122.5),
    Connection("door_left", "door_top", "door", 1127.5),
    Connection("door_right", "door_top", "door", 1127.5),
    Connection("door_left", "door_brace", "door", 1010, True),
    Connection("door_right", "door_brace", "door", 190, True),
)


def _brace_cut_angle(run_mm: float, rise_mm: float, frame_mm: float) -> float:
    axis = math.degrees(math.atan2(rise_mm, run_mm))
    tilt = math.degrees(math.asin(frame_mm / math.hypot(run_mm, rise_mm)))
    return 90 - axis - tilt


def _angle_checks(design: Design) -> tuple[AngleCheck, ...]:
    side_rise = (
        design.front_post_height
        - design.leg_extension
        - 2 * design.frame
        - 2 * design.diagonal_end_setback
    )
    d2_rise = (
        design.door_frame_height - 2 * design.frame - 2 * design.diagonal_end_setback
    )
    return (
        AngleCheck(
            "SIDE-PITCH",
            "finished side-frame pitch",
            design.plan_grid_depth,
            design.side_fall,
            7.4,
            math.degrees(math.atan2(design.side_fall, design.plan_grid_depth)),
        ),
        AngleCheck(
            "ROOF-PITCH",
            "finished roof-beam pitch",
            design.roof_run,
            design.roof_rise,
            8.8,
            design.roof_angle,
        ),
        AngleCheck(
            "D1",
            "side diagonal saw cut",
            design.inner_depth,
            side_rise,
            36.0,
            _brace_cut_angle(
                design.inner_depth,
                side_rise,
                design.frame,
            ),
        ),
        AngleCheck(
            "D2",
            "back and door diagonal saw cut",
            design.inner_width,
            d2_rise,
            40.0,
            _brace_cut_angle(
                design.inner_width,
                d2_rise,
                design.frame,
            ),
        ),
    )


def _diagonal_station(design: Design, connection: Connection) -> float:
    if connection.into_beam in {"left_brace", "right_brace"}:
        return (
            design.front_post_height - design.frame - design.diagonal_end_setback
            if connection.from_beam.startswith("front_post")
            else design.leg_extension + design.frame + design.diagonal_end_setback
        )
    if connection.into_beam == "back_brace":
        return (
            design.back_height - design.frame - design.diagonal_end_setback
            if connection.from_beam == "back_post_right"
            else design.leg_extension + design.frame + design.diagonal_end_setback
        )
    if connection.into_beam == "door_brace":
        return (
            design.door_bottom
            + design.door_frame_height
            - design.frame
            - design.diagonal_end_setback
            if connection.from_beam == "door_left"
            else design.door_bottom + design.frame + design.diagonal_end_setback
        )
    raise ValueError(f"unknown diagonal connection: {connection}")


def _screw_marks(design: Design) -> tuple[ScrewMark, ...]:
    marks: list[ScrewMark] = []
    for index, connection in enumerate(CONNECTIONS, 1):
        target_station = (
            _diagonal_station(design, connection)
            if connection.diagonal
            else connection.target_station_mm
        )
        for lane_index, lane in enumerate(SCREW_LANES_MM, 1):
            marks.append(
                ScrewMark(
                    f"F{index:02d}-{lane_index}",
                    connection.from_beam,
                    connection.into_beam,
                    connection.face,
                    target_station,
                    design.frame,
                    lane,
                    connection.diagonal,
                )
            )
    return tuple(marks)


def _find_overlaps(marks: tuple[ScrewMark, ...]) -> tuple[tuple[str, str, float], ...]:
    overlaps: list[tuple[str, str, float]] = []
    for index, first in enumerate(marks):
        for second in marks[index + 1 :]:
            if (first.from_beam, first.into_beam, first.target_face) != (
                second.from_beam,
                second.into_beam,
                second.target_face,
            ):
                continue
            distance = math.hypot(
                first.target_station_mm - second.target_station_mm,
                first.lane_mm - second.lane_mm,
            )
            if distance < MINIMUM_SCREW_SPACING_MM:
                overlaps.append((first.code, second.code, distance))
    return tuple(overlaps)


def _sub(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _scale(a: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def _point_segment_distance(
    point: tuple[float, float, float],
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> float:
    direction = _sub(end, start)
    length_squared = _dot(direction, direction)
    parameter = (
        _dot(_sub(point, start), direction) / length_squared if length_squared else 0.0
    )
    nearest = _add(start, _scale(direction, max(0.0, min(1.0, parameter))))
    delta = _sub(point, nearest)
    return math.sqrt(_dot(delta, delta))


def _segment_distance(
    first_start: tuple[float, float, float],
    first_end: tuple[float, float, float],
    second_start: tuple[float, float, float],
    second_end: tuple[float, float, float],
) -> float:
    """Return the shortest distance between two finite screw centerlines."""
    u = _sub(first_end, first_start)
    v = _sub(second_end, second_start)
    w = _sub(first_start, second_start)
    a = _dot(u, u)
    b = _dot(u, v)
    c = _dot(v, v)
    d = _dot(u, w)
    e = _dot(v, w)
    denominator = a * c - b * b
    if denominator < 1e-12:
        return min(
            _point_segment_distance(first_start, second_start, second_end),
            _point_segment_distance(first_end, second_start, second_end),
            _point_segment_distance(second_start, first_start, first_end),
            _point_segment_distance(second_end, first_start, first_end),
        )
    else:
        first_parameter = max(0.0, min(1.0, (b * e - c * d) / denominator))
        second_parameter = (b * first_parameter + e) / c if c else 0.0
        if second_parameter < 0.0:
            second_parameter = 0.0
            first_parameter = max(0.0, min(1.0, -d / a if a else 0.0))
        elif second_parameter > 1.0:
            second_parameter = 1.0
            first_parameter = max(0.0, min(1.0, (b - d) / a if a else 0.0))
    delta = _sub(
        _sub(first_start, second_start),
        _sub(_scale(v, second_parameter), _scale(u, first_parameter)),
    )
    return math.sqrt(max(0.0, _dot(delta, delta)))


def _screw_paths(
    design: Design,
    marks: tuple[ScrewMark, ...],
    parts: list[Part],
) -> tuple[ScrewPath, ...]:
    """Model paths driven from posts/stiles into their adjoining frame parts."""
    boxes = {part.name: part.solid.BoundingBox() for part in parts}
    vertical_sources = {
        "front_post_left",
        "front_post_right",
        "back_post_left",
        "back_post_right",
        "door_left",
        "door_right",
    }
    paths: list[ScrewPath] = []
    for mark in marks:
        if mark.from_beam not in vertical_sources:
            continue
        source = boxes[mark.from_beam]
        target = boxes[mark.into_beam]
        axis = "x" if target.xlen > design.frame + 1e-6 else "y"
        if axis == "x":
            positive = target.xmin >= source.xmax - 1e-6
            start_axis = source.xmin if positive else source.xmax
            start = (start_axis, source.ymin + mark.lane_mm, mark.target_station_mm)
            end = (
                start_axis
                + (design.screw_length if positive else -design.screw_length),
                start[1],
                start[2],
            )
        else:
            positive = target.ymin >= source.ymax - 1e-6
            start_axis = source.ymin if positive else source.ymax
            start = (
                source.xmin + design.frame - mark.lane_mm,
                start_axis,
                mark.target_station_mm,
            )
            end = (
                start[0],
                start_axis
                + (design.screw_length if positive else -design.screw_length),
                start[2],
            )
        if mark.diagonal:
            # At a corner the brace shares the rail's end station. Angle the
            # screw toward the brace as it leaves the post so it clears the
            # rail screw instead of driving two centerlines through one path.
            angle = math.radians(design.diagonal_screw_angle)
            axial_length = design.screw_length * math.cos(angle)
            z_direction = (
                -1 if mark.target_station_mm > source.zmin + source.zlen / 2 else 1
            )
            if axis == "x":
                end = (
                    start_axis + (axial_length if positive else -axial_length),
                    start[1],
                    start[2] + z_direction * design.screw_length * math.sin(angle),
                )
            else:
                end = (
                    start[0],
                    start_axis + (axial_length if positive else -axial_length),
                    start[2] + z_direction * design.screw_length * math.sin(angle),
                )
        paths.append(
            ScrewPath(
                mark.code,
                mark.from_beam,
                mark.into_beam,
                start,
                end,
                axis,
                design.frame,
            )
        )
    return tuple(paths)


def find_screw_path_collisions(
    paths: tuple[ScrewPath, ...],
) -> tuple[tuple[str, str, float], ...]:
    collisions: list[tuple[str, str, float]] = []

    def after_source(
        path: ScrewPath,
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        direction = _sub(path.end, path.start)
        length = math.sqrt(_dot(direction, direction))
        if not length or path.source_exit_mm <= 0:
            return path.start, path.end
        unit = _scale(direction, 1 / length)
        return _add(path.start, _scale(unit, path.source_exit_mm)), path.end

    for index, first in enumerate(paths):
        for second in paths[index + 1 :]:
            first_start, first_end = after_source(first)
            second_start, second_end = after_source(second)
            distance = _segment_distance(
                first_start, first_end, second_start, second_end
            )
            if distance < SCREW_PATH_CLEARANCE_MM:
                collisions.append((first.code, second.code, distance))
    return tuple(collisions)


def analyze_frame_fastening(design: Design) -> FasteningAnalysis:
    """Check the nominal beam screw marks against the current model names."""
    _, parts = build(design)
    beam_names = {
        part.name
        for part in parts
        if part.material == "wood"
        and part.width == design.frame
        and part.thickness == design.frame
    }
    referenced = {
        name
        for connection in CONNECTIONS
        for name in (
            connection.from_beam,
            connection.into_beam,
        )
    }
    missing = referenced - beam_names
    if missing:
        raise ValueError(
            f"fastening schedule names missing frame beams: {sorted(missing)}"
        )

    marks = _screw_marks(design)
    screw_paths = _screw_paths(design, marks, parts)
    overlaps = _find_overlaps(marks)
    path_collisions = find_screw_path_collisions(screw_paths)
    return FasteningAnalysis(
        marks,
        overlaps,
        screw_paths,
        path_collisions,
        _angle_checks(design),
        (
            "Fit every diagonal corner to corner and trim its ends flush with the receiving member faces",
            f"Drive the {design.screw_length:g} mm diagonal screws from the vertical members at a slight angle",
            "Measure the finished frame before final fastening and use the measured angle for the scribe",
            "Do not use the cladding nail pattern for beam screws",
        ),
    )


def fastening_report(design: Design) -> str:
    """Return the human-readable audit retained beside generated outputs."""
    analysis = analyze_frame_fastening(design)
    lines = [
        "# Frame fastening audit",
        "",
        "This is a beam screw-layout and collision check, not a structural screw-sizing calculation.",
        "Cladding is excluded because it is nailed.",
        "",
        f"- Beam-to-beam connections: {len(CONNECTIONS)}",
        f"- Nominal screw marks: {len(analysis.screws)}",
        f"- Screw-mark overlaps: {len(analysis.overlaps)}",
        f"- Screw-path collisions: {len(analysis.path_collisions)}",
        "- Result: PASS"
        if not analysis.overlaps and not analysis.path_collisions
        else "- Result: ADJUST",
        "",
        "## Angle checks",
        "",
        "| Check | Use | Drawing guide | Model guide | Run × rise |",
        "|---|---|---:|---:|---:|",
    ]
    for check in analysis.angles:
        lines.append(
            f"| {check.code} | {check.description} | {check.drawing_degrees:.1f}° | "
            f"{check.model_degrees:.1f}° | {check.run_mm:.0f} × {check.rise_mm:.0f} mm |"
        )
    lines.extend(
        (
            "",
            "## Screw marks",
            "",
            "| Mark | From beam | Into beam | Face | Source station | Target station | Lane |",
            "|---|---|---|---|---:|---:|---:|",
        )
    )
    for screw in analysis.screws:
        from_code = BEAM_CODES.get(screw.from_beam, screw.from_beam)
        into_code = BEAM_CODES.get(screw.into_beam, screw.into_beam)
        lines.append(
            f"| {screw.code} | {from_code} ({screw.from_beam}) | {into_code} ({screw.into_beam}) | "
            f"{screw.target_face} | {screw.source_station_mm:.1f} mm | "
            f"{screw.target_station_mm:.1f} mm | {screw.lane_mm:.1f} mm |"
        )
    lines.extend(("", "## Workshop notes", ""))
    lines.extend(f"- {note}." for note in analysis.recommendations)
    lines.append(
        "- Measure the finished frame side and roof pitch with a bevel gauge; record the actual value before final screws."
    )
    return "\n".join(lines) + "\n"


def fastening_summary(design: Design) -> str:
    """Return a short guide-ready summary of the audit."""
    analysis = analyze_frame_fastening(design)
    result = (
        "PASS" if not analysis.overlaps and not analysis.path_collisions else "ADJUST"
    )
    return (
        f"{len(analysis.screws)} nominal beam screw marks across {len(CONNECTIONS)} "
        f"beam-to-beam connections · {len(analysis.overlaps)} screw-mark overlaps · "
        f"{len(analysis.path_collisions)} screw-path collisions · {result}. "
        f"Diagonals run corner to corner; their {design.screw_length:g} mm screws start in the vertical members "
        f"at {design.diagonal_screw_angle:g}° and are checked as paths; measure the finished frame angle "
        "before the final screws. Cladding is nailed, not included in this check."
    )
