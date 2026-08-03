"""Generate a printable, model-derived cutting and assembly guide."""

from __future__ import annotations

import argparse
import html
import json
import math
import os
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only the projection helpers name a CadQuery solid, and they are typed
    # rather than imported at runtime: the guide is drawn from geometry the
    # caller already built, so this module never touches cadquery itself.
    import cadquery as cq

from .cutlists import (
    BEAM_CODES,
    BOARD_WIDTH,
    COVER_WIDTH,
    DEFAULT_KERF,
    CutPiece,
    beam_pieces,
    cladding_pieces,
    pack_stock,
    panel_stock_plan,
)
from .fastening import (
    HARDWARE_SCHEDULE,
    SCREW_LANES_MM,
    SCREW_PATH_CLEARANCE_MM,
    FasteningAnalysis,
    ScrewMark,
    analyze_frame_fastening,
    screw_path_distance,
)
from .model import Design, box_at, build, side_panel

SITE_URL = "https://feelep.xyz/dass"
SOCIAL_IMAGE_URL = f"{SITE_URL}/web-renders/in-situ-open.jpg"
IN_SITU_CROP_FOCUS = 1.0
# Set both variables after uploading the clip in Stream. Until then, the
# generated page keeps the local H.264 fallback so previews remain usable.
CLOUDFLARE_STREAM_CUSTOMER_CODE = os.environ.get(
    "DASS_CLOUDFLARE_STREAM_CUSTOMER_CODE", ""
).strip()
CLOUDFLARE_STREAM_VIDEO_ID = os.environ.get(
    "DASS_CLOUDFLARE_STREAM_VIDEO_ID", ""
).strip()
CLOUDFLARE_STREAM_PLAYER_URL = (
    f"https://customer-{CLOUDFLARE_STREAM_CUSTOMER_CODE}.cloudflarestream.com/"
    f"{CLOUDFLARE_STREAM_VIDEO_ID}/iframe"
    if CLOUDFLARE_STREAM_CUSTOMER_CODE and CLOUDFLARE_STREAM_VIDEO_ID
    else ""
)


def social_head(title: str, description: str, canonical_path: str = "") -> str:
    """Return the shared document and social-card metadata for a public page."""
    canonical = f"{SITE_URL}/{canonical_path}" if canonical_path else f"{SITE_URL}/"
    title_attr = html.escape(title, quote=True)
    description_attr = html.escape(description, quote=True)
    canonical_attr = html.escape(canonical, quote=True)
    image_attr = html.escape(SOCIAL_IMAGE_URL, quote=True)
    return f"""  <meta name="description" content="{description_attr}">
  <link rel="canonical" href="{canonical_attr}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="DASS">
  <meta property="og:title" content="{title_attr}">
  <meta property="og:description" content="{description_attr}">
  <meta property="og:url" content="{canonical_attr}">
  <meta property="og:image" content="{image_attr}">
  <meta property="og:image:alt" content="Open timber outdoor toilet in a forest clearing">
  <meta property="og:image:width" content="1400">
  <meta property="og:image:height" content="1400">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@feelepxyz">
  <meta name="twitter:creator" content="@feelepxyz">
  <meta name="twitter:title" content="{title_attr}">
  <meta name="twitter:description" content="{description_attr}">
  <meta name="twitter:image" content="{image_attr}">
  <meta name="twitter:image:alt" content="Open timber outdoor toilet in a forest clearing">"""


PART_NAMES = {
    "front_post_left": "left front post",
    "back_post_left": "left rear post",
    "left_bottom": "left lower rail",
    "left_top": "left upper rail",
    "left_brace": "left diagonal brace",
    "front_post_right": "right front post",
    "back_post_right": "right rear post",
    "right_bottom": "right lower rail",
    "right_top": "right upper rail",
    "right_brace": "right diagonal brace",
    "front_bottom": "front opening rail",
    "back_bottom": "back lower rail",
    "back_top": "back upper rail",
    "back_brace": "back diagonal brace",
    "roof_front": "roof front cross-beam",
    "roof_back": "roof rear cross-beam",
    "roof_left": "roof left slope beam",
    "roof_right": "roof right slope beam",
    "roof_middle": "roof middle connector",
    "floor_back_support": "floor rear bearer",
    "floor_left_support": "floor left bearer",
    "floor_right_support": "floor right bearer",
    "seat_rail_1": "seat upper front rail",
    "seat_rail_2": "seat upper rear rail",
    "seat_support_left": "seat opening left bearer",
    "seat_support_right": "seat opening right bearer",
    "seat_support_outer_left": "seat outer left bearer",
    "seat_support_outer_right": "seat outer right bearer",
    "seat_box_support_front": "fixed front seat-box bearer",
    "seat_box_support_rear": "fixed rear seat-box bearer",
    "seat_floor_support": "seat-front floor bearer",
    "door_left": "door left stile",
    "door_right": "door right stile",
    "door_bottom": "door lower rail",
    "door_top": "door upper rail",
    "door_brace": "door diagonal brace",
}


MODULES = [
    ("A", "Roof unit", ("RB",)),
    ("B", "Door unit", ("DB", "DCB")),
    ("C", "Left side", ("LS",)),
    ("D", "Right side", ("RS",)),
    ("E", "Back unit", ("BW",)),
    ("F", "Shell joint", ("FBH", "FBB", "FBS")),
    ("G", "Floor deck", ("FCB",)),
    ("H", "Seat box", ("SBH", "SBS", "STB")),
    ("I", "Seat supports", ("SBB",)),
    ("J", "Seat box supports", ("SBB", "SBF")),
    ("K", "Seat front cladding", ("SFB",)),
]


def fmt(value: float) -> str:
    """A drawing-set number: no trailing zeros, thousands spaced as `1 315.1`."""
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    whole, dot, fraction = text.partition(".")
    sign, whole = ("-", whole[1:]) if whole.startswith("-") else ("", whole)
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return sign + " ".join(groups) + dot + fraction


def brace_angle(design: Design, piece: CutPiece) -> float | None:
    if piece.name in {"left_brace", "right_brace"}:
        run = design.inner_depth
        rise = design.front_post_height - design.leg_extension - 2 * design.frame
    elif piece.name in {"back_brace", "door_brace"}:
        run = design.inner_width
        rise = design.door_frame_height - 2 * design.frame
    else:
        return None
    axis = math.degrees(math.atan2(rise, run)) + math.degrees(
        math.asin(design.frame / math.hypot(run, rise))
    )
    return 90 - axis


def stock_bar(
    stock_id: str,
    pieces: list[CutPiece],
    stock_length: float,
    kerf: float,
    stock_width: float,
) -> str:
    position = 0.0
    segments: list[str] = []
    for piece in pieces:
        left = position / stock_length * 100
        width = piece.length / stock_length * 100
        gang_class = " is-gang" if piece.gang_cut else ""
        segments.append(
            f'<div class="stock-piece{gang_class}" style="left:{left:.5f}%;width:{width:.5f}%" '
            f'title="{html.escape(piece.code)} · {fmt(piece.length)} mm">'
            f"<b>{html.escape(piece.code)}</b><span>{fmt(piece.length)} mm</span></div>"
        )
        cut_at = position + piece.length
        segments.append(
            f'<i class="saw-tick" style="left:{cut_at / stock_length * 100:.5f}%" '
            f'aria-hidden="true"></i>'
        )
        position += piece.length + kerf
    waste = stock_length - position
    segments.append(
        f'<div class="stock-waste" style="left:{position / stock_length * 100:.5f}%;'
        f'width:{max(0, waste) / stock_length * 100:.5f}%"><span>{fmt(waste)} mm</span></div>'
    )
    # The offcut reads once, off the hatched block; the stock length reads once,
    # off the right-hand datum. Neither is restated in the header.
    return f"""
    <article class="stock">
      <header>
        <label><input type="checkbox" data-check="{stock_id}"> <b>{stock_id}</b></label>
        <span class="stock-count">{len(pieces)} pieces</span>
      </header>
      <div class="stock-scroll">
        <div class="stock-track" style="--stock-aspect:{stock_length / stock_width:.6f}"
          role="img" aria-label="{stock_id}: {"; ".join(f"{p.code}, {fmt(p.length)} millimetres" for p in pieces)}; {fmt(waste)} millimetre offcut">
          {"".join(segments)}
        </div>
      </div>
    </article>"""


def _ordered_batches(
    groups: dict[tuple[float, float | None], list[CutPiece]],
) -> list[tuple[tuple[float, float | None], list[CutPiece]]]:
    """Longest first, mitred batches before square ones."""
    return sorted(
        groups.items(),
        key=lambda item: (item[0][1] is None, -(item[0][1] or 0), -item[0][0]),
    )


def _batch_groups(
    pieces: list[CutPiece], design: Design, include_gang: bool = True
) -> dict[tuple[float, float | None], list[CutPiece]]:
    groups: dict[tuple[float, float | None], list[CutPiece]] = defaultdict(list)
    for piece in pieces:
        if include_gang or not piece.gang_cut:
            groups[(round(piece.length, 1), brace_angle(design, piece))].append(piece)
    return groups


def cut_batches(
    pieces: list[CutPiece],
    stock_lookup: dict[str, str],
    design: Design,
    include_gang: bool = True,
) -> str:
    groups = _batch_groups(pieces, design, include_gang)
    ordered = _ordered_batches(groups)
    rows = []
    for step, ((length, angle), batch) in enumerate(ordered, 1):
        batch.sort(key=lambda piece: (stock_lookup[piece.code], piece.code))
        cut = (
            f"{angle:.1f}° mitre, both ends; cuts parallel"
            if angle is not None
            else "90° square"
        )
        # Which stock each code comes off is drawn on the stock bars below, so
        # the batch table carries the saw sequence and nothing else.
        rows.append(
            f'<tr><td class="pass">{step}</td>'
            f'<td class="measure">{fmt(length)} mm</td><td>{cut}</td>'
            f'<td class="marks">{len(batch)} × '
            f"{' '.join(f'<b>{p.code}</b>' for p in batch)}</td></tr>"
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# Plate drawing
#
# Every diagram below is projected straight off the CAD solids or off the same
# cut pieces the tables are built from. No plate carries a hand-placed
# coordinate, so a member cannot sit wrongly in a drawing without also sitting
# wrongly in the model.
# ---------------------------------------------------------------------------

Point = tuple[float, float]


@dataclass(frozen=True)
class View:
    """Orthographic map from model millimetres onto plate space (u right, v down)."""

    u_axis: int
    u_sign: float
    v_axis: int
    v_sign: float
    caption: str
    short: str

    @property
    def depth_axis(self) -> int:
        return ({0, 1, 2} - {self.u_axis, self.v_axis}).pop()

    # The caller builds its three axis values in a list, so take any sequence.
    # Only the two projected axes are ever read.
    def __call__(self, point: Sequence[float]) -> Point:
        return (self.u_sign * point[self.u_axis], self.v_sign * point[self.v_axis])


@dataclass(frozen=True)
class AxonometricView:
    """Orthographic isometric view used for assembly callouts."""

    u_basis: tuple[float, float, float]
    v_basis: tuple[float, float, float]
    caption: str
    short: str

    def __call__(self, point: Sequence[float]) -> Point:
        return (
            sum(axis * value for axis, value in zip(self.u_basis, point)),
            sum(axis * value for axis, value in zip(self.v_basis, point)),
        )


PLAN = View(0, 1, 1, -1, "front edge at the bottom", "plan")
FRONT = View(0, 1, 2, -1, "seen from outside the door", "front elevation")
REAR = View(0, -1, 2, -1, "seen from outside the back wall", "rear elevation")
LEFT = View(1, -1, 2, -1, "front edge to the right", "left elevation")
RIGHT = View(1, 1, 2, -1, "front edge to the left", "right elevation")
AXO_RIGHT = AxonometricView(
    (math.sqrt(0.5), math.sqrt(0.5), 0),
    (1 / math.sqrt(6), -1 / math.sqrt(6), -math.sqrt(2 / 3)),
    "isometric view from the right front corner",
    "right-front isometric",
)
AXO_LEFT = AxonometricView(
    (math.sqrt(0.5), -math.sqrt(0.5), 0),
    (-1 / math.sqrt(6), -1 / math.sqrt(6), -math.sqrt(2 / 3)),
    "isometric view from the left front corner",
    "left-front isometric",
)


def convex_hull(points: list[Point]) -> list[Point]:
    ordered = sorted({(round(u, 3), round(v, 3)) for u, v in points})
    if len(ordered) < 3:
        return ordered

    def turn(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(source: list[Point]) -> list[Point]:
        stack: list[Point] = []
        for point in source:
            while len(stack) > 1 and turn(stack[-2], stack[-1], point) <= 0:
                stack.pop()
            stack.append(point)
        return stack[:-1]

    return half(ordered) + half(ordered[::-1])


def outline(solid: cq.Shape, view: View) -> list[Point]:
    """Exact projected profile of one part.

    Almost every part is a prism square to the plate, so its own largest face
    gives the profile in order — including the notch in a side field, which a
    convex hull would quietly fill in. Anything tilted out of the plate, such
    as a roof member seen in plan, falls back to its projected hull.
    """
    square_faces = [
        face
        for face in solid.Faces()
        if abs(face.normalAt().toTuple()[view.depth_axis]) > 0.999
    ]
    if square_faces:
        profile = max(square_faces, key=lambda face: face.Area())
        points = [view(vertex.toTuple()) for vertex in profile.outerWire().Vertices()]
        if len(points) > 2:
            return points
    return convex_hull([view(vertex.toTuple()) for vertex in solid.Vertices()])


def projected_outline(solid: cq.Shape, view: AxonometricView) -> list[Point]:
    """Return the projected outer face, preserving notches in side panels."""
    planar_faces = [
        face for face in solid.Faces() if len(face.outerWire().Vertices()) > 2
    ]
    if planar_faces:
        face = max(planar_faces, key=lambda candidate: candidate.Area())
        points = [view(vertex.toTuple()) for vertex in face.outerWire().Vertices()]
        if len(points) > 2:
            return points
    return convex_hull([view(vertex.toTuple()) for vertex in solid.Vertices()])


def projected_face_at(
    solid: cq.Shape, view: AxonometricView, axis: int, coordinate: float
) -> list[Point]:
    """Project the largest planar face on one named model plane."""
    faces = []
    for face in solid.Faces():
        vertices = face.outerWire().Vertices()
        if len(vertices) < 3:
            continue
        if all(abs(vertex.toTuple()[axis] - coordinate) < 1e-6 for vertex in vertices):
            faces.append(face)
    if faces:
        face = max(faces, key=lambda candidate: candidate.Area())
        return [view(vertex.toTuple()) for vertex in face.outerWire().Vertices()]
    return projected_outline(solid, view)


def projected_edges(
    solid: cq.Shape, view: AxonometricView
) -> list[tuple[Point, Point]]:
    """Return the straight CAD edges projected into a corner view."""
    edges: list[tuple[Point, Point]] = []
    seen: set[tuple[Point, Point]] = set()
    for edge in solid.Edges():
        vertices = edge.Vertices()
        if len(vertices) < 2:
            continue
        start = view(vertices[0].toTuple())
        end = view(vertices[-1].toTuple())
        key: tuple[Point, Point] = (start, end) if start <= end else (end, start)
        if key in seen or math.dist(start, end) < 1e-6:
            continue
        seen.add(key)
        edges.append((start, end))
    return edges


def cross_section(
    solid: cq.Shape, view: View, cut: float, slab: float = 0.4
) -> list[Point]:
    """Profile where a cutting plane square to the plate crosses one part."""
    box = solid.BoundingBox()
    lows = [box.xmin - 1, box.ymin - 1, box.zmin - 1]
    sizes = [box.xlen + 2, box.ylen + 2, box.zlen + 2]
    axis = view.depth_axis
    if not lows[axis] < cut < lows[axis] + sizes[axis]:
        return []
    lows[axis], sizes[axis] = cut - slab / 2, slab
    sliced = solid.intersect(box_at(*lows, *sizes))
    points = [view(vertex.toTuple()) for vertex in sliced.Vertices()]
    return convex_hull(points) if len(points) > 2 else []


class Plate:
    """An SVG drawing surface working in plate millimetres.

    Plates are emitted at one fixed user-unit width so that a code mark or a
    dimension reads at the same size on every drawing in the document, whatever
    the part actually measures.
    """

    WIDTH = 1000.0

    def __init__(
        self, shapes: list[list[Point]], margin: float = 62.0, pad: float = 0.0
    ) -> None:
        points = [point for shape in shapes for point in shape]
        self.umin = min(u for u, _ in points)
        self.vmin = min(v for _, v in points)
        self.umax = max(u for u, _ in points)
        self.vmax = max(v for _, v in points)
        u_span = self.umax - self.umin
        v_span = self.vmax - self.vmin
        self.margin = margin
        self.scale = (self.WIDTH - 2 * margin) / u_span
        self.height = v_span * self.scale + 2 * margin + pad
        self.body: list[str] = []

    def x(self, u: float) -> float:
        return self.margin + (u - self.umin) * self.scale

    def y(self, v: float) -> float:
        return self.margin + (v - self.vmin) * self.scale

    def at(self, point: Point) -> Point:
        return (self.x(point[0]), self.y(point[1]))

    def add(self, markup: str) -> None:
        self.body.append(markup)

    def shape(self, points: list[Point], css: str) -> None:
        if len(points) < 3:
            return
        path = " ".join(
            f"{'M' if index == 0 else 'L'}{self.x(u):.1f} {self.y(v):.1f}"
            for index, (u, v) in enumerate(points)
        )
        self.add(f'<path class="{css}" d="{path} Z"/>')

    def line(self, a: Point, b: Point, css: str) -> None:
        self.add(
            f'<line class="{css}" x1="{self.x(a[0]):.1f}" y1="{self.y(a[1]):.1f}" '
            f'x2="{self.x(b[0]):.1f}" y2="{self.y(b[1]):.1f}"/>'
        )

    def wire(self, solid: cq.Shape, view: AxonometricView, css: str) -> None:
        for start, end in projected_edges(solid, view):
            self.line(start, end, css)

    def linear_dim(self, a: Point, b: Point, offset: float, text: str) -> None:
        """Draw a dimension parallel to an arbitrary projected model edge."""
        start = self.at(a)
        end = self.at(b)
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        normal = (-dy / length, dx / length)
        shift = (normal[0] * offset * self.scale, normal[1] * offset * self.scale)
        shifted_start = (start[0] + shift[0], start[1] + shift[1])
        shifted_end = (end[0] + shift[0], end[1] + shift[1])
        self.add(
            f'<path class="dim" d="M{start[0]:.1f} {start[1]:.1f} '
            f"L{shifted_start[0]:.1f} {shifted_start[1]:.1f} "
            f"M{end[0]:.1f} {end[1]:.1f} "
            f"L{shifted_end[0]:.1f} {shifted_end[1]:.1f} "
            f"M{shifted_start[0]:.1f} {shifted_start[1]:.1f} "
            f'L{shifted_end[0]:.1f} {shifted_end[1]:.1f}"/>'
        )
        tick = 5.0
        for point in (shifted_start, shifted_end):
            self.add(
                f'<path class="dim-tick" d="M{point[0] - normal[0] * tick:.1f} '
                f"{point[1] - normal[1] * tick:.1f} "
                f"L{point[0] + normal[0] * tick:.1f} "
                f'{point[1] + normal[1] * tick:.1f}"/>'
            )
        angle = math.degrees(math.atan2(dy, dx))
        while angle > 90:
            angle -= 180
        while angle <= -90:
            angle += 180
        middle = (
            (shifted_start[0] + shifted_end[0]) / 2 + normal[0] * 14,
            (shifted_start[1] + shifted_end[1]) / 2 + normal[1] * 14,
        )
        self.add(
            f'<text class="dim-text" x="{middle[0]:.1f}" y="{middle[1]:.1f}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'transform="rotate({angle:.1f} {middle[0]:.1f} {middle[1]:.1f})">'
            f"{html.escape(text)}</text>"
        )

    def loop(self, points: list[Point], css: str) -> None:
        if len(points) < 2:
            return
        projected = " ".join(f"{self.x(u):.1f},{self.y(v):.1f}" for u, v in points)
        self.add(f'<polyline class="{css}" points="{projected}"/>')

    def circle(self, point: Point, radius: float, css: str) -> None:
        x, y = self.at(point)
        self.add(
            f'<circle class="{css}" cx="{x:.1f}" cy="{y:.1f}" '
            f'r="{radius * self.scale:.1f}"/>'
        )

    def group(self, start: int, css: str) -> None:
        """Wrap the markup added since ``start`` in a visibility layer."""
        contents = "".join(self.body[start:])
        del self.body[start:]
        self.add(f'<g class="{css}">{contents}</g>')

    def screw(self, point: Point, outward: Point, line: bool = True) -> None:
        """Draw a screw head and, when visible in projection, its driven stem."""
        head = point
        if line:
            stem = (point[0] + outward[0], point[1] + outward[1])
            if math.dist(point, stem) > 1e-6:
                self.line(point, stem, "screw-stem")
                head = stem
        self.circle(head, 4.0, "screw-head")
        self.circle(head, 1.25, "screw-recess")

    def screw_path(self, start: Point, end: Point) -> None:
        """Draw a measured screw path with its sunk head at the source side."""
        self.line(start, end, "screw-stem")
        self.circle(start, 4.0, "screw-head")
        self.circle(start, 1.25, "screw-recess")

    def label(
        self,
        point: Point,
        text: str,
        css: str = "mark",
        turned: bool = False,
        anchor: str = "middle",
        angle: float | None = None,
        middle: bool = False,
    ) -> None:
        x, y = self.at(point)
        rotation = -90 if turned else 0 if angle is None else angle
        turn = (
            f' transform="rotate({rotation:.1f} {x:.1f} {y:.1f})"'
            if abs(rotation) > 1e-6
            else ""
        )
        baseline = ' dominant-baseline="middle"' if middle else ""
        self.add(
            f'<text class="{css}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"'
            f"{turn}{baseline}>{html.escape(text)}</text>"
        )

    def corner(self, text: str) -> None:
        """Note in the lower margin, clear of the drawing and dimensions."""
        self.add(
            f'<text class="note-text" x="14" y="{self.height - 52:.1f}" '
            f'text-anchor="start">'
            f"{html.escape(text)}</text>"
        )

    def leader(
        self, target: Point, seat: Point, text: str, anchor: str = "start"
    ) -> None:
        """Call out a face or a thickness without crowding the geometry."""
        tx, ty = self.at(target)
        sx, sy = self.at(seat)
        self.add(f'<path class="leader" d="M{tx:.1f} {ty:.1f} L{sx:.1f} {sy:.1f}"/>')
        self.add(f'<circle class="leader-dot" cx="{tx:.1f}" cy="{ty:.1f}" r="4"/>')
        self.add(
            f'<text class="small" x="{sx + (9 if anchor == "start" else -9):.1f}" '
            f'y="{sy + 6:.1f}" text-anchor="{anchor}">{html.escape(text)}</text>'
        )

    def code_in(self, points: list[Point], text: str) -> None:
        """Stamp a centred code mark aligned with the member's long axis.

        Codes are red and underlined, as the reference set letters them.
        """
        if len(points) < 2 or not text:
            return
        us = [u for u, _ in points]
        vs = [v for _, v in points]
        if max(max(us) - min(us), max(vs) - min(vs)) * self.scale < 42:
            return
        middle = ((min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2)
        longest = max(
            (
                (point, points[(index + 1) % len(points)])
                for index, point in enumerate(points)
            ),
            key=lambda pair: math.dist(pair[0], pair[1]),
        )
        angle = math.degrees(
            math.atan2(longest[1][1] - longest[0][1], longest[1][0] - longest[0][0])
        )
        while angle > 90:
            angle -= 180
        while angle <= -90:
            angle += 180
        self.label(middle, text, "mark", angle=angle, middle=True)

    TICK = 4.0

    def dim(self, a: Point, b: Point, offset: float, text: str | None = None) -> None:
        """Dimension between two plate points; the value is measured, not typed.

        Drawn the way the reference set draws it: hairline extension lines, a
        run between them closed by 45° architect's ticks, and the value clear of
        the line rather than sitting on it.
        """
        measure = text if text is not None else fmt(math.dist(a, b))
        vertical = abs(a[0] - b[0]) < abs(a[1] - b[1])
        tick = self.TICK
        x1, y1 = self.at(a)
        x2, y2 = self.at(b)
        if vertical:
            side = 1 if offset >= 0 else -1
            x = self.WIDTH - 18 if side > 0 else 18
            self.add(
                f'<path class="dim" d="M{x1:.1f} {y1:.1f} H{x:.1f} M{x2:.1f} {y2:.1f} H{x:.1f} '
                f'M{x:.1f} {y1:.1f} V{y2:.1f}"/>'
            )
            for y in (y1, y2):
                self.add(
                    f'<path class="dim-tick" d="M{x - tick:.1f} {y - tick:.1f} '
                    f'L{x + tick:.1f} {y + tick:.1f}"/>'
                )
            if measure:
                mid = (y1 + y2) / 2
                text_x = x - 8 if side > 0 else x + 8
                self.add(
                    f'<text class="dim-text" x="{text_x:.1f}" y="{mid:.1f}" '
                    f'text-anchor="middle" transform="rotate(-90 {text_x:.1f} {mid:.1f})">'
                    f"{html.escape(measure)}</text>"
                )
        else:
            side = 1 if offset >= 0 else -1
            y = self.height - 18 if side > 0 else 18
            self.add(
                f'<path class="dim" d="M{x1:.1f} {y1:.1f} V{y:.1f} M{x2:.1f} {y2:.1f} V{y:.1f} '
                f'M{x1:.1f} {y:.1f} H{x2:.1f}"/>'
            )
            for x in (x1, x2):
                self.add(
                    f'<path class="dim-tick" d="M{x - tick:.1f} {y + tick:.1f} '
                    f'L{x + tick:.1f} {y - tick:.1f}"/>'
                )
            if measure:
                text_y = y - 9 if side > 0 else y + 17
                self.add(
                    f'<text class="dim-text" x="{(x1 + x2) / 2:.1f}" y="{text_y:.1f}" '
                    f'text-anchor="middle">{html.escape(measure)}</text>'
                )

    def svg(
        self,
        number: str,
        title: str,
        caption: str,
        css: str = "plate",
        note: str = "",
    ) -> str:
        """One numbered drawing, captioned beneath the way a set captions them."""
        aside = f'<span class="drawing-note">{html.escape(note)}</span>' if note else ""
        return (
            f'<figure class="drawing">'
            f"{self.element(css, title, caption)}"
            f"<figcaption>"
            f'<span class="drawing-name">{html.escape(title.upper())}</span>'
            f'<span class="drawing-ref">{html.escape(number)} · '
            f"{html.escape(caption.upper())}</span>{aside}"
            f"</figcaption>"
            f"</figure>"
        )

    def element(self, css: str, title: str, caption: str) -> str:
        """Return the SVG element without its figure wrapper."""
        return (
            f'<svg class="{css}" viewBox="0 0 {self.WIDTH:.0f} {self.height:.0f}" '
            f'role="img" aria-label="{html.escape(title)}: {html.escape(caption)}">'
            f"{''.join(self.body)}"
            f"</svg>"
        )


@dataclass(frozen=True)
class Panel:
    """One joined cladding field and the boards it is actually built from."""

    key: str
    prefix: str
    title: str
    axis: int
    pieces: tuple[CutPiece, ...]
    note: str = ""

    @property
    def count(self) -> int:
        return len(self.pieces)

    @property
    def trim(self) -> float:
        return self.pieces[0].panel_end_trim or 0.0

    @property
    def joined(self) -> float:
        """Width straight off the bench, before the terminal edge is trimmed."""
        return self.count * COVER_WIDTH + BOARD_WIDTH - COVER_WIDTH

    @property
    def span(self) -> float:
        return self.joined - self.trim

    @property
    def blank(self) -> float:
        return self.pieces[0].length

    @property
    def codes(self) -> str:
        return f"{self.pieces[0].code}–{self.pieces[-1].code}"


@dataclass(frozen=True)
class CladdingScrewMark:
    """One cladding fixing located on its finished board and support beam."""

    board_code: str
    row_member: str
    point: tuple[float, float, float]
    frame_clearance: float


@dataclass(frozen=True)
class CladdingScrewRow:
    """One adjusted fixing row and its collision-checked board marks."""

    member_name: str
    station: float
    marks: tuple[CladdingScrewMark, ...]


def cladding_board_spans(panel: Panel, start: float = 0.0) -> list[tuple[float, float]]:
    """Return the actual material span of each board after the field trim."""
    field_end = start + panel.span
    return [
        (
            start + index * COVER_WIDTH,
            min(start + index * COVER_WIDTH + BOARD_WIDTH, field_end),
        )
        for index in range(panel.count)
    ]


def cladding_board_centres(panel: Panel, start: float = 0.0) -> list[float]:
    """Return centres of the finished board material, including the end trim."""
    return [(low + high) / 2 for low, high in cladding_board_spans(panel, start)]


PANEL_SPECS = (
    (
        "door_panel",
        "DCB",
        "Door field",
        0,
        "fixed to the inside face of the door frame",
    ),
    (
        "left_wall",
        "LSC",
        "Left side field",
        1,
        "gang-cut to the roof pitch after joining",
    ),
    (
        "right_wall",
        "RSC",
        "Right side field",
        1,
        "gang-cut to the roof pitch after joining",
    ),
    ("back_wall", "BWC", "Back wall field", 0, "centred between the rear posts"),
    ("floor", "FCB", "Floor deck", 0, "lands on three bearers and the front rail"),
    (
        "seat_top",
        "STB",
        "Seat top",
        1,
        "boards run across the box; oval opening cut after joining",
    ),
    (
        "seat_front",
        "SFB",
        "Seat front field",
        0,
        "closes the seat box down to the floor",
    ),
)


def panels(boards: list[CutPiece]) -> dict[str, Panel]:
    grouped: dict[str, list[CutPiece]] = defaultdict(list)
    for piece in boards:
        grouped[piece.code.rstrip("0123456789")].append(piece)
    return {
        key: Panel(key, prefix, title, axis, tuple(grouped[prefix]), note)
        for key, prefix, title, axis, note in PANEL_SPECS
    }


def board_joints(panel: Panel) -> list[float]:
    """Board joint positions across a joined field, measured from board one."""
    return [index * COVER_WIDTH for index in range(1, panel.count)]


# ---------------------------------------------------------------------------
# Reference views: photoreal renders, static drawing renders, and the model
# ---------------------------------------------------------------------------

DRAWING_RENDERS = (
    (
        "drawing-open",
        "Open",
        "Isometric SVG at the same angle as the model viewer.",
    ),
    (
        "drawing-closed",
        "Closed",
        "The finished unit rendered with the drawing-set palette.",
    ),
)
SVG_RENDERS = frozenset(name for name, _, _ in DRAWING_RENDERS)


def render_asset(name: str) -> str:
    """Return the staged gallery path, preserving vector drawing renders."""
    extension = "svg" if name in SVG_RENDERS else "jpg"
    return f"web-renders/{name}.{extension}"


GALLERY = (
    (
        "In situ",
        (
            ("in-situ-open", "Open", ""),
            ("in-situ-closed", "Closed", "The same plate with everything shut."),
        ),
    ),
    (
        "Render",
        (
            (
                "open-hero",
                "Open",
                "Three-quarter view, door swung clear of the opening.",
            ),
            (
                "open-doorway",
                "Doorway",
                "Straight into the opening at standing height.",
            ),
            (
                "open-interior",
                "Interior",
                "Down onto the seat box, floor deck, and back wall.",
            ),
            ("closed-hero", "Closed", "Three-quarter view of the finished shell."),
            (
                "closed-rear-quarter",
                "Rear",
                "Back wall, rear posts, and the roof overhang.",
            ),
            ("closed-above", "Above", "The mono-pitch roof and its sheet overhangs."),
        ),
    ),
    ("Drawing render", DRAWING_RENDERS),
    (
        "Elevation",
        (
            ("flat-front", "Front", "Square-on front elevation, door closed."),
            (
                "flat-front-open",
                "Front open",
                "Square-on with the door swung, showing the opening.",
            ),
            ("flat-back", "Back", "Square-on rear elevation."),
            (
                "flat-left",
                "Left",
                "Square-on left side; the cladding falls to the rear.",
            ),
            ("flat-right", "Right", "Square-on right side, mirror of the left."),
            ("flat-top", "Top", "Orthographic plan of the roof sheet."),
        ),
    ),
)

FIRST_VIEW = GALLERY[0][1][0][0]

PROGRESS_GALLERY = (
    (
        "saw-setup-for-beam-cuts.jpg",
        "saw setup for beam cuts.jpg",
        "Saw setup for beam cuts",
        "Set the stop before the first beam batch. The 45 × 45 stock stays on one setting while the blanks are cut to length.",
    ),
    (
        "beam-cuts.jpg",
        "beam cuts.jpg",
        "Beam cuts",
        "Mark each piece as it leaves the saw. The cut parts are now ready to move into their lettered unit stacks.",
    ),
    (
        "sorted-beam-cuts.jpg",
        "sorted beam cuts.jpg",
        "Sorted beam cuts",
        "The cut beams are grouped by mark before they move into their assembly stacks.",
    ),
    (
        "assembling-frames.jpg",
        "assembling frames.jpg",
        "Assembling frames",
        "A clamp holds a frame joint square while the next frame is assembled.",
    ),
    (
        "side-panel.jpg",
        "IMG_8589.jpeg",
        "Side panel assembled",
        "A braced side panel, marked and ready to join to the rest of the shell.",
    ),
    (
        "assembling-side.jpg",
        "assembling side.jpeg",
        "Assembling the side",
        "The side frame and cladding come together around the diagonal brace.",
    ),
    (
        "sides.jpg",
        "sides.jpeg",
        "Sides standing",
        "Both side panels are standing while the floor frame is prepared below them.",
    ),
    (
        "sides-and-floor.jpg",
        "sides and floor.jpeg",
        "Sides and floor",
        "The side panels meet the floor frame and the shell starts to read as one unit.",
    ),
    (
        "assembled-no-roof.jpg",
        "assembled-no-roof.jpeg",
        "Shell assembled",
        "Sides, back, floor, and seat are joined and standing on site, with the roof still to go on.",
    ),
    (
        "closed-roof-unattached.jpg",
        "closed-roof-unattached.jpeg",
        "Roof sheets laid on",
        "The door is hung and the corrugated sheets rest on the rafters, weighted down until they are fixed.",
    ),
    (
        "assembled-no-roof-occupied.jpg",
        "assembled-no-roof-occupied.jpeg",
        "Seat test",
        "The first sit-down proves the seat height and the depth of the shell against the drawing.",
    ),
)

PROGRESS_VIDEO = (
    "cutting.mp4",
    "cutting-poster.jpg",
    "Cutting the cladding batch",
    "A field recording from the first cladding-cutting session.",
)

STARTED_GALLERY = (
    (
        "original-side-drawing.jpg",
        "docs/original-drawing/drawing-sides.png",
        "Original side drawing",
        2618,
        818,
    ),
    (
        "validation-open.jpg",
        "docs/verification/evolution/validation-open-final_20260730T101806Z.png",
        "Early open-model validation",
        1800,
        1200,
    ),
    (
        "seat-section-comparison.jpg",
        "docs/verification/evolution/overlay-seat-section.png",
        "Seat-section comparison",
        720,
        975,
    ),
    (
        "door-front-comparison.jpg",
        "docs/verification/evolution/overlay-door-front.png",
        "Door-front comparison",
        735,
        960,
    ),
)


def story_arrow(direction: str) -> str:
    paths = {
        "down": "M12 3v17m0 0 6-6m-6 6-6-6",
        "up": "M12 21V4m0 0 6 6m-6-6-6 6",
        "left": "M21 12H4m0 0 6 6m-6-6 6-6",
        "right": "M3 12h17m0 0-6-6m6 6-6 6",
    }
    return (
        f'<svg class="story-arrow" viewBox="0 0 24 24" aria-hidden="true">'
        f'<path d="{paths[direction]}"/></svg>'
    )


def story_nav(active: str) -> str:
    started_current = ' aria-current="page"' if active == "started" else ""
    drawing_current = ' aria-current="page"' if active == "drawing" else ""
    going_current = ' aria-current="page"' if active == "going" else ""
    started_href = (
        "#story-nav" if active == "started" else "how-it-started.html#story-nav"
    )
    drawing_href = "#story-nav" if active == "drawing" else "cut-guide.html#story-nav"
    going_href = "#story-nav" if active == "going" else "how-its-going.html#story-nav"
    started_direction = "down" if active == "started" else "left"
    drawing_direction = "down" if active == "drawing" else "up"
    going_direction = "down" if active == "going" else "right"
    return f"""
    <nav class="story-nav" id="story-nav" aria-label="Project story">
      <a class="story-link story-link-start" href="{started_href}"{started_current}>
        {story_arrow(started_direction)}
        <span class="story-link-copy"><b>How it started</b><small>Original design</small></span>
      </a>
      <a class="story-link story-link-drawing" href="{drawing_href}"{drawing_current}>
        <span class="story-link-copy"><b>Working drawing</b><small>Cut and assemble</small></span>
        {story_arrow(drawing_direction)}
      </a>
      <a class="story-link story-link-going" href="{going_href}"{going_current}>
        <span class="story-link-copy"><b>How it's going</b><small>Real-world progress</small></span>
        {story_arrow(going_direction)}
      </a>
    </nav>"""


def gallery_html() -> str:
    groups = "".join(
        '<span class="pill-group"><i>{}</i>{}</span>'.format(
            html.escape(group),
            "".join(
                f'<button class="pill{" is-on" if name == FIRST_VIEW else ""}" type="button" '
                f'data-view="{name}" aria-pressed="{"true" if name == FIRST_VIEW else "false"}">'
                f"{html.escape(label)}</button>"
                for name, label, _ in views
            ),
        )
        for group, views in GALLERY
    )
    # The in-situ composites are portrait plates; they fill the square frame and
    # crop rather than sitting letterboxed inside it.
    shots = "".join(
        f'<img class="shot{" is-on" if name == FIRST_VIEW else ""}'
        f'{" is-crop" if group == "In situ" else ""}" data-view="{name}" '
        f'{"src" if name == FIRST_VIEW else "data-src"}="{render_asset(name)}" '
        f'alt="{html.escape(caption)}" data-caption="{html.escape(caption)}" decoding="async">'
        for group, views in GALLERY
        for name, _, caption in views
    )
    first_caption = GALLERY[0][1][0][2]
    return f"""
      <figure class="gallery">
        <div class="view-frame">{shots}</div>
        <div class="view-controls" role="group" aria-label="Choose a view">{groups}</div>
        <figcaption class="gallery-caption">{html.escape(first_caption)}</figcaption>
      </figure>"""


def viewer_parts(design: Design, boards: list[CutPiece]) -> dict[str, dict[str, str]]:
    """Everything the model viewer shows when a piece is picked."""
    _, part_list = build(design)
    fields = {panel.key: panel for panel in panels(boards).values()}
    data: dict[str, dict[str, str]] = {}
    for part in part_list:
        panel = fields.get(part.name)
        if panel:
            code = panel.codes
            size = f"{fmt(panel.span)} × {fmt(panel.blank)} × {fmt(part.thickness)}"
            detail = f"{panel.count} joined boards"
        else:
            code = BEAM_CODES.get(part.name, "")
            size = f"{fmt(part.length)} × {fmt(part.width)} × {fmt(part.thickness)}"
            detail = "blank length × section" if code else "bought in"
        if part.material == "metal roof":
            tone = "roof"
        elif part.material == "metal":
            tone = "metal"
        elif part.material == "dark wood":
            tone = "deck"
        else:
            tone = "field" if panel else "frame"
        data[part.name] = {
            "name": PART_NAMES.get(part.name, part.name.replace("_", " ")),
            "code": code,
            "size": size,
            "detail": detail,
            "category": part.category,
            # The shared timber pipeline picks a role off `material`; without it
            # the roof sheet and the hinges would all be dressed as wood.
            "material": part.material or "wood",
            "tone": tone,
        }
    return data


def viewer_html() -> str:
    return """
      <figure class="viewer">
        <div class="view-frame viewer-frame">
          <img class="drawing-render" src="web-renders/drawing-open.svg"
          alt="The finished building rendered in the drawing-set palette">
          <canvas class="viewer-canvas" tabindex="0"
          aria-label="Interactive model of the finished building. Use arrow keys to rotate."></canvas>
          <div class="viewer-tip" hidden></div>
          <p class="viewer-status">Loading the model…</p>
        </div>
        <div class="view-controls" role="group" aria-label="Model controls">
          <span class="pill-group"><i>Model</i>
            <button class="pill is-on" type="button" data-variant="open" aria-pressed="true">Open</button>
            <button class="pill" type="button" data-variant="closed" aria-pressed="false">Closed</button>
          </span>
          <span class="pill-group"><i>Finish</i>
            <button class="pill is-on" type="button" data-finish="line" aria-pressed="true">Line</button>
            <button class="pill" type="button" data-finish="textured" aria-pressed="false">Textured</button>
          </span>
        </div>
        <figcaption><span class="on-screen">Interactive line model. Drag to rotate, scroll or pinch to zoom,
        and click a piece to identify it.</span><span class="on-paper">The finished building.</span></figcaption>
      </figure>"""


GALLERY_SCRIPT = """
  document.querySelectorAll(".gallery").forEach((gallery) => {
    const shots = [...gallery.querySelectorAll(".shot")];
    const pills = [...gallery.querySelectorAll(".pill")];
    const caption = gallery.querySelector(".gallery-caption");
    pills.forEach((pill) => pill.addEventListener("click", () => {
      pills.forEach((other) => {
        other.classList.toggle("is-on", other === pill);
        other.setAttribute("aria-pressed", String(other === pill));
      });
      shots.forEach((shot) => {
        const showing = shot.dataset.view === pill.dataset.view;
        if (showing && !shot.getAttribute("src")) shot.src = shot.dataset.src;
        shot.classList.toggle("is-on", showing);
        if (showing) caption.textContent = shot.dataset.caption;
      });
    }));
  });
"""


VIEWER_SCRIPT = """
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
// One timber pipeline, shared with the photoreal renderer.
import {
  dressModel,
  groupByPart,
  loadTexture,
  partKeyFor,
  plankFrame,
} from "./vendor/materials.mjs";

// Every piece the viewer can name, keyed by the node name the CAD export writes.
const PARTS = __PARTS__;
const ATLAS = __ATLAS__;

// The model is drawn, not photographed, until the reader asks for the material.
const SHEET = 0xffffff;
const CODE = 0xbb261a;
const INK = 0x151515;
const SHADE = { frame: 0xffffff, field: 0xf2f2f0, deck: 0xe6e6e6, metal: 0xdededc, roof: 0xe6e6e6 };

const figure = document.querySelector(".viewer");
const frame = figure.querySelector(".viewer-frame");
const canvas = figure.querySelector(".viewer-canvas");
const tip = figure.querySelector(".viewer-tip");
const status = figure.querySelector(".viewer-status");

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
} catch (error) {
  status.textContent = "This browser cannot draw the model; the renders alongside show the same geometry.";
  throw error;
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = false;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = new THREE.Color(SHEET);
// Keep this camera block identical to the in-situ renderer. The interactive
// model is the drawing-set version of the photograph beside it.
const IN_SITU_CAMERA = Object.freeze({
  azimuth: -44,
  cameraHeight: 1300,
  distance: 4200,
  frameWidth: 2500,
  offsetX: 0,
  offsetY: 0,
  anchorX: 643.37172,
  anchorY: 0,
  anchorZ: 26.016753,
});
const IN_SITU_ASPECT = 3 / 4;
const IN_SITU_CROP_FOCUS = __IN_SITU_CROP_FOCUS__;
const horizontalFov = 2 * Math.atan(
  IN_SITU_CAMERA.frameWidth / 2 / IN_SITU_CAMERA.distance,
);
const verticalFov = 2 * Math.atan(Math.tan(horizontalFov / 2) / IN_SITU_ASPECT);
const camera = new THREE.PerspectiveCamera(
  THREE.MathUtils.radToDeg(verticalFov), IN_SITU_ASPECT, 10, 40000,
);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.enablePan = false;
controls.enableRotate = true;
controls.rotateSpeed = 0.8;
controls.minDistance = IN_SITU_CAMERA.distance / 4;
controls.maxDistance = IN_SITU_CAMERA.distance / 0.55;
controls.maxPolarAngle = Math.PI;

function sizeCamera(width, height) {
  // The photograph is rendered as a 3:4 plate, then cropped to this square
  // from the bottom. An off-axis view preserves that exact perspective; tilting
  // the camera to reposition the model would change the verticals.
  const fullHeight = width / IN_SITU_ASPECT;
  const offsetY = Math.max(0, (fullHeight - height) * IN_SITU_CROP_FOCUS);
  camera.setViewOffset(width, fullHeight, 0, offsetY, width, height);
}

// Flat, even light for the drawn finish; the sun only wakes up for the material.
const sky = new THREE.HemisphereLight(0xffffff, 0xd7d7d4, 2.6);
scene.add(sky);
const sun = new THREE.DirectionalLight(0xfff2dc, 0);
sun.position.set(-1600, 2600, 1900);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.bias = -0.0012;
const shadowBox = sun.shadow.camera;
shadowBox.left = shadowBox.bottom = -1600;
shadowBox.right = shadowBox.top = 1600;
shadowBox.near = 100;
shadowBox.far = 6000;
scene.add(sun);
const fill = new THREE.DirectionalLight(0xdfe9ee, 0.35);
fill.position.set(1600, 700, -1500);
scene.add(fill);

// The model stands on its own posts, so it needs a floor to cast onto.
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(9000, 9000),
  new THREE.ShadowMaterial({ opacity: 0 }),
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const edgeInk = new THREE.LineBasicMaterial({ color: INK, linewidth: 1.25 });
const edgeCode = new THREE.LineBasicMaterial({ color: CODE, linewidth: 1.25 });
const plankInk = new THREE.LineBasicMaterial({ color: INK, linewidth: 0.75 });

const lineMaterials = new Map();
function lineMaterialFor(key) {
  if (!lineMaterials.has(key)) {
    const tone = PARTS[key] ? PARTS[key].tone : "frame";
    // Line finish is a drawing, not a shaded render: beams stay white on every
    // face and their EdgesGeometry supplies the black construction outline.
    lineMaterials.set(key, new THREE.MeshBasicMaterial({
      color: SHADE[tone] ?? SHEET,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: 1,
      polygonOffsetUnits: 1,
    }));
  }
  return lineMaterials.get(key);
}

let finish = "line";

// Highlighting has to work in both finishes: the drawn one tints its flat fill
// and turns its outline red, the textured one lifts the piece with emissive.
function paint(key, mode) {
  for (const mesh of meshesFor(key)) {
    const line = mesh.userData.lineMaterial;
    if (line) {
      const tone = PARTS[key] ? PARTS[key].tone : "frame";
      line.color.setHex(
        mode === "select" ? 0xf6dedc : mode === "hover" ? 0xefefed : (SHADE[tone] ?? SHEET),
      );
    }
    if (mesh.userData.edges) {
      mesh.userData.edges.material = mode === "select" ? edgeCode : edgeInk;
    }
    const textured = mesh.userData.texturedMaterial;
    if (textured) {
      textured.emissive.setHex(
        mode === "select" ? 0x4a1109 : mode === "hover" ? 0x201a14 : 0x000000,
      );
    }
  }
}

// The export can write one mesh per box face, named `<part>_1` ... `<part>_6`,
// and some part names end in a digit of their own, so walk the name back.
function keyForObject(object) {
  for (let node = object; node; node = node.parent) {
    if (!node.name) continue;
    const key = partKeyFor(PARTS, node.name);
    if (key) return key;
  }
  return null;
}

function meshesFor(key) {
  const found = [];
  if (current) {
    current.traverse((node) => {
      if (node.isMesh && keyForObject(node) === key) found.push(node);
    });
  }
  return found;
}

const loader = new GLTFLoader();
const variants = new Map();
let current = null;
let framed = false;
let textures = null;
let environment = null;
window.__dassDrawing = {
  THREE,
  scene,
  camera,
  ground,
  get current() { return current; },
};

/**
 * A sky-to-ground gradient, blurred into an environment map.
 *
 * The roof sheet is metal, and a metal with nothing to reflect renders black.
 * This is drawn rather than loaded so the page gains no new asset for it.
 */
function environmentMap() {
  if (environment) return environment;
  const canvas = document.createElement("canvas");
  canvas.width = 16;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  const gradient = context.createLinearGradient(0, 0, 0, canvas.height);
  gradient.addColorStop(0, "#dfe7ee");
  gradient.addColorStop(0.48, "#f6f5f1");
  gradient.addColorStop(0.52, "#b9b3a6");
  gradient.addColorStop(1, "#6f6a5e");
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const sky = new THREE.CanvasTexture(canvas);
  sky.mapping = THREE.EquirectangularReflectionMapping;
  sky.colorSpace = THREE.SRGBColorSpace;
  const pmrem = new THREE.PMREMGenerator(renderer);
  environment = pmrem.fromEquirectangular(sky).texture;
  pmrem.dispose();
  sky.dispose();
  return environment;
}

async function loadTextures() {
  if (textures) return textures;
  status.hidden = false;
  status.textContent = "Loading the material…";
  const anisotropy = renderer.capabilities.getMaxAnisotropy();
  const lap = {
    wrapS: THREE.MirroredRepeatWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
    anisotropy,
  };
  const [map, normalMap, roughnessMap, corrugation, plankMap, plankNormal, plankRoughness] =
    await Promise.all([
      loadTexture("textures/wood-color.jpg", THREE.SRGBColorSpace, { anisotropy }),
      loadTexture("textures/wood-normal.jpg", THREE.NoColorSpace, { anisotropy }),
      loadTexture("textures/wood-roughness.jpg", THREE.NoColorSpace, { anisotropy }),
      loadTexture("textures/corrugation-normal.png", THREE.NoColorSpace, { anisotropy }),
      loadTexture("textures/plank-atlas.jpg", THREE.SRGBColorSpace, lap),
      loadTexture("textures/plank-normal.jpg", THREE.NoColorSpace, lap),
      loadTexture("textures/plank-roughness.jpg", THREE.NoColorSpace, lap),
    ]);
  textures = {
    textures: { map, normalMap, roughnessMap, corrugation },
    plank: { map: plankMap, normalMap: plankNormal, roughnessMap: plankRoughness },
  };
  return textures;
}

async function setFinish(next) {
  finish = next;
  const wanted = next === "textured";
  if (wanted && current && !current.userData.dressed) {
    const loaded = await loadTextures();
    // The roof tells its painted face from its galvanised one by world normal,
    // and the open variant arrives rotated, so the matrices must be current.
    current.updateMatrixWorld(true);
    dressModel(current, {
      parts: PARTS,
      textures: loaded.textures,
      plank: loaded.plank,
      atlas: ATLAS,
    });
    current.traverse((node) => {
      if (node.isMesh && !node.userData.isEdge) node.userData.texturedMaterial = node.material;
    });
    current.userData.dressed = true;
    status.hidden = true;
  }
  lightFinish(wanted);
  applyFinish();
  select(selected);
  draw();
}

// The drawn finish wants flat light and no shadow; the material wants a sun.
function lightFinish(wanted) {
  sky.intensity = wanted ? 1.5 : 2.6;
  sun.intensity = wanted ? 2.4 : 0;
  fill.intensity = wanted ? 0.7 : 0.35;
  ground.material.opacity = wanted ? 0.22 : 0;
  renderer.shadowMap.enabled = wanted;
  scene.environment = wanted ? environmentMap() : null;
}

function applyFinish() {
  if (!current) return;
  const wanted = finish === "textured";
  current.traverse((node) => {
    if (!node.isMesh || node.userData.isEdge) return;
    const material = wanted ? node.userData.texturedMaterial : node.userData.lineMaterial;
    if (material) node.material = material;
    node.castShadow = wanted;
    node.receiveShadow = wanted;
    if (node.userData.edges) node.userData.edges.visible = !wanted;
  });
  current.traverse((node) => {
    if (node.userData.isPlankSeam) node.visible = !wanted;
  });
}

function trianglePlaneSegment(a, b, c, axis, cut) {
  const points = [];
  const vertices = [a, b, c];
  const epsilon = 1e-5;
  for (let i = 0; i < 3; i += 1) {
    const start = vertices[i];
    const end = vertices[(i + 1) % 3];
    const da = start.dot(axis) - cut;
    const db = end.dot(axis) - cut;
    if (Math.abs(da) <= epsilon) points.push(start.clone());
    if (da * db < -epsilon * epsilon) {
      points.push(start.clone().lerp(end, da / (da - db)));
    }
  }
  const unique = points.filter(
    (point, index) => !points.slice(0, index).some((other) => other.distanceToSquared(point) < 1e-8),
  );
  if (unique.length !== 2 || unique[0].distanceToSquared(unique[1]) < 1e-8) return null;
  return unique;
}

/**
 * Draw the 110 mm råspont covers on every boarded CAD panel.
 *
 * CAD keeps a joined field as one solid. These plane intersections add only
 * the board joints, using the same layout data as the textured finish.
 */
function addPlankLines(root) {
  for (const [key, group] of groupByPart(root, PARTS)) {
    if (!group.planked) continue;
    for (const mesh of group.meshes) {
      if (mesh.geometry.index) mesh.geometry = mesh.geometry.toNonIndexed();
    }
    const frame = plankFrame(group, key);
    let acrossMax = -Infinity;
    const point = new THREE.Vector3();
    for (const mesh of group.meshes) {
      const position = mesh.geometry.attributes.position;
      for (let i = 0; i < position.count; i += 1) {
        point.fromBufferAttribute(position, i);
        acrossMax = Math.max(acrossMax, point.dot(frame.across));
      }
    }
    for (
      let cut = frame.origin.across + ATLAS.coverMm;
      cut < acrossMax - 1e-3;
      cut += ATLAS.coverMm
    ) {
      for (const mesh of group.meshes) {
        const positions = [];
        const attribute = mesh.geometry.attributes.position;
        const index = mesh.geometry.index;
        const count = index ? index.count : attribute.count;
        const a = new THREE.Vector3();
        const b = new THREE.Vector3();
        const c = new THREE.Vector3();
        const normal = new THREE.Vector3();
        for (let i = 0; i < count; i += 3) {
          a.fromBufferAttribute(attribute, index ? index.getX(i) : i);
          b.fromBufferAttribute(attribute, index ? index.getX(i + 1) : i + 1);
          c.fromBufferAttribute(attribute, index ? index.getX(i + 2) : i + 2);
          const segment = trianglePlaneSegment(a, b, c, frame.across, cut);
          if (!segment) continue;
          normal.copy(b).sub(a).cross(c.clone().sub(a)).normalize().multiplyScalar(0.2);
          positions.push(segment[0].clone().add(normal), segment[1].clone().add(normal));
        }
        if (!positions.length) continue;
        const geometry = new THREE.BufferGeometry().setFromPoints(positions);
        const seams = new THREE.LineSegments(geometry, plankInk);
        seams.userData.isEdge = true;
        seams.userData.isPlankSeam = true;
        seams.raycast = () => {};
        // Depth sorting in the SVG exporter must be allowed to interleave
        // seams with nearer faces; a forced late render would expose joints
        // through the roof and walls even though WebGL's depth buffer hides
        // them in the live viewer.
        seams.renderOrder = 0;
        mesh.add(seams);
      }
    }
  }
}

async function show(name) {
  if (!variants.has(name)) {
    status.hidden = false;
    status.textContent = "Loading the " + name + " model…";
    const gltf = await loader.loadAsync("renders/dass-" + name + ".glb");
    addPlankLines(gltf.scene);
    gltf.scene.traverse((node) => {
      if (!node.isMesh) return;
      const key = keyForObject(node);
      const material = lineMaterialFor(key ?? "frame");
      node.material = material;
      node.userData.lineMaterial = material;
      // The outline is what makes this read as a drawing rather than a render.
      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(node.geometry, 18), edgeInk,
      );
      edges.userData.isEdge = true;
      edges.raycast = () => {};
      node.add(edges);
      node.userData.edges = edges;
    });
    variants.set(name, gltf.scene);
  }
  if (current) scene.remove(current);
  current = variants.get(name);
  scene.add(current);
  const drawing = figure.querySelector(".drawing-render");
  if (drawing) {
    drawing.src = "web-renders/drawing-" + name + ".svg";
  }
  await setFinish(finish);
  if (!framed) {
    const azimuth = THREE.MathUtils.degToRad(IN_SITU_CAMERA.azimuth);
    const direction = new THREE.Vector3(
      Math.sin(azimuth), 0, Math.cos(azimuth),
    );
    const anchor = new THREE.Vector3(
      IN_SITU_CAMERA.anchorX,
      IN_SITU_CAMERA.anchorY + IN_SITU_CAMERA.cameraHeight,
      IN_SITU_CAMERA.anchorZ,
    );
    camera.position.copy(anchor).addScaledVector(direction, IN_SITU_CAMERA.distance);
    controls.target.copy(anchor);
    sizeCamera(frame.clientWidth, frame.clientHeight);
    camera.lookAt(controls.target);
    framed = true;
  }
  hovered = null;
  select(null);
  status.hidden = true;
  draw();
}

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let hovered = null;
let selected = null;

function pick(event) {
  const box = canvas.getBoundingClientRect();
  pointer.x = ((event.clientX - box.left) / box.width) * 2 - 1;
  pointer.y = -((event.clientY - box.top) / box.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hit = current
    ? raycaster.intersectObject(current, true).find(({ object }) => keyForObject(object))
    : null;
  return hit ? keyForObject(hit.object) : null;
}

function select(key, event) {
  if (selected && selected !== key) paint(selected, "base");
  selected = key;
  if (!key) {
    tip.hidden = true;
    return;
  }
  paint(key, "select");
  const part = PARTS[key];
  tip.textContent = "";
  const code = document.createElement("b");
  code.textContent = part.code || part.category;
  const name = document.createElement("span");
  name.className = "tip-name";
  name.textContent = part.name;
  const size = document.createElement("span");
  size.className = "tip-size";
  size.textContent = part.size + " mm";
  const detail = document.createElement("span");
  detail.textContent = part.detail;
  tip.append(code, name, size, detail);
  tip.hidden = false;
  const box = frame.getBoundingClientRect();
  const x = event ? event.clientX - box.left : box.width / 2;
  const y = event ? event.clientY - box.top : box.height / 2;
  tip.style.left = Math.min(Math.max(10, x + 14), box.width - tip.offsetWidth - 10) + "px";
  tip.style.top = Math.min(Math.max(10, y + 14), box.height - tip.offsetHeight - 10) + "px";
  draw();
}

canvas.addEventListener("pointermove", (event) => {
  const key = pick(event);
  frame.classList.toggle("is-over", Boolean(key));
  if (key === hovered) return;
  if (hovered && hovered !== selected) paint(hovered, "base");
  hovered = key;
  if (hovered && hovered !== selected) paint(hovered, "hover");
  draw();
});

let pressed = null;
canvas.addEventListener("pointerdown", (event) => {
  pressed = [event.clientX, event.clientY];
  frame.classList.add("is-dragging");
});
canvas.addEventListener("pointerup", (event) => {
  frame.classList.remove("is-dragging");
  if (!pressed) return;
  const moved = Math.hypot(event.clientX - pressed[0], event.clientY - pressed[1]);
  pressed = null;
  if (moved > 5) return;
  select(pick(event), event);
});
canvas.addEventListener("pointercancel", () => {
  pressed = null;
  frame.classList.remove("is-dragging");
});

canvas.addEventListener("keydown", (event) => {
  const step = THREE.MathUtils.degToRad(12);
  const rotate = {
    ArrowLeft: () => controls.rotateLeft(step),
    ArrowRight: () => controls.rotateLeft(-step),
    ArrowUp: () => controls.rotateUp(step),
    ArrowDown: () => controls.rotateUp(-step),
  };
  const turn = rotate[event.key];
  if (!turn) return;
  event.preventDefault();
  turn();
  controls.update();
  draw();
});

function wireGroup(attribute, run) {
  const pills = [...figure.querySelectorAll(`.pill[data-${attribute}]`)];
  pills.forEach((pill) => pill.addEventListener("click", () => {
    pills.forEach((other) => {
      other.classList.toggle("is-on", other === pill);
      other.setAttribute("aria-pressed", String(other === pill));
    });
    Promise.resolve(run(pill.dataset[attribute])).catch((error) => {
      status.hidden = false;
      status.textContent = "That finish did not load; the drawn model still works.";
      console.error(error);
    });
  }));
}

wireGroup("variant", show);
wireGroup("finish", setFinish);

let pending = false;
function draw() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => {
    pending = false;
    const width = frame.clientWidth;
    const height = frame.clientHeight;
    if (canvas.width !== width || canvas.height !== height) {
      renderer.setSize(width, height, false);
      sizeCamera(width, height);
    }
    ground.visible = camera.position.y >= ground.position.y;
    if (controls.update()) draw();
    renderer.render(scene, camera);
  });
}

controls.addEventListener("change", draw);
new ResizeObserver(draw).observe(frame);

// Paper takes the drawn model, never the photographs. A live canvas does not
// print dependably, so the sheet carries a still: rendered at print resolution
// and read back in the same tick, while the drawing buffer is still valid. The
// model is always lettered in line here, whatever finish the screen is showing.
//
// The camera crops a square out of its 3:4 plate, so the still is square at a
// fixed size: the frame is already hidden when the print media query is what
// called this, and paper wants more resolution than the screen ever asks for.
const STILL = 1600;
// Built here rather than shipped empty in the markup: without the script there
// is no still to print, and the photograph is the right thing on the sheet. Its
// size is stated up front so the sheet paginates the same whether or not the
// still has decoded yet.
const printShot = document.createElement("img");
printShot.className = "viewer-print";
printShot.alt = "The finished building, drawn in line.";
printShot.width = STILL;
printShot.height = STILL;
frame.after(printShot);

function takePrintStill() {
  if (!current) return;
  const shown = finish;
  if (shown !== "line") {
    finish = "line";
    lightFinish(false);
    applyFinish();
  }
  const ratio = renderer.getPixelRatio();
  try {
    renderer.setPixelRatio(1);
    renderer.setSize(STILL, STILL, false);
    sizeCamera(STILL, STILL);
    renderer.render(scene, camera);
    printShot.src = canvas.toDataURL("image/png");
    printShot.hidden = false;
    document.body.classList.add("has-print-model");
  } catch (error) {
    // Nothing to print from the canvas; the photograph stays on the sheet.
    document.body.classList.remove("has-print-model");
    console.error(error);
  }
  renderer.setPixelRatio(ratio);
  if (frame.clientWidth) {
    renderer.setSize(frame.clientWidth, frame.clientHeight, false);
    sizeCamera(frame.clientWidth, frame.clientHeight);
  }
  if (shown !== "line") {
    finish = shown;
    lightFinish(true);
    applyFinish();
  }
  draw();
}

window.addEventListener("beforeprint", takePrintStill);
// Print preview and headless print-to-PDF switch the media without ever firing
// beforeprint, so the media query is the second way in.
const onPaper = window.matchMedia("print");
onPaper.addEventListener("change", (event) => { if (event.matches) takePrintStill(); });
show("open").catch((error) => {
  status.hidden = false;
  status.textContent = "The model did not load; the renders alongside show the same geometry.";
  console.error(error);
});
"""


DEFAULT_ATLAS = {"cells": 8, "lengthMm": 1200.0, "boardMm": 120.0, "coverMm": 110.0}


def plank_atlas(renders: Path = Path("build/renders")) -> dict:
    """Atlas geometry the board pass needs, taken from the render manifest."""
    manifest = renders / "manifest.json"
    if not manifest.exists():
        return DEFAULT_ATLAS
    plank = json.loads(manifest.read_text()).get("textures", {}).get("plank", {})
    return {key: plank.get(key, value) for key, value in DEFAULT_ATLAS.items()}


def viewer_script(parts: dict[str, dict[str, str]]) -> str:
    return (
        VIEWER_SCRIPT.replace("__PARTS__", json.dumps(parts, separators=(",", ":")))
        .replace("__ATLAS__", json.dumps(plank_atlas(), separators=(",", ":")))
        .replace("__IN_SITU_CROP_FOCUS__", str(IN_SITU_CROP_FOCUS))
    )


def bounds(shape: list[Point]) -> tuple[float, float, float, float]:
    return (
        min(u for u, _ in shape),
        min(v for _, v in shape),
        max(u for u, _ in shape),
        max(v for _, v in shape),
    )


def draw_field(
    plate: Plate,
    profile: list[Point],
    solid: cq.Shape,
    panel: Panel,
    view: View,
    uid: str,
    label: bool = True,
) -> None:
    """Draw fixed cladding with its nominal on-frame trim still attached."""
    if panel.axis not in {view.u_axis, view.v_axis}:
        raise ValueError("the cladding trim must be visible in the unit view")
    plate.shape(profile, "field")
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()
    panel_projected_axis = 0 if panel.axis == view.u_axis else 1
    run_projected_axis = 1 - panel_projected_axis
    panel_sign = view.u_sign if panel_projected_axis == 0 else view.v_sign

    terminal = panel_sign * (lows[panel.axis] + panel.span)
    rough_terminal = panel_sign * (lows[panel.axis] + panel.joined)
    terminal_points = [
        point[run_projected_axis]
        for point in profile
        if math.isclose(point[panel_projected_axis], terminal, abs_tol=1e-3)
    ]
    if len(terminal_points) < 2:
        terminal_points = [point[run_projected_axis] for point in profile]
    trim_low, trim_high = min(terminal_points), max(terminal_points)
    trim_points = [
        (terminal, trim_low),
        (rough_terminal, trim_low),
        (rough_terminal, trim_high),
        (terminal, trim_high),
    ]
    trim = [
        point if panel_projected_axis == 0 else (point[1], point[0])
        for point in trim_points
    ]
    plate.shape(trim, "trim")
    cut_start = trim[0]
    cut_end = trim[3]
    plate.line(cut_start, cut_end, "cut")
    trim_notes = [f"CUT AFTER FIXING · {fmt(panel.trim)} mm TRIM"]

    if panel.pieces[0].gang_cut:
        depth = (lows[view.depth_axis] + highs[view.depth_axis]) / 2

        def projected(across: float, along: float) -> Point:
            point = [0.0, 0.0, 0.0]
            point[panel.axis] = across
            point[run] = along
            point[view.depth_axis] = depth
            return view(tuple(point))

        start = lows[panel.axis]
        finish = start + panel.span
        rough_top = lows[run] + panel.blank
        cut_start = projected(
            start,
            lows[run] + (panel.pieces[0].finished_long or panel.blank),
        )
        cut_end = projected(
            finish,
            lows[run] + (panel.pieces[-1].finished_short or panel.blank),
        )
        rough_end = projected(finish, rough_top)
        plate.shape([cut_start, rough_end, cut_end], "trim")
        plate.line(cut_start, cut_end, "cut")
        trim_notes.append("MARK GANG CUT AFTER FIXING")

    start = len(plate.body)
    for joint in board_joints(panel):
        ends = []
        for far in (False, True):
            point = [0.0, 0.0, 0.0]
            point[panel.axis] = lows[panel.axis] + joint
            point[run] = highs[run] + 20 if far else lows[run] - 20
            point[view.depth_axis] = (
                lows[view.depth_axis] + highs[view.depth_axis]
            ) / 2
            ends.append(view(point))
        plate.line(ends[0], ends[1], "joint")
    joints = "".join(plate.body[start:])
    del plate.body[start:]
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{plate.x(u):.1f} {plate.y(v):.1f}"
        for index, (u, v) in enumerate(profile)
    )
    plate.add(f'<clipPath id="{uid}"><path d="{path} Z"/></clipPath>')
    plate.add(f'<g clip-path="url(#{uid})">{joints}</g>')
    draw_cladding_codes(plate, solid, panel, view)
    plate.corner(" · ".join(trim_notes))


def draw_cladding_codes(
    plate: Plate, solid: cq.Shape, panel: Panel, view: View
) -> None:
    """Place every board code at the centre of its projected material strip."""
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()
    depth = (lows[view.depth_axis] + highs[view.depth_axis]) / 2
    run_start = [0.0, 0.0, 0.0]
    run_end = [0.0, 0.0, 0.0]
    run_start[panel.axis] = run_end[panel.axis] = lows[panel.axis]
    run_start[run] = lows[run]
    run_end[run] = highs[run]
    run_start[view.depth_axis] = run_end[view.depth_axis] = depth
    projected_start = view(run_start)
    projected_end = view(run_end)
    angle = math.degrees(
        math.atan2(
            projected_end[1] - projected_start[1],
            projected_end[0] - projected_start[0],
        )
    )
    while angle > 90:
        angle -= 180
    while angle <= -90:
        angle += 180

    centres = cladding_board_centres(panel, lows[panel.axis])
    for centre, piece in zip(centres, panel.pieces):
        point = [0.0, 0.0, 0.0]
        point[panel.axis] = centre
        point[run] = (lows[run] + highs[run]) / 2
        point[view.depth_axis] = depth
        plate.label(
            view(point),
            piece.code,
            "cladding-code",
            angle=angle,
            middle=True,
        )


def draw_individual_cladding(
    plate: Plate,
    solid: cq.Shape,
    panel: Panel,
    view: View,
) -> None:
    """Draw each joined-board cover as its own measured board outline."""
    if panel.axis != view.u_axis:
        raise ValueError("individual cladding must run across the drawing")
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()
    depth = (lows[view.depth_axis] + highs[view.depth_axis]) / 2
    across_start = lows[panel.axis]
    across_end = across_start + panel.span
    run_start, run_end = lows[run], highs[run]
    for index in range(panel.count):
        start = across_start + index * COVER_WIDTH
        end = min(start + BOARD_WIDTH, across_end)
        if end <= start:
            continue
        corners: list[Point] = []
        for across, along in (
            (start, run_start),
            (end, run_start),
            (end, run_end),
            (start, run_end),
        ):
            point = [0.0, 0.0, 0.0]
            point[panel.axis] = across
            point[run] = along
            point[view.depth_axis] = depth
            corners.append(view(tuple(point)))
        plate.shape(corners, "field")


def plate_for(
    shapes: dict[str, list[Point]],
    members: tuple[str, ...],
    ghosts: tuple[str, ...] = (),
    margin: float = 62.0,
    pad: float = 26.0,
) -> Plate:
    plate = Plate(list(shapes.values()), margin=margin, pad=pad)
    for name in ghosts:
        plate.shape(shapes[name], "ghost")
    return plate


def draw_members(
    plate: Plate, shapes: dict[str, list[Point]], members: tuple[str, ...]
) -> None:
    for name in members:
        plate.shape(shapes[name], "member")
    for name in members:
        plate.code_in(shapes[name], BEAM_CODES.get(name, ""))


def draw_perspective_members(
    plate: Plate,
    shapes: dict[str, list[Point]],
    parts: dict[str, cq.Shape],
    members: tuple[str, ...],
    view: AxonometricView,
) -> None:
    """Draw support beams with their projected square sections and depth edges."""
    for name in members:
        plate.shape(shapes[name], "member")
        plate.wire(parts[name], view, "member-edge")
        plate.code_in(shapes[name], BEAM_CODES.get(name, ""))


def _box_axis(box: object, axis: int) -> tuple[float, float]:
    names = (("xmin", "xmax"), ("ymin", "ymax"), ("zmin", "zmax"))[axis]
    return (getattr(box, names[0]), getattr(box, names[1]))


def _point_add(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _point_scale(
    point: tuple[float, float, float], factor: float
) -> tuple[float, float, float]:
    return (point[0] * factor, point[1] * factor, point[2] * factor)


def _point_sub(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _point_dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _point_unit(point: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(_point_dot(point, point))
    if length < 1e-9:
        raise ValueError("cannot normalise a zero-length point vector")
    return _point_scale(point, 1 / length)


def _box_point_distance(point: tuple[float, float, float], box: object) -> float:
    x_low, x_high = _box_axis(box, 0)
    y_low, y_high = _box_axis(box, 1)
    z_low, z_high = _box_axis(box, 2)
    deltas: tuple[float, float, float] = (
        max(x_low - point[0], 0.0, point[0] - x_high),
        max(y_low - point[1], 0.0, point[1] - y_high),
        max(z_low - point[2], 0.0, point[2] - z_high),
    )
    return math.sqrt(_point_dot(deltas, deltas))


def _face_center(face: cq.Face) -> tuple[float, float, float]:
    x, y, z = face.Center().toTuple()
    return (x, y, z)


def _face_normal(face: cq.Face) -> tuple[float, float, float]:
    x, y, z = face.normalAt().toTuple()
    return (x, y, z)


def _target_entry_face(target: cq.Shape, source: cq.Shape, mark: ScrewMark) -> cq.Face:
    """Find the target face at the actual beam-to-beam contact."""
    faces = target.Faces()
    source_box = source.BoundingBox()
    if mark.target_face in {"slope-front", "slope-rear"}:
        end_area = min(face.Area() for face in faces)
        candidates = [face for face in faces if face.Area() <= end_area * 1.25]
    else:
        axis = {
            "inside-back": 1,
            "inside-side": 0,
            "outside-side": 0,
        }.get(mark.target_face, 0 if mark.target_face == "slope-middle" else 1)
        if mark.target_face in {"front", "rear", "door", "slope-middle"}:
            axis = 0
        candidates = [face for face in faces if abs(_face_normal(face)[axis]) > 0.8]
    if not candidates:
        raise ValueError(f"no entry face found for {mark.code}")
    return min(
        candidates,
        key=lambda face: (
            _box_point_distance(_face_center(face), source_box),
            face.Area(),
        ),
    )


def _target_centerline_point(
    target: cq.Shape, axis: int, station: float
) -> tuple[float, float, float] | None:
    """Interpolate a point along a beam's two smallest-area end faces."""
    ends = _target_end_centres(target)
    if len(ends) < 2:
        return None
    first, second = max(
        (
            (first, second)
            for index, first in enumerate(ends)
            for second in ends[index + 1 :]
        ),
        key=lambda pair: math.dist(pair[0], pair[1]),
    )
    a, b = first, second
    if abs(b[axis] - a[axis]) < 1e-9:
        return None
    fraction = (station - a[axis]) / (b[axis] - a[axis])
    return _point_add(a, _point_scale(_point_sub(b, a), fraction))


def _target_end_centres(target: cq.Shape) -> list[tuple[float, float, float]]:
    """Return the centres of the two small end faces of a beam."""
    faces = target.Faces()
    end_area = min(face.Area() for face in faces)
    return [_face_center(face) for face in faces if face.Area() <= end_area * 1.25]


def _drawing_screw_path(
    target: cq.Shape,
    source: cq.Shape,
    mark: ScrewMark,
    design: Design,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return a 120 mm path from the source side into the target beam."""
    face = _target_entry_face(target, source, mark)
    normal = _face_normal(face)
    point = list(_face_center(face))
    face_box = face.BoundingBox()

    if not mark.centered:
        # Stationed joints use the model's measured station on the receiving
        # face. Mitred braces and the roof end faces keep their actual CAD face
        # centres.
        if mark.position_axis is not None:
            point[mark.position_axis] = mark.target_station_mm
        elif not mark.diagonal and mark.target_face in {
            "front",
            "rear",
            "door",
            "side",
        }:
            if face_box.zmin - 1e-6 <= mark.target_station_mm <= face_box.zmax + 1e-6:
                point[2] = mark.target_station_mm
        elif not mark.diagonal and mark.target_face == "slope-middle":
            centreline = _target_centerline_point(target, 1, mark.target_station_mm)
            if centreline is not None:
                point[1] = mark.target_station_mm
                point[2] = centreline[2]
        elif (
            not mark.diagonal
            and mark.target_face == "underside"
            and face_box.xmin - 1e-6 <= mark.target_station_mm <= face_box.xmax + 1e-6
        ):
            point[0] = mark.target_station_mm

        if mark.position_axis is None:
            # Keep the two scheduled screws centred on the 45 mm receiving
            # section.
            if mark.target_face == "underside":
                lane_axis = 2
            elif abs(normal[0]) > 0.8:
                lane_axis = 2 if mark.target_face == "slope-middle" else 1
            else:
                lane_axis = 0
            point[lane_axis] += mark.lane_mm - design.frame / 2
    entry = (point[0], point[1], point[2])

    source_box = source.BoundingBox()
    source_centre = (
        (source_box.xmin + source_box.xmax) / 2,
        (source_box.ymin + source_box.ymax) / 2,
        (source_box.zmin + source_box.zmax) / 2,
    )
    if mark.diagonal:
        end_centres = _target_end_centres(target)
        entry_end = min(end_centres, key=lambda centre: math.dist(centre, entry))
        other_end = max(end_centres, key=lambda centre: math.dist(centre, entry))
        inward = _point_unit(_point_sub(other_end, entry_end))
    else:
        inward = _point_scale(
            normal,
            -1 if _point_dot(_point_sub(source_centre, entry), normal) > 0 else 1,
        )
    target_centre = _point_add(entry, _point_scale(inward, design.frame / 2))
    head = _point_sub(target_centre, _point_scale(inward, design.screw_length))
    return head, target_centre


def draw_frame_screws(
    plate: Plate,
    parts: dict[str, cq.Shape],
    names: set[str],
    view: View | AxonometricView,
    fastening: FasteningAnalysis,
    design: Design,
    pairs: set[tuple[str, str]] | None = None,
) -> None:
    """Project every scheduled beam screw from a source beam into its target."""
    start = len(plate.body)
    for mark in fastening.screws:
        if mark.from_beam not in names or mark.into_beam not in names:
            continue
        if pairs is not None and (mark.from_beam, mark.into_beam) not in pairs:
            continue
        head, target_centre = _drawing_screw_path(
            parts[mark.into_beam], parts[mark.from_beam], mark, design
        )
        plate.screw_path(view(head), view(target_centre))
    plate.group(start, "screw-layer screw-frame")


def _seat_installation_perspective(
    design: Design,
    parts: dict[str, cq.Shape],
    fastening: FasteningAnalysis,
    side: str,
    view: AxonometricView,
) -> Plate:
    """Draw the installed shell and fixed bearers from one front corner."""
    wall = f"{side}_wall"
    members = (
        "seat_box_support_front",
        "seat_box_support_rear",
        "seat_floor_support",
    )
    context = ("floor", "back_wall", wall)
    shapes = {
        name: projected_outline(parts[name], view) for name in (*members, *context)
    }
    wall_box = parts[wall].BoundingBox()
    back_box = parts["back_wall"].BoundingBox()
    wall_inner_x = wall_box.xmin if side == "right" else wall_box.xmax
    shapes[wall] = projected_face_at(parts[wall], view, 0, wall_inner_x)
    # The model fits the back field between the side skins. From inside the
    # shell its visible face is therefore the front face at ymin, meeting the
    # side's inner face before that side continues to the rear outer edge.
    shapes["back_wall"] = projected_face_at(parts["back_wall"], view, 1, back_box.ymin)
    plate = Plate(list(shapes.values()), margin=62, pad=72)

    for name in context:
        plate.shape(shapes[name], "ghost")
        plate.wire(parts[name], view, "ghost-edge")
    draw_perspective_members(plate, shapes, parts, members, view)

    pair_set = {(wall, member) for member in members}
    draw_frame_screws(
        plate,
        parts,
        set(members) | {wall},
        view,
        fastening,
        design,
        pair_set,
    )

    # The front 352 mm marker checks SBB1/SBF1 at the side wall. Anchor the
    # upper marker at the outer, back corner of SBB2 so its line visibly runs
    # from the beam end down to the floor.
    plate.linear_dim(
        view(
            (
                wall_inner_x,
                design.seat_front_support_y + design.frame / 2,
                design.floor_top,
            )
        ),
        view(
            (
                wall_inner_x,
                design.seat_front_support_y + design.frame / 2,
                design.seat_support_top,
            )
        ),
        34,
        f"{fmt(design.seat_support_top - design.floor_top)} mm",
    )
    rear_support_box = parts["seat_box_support_rear"].BoundingBox()
    back_x = rear_support_box.xmax if side == "right" else rear_support_box.xmin
    plate.linear_dim(
        view((back_x, rear_support_box.ymax, design.floor_top)),
        view((back_x, rear_support_box.ymax, design.seat_support_top)),
        -34,
        f"{fmt(design.seat_support_top - design.floor_top)} mm",
    )
    plate.linear_dim(
        view((wall_inner_x, back_box.ymin, design.seat_support_top)),
        view((wall_inner_x, design.seat_front_support_y, design.seat_support_top)),
        -42,
        f"{fmt(design.seat_front_support_from_back)} mm",
    )
    plate.corner(
        f"{wall.upper()} · SBB1 / SBB2 / SBF1 · {fmt(design.seat_front_support_from_back)} FROM BACK · "
        "23 MM SIDE CLADDING · 2 × 120 SCREWS FROM OUTSIDE"
    )
    return plate


def seat_installation_perspective(
    design: Design,
    parts: dict[str, cq.Shape],
    fastening: FasteningAnalysis,
) -> str:
    """Return a right/left toggle drawing for the fixed seat-box bearers."""
    right = _seat_installation_perspective(design, parts, fastening, "right", AXO_RIGHT)
    left = _seat_installation_perspective(design, parts, fastening, "left", AXO_LEFT)
    title = "Seat box supports"
    caption = "isometric projection"
    return (
        '<figure class="drawing perspective-drawing">'
        f"{right.element('plate perspective-right', title, 'right side')}"
        f"{left.element('plate perspective-left', title, 'left side')}"
        "<figcaption>"
        f'<span class="drawing-name">{html.escape(title.upper())}</span>'
        f'<span class="drawing-ref">A-411 · {html.escape(caption.upper())}</span>'
        '<span class="drawing-note">Flip the side toggle to see the two outside screw pairs.</span>'
        "</figcaption>"
        "</figure>"
    )


def _cladding_frame_paths(
    member_name: str,
    parts: dict[str, cq.Shape],
    fastening: FasteningAnalysis,
    design: Design,
) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    """Return frame screw paths which pass through one cladding support."""
    return tuple(
        _drawing_screw_path(
            parts[mark.into_beam],
            parts[mark.from_beam],
            mark,
            design,
        )
        for mark in fastening.screws
        if member_name in {mark.from_beam, mark.into_beam}
    )


def cladding_screw_layout(
    solid: cq.Shape,
    panel: Panel,
    view: View,
    parts: dict[str, cq.Shape],
    row_members: tuple[str, str],
    fastening: FasteningAnalysis,
    design: Design,
) -> tuple[CladdingScrewRow, ...]:
    """Place cladding fixings on finished boards clear of frame screw paths."""
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()
    depth = (lows[view.depth_axis] + highs[view.depth_axis]) / 2
    spans = cladding_board_spans(panel, lows[panel.axis])
    field_centre = lows[panel.axis] + panel.span / 2
    rows: list[CladdingScrewRow] = []

    for member_name in row_members:
        member = parts[member_name].BoundingBox()
        member_low, member_high = _box_axis(member, run)
        member_depth_low, member_depth_high = _box_axis(member, view.depth_axis)
        member_centre = (member_low + member_high) / 2
        panel_run_centre = (lows[run] + highs[run]) / 2
        lane_stations = (
            member_low + SCREW_LANES_MM[0],
            member_low + SCREW_LANES_MM[-1],
        )
        row_stations = (member_centre,) + tuple(
            sorted(
                lane_stations,
                key=lambda station: abs(station - panel_run_centre),
            )
        )
        frame_paths = _cladding_frame_paths(member_name, parts, fastening, design)

        def frame_clearance(
            across: float,
            station: float,
            paths: tuple[
                tuple[tuple[float, float, float], tuple[float, float, float]], ...
            ] = frame_paths,
            depth_low: float = member_depth_low,
            depth_high: float = member_depth_high,
        ) -> float:
            if not paths:
                return math.inf
            start = [0.0, 0.0, 0.0]
            end = [0.0, 0.0, 0.0]
            start[panel.axis] = end[panel.axis] = across
            start[run] = end[run] = station
            start[view.depth_axis] = depth_low
            end[view.depth_axis] = depth_high
            path_start = (start[0], start[1], start[2])
            path_end = (end[0], end[1], end[2])
            return min(
                screw_path_distance(path_start, path_end, screw_start, screw_end)
                for screw_start, screw_end in paths
            )

        def candidates(low: float, high: float) -> list[float]:
            centre = (low + high) / 2
            edge_margin = min(BOARD_WIDTH - COVER_WIDTH, (high - low) / 2)
            lower = low + edge_margin
            upper = high - edge_margin
            direction = 1 if centre < field_centre else -1
            values = [centre]
            for delta in range(1, math.ceil(high - low) + 1):
                values.extend((centre + direction * delta, centre - direction * delta))
            return [value for value in values if lower <= value <= upper]

        for station in dict.fromkeys(row_stations):
            marks: list[CladdingScrewMark] = []
            for piece, (board_low, board_high) in zip(panel.pieces, spans):
                choice = next(
                    (
                        (across, clearance)
                        for across in candidates(board_low, board_high)
                        if (clearance := frame_clearance(across, station))
                        >= SCREW_PATH_CLEARANCE_MM
                    ),
                    None,
                )
                if choice is None:
                    break
                across, clearance = choice
                point = [0.0, 0.0, 0.0]
                point[panel.axis] = across
                point[run] = station
                point[view.depth_axis] = depth
                marks.append(
                    CladdingScrewMark(
                        piece.code,
                        member_name,
                        (point[0], point[1], point[2]),
                        clearance,
                    )
                )
            if len(marks) == panel.count:
                rows.append(CladdingScrewRow(member_name, station, tuple(marks)))
                break
        else:
            raise ValueError(f"no collision-free cladding screw row on {member_name}")
    return tuple(rows)


def draw_cladding_screws(
    plate: Plate,
    profile: list[Point],
    solid: cq.Shape,
    panel: Panel,
    view: View,
    parts: dict[str, cq.Shape],
    row_members: tuple[str, str],
    fastening: FasteningAnalysis,
    design: Design,
) -> None:
    """Draw two model-backed screw rows through every board in a field."""
    start = len(plate.body)
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    depth = (lows[view.depth_axis] + highs[view.depth_axis]) / 2
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()
    field_start = lows[panel.axis]
    field_end = field_start + panel.span
    field_bounds = bounds(profile)
    panel_projected_axis = 0 if panel.axis == view.u_axis else 1
    run_projected_axis = 1 - panel_projected_axis
    run_world_axis = run
    edge_names = (
        ("LEFT", "RIGHT")
        if run_world_axis == 0
        else ("TOP", "BOTTOM")
        if run_world_axis == 2
        else ("REAR", "FRONT")
    )
    layout = cladding_screw_layout(
        solid,
        panel,
        view,
        parts,
        row_members,
        fastening,
        design,
    )
    for screw_row in layout:
        row = screw_row.station

        def at(across: float, row_value: float = row) -> Point:
            point = [0.0, 0.0, 0.0]
            point[panel.axis] = across
            point[run] = (lows[run] + highs[run]) / 2
            point[run] = row_value
            point[view.depth_axis] = depth
            return view(tuple(point))

        line_start, line_end = at(field_start), at(field_end)
        plate.line(line_start, line_end, "screw-guide")
        for mark in screw_row.marks:
            plate.screw(view(mark.point), (0.0, 0.0), line=False)

        row_projected = line_start[run_projected_axis]
        edge = min(
            (
                (
                    abs(row_projected - value),
                    value,
                    edge_names[index],
                )
                for index, value in enumerate(
                    field_bounds[::2] if run_projected_axis == 0 else field_bounds[1::2]
                )
            ),
            key=lambda item: item[0],
        )
        dimension_point = list(line_start)
        dimension_point[run_projected_axis] = edge[1]
        plate.dim(
            (dimension_point[0], dimension_point[1]),
            line_start,
            44,
            f"{fmt(edge[0])} mm FROM {edge[2]}",
        )
    plate.group(start, "screw-layer screw-cladding")


def draw_unit_screws(
    plate: Plate,
    parts: dict[str, cq.Shape],
    names: set[str],
    view: View,
    fastening: FasteningAnalysis,
    design: Design,
    fields: dict[str, Panel],
    field_name: str | None = None,
    row_members: tuple[str, str] | None = None,
    frame_pairs: set[tuple[str, str]] | None = None,
) -> None:
    draw_frame_screws(plate, parts, names, view, fastening, design, frame_pairs)
    if field_name:
        if row_members is None:
            raise ValueError("cladding fields need two frame row members")
        draw_cladding_screws(
            plate,
            outline(parts[field_name], view),
            parts[field_name],
            fields[field_name],
            view,
            parts,
            row_members,
            fastening,
            design,
        )


def module_plates(design: Design, boards: list[CutPiece]) -> dict[str, str]:
    """One precise construction plate per lettered stack."""
    _, part_list = build(design)
    parts = {part.name: part.solid for part in part_list}
    # The modeled side fields already carry the roof reliefs, which the workshop
    # scribes from the finished roof instead of cutting from nominal numbers.
    # Each unit plate adds the rough terminal edge that is trimmed after fixing.
    parts["left_wall"] = side_panel(design, design.frame, False)
    parts["right_wall"] = side_panel(design, design.width - design.frame, True)
    fields = panels(boards)
    fastening = analyze_frame_fastening(design)
    plates: dict[str, str] = {}

    def shapes_for(view: View, *names: str) -> dict[str, list[Point]]:
        return {name: outline(parts[name], view) for name in names}

    # A · Roof unit, in plan, with the sheet it carries.
    members = ("roof_left", "roof_right", "roof_front", "roof_back", "roof_middle")
    shapes = shapes_for(PLAN, *members, "roof")
    plate = plate_for(shapes, members, ("roof",))
    draw_members(plate, shapes, members)
    draw_unit_screws(plate, parts, set(members), PLAN, fastening, design, fields)
    frame_box = bounds([point for name in members for point in shapes[name]])
    sheet = bounds(shapes["roof"])
    plate.dim((sheet[0], sheet[3]), (sheet[2], sheet[3]), 40)
    plate.dim((frame_box[0], frame_box[1]), (frame_box[2], frame_box[1]), -40)
    plate.dim((sheet[2], sheet[1]), (sheet[2], sheet[3]), 40)
    plate.corner(
        "sheet ghosted · slope beams foreshortened, cut them to the batch length"
    )
    plates["A"] = plate.svg(
        "A-401",
        "Roof unit",
        PLAN.short,
        note=f"{PLAN.caption} · built flat, then hung",
    )

    # B · Door unit, seen from outside, with the field on its inner face.
    members = ("door_left", "door_right", "door_bottom", "door_top", "door_brace")
    shapes = shapes_for(FRONT, *members, "door_panel")
    plate = plate_for(shapes, members)
    draw_field(
        plate,
        shapes["door_panel"],
        parts["door_panel"],
        fields["door_panel"],
        FRONT,
        "door-field",
    )
    draw_members(plate, shapes, members)
    draw_unit_screws(
        plate,
        parts,
        set(members),
        FRONT,
        fastening,
        design,
        fields,
        "door_panel",
        ("door_bottom", "door_top"),
    )
    frame_box = bounds([point for name in members for point in shapes[name]])
    field_box = bounds(shapes["door_panel"])
    plate.dim((frame_box[0], frame_box[1]), (frame_box[2], frame_box[1]), -40)
    plate.dim((frame_box[0], frame_box[1]), (frame_box[0], frame_box[3]), -40)
    plate.dim((field_box[2], field_box[1]), (field_box[2], field_box[3]), 40)
    plates["B"] = plate.svg(
        "A-402",
        "Door unit",
        FRONT.short,
        note=f"{FRONT.caption} · hatched edge is the estimated on-frame trim",
    )

    # C and D · Side units, each seen from outside its own wall.
    for letter, number, side, view in (
        ("C", "A-403", "left", LEFT),
        ("D", "A-404", "right", RIGHT),
    ):
        members = (
            f"front_post_{side}",
            f"back_post_{side}",
            f"{side}_bottom",
            f"{side}_top",
            f"{side}_brace",
        )
        wall = f"{side}_wall"
        field = fields[wall]
        shapes = shapes_for(view, *members, wall)
        plate = plate_for(shapes, members)
        draw_field(plate, shapes[wall], parts[wall], field, view, f"{side}-field")
        draw_members(plate, shapes, members)
        draw_unit_screws(
            plate,
            parts,
            set(members),
            view,
            fastening,
            design,
            fields,
            wall,
            (f"{side}_bottom", f"{side}_top"),
        )
        field_box = bounds(shapes[wall])
        post = bounds(shapes[f"front_post_{side}"])
        plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 40)
        plate.dim(
            (post[0] if side == "right" else post[2], field_box[1]),
            (post[0] if side == "right" else post[2], field_box[3]),
            -40 if side == "right" else 40,
        )
        bottom = bounds(shapes[f"{side}_bottom"])
        bottom_edge = bottom[0] if side == "right" else bottom[2]
        plate.dim(
            (bottom_edge, post[3]),
            (bottom_edge, bottom[3]),
            -40 if side == "right" else 40,
            fmt(design.leg_extension),
        )
        notch = view(
            (
                0,
                design.frame / 2,
                design.leg_extension + design.frame / 2,
            )
        )
        notch_note = view(
            (
                0,
                design.frame + 130,
                design.leg_extension + design.frame + 80,
            )
        )
        plate.leader(
            notch,
            notch_note,
            f"{fmt(design.frame)} × {fmt(design.frame)} NOTCH",
            "start" if view.u_sign > 0 else "end",
        )
        fall = (field.pieces[0].finished_long or field.blank) - (
            field.pieces[-1].finished_short or field.blank
        )
        plates[letter] = plate.svg(
            number,
            f"{side.title()} side unit",
            view.short,
            note=f"{view.caption} · {fmt(fall)} fall over {fmt(field.span)} · "
            f"{fmt(design.frame)} × {fmt(design.frame)} bottom-front notch",
        )

    # E · Back unit, seen from outside, between the two rear posts.
    members = ("back_bottom", "back_top", "back_brace")
    ghosts = ("back_post_left", "back_post_right")
    shapes = shapes_for(REAR, *members, *ghosts, "back_wall")
    plate = plate_for(shapes, members, ghosts)
    draw_field(
        plate,
        shapes["back_wall"],
        parts["back_wall"],
        fields["back_wall"],
        REAR,
        "back-field",
    )
    draw_members(plate, shapes, members)
    draw_unit_screws(
        plate,
        parts,
        set(members) | set(ghosts),
        REAR,
        fastening,
        design,
        fields,
        "back_wall",
        ("back_bottom", "back_top"),
    )
    posts = bounds([point for name in ghosts for point in shapes[name]])
    rear_post = bounds(shapes["back_post_left"])
    field_box = bounds(shapes["back_wall"])
    plate.dim((posts[0], posts[1]), (posts[2], posts[1]), -40)
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 40)
    plate.dim((posts[0], field_box[3]), (field_box[0], field_box[3]), 84)
    plate.dim((posts[2], field_box[1]), (posts[2], field_box[3]), 36)
    bottom = bounds(shapes["back_bottom"])
    plate.dim(
        (bottom[2], rear_post[3]),
        (bottom[2], bottom[3]),
        -40,
        fmt(design.leg_extension),
    )
    plates["E"] = plate.svg(
        "A-405",
        "Back unit",
        REAR.short,
        note=f"{REAR.caption} · posts ghosted · trim after the boards are fixed",
    )

    # F · Shell joint, in plan, with all four floor-level beams fitted inside
    # the ghosted side and back shell. The front opening rail is installed here
    # rather than left as a ghost for the later floor-deck operation.
    members = (
        "floor_back_support",
        "floor_left_support",
        "floor_right_support",
        "front_bottom",
    )
    ghosts = (
        "left_bottom",
        "right_bottom",
        "back_bottom",
        "left_wall",
        "right_wall",
        "back_wall",
    )
    shapes = shapes_for(PLAN, *members, *ghosts)
    plate = plate_for(shapes, members, ghosts)
    draw_members(plate, shapes, members)
    for name in ("left_bottom", "right_bottom", "back_bottom"):
        plate.code_in(shapes[name], BEAM_CODES[name])
    shell_joint_pairs = {
        ("floor_back_support", "back_bottom"),
        ("floor_right_support", "right_bottom"),
        ("floor_left_support", "left_bottom"),
        ("left_bottom", "front_bottom"),
        ("right_bottom", "front_bottom"),
    }
    draw_frame_screws(
        plate,
        parts,
        set(members) | set(ghosts),
        PLAN,
        fastening,
        design,
        shell_joint_pairs,
    )
    shell = bounds([point for name in members + ghosts for point in shapes[name]])
    plate.dim((shell[0], shell[3]), (shell[2], shell[3]), 44)
    plate.corner(
        "8 × 120 SCREWS · 6 FROM INSIDE OUT · 2 FROM OUTSIDE SIDE RAILS INTO FBH1"
    )
    plates["F"] = plate.svg(
        "A-406",
        "Shell joint",
        PLAN.short,
        note=f"{PLAN.caption} · sides and back ghosted · fit FBB1, FBS1, FBS2, and FBH1",
    )

    # G · Floor deck, in plan. The bearers and front rail are already fitted;
    # keep them ghosted and show only the cladding operation.
    members = ("floor_back_support", "floor_left_support", "floor_right_support")
    ghosts = members + ("front_bottom",)
    shapes = shapes_for(PLAN, *ghosts, "floor")
    plate = plate_for(shapes, (), ghosts)
    draw_field(
        plate, shapes["floor"], parts["floor"], fields["floor"], PLAN, "floor-field"
    )
    draw_cladding_screws(
        plate,
        shapes["floor"],
        parts["floor"],
        fields["floor"],
        PLAN,
        parts,
        ("front_bottom", "floor_back_support"),
        fastening,
        design,
    )
    field_box = bounds(shapes["floor"])
    rail = bounds(shapes["front_bottom"])
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 44)
    plate.dim((field_box[0], field_box[1]), (field_box[0], field_box[3]), -40)
    plate.label(
        ((rail[0] + rail[2]) / 2, rail[1] + (rail[3] - rail[1]) / 2),
        "FBH1 · FRONT EDGE LANDS HERE LAST",
        "small",
    )
    plates["G"] = plate.svg(
        "A-407",
        "Floor deck",
        PLAN.short,
        note=f"{PLAN.caption} · cladding side only · bearers already fitted",
    )

    # H · Seat box, in plan, with everything the top has to clear. The top
    # boards now run across the 852 mm width, so the outer side beams carry
    # the two board-fixing screw rows.
    members = (
        "seat_rail_1",
        "seat_rail_2",
        "seat_support_left",
        "seat_support_right",
        "seat_support_outer_left",
        "seat_support_outer_right",
    )
    shapes = shapes_for(PLAN, *members, "seat_top")
    plate = plate_for(shapes, members)
    draw_field(
        plate,
        shapes["seat_top"],
        parts["seat_top"],
        fields["seat_top"],
        PLAN,
        "seat-field",
        label=False,
    )
    for name in members:
        plate.shape(shapes[name], "under")
        plate.code_in(shapes[name], BEAM_CODES.get(name, ""))
    draw_unit_screws(
        plate,
        parts,
        set(members),
        PLAN,
        fastening,
        design,
        fields,
        "seat_top",
        ("seat_support_outer_left", "seat_support_outer_right"),
    )
    centre = (design.width / 2, -(design.back_wall_front - design.seat_depth / 2))
    plate.add(
        f'<ellipse class="opening" cx="{plate.x(centre[0]):.1f}" cy="{plate.y(centre[1]):.1f}" '
        f'rx="{design.seat_hole_width / 2 * plate.scale:.1f}" '
        f'ry="{design.seat_hole_depth / 2 * plate.scale:.1f}"/>'
    )
    field_box = bounds(shapes["seat_top"])
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 44)
    plate.dim((field_box[2], field_box[1]), (field_box[2], field_box[3]), 40)
    plate.label(
        centre,
        f"{fmt(design.seat_hole_width)} × {fmt(design.seat_hole_depth)}",
        "small",
    )
    plates["H"] = plate.svg(
        "A-408",
        "Seat box",
        PLAN.short,
        note=(
            f"{PLAN.caption} · 852 removable box · STB1–STB{fields['seat_top'].count} "
            "run across the width · trim before cutting the opening"
        ),
    )

    # I · Fixed seat-box supports, in plan. The floor, side cladding, and back
    # wall are already in place; the two full-width bearers sit directly below
    # SBH1 and SBH2 and are driven from both side exteriors.
    members = ("seat_box_support_front", "seat_box_support_rear")
    ghosts = (
        "left_wall",
        "right_wall",
        "back_wall",
        "left_bottom",
        "right_bottom",
        "back_bottom",
        "front_bottom",
    )
    shapes = shapes_for(PLAN, *members, *ghosts, "floor")
    plate = plate_for(shapes, members, ghosts)
    plate.shape(shapes["floor"], "field")
    draw_members(plate, shapes, members)
    support_pairs = {
        ("left_wall", "seat_box_support_front"),
        ("right_wall", "seat_box_support_front"),
        ("left_wall", "seat_box_support_rear"),
        ("right_wall", "seat_box_support_rear"),
    }
    draw_frame_screws(
        plate,
        parts,
        set(members) | set(ghosts),
        PLAN,
        fastening,
        design,
        support_pairs,
    )
    support_front = bounds(shapes["seat_box_support_front"])
    back_wall_edge = PLAN((design.interior_x, design.back_wall_front, 0))
    front_support_edge = PLAN(
        (design.interior_x, design.seat_front_y + design.cladding, 0)
    )
    plate.dim(
        (support_front[0], back_wall_edge[1]),
        (support_front[0], front_support_edge[1]),
        44,
        fmt(design.back_wall_front - (design.seat_front_y + design.cladding)),
    )
    plate.corner(
        "SBB1 / SBB2 · 854 LONG · 4 × 120 SCREWS FROM OUTSIDE THROUGH SIDE CLADDING"
    )
    plates["I"] = plate.svg(
        "A-409",
        "Seat supports",
        PLAN.short,
        note=(
            f"{PLAN.caption} · floor, sides, and back already attached · "
            f"{fmt(design.back_wall_front - (design.seat_front_y + design.cladding))} "
            "from back wall to front support face"
        ),
    )

    # J · Corner view for the outside screw pair and the seat-front panel.
    plates["J"] = seat_installation_perspective(design, parts, fastening)

    # K · The loose seat-front boards, shown square-on with both fixing beams
    # ghosted into the finished unit. This is a cladding-only view: the field
    # carries its own board codes and the two fixing rows carry one screw per
    # board at each support.
    members = ("seat_floor_support", "seat_box_support_front")
    ghosts = members
    shapes = shapes_for(FRONT, *members, *ghosts, "seat_front")
    plate = plate_for(shapes, (), ())
    draw_individual_cladding(
        plate,
        parts["seat_front"],
        fields["seat_front"],
        FRONT,
    )
    for name in ghosts:
        plate.shape(shapes[name], "ghost")
    draw_cladding_codes(plate, parts["seat_front"], fields["seat_front"], FRONT)
    draw_cladding_screws(
        plate,
        shapes["seat_front"],
        parts["seat_front"],
        fields["seat_front"],
        FRONT,
        parts,
        members,
        fastening,
        design,
    )
    field_box = bounds(shapes["seat_front"])
    plate.dim(
        (field_box[0], field_box[1]),
        (field_box[0], field_box[3]),
        -40,
        fmt(design.seat_height - design.cladding),
    )
    plate.dim(
        (field_box[0], field_box[3]),
        (field_box[2], field_box[3]),
        44,
        fmt(design.interior_width),
    )
    plate.corner(
        f"SFB1–SFB8 · {fmt(design.seat_front_support_from_back)} FROM BACK · "
        "2 SCREWS PER BOARD TO SBF1 AND SBB1"
    )
    plates["K"] = plate.svg(
        "A-412",
        "Seat front cladding",
        FRONT.short,
        note=(
            f"{FRONT.caption} · cladding face only · {fmt(design.cladding)} mm wall · "
            "SBF1 and SBB1 ghosted"
        ),
    )
    return plates


"""The sheet stylesheet.

Kept out of the page f-string so CSS braces stay single, and because the whole
visual world lives here: white sheets on a grey ground, one monoline face, red
for codes, blue for dimensions, and four line weights.
"""
STYLE = """
    @font-face {
      font-family:InputMono;
      src:url("fonts/InputMono-Regular.woff2") format("woff2");
      font-weight:400; font-style:normal; font-display:swap;
    }
    :root {
      --sheet:#fff; --ground:#e4e4e1; --ink:#151515; --line:#000;
      --timber:#7f7f7f; --grey-dark:#5a5a5a; --grey-mid:#959595;
      --grey-light:#b7b7b7; --grey-pale:#e6e6e6; --grey-faint:#f2f2f0;
      --code:#bb261a; --code-deep:#8f1c13; --dim:#63a4f5; --dim-ink:#1668c4;
      --mono:InputMono,ui-monospace,SFMono-Regular,Consolas,monospace;
      --hair:.5px; --object:.8px; --section:1.4px;
      /* Four lettering steps and two display steps. A drawing set letters at a
         handful of sizes; the face has one weight, so size carries the rank. */
      --t-fine:.62rem; --t-small:.7rem; --t-mark:.76rem; --t-note:.83rem;
      --t-title:clamp(1.25rem,2.5vw,1.9rem); --t-doc:clamp(1.7rem,4.2vw,3rem);
    }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body {
      margin:0; padding:0; background:var(--ground); color:var(--ink);
      font-family:var(--mono); font-size:var(--t-note); line-height:1.65;
      -webkit-font-smoothing:antialiased;
    }
    .defs { position:absolute; width:0; height:0; overflow:hidden; }
    a { color:inherit; }
    button,input { font:inherit; font-family:var(--mono); }
    h1,h2,h3,h4 { margin:0; font-weight:400; text-transform:uppercase; }
    h1 { font-size:var(--t-doc); letter-spacing:.01em; line-height:1.08; }
    h2 { font-size:var(--t-title); letter-spacing:.02em; color:var(--code-deep); }
    h3 { font-size:var(--t-mark); letter-spacing:.14em; }
    h4 { font-size:var(--t-fine); letter-spacing:.14em; color:var(--grey-dark); }
    p { margin:0; max-width:68ch; }
    b,strong { font-weight:400; }

    .set { width:min(1360px,100%); margin:auto; padding:clamp(16px,3vw,44px) clamp(12px,3vw,44px) 120px; }
    .sheet {
      background:var(--sheet); border:1px solid var(--line);
      padding:clamp(24px,3vw,48px); margin-bottom:clamp(24px,4vw,56px);
      break-after:page;
    }
    .sheet:last-child { margin-bottom:0; }

    /* Sheet head: number, title, and a rule with air on both sides. */
    .sheet-head { margin-bottom:40px; }
    .sheet-no {
      display:block; font-size:var(--t-fine); letter-spacing:.22em;
      color:var(--grey-dark); margin-bottom:14px;
    }
    .sheet-head h2 { padding-bottom:20px; border-bottom:1px solid var(--line); }
    .sheet-note { margin-top:24px; color:var(--ink); }
    .sheet-note + .sheet-note { margin-top:14px; }

    /* Masthead is the one title block in the set. */
    .masthead {
      background:var(--sheet); border:1px solid var(--line);
      padding:clamp(24px,3vw,48px); margin-bottom:clamp(24px,4vw,56px);
    }
    .masthead-top {
      display:grid; grid-template-columns:minmax(0,1fr) auto;
      gap:40px; align-items:start;
    }
    .masthead h1 { margin-bottom:18px; }
    .masthead-sub { color:var(--grey-dark); }
    .title-block { display:grid; grid-template-columns:auto auto; border:1px solid var(--line); }
    .title-block dt, .title-block dd {
      margin:0; padding:10px 16px; font-size:var(--t-fine); letter-spacing:.12em;
      text-transform:uppercase; border-bottom:1px solid var(--grey-pale);
    }
    .title-block dt { color:var(--grey-dark); border-right:1px solid var(--grey-pale); }
    .title-block > div { display:contents; }
    .title-block > div:last-child dt, .title-block > div:last-child dd { border-bottom:0; }
    .title-block a {
      display:inline-flex; align-items:center; gap:7px; color:inherit;
      text-decoration:underline; text-underline-offset:3px;
    }
    .source-icon {
      width:1.05em; height:1.05em; fill:none; stroke:currentColor;
      stroke-width:2; stroke-linecap:round; stroke-linejoin:round; flex:none;
    }

    /* The three project phases sit above each page, like a small sheet index. */
    .story-nav {
      display:grid; grid-template-columns:1fr 1fr 1fr; margin-top:36px;
      border-top:1px solid var(--line); border-bottom:1px solid var(--line);
      scroll-margin-top:16px;
    }
    .story-link {
      display:flex; align-items:center; justify-content:space-between; gap:18px;
      min-height:78px; padding:16px 18px; color:inherit; text-decoration:none;
    }
    .story-link + .story-link { border-left:1px solid var(--grey-pale); }
    .story-link:hover { background:var(--grey-faint); }
    .story-link:focus-visible { outline:1px solid var(--line); outline-offset:-4px; }
    .story-link-copy { display:flex; flex-direction:column; gap:4px; }
    .story-link-copy b {
      font-size:var(--t-mark); letter-spacing:.14em; text-transform:uppercase;
    }
    .story-link-copy small {
      font-size:var(--t-fine); letter-spacing:.12em; text-transform:uppercase;
      color:var(--grey-dark);
    }
    .story-link-start { text-align:left; }
    .story-link-start .story-link-copy { align-items:flex-start; }
    .story-link-drawing { text-align:center; justify-content:center; }
    .story-link-drawing .story-link-copy { align-items:center; }
    .story-link-going { text-align:right; }
    .story-link-going .story-link-copy { align-items:flex-end; }
    .story-link[aria-current="page"] .story-link-copy b { color:var(--code); }
    .story-arrow {
      width:25px; height:25px; fill:none; stroke:var(--ink); stroke-width:1.4;
      stroke-linecap:round; stroke-linejoin:round; flex:none;
    }
    .story-link:hover .story-arrow { stroke:var(--code); }

    .progress-grid {
      display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:32px;
      margin-top:36px;
    }
    .progress-photo { min-width:0; margin:0; }
    .progress-photo-frame {
      aspect-ratio:3 / 4; overflow:hidden; background:var(--grey-faint);
      border:1px solid var(--line);
    }
    .progress-photo img { display:block; width:100%; height:100%; object-fit:cover; }
    .progress-photo figcaption { padding:22px 12px 6px; }
    .progress-photo-title {
      display:block; font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase;
    }
    .progress-photo-note {
      display:block; max-width:58ch; margin-top:10px; font-size:var(--t-small);
      line-height:1.6; color:var(--grey-dark);
    }
    .progress-video-figure {
      grid-column:1 / -1; min-width:0; margin:0;
    }
    .progress-video-frame {
      width:min(100%, 540px); aspect-ratio:9 / 16; margin:0 auto; overflow:hidden;
      background:var(--grey-faint); border:1px solid var(--line);
    }
    .progress-video {
      display:block; width:100%; height:100%; object-fit:contain; background:#111; border:0;
    }
    .progress-video-figure figcaption {
      width:min(100%, 540px); margin:0 auto; padding:22px 12px 6px;
    }

    .started-story { display:grid; gap:36px; margin-top:36px; }
    .started-story p { max-width:68ch; }
    .started-figure { margin:0; }
    .started-figure img {
      display:block; width:100%; height:auto; background:var(--grey-faint);
      border:1px solid var(--line);
    }
    .started-figure figcaption { padding:22px 12px 6px; }
    .started-figure-title {
      display:block; font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase;
    }
    .started-figure-pair {
      display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:32px;
    }

    /* Schedule: a quantity table, not a row of hero numbers. */
    caption {
      text-align:left; padding-bottom:14px; font-size:var(--t-fine);
      letter-spacing:.18em; text-transform:uppercase; color:var(--grey-dark);
    }
    table { width:100%; border-collapse:collapse; }
    th, td { padding:13px 16px; text-align:left; vertical-align:top; }
    th {
      font-size:var(--t-fine); letter-spacing:.14em; text-transform:uppercase;
      font-weight:400; color:var(--grey-dark); border-bottom:1px solid var(--line);
    }
    td { border-bottom:1px solid var(--grey-pale); font-size:var(--t-mark); }
    tbody tr:last-child td { border-bottom:1px solid var(--grey-light); }
    tfoot td { border-bottom:0; color:var(--grey-dark); font-size:var(--t-small); }
    th:first-child, td:first-child { padding-left:0; }
    th:last-child, td:last-child { padding-right:0; }
    .table-scroll { overflow-x:auto; margin-top:36px; }
    .table-scroll table { min-width:620px; }

    /* The two inks. Red is codes. Blue is dimensions and measured detail. */
    .code, .marks b, .stock-piece b, .code-strip b { color:var(--code); letter-spacing:.06em; }
    .measure { color:var(--dim-ink); white-space:nowrap; }
    .pass { color:var(--grey-dark); }
    .marks b + b { margin-left:8px; }

    /* Caution notes: command first, risk second. */
    /* A drawing set boxes its notes and letters the heading in red; it does not
       tab them with a coloured edge. */
    /* A note is prose in a box, so it holds the same measure as prose: the
       border sits just clear of the text instead of ruling the whole sheet. */
    .note {
      --note-pad:24px;
      margin:36px 0; padding:20px var(--note-pad); border:1px solid var(--line);
      max-width:calc(68ch + 2 * var(--note-pad) + 2px);
    }
    /* A note carrying a batch table is sized by the table it holds, not by the
       measure its prose would take. */
    .note:has(.table-scroll) { max-width:none; }
    .note h3 { color:var(--code-deep); margin-bottom:12px; }
    .note p + p { margin-top:12px; }
    .note ol { margin:12px 0 0; padding-left:22px; }
    .note ol li { margin-bottom:10px; max-width:66ch; }
    .note ol li:last-child { margin-bottom:0; }

    /* Drawings. One caption under each, centred, the way the set captions them. */
    .drawing { margin:0; }
    .plate { display:block; width:100%; height:auto; background:var(--sheet); }
    .perspective-drawing .perspective-left { display:none; }
    .drawing figcaption { padding:22px 12px 6px; text-align:center; }
    .drawing-name { display:block; font-size:var(--t-small); letter-spacing:.16em; text-transform:uppercase; }
    .drawing-ref {
      display:block; margin-top:8px; font-size:var(--t-fine); letter-spacing:.14em;
      text-transform:uppercase; color:var(--grey-dark);
    }
    .drawing-note {
      display:block; margin:10px auto 0; max-width:58ch;
      font-size:var(--t-small); line-height:1.6; color:var(--grey-dark);
    }

    .plate .member { fill:var(--sheet); stroke:var(--line); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .member-edge { fill:none; stroke:var(--line); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .cut-member { fill:url(#hatch); stroke:var(--line); stroke-width:var(--section); vector-effect:non-scaling-stroke; }
    .plate .field { fill:var(--grey-faint); stroke:var(--line); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .cut-field { fill:var(--grey-pale); stroke:var(--line); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .blank { fill:#fafafa; stroke:var(--grey-mid); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .ghost { fill:none; stroke:var(--grey-mid); stroke-width:var(--hair); stroke-dasharray:10 6; vector-effect:non-scaling-stroke; }
    .plate .ghost-edge { fill:none; stroke:var(--grey-mid); stroke-width:var(--hair); stroke-dasharray:10 6; vector-effect:non-scaling-stroke; }
    .plate .under { fill:none; stroke:var(--grey-dark); stroke-width:var(--hair); stroke-dasharray:7 5; vector-effect:non-scaling-stroke; }
    .plate .joint { stroke:var(--grey-light); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .trim { fill:url(#hatch-fine); stroke:var(--grey-dark); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .cut { fill:none; stroke:var(--line); stroke-width:var(--section); vector-effect:non-scaling-stroke; }
    .plate .opening { fill:none; stroke:var(--line); stroke-width:var(--section); vector-effect:non-scaling-stroke; }
    .plate .dim, .plate .dim-tick { fill:none; stroke:var(--dim); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .leader { fill:none; stroke:var(--dim); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .leader-dot { fill:var(--dim); stroke:none; }
    .plate text { fill:var(--ink); font-family:var(--mono); font-size:13px; letter-spacing:.06em; }
    /* A code has to stay legible over hatching, so it carries a white halo. */
    .plate .mark {
      fill:var(--code); font-size:16px; letter-spacing:.08em;
      stroke:var(--sheet); stroke-width:3.5; paint-order:stroke;
    }
    .plate .cladding-code {
      fill:var(--code-deep); font-size:11px; letter-spacing:.04em;
      stroke:var(--sheet); stroke-width:3px; paint-order:stroke;
    }
    .plate .small { fill:var(--dim-ink); font-size:12px; }
    .plate .note-text { fill:var(--grey-dark); font-size:12px; }
    .plate .dim-text { fill:var(--dim-ink); font-size:12px; letter-spacing:.04em; }
    .plate .screw-guide {
      fill:none; stroke:var(--grey-light); stroke-width:var(--hair); stroke-dasharray:7 5;
      vector-effect:non-scaling-stroke;
    }
    .plate .screw-stem {
      fill:none; stroke:var(--line); stroke-width:1.2px; vector-effect:non-scaling-stroke;
    }
    .plate .screw-head { fill:var(--ink); stroke:var(--line); stroke-width:var(--hair); vector-effect:non-scaling-stroke; }
    .plate .screw-recess { fill:var(--sheet); stroke:none; }

    /* Stock bars: one scaled diagram per stock length. */
    .stock-list { display:grid; gap:28px; margin-top:36px; }
    /* The bar inside is 860px wide and scrolls itself; without this the article
       inherits that as its minimum and the whole document scrolls sideways. */
    .stock { break-inside:avoid; min-width:0; }
    .stock > header {
      display:flex; justify-content:space-between; align-items:baseline;
      gap:20px; padding-bottom:12px;
    }
    .stock header label { display:flex; align-items:center; gap:10px; cursor:pointer; }
    .stock header b { color:var(--ink); font-size:var(--t-mark); letter-spacing:.14em; }
    .stock-count { font-size:var(--t-fine); letter-spacing:.14em; text-transform:uppercase; color:var(--grey-dark); }
    input[type=checkbox] { accent-color:var(--code); width:15px; height:15px; margin:0; }
    .stock-scroll { overflow-x:auto; padding-bottom:46px; }
    .stock-track {
      position:relative; min-width:860px; width:100%; height:auto;
      aspect-ratio:var(--stock-aspect);
      background:var(--sheet); border:1px solid var(--line);
    }
    .stock-piece, .stock-waste { position:absolute; top:0; bottom:0; overflow:visible; }
    .stock-piece {
      padding:0 9px; border-right:var(--hair) solid var(--grey-light);
    }
    .stock-piece b, .stock-piece span {
      position:absolute; left:9px; white-space:nowrap;
    }
    .stock-piece b { top:calc(100% + 7px); font-size:var(--t-small); }
    .stock-piece span { top:calc(100% + 23px); font-size:var(--t-fine); color:var(--dim-ink); }
    .stock-piece.is-gang { background:var(--sheet); }
    .saw-tick { position:absolute; top:-4px; bottom:-4px; width:1px; background:var(--line); z-index:2; }
    .stock-waste {
      background:repeating-linear-gradient(135deg,transparent 0 5px,var(--grey-light) 5px 6px);
      border-left:1px dashed var(--line);
    }
    .stock-waste span {
      position:absolute; top:calc(100% + 7px); left:50%; transform:translateX(-50%);
      font-size:var(--t-fine); color:var(--grey-dark); background:var(--sheet);
      padding:2px 5px; white-space:nowrap;
    }
    /* General arrangement: image and model, controls under each frame. */
    .view-grid { display:grid; grid-template-columns:1fr 1fr; gap:32px; margin-top:36px; }
    /* Grid children default to min-content width, and the control strip is
       wide; without this the two frames push each other off the sheet. */
    .gallery, .viewer { display:flex; flex-direction:column; margin:0; min-width:0; }
    /* The print still and the paper wording exist only for the printed set. */
    .viewer-print, .on-paper { display:none; }
    .view-frame {
      position:relative; aspect-ratio:1; overflow:hidden;
      background:var(--grey-faint); border:1px solid var(--line);
    }
    .shot {
      position:absolute; inset:0; width:100%; height:100%;
      object-fit:contain; opacity:0; transition:opacity .15s linear;
    }
    /* The in-situ composites are portrait; they fill the square and crop. */
    .shot.is-crop { object-fit:cover; object-position:center 38%; }
    .shot.is-on { opacity:1; }
    /* Wrapping rather than scrolling: a hidden group is a group nobody finds. */
    .view-controls {
      display:flex; flex-wrap:wrap; border:1px solid var(--line); border-top:0;
    }
    .pill-group { display:flex; align-items:center; flex:0 0 auto; }
    .pill-group + .pill-group { border-left:1px solid var(--grey-pale); }
    .pill-group i {
      padding:0 12px; font-style:normal; font-size:var(--t-fine); letter-spacing:.14em;
      text-transform:uppercase; color:var(--grey-mid); white-space:nowrap;
    }
    .pill {
      border:0; background:none; padding:14px 13px; cursor:pointer;
      font-size:var(--t-fine); letter-spacing:.12em; text-transform:uppercase;
      color:var(--grey-dark); white-space:nowrap;
    }
    .pill:hover { color:var(--ink); }
    .pill.is-on { color:var(--code); box-shadow:inset 0 -2px 0 var(--code); }
    .pill:focus-visible { outline:1px solid var(--line); outline-offset:-3px; }
    .gallery figcaption, .viewer figcaption {
      padding:18px 2px 0; font-size:var(--t-small); line-height:1.6; color:var(--grey-dark);
    }
    .gallery figcaption:empty { display:none; }
    .viewer-frame { cursor:grab; }
    .viewer-frame.is-over { cursor:pointer; }
    .viewer-frame.is-dragging { cursor:grabbing; }
    .viewer-canvas { position:absolute; inset:0; z-index:1; display:block; width:100%; height:100%; touch-action:none; }
    .viewer-canvas:focus-visible { outline:1px solid var(--code); outline-offset:-4px; }
    /* Keep the rendered plate as a no-JS fallback; the live canvas must sit above it. */
    .drawing-render { position:absolute; inset:0; z-index:0; width:100%; height:100%; object-fit:contain; pointer-events:none; }
    .viewer-status {
      position:absolute; z-index:4; left:0; right:0; bottom:0; margin:0; padding:9px 12px;
      background:var(--sheet); border-top:1px solid var(--grey-pale);
      font-size:var(--t-fine); letter-spacing:.12em; text-transform:uppercase; color:var(--grey-dark);
    }
    .viewer-tip {
      position:absolute; z-index:3; min-width:160px; max-width:240px; padding:11px 13px;
      background:var(--sheet); border:1px solid var(--line); pointer-events:none;
    }
    .viewer-tip b { display:block; color:var(--code); font-size:var(--t-note); letter-spacing:.08em; }
    .viewer-tip span { display:block; font-size:var(--t-fine); line-height:1.5; }
    .viewer-tip .tip-name { margin:3px 0 6px; text-transform:uppercase; letter-spacing:.1em; color:var(--grey-dark); }
    .viewer-tip .tip-size { color:var(--dim-ink); }

    /* Unit drawings. */
    .drawing-grid {
      display:grid; grid-template-columns:1fr 1fr; gap:44px 40px; margin-top:36px;
    }
    .unit { display:flex; flex-direction:column; break-inside:avoid; }
    .unit > header { display:flex; gap:14px; align-items:baseline; margin-bottom:8px; }
    .unit-letter { color:var(--code); font-size:var(--t-mark); letter-spacing:.14em; }
    .unit-face { display:flex; margin-left:auto; border:1px solid var(--grey-light); }
    .unit-face button {
      border:0; background:var(--sheet); padding:7px 9px; cursor:pointer;
      color:var(--grey-dark); font-size:var(--t-fine); letter-spacing:.1em;
      text-transform:uppercase;
    }
    .unit-face button + button { border-left:1px solid var(--grey-light); }
    .unit-face button.is-on { color:var(--code); box-shadow:inset 0 -2px 0 var(--code); }
    .unit-face button:focus-visible { outline:1px solid var(--line); outline-offset:-3px; }
    .unit[data-face="cladding"] .plate .member,
    .unit[data-face="cladding"] .plate .under,
    .unit[data-face="cladding"] .plate .ghost,
    .unit[data-face="cladding"] .plate .mark { opacity:.14; }
    .unit[data-face="frame"] .plate .cladding-code { opacity:0; }
    .unit[data-face="cladding"] .plate .cladding-code { opacity:1; }
    .unit[data-face="left"] .perspective-right { display:none; }
    .unit[data-face="left"] .perspective-left { display:block; }
    .unit[data-face="right"] .perspective-right { display:block; }
    .unit[data-face="right"] .perspective-left { display:none; }
    .unit[data-face="frame"] .screw-cladding { opacity:0; }
    .unit[data-face="cladding"] .screw-frame { opacity:0; }
    .unit-steps { margin-top:16px; padding-top:14px; border-top:1px solid var(--grey-pale); }
    .unit-steps ol { margin:10px 0 0; padding-left:22px; }
    .unit-steps li { margin-bottom:8px; font-size:var(--t-small); line-height:1.55; }
    .unit-steps li:last-child { margin-bottom:0; }
    .code-strip { display:flex; flex-wrap:wrap; gap:4px 12px; padding:14px 0 0; font-size:var(--t-fine); }
    .stack-check {
      display:flex; align-items:center; gap:10px; margin-top:16px; padding-top:14px;
      border-top:1px solid var(--grey-pale); font-size:var(--t-fine); letter-spacing:.14em;
      text-transform:uppercase; color:var(--grey-dark); cursor:pointer;
    }

    .set-foot {
      display:flex; flex-wrap:wrap; align-items:flex-start; justify-content:space-between;
      gap:20px; margin-top:clamp(24px,4vw,56px); padding:24px clamp(24px,3vw,48px);
      background:var(--sheet); border:1px solid var(--line);
    }
    .set-foot p { font-size:var(--t-small); color:var(--grey-dark); }
    .set-foot-copy { display:flex; flex-direction:column; align-items:flex-start; gap:20px; }
    .set-foot-nav { display:flex; flex-wrap:wrap; gap:12px; align-items:flex-start; }
    .set-foot-link {
      display:inline-flex; align-items:center; justify-content:space-between; gap:18px;
      min-height:56px; padding:12px 16px; border:1px solid var(--line);
      color:inherit; font-size:var(--t-fine); letter-spacing:.14em;
      text-transform:uppercase; text-decoration:none;
    }
    .set-foot-link .story-arrow { width:20px; height:20px; }
    .set-foot-link:hover, .set-foot-link:focus-visible {
      background:var(--code); border-color:var(--code); color:#fff; outline:0;
    }
    .reset {
      margin-top:0; border:1px solid var(--line); background:none; color:var(--ink);
      padding:11px 18px; font-size:var(--t-fine); letter-spacing:.14em; text-transform:uppercase; cursor:pointer;
    }
    .reset:hover, .reset:focus-visible { background:var(--code); border-color:var(--code); color:#fff; outline:0; }

    @media (max-width:1080px) { .view-grid, .drawing-grid { grid-template-columns:1fr; } }
    @media (max-width:720px) {
      :root { --t-fine:.6rem; --t-small:.68rem; --t-mark:.73rem; --t-note:.8rem; }
      .masthead-top { grid-template-columns:1fr; gap:28px; }
      .story-nav, .progress-grid, .started-figure-pair { grid-template-columns:1fr; }
      .story-link + .story-link { border-left:0; border-top:1px solid var(--grey-pale); }
      .story-link { justify-content:space-between; text-align:left; }
      .story-link .story-link-copy { align-items:flex-start; order:1; }
      .story-link .story-arrow { order:2; }
      /* One row per group, pills wrapping inside it, so nothing sits off-screen. */
      .view-controls { flex-direction:column; }
      .pill-group { flex-wrap:wrap; width:100%; }
      .pill-group + .pill-group { border-left:0; border-top:1px solid var(--grey-pale); }
      .pill-group i { flex:0 0 100%; padding:10px 12px 2px; }
      .pill { padding:10px 12px; }
    }
    @media print {
      /* The head of air belongs to the page box, not to the sheet: padding only
         reaches the first page a sheet fragments onto, so a story page that ran
         over opened its second page hard against the trim. */
      @page { size:A4 landscape; margin:14mm 9mm 10mm; }
      body { background:#fff; font-size:8.4pt; }
      .set { width:100%; padding:0; }
      .sheet, .masthead { border:0; padding:0; margin:0; }
      .sheet { break-before:page; }
      /* The set ends on its last sheet; nothing may push an empty page after it. */
      .sheet:last-of-type { break-after:auto; }
      .view-controls, .reset, .viewer-status, .viewer-tip, .set-foot { display:none; }
      .story-nav { display:none; }
      .view-grid { grid-template-columns:1fr; }
      /* The title sheet carries the drawn model, not the photographs. The
         gallery only returns if the canvas never produced a still. */
      .gallery, .viewer { display:none; }
      body.has-print-model .viewer { display:block; }
      body:not(.has-print-model) .gallery { display:block; }
      .viewer-frame { display:none; }
      /* The still carries its own width and height, so a pair of max- bounds
         would be applied one at a time and stretch the model across the sheet.
         State one side and let the other follow the drawing's ratio. The height
         is every millimetre the title block and the caption leave on the page;
         a grid row would say the same thing but Chrome does not shrink an `fr`
         row while it is paginating, and the model runs off the foot. */
      .viewer-print { display:block; margin:0 auto; width:auto; height:104mm; max-width:100%; }
      .viewer figcaption { text-align:center; }
      .on-screen { display:none; }
      .on-paper { display:inline; }
      /* The frame is square on screen; on paper it must not eat a whole sheet. */
      .view-frame { aspect-ratio:auto; height:auto; border:0; background:none; text-align:center; }
      .shot { position:static; width:auto; height:auto; max-width:100%; max-height:96mm; }
      .shot:not(.is-on) { display:none; }
      .gallery figcaption { padding-top:8px; }
      /* Keep the title block and main views on one sheet. The sheet ends on a
         page break, so the page margin is already the air under the model and
         padding here would only cost the drawing height. */
      .masthead { padding-bottom:0; break-after:page; }
      /* The story pages carry a title bar, not a title sheet: nothing is drawn
         beside it, so a page of its own printed all but empty. It rides on the
         head of its own sheet instead. */
      .masthead-progress { break-after:auto; padding-bottom:8mm; }
      .masthead-progress + .sheet { break-before:auto; }
      .masthead .view-grid { margin-top:5mm; }
      .masthead .view-frame { max-height:65mm; }
      .masthead h1 { margin-bottom:8px; }
      caption { padding-bottom:7px; }
      th, td { padding:6px 10px; }
      .title-block dt, .title-block dd { padding:5px 10px; }
      .note { --note-pad:16px; margin:16px 0; padding:12px var(--note-pad); }
      .sheet-head { margin-bottom:20px; }
      .sheet-head h2 { padding-bottom:10px; }
      .sheet-note { margin-top:12px; }
      .table-scroll, .stock-list { margin-top:18px; }
      .stock-scroll, .table-scroll { overflow:visible; }
      .stock-track { min-width:0; height:auto; }
      /* Paper has no scroller to clip into: an offcut label centred on a
         hairline waste block would print off the edge of the sheet, so the
         last one on a track hangs from its right end instead. */
      .stock-waste span { left:auto; right:0; transform:none; }
      /* One unit, one sheet. Each unit is built standalone, so the sheet a
         builder carries to the bench holds its drawing, its steps and its codes
         together. The unit is exactly one page tall and the drawing takes every
         millimetre the steps beside it leave, so no plate is ever guessed at a
         height and no drawing is ever split across a page. */
      /* No top margin: every unit already opens its own sheet, and 8mm of it
         would push the first unit past the page and orphan its header. The
         height is the page box, which the page margin has already inset. */
      .drawing-grid { display:block; margin-top:0; }
      .unit {
        display:grid; grid-template-columns:1fr 74mm;
        grid-template-rows:auto 1fr auto auto; gap:6mm 8mm;
        height:184mm; break-before:page;
      }
      .unit > header { grid-column:1 / -1; }
      .unit .drawing {
        grid-column:1; grid-row:2 / span 3;
        display:flex; flex-direction:column; min-height:0;
      }
      .unit .drawing .plate { flex:1 1 auto; min-height:0; }
      .unit .unit-steps { grid-column:2; grid-row:2; }
      .unit .code-strip { grid-column:2; grid-row:3; align-content:end; }
      .unit .stack-check { grid-column:2; grid-row:4; }
      /* A drawing set letters its caption on one line and keeps the note under
         it; stacked on paper the caption would eat the drawing's height. */
      .drawing figcaption { padding:8px 12px 0; }
      .drawing-name, .drawing-ref { display:inline; margin-top:0; }
      .drawing-ref::before { content:" · "; }
      .drawing-note { margin-top:5px; }
      .unit-face { display:none; }
      .unit .screw-layer { opacity:1 !important; }
      .code-strip { padding-top:7px; }
      .stack-check { margin-top:8px; padding-top:7px; }
      .drawing, .unit, .stock, .note { break-inside:avoid; }
      /* A photograph or a source drawing prints whole, with its caption under
         it. `break-inside` is only honoured while a block still fits the page,
         so each figure is bound on its height first: the image states one side
         and takes the ratio for the other, the way the model still does. */
      .started-figure, .started-figure-pair, .progress-photo, .progress-video-figure { break-inside:avoid; }
      .started-story { gap:10mm; margin-top:8mm; }
      .started-figure img { width:auto; height:auto; max-width:100%; max-height:118mm; margin:0 auto; }
      .started-figure-pair { gap:8mm; align-items:start; }
      .progress-grid { gap:8mm; margin-top:8mm; }
      .progress-photo-frame { width:auto; height:130mm; max-width:100%; margin:0 auto; }
      .started-figure figcaption, .progress-photo figcaption { padding:5mm 0 0; }
      .progress-photo-note { margin-top:4px; }
      .progress-video-figure { display:none; }
      a { text-decoration:none; }
    }
"""


def guide_html(
    design: Design,
    beam_stock_length: float = 4200,
    cladding_stock_length: float = 4500,
    kerf: float = DEFAULT_KERF,
) -> str:
    beams = beam_pieces(design)
    boards = cladding_pieces(design)
    beam_stocks = pack_stock(beams, beam_stock_length, kerf)
    panel_stocks = panel_stock_plan(boards, cladding_stock_length, kerf)
    all_pieces = beams + boards
    code_map = {piece.code: piece for piece in all_pieces}
    first_panel_length = round(design.door_height, 1)
    last_panel_length = min(round(piece.length, 1) for piece in boards)
    roof_slope = math.hypot(design.roof_run, design.roof_rise)
    roof_plan_depth = (
        roof_slope + 2 * design.frame
    ) * design.roof_run / roof_slope + design.frame * design.roof_rise / roof_slope
    roof_side_overhang = (1050 - design.width) / 2
    roof_end_overhang = (1085 - roof_plan_depth) / 2

    plates = module_plates(design, boards)
    fields = panels(boards)
    side_steps = {}
    for letter, key, edge in (
        ("C", "left_wall", "LSC"),
        ("D", "right_wall", "RSC"),
    ):
        field = fields[key]
        side_steps[letter] = (
            f"Build the frame. Match its diagonals before you fix {edge}1 to {edge}7.",
            f"Fix the square {edge} boards from front to rear. Align their lower and front edges.",
            (
                f"Mark {fmt(field.pieces[0].finished_long or field.blank)} at the front "
                f"and {fmt(field.pieces[-1].finished_short or field.blank)} at the rear. "
                "Set the circular-saw guide and make one gang cut after the boards are fixed."
            ),
            (
                f"Use the rear frame edge to set the circular-saw guide. Cut the estimated "
                f"{fmt(field.trim)} overhang, then cut the {fmt(design.frame)} × "
                f"{fmt(design.frame)} bottom-front notch."
            ),
            "Do not pre-cut the roof reliefs. Hang and close the roof, then cut only to the scribe.",
        )
    unit_steps = {
        "A": (
            "Lay RBH1 and RBH2 around RBS1 and RBS2. Center RBC1. Match the diagonals, then place the frame screw marks.",
            (
                f"Center the metal sheet with {fmt(roof_side_overhang)} at each side and "
                f"{fmt(roof_end_overhang)} at the front and rear."
            ),
            "Fit the moving hinge leaf. After the shell is square, fit the fixed leaf and hang the roof.",
        ),
        "B": (
            "Build the DBV and DBH frame. Fit DBD1 and match the diagonals.",
            "Fix DCB1 to DCB9 on the inside face. Align DCB1 with the left frame edge.",
            (
                f"Use the right frame edge to set the circular-saw guide. Cut the estimated "
                f"{fmt(fields['door_panel'].trim)} overhang after the boards are fixed."
            ),
            (
                f"Cut the two top reliefs shown. Fit the moving hinge leaves, then hang the door "
                f"with a {fmt(design.hinge_gap)} gap after the shell is square."
            ),
        ),
        "C": side_steps["C"],
        "D": side_steps["D"],
        "E": (
            "Build BWH1 and BWH2 with BWD1. Install this bare frame between the two side units.",
            "Attach the left and right side units to the back unit with the indicated beam screws. Drive from the rear posts into BWH1 and BWH2 at each marked landing.",
            "Fix BWC1 to BWC8 inside the side cladding. Align BWC1 with the left landing mark.",
            (
                f"Use the right landing mark to set the circular-saw guide. Cut the estimated "
                f"{fmt(fields['back_wall'].trim)} overhang after the boards are fixed."
            ),
        ),
        "F": (
            (
                f"Brace the left and right units upright. Keep the bottom of LSH1, RSH1, and BWH1 "
                f"{fmt(design.leg_extension)} mm above ground while you install the back frame between them."
            ),
            "Fit FBB1 between BWH1, FBS1 and FBS2 between LSH1 and RSH1, and FBH1 across the front opening. Keep all four beams square and flush with the shell frame.",
            (
                "Drive two 6 × 120 mm screws from FBB1 through the back wall into BWH1, "
                "one 100 mm from each end. Drive two from FBS1 into LSH1 and two from "
                "FBS2 into RSH1, all from inside the structure outwards. Then drive one "
                "centred screw from each outside side rail into FBH1."
            ),
            f"Install FBH1 across the front at the {fmt(design.leg_extension)} leg datum. Measure the finished frame before the final screws.",
        ),
        "G": (
            "Fix FCB1 to FCB8 to the installed bearers. Align FCB1 with the left bearer edge.",
            (
                f"Use the right bearer edge to set the circular-saw guide. Cut the estimated "
                f"{fmt(fields['floor'].trim)} overhang after the boards are fixed."
            ),
            "Lower the finished deck into the square shell. Fasten its front edge to FBH1.",
        ),
        "H": (
            (
                "Build the removable 852 mm seat box from SBH1, SBH2, SBS1–SBS4. "
                f"Keep {fmt(design.seat_box_clearance / 2)} mm clearance at each side."
            ),
            (
                f"Fix STB1 to STB{fields['seat_top'].count} across the top frame, "
                "with the board ends supported by SBS3 and SBS4."
            ),
            (
                f"Cut the estimated {fmt(fields['seat_top'].trim)} overhang. Then cut the "
                f"{fmt(design.seat_hole_width)} × {fmt(design.seat_hole_depth)} opening."
            ),
            "Use the two outer support beams for the board screw rows. Make sure the opening clears the inner bearers and rails. Seal every fresh cladding cut.",
        ),
        "I": (
            "With the floor deck, sides, and back attached, place SBB1 directly under SBH1 and SBB2 directly under SBH2.",
            f"Set the upper edge of both support beams {fmt(design.seat_support_top - design.floor_top)} mm above the floor deck: 397 mm front-panel height minus 45 mm seat-box beam height.",
            "Drive one 6 × 120 mm screw from each side exterior into the centre of each support beam. Check the front beam face against the dimension on A-409.",
        ),
        "J": (
            "Lower the centred 852 mm seat box onto SBB1 and SBB2. Leave the support beams fixed to the shell so the box can lift out as one assembly.",
            f"Check SBB1 and SBF1 on the shared {fmt(design.seat_front_support_from_back)} mm-from-back datum before the front boards are fixed.",
            "Use the right/left toggle to check both outside screw pairs and confirm the two side clearances before final finishing.",
        ),
        "K": (
            "Lay SFB1 to SFB8 as individual boards. Keep their vertical joints in the order shown.",
            f"Trim the joined field to the {fmt(design.interior_width)} mm before fixing.",
            "Fix every board to SBF1 at floor level and SBB1 under the seat box. The two screw rows are shown on the drawing.",
        ),
    }
    module_cards = []
    for letter, title, prefixes in MODULES:
        codes = [
            code
            for code in code_map
            if any(code.startswith(prefix) for prefix in prefixes)
        ]
        codes.sort()
        steps = "".join(f"<li>{step}</li>" for step in unit_steps[letter])
        if letter == "J":
            face_controls = (
                f'<div class="unit-face" data-unit-face="{letter}" role="group" '
                f'aria-label="{title} drawing layer">'
                '<button class="is-on" type="button" data-face="right" '
                'aria-pressed="true">Right side</button>'
                '<button type="button" data-face="left" '
                'aria-pressed="false">Left side</button></div>'
            )
        elif letter in "BCDEH":
            face_controls = (
                f'<div class="unit-face" data-unit-face="{letter}" role="group" '
                f'aria-label="{title} drawing layer">'
                '<button class="is-on" type="button" data-face="frame" '
                'aria-pressed="true">Frame</button>'
                '<button type="button" data-face="cladding" '
                'aria-pressed="false">Cladding</button></div>'
            )
        else:
            face_controls = ""
        face = "right" if letter == "J" else "cladding" if letter in "GK" else "frame"
        module_cards.append(f"""
          <article class="unit" id="unit-{letter.lower()}" data-face="{face}">
            <header><span class="unit-letter">Stack {letter}</span><div><h3>{title}</h3></div>{face_controls}</header>
            {plates[letter]}
            <div class="unit-steps"><h4>Assembly</h4><ol>{steps}</ol></div>
            <div class="code-strip">{"".join(f'<b class="code">{code}</b>' for code in codes)}</div>
            <label class="stack-check"><input type="checkbox" data-check="unit-{letter.lower()}"> Unit complete</label>
          </article>""")

    beam_stock_html = "".join(
        stock_bar(f"B{index:02d}", stock, beam_stock_length, kerf, design.frame * 2)
        for index, stock in enumerate(beam_stocks, 1)
    )
    panel_stock_html = "".join(
        stock_bar(f"P{index:02d}", stock, cladding_stock_length, kerf, BOARD_WIDTH * 2)
        for index, stock in enumerate(panel_stocks, 1)
    )
    first_panel_stocks = [
        stock
        for stock in panel_stocks
        if any(round(piece.length, 1) == first_panel_length for piece in stock)
    ]
    hardware_rows = "".join(
        f"<tr><td>{use}</td><td>{fastener}</td></tr>"
        for use, fastener in HARDWARE_SCHEDULE
    )

    return f"""<!doctype html>
<!--
THESIS: The guide is the drawing set itself, numbered sheet by numbered sheet; it refuses the dashboard and the cutting-ticket poster alike.
OWN-WORLD: White sheets on a grey ground, one monoline face at one weight, black line work in four weights, red for part codes, blue for dimensions, hatching for cut timber.
STORY: See the building, cut by batch, then build and trim each lettered unit.
FIRST VIEWPORT: Title block and main views; numbered sheets run A-200 to A-400.
FORM: Swedish construction drawing set, pinned by the brief to drawing-sides.png; captions, drawing numbers, and title block follow that sheet.
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DASS · Working drawing</title>
{
        social_head(
            "DASS · Can AI build a toilet yet?",
            "An open parametric CAD model, cut list, and interactive workshop guide for a small outdoor toilet.",
        )
    }
  <script type="importmap">
  {{"imports":{{"three":"./vendor/three.module.min.js","three/addons/":"./vendor/addons/"}}}}
  </script>
  <style>{STYLE}</style>
</head>
<body>
<svg class="defs" aria-hidden="true" focusable="false"><defs>
  <pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
    <line x1="0" y1="0" x2="0" y2="7" stroke="#7f7f7f" stroke-width="1"/>
  </pattern>
  <pattern id="hatch-fine" width="5" height="5" patternTransform="rotate(135)" patternUnits="userSpaceOnUse">
    <line x1="0" y1="0" x2="0" y2="5" stroke="#b7b7b7" stroke-width="1"/>
  </pattern>
</defs></svg>
<main class="set">
  <header class="masthead" id="top">
    <div class="masthead-top">
      <div>
        <span class="sheet-no">WORKING DRAWING</span>
        <h1>Can AI build a toilet yet?</h1>
        <p class="masthead-sub">An experiment in re-drawing a technical drawing as an editable parametric CAD model with Claude and Codex.</p>
      </div>
      <dl class="title-block">
        <div><dt>Project</dt><dd>DASS</dd></div>
        <div><dt>Issue</dt><dd>2026-07-30</dd></div>
        <div><dt>Architect</dt><dd><a href="https://www.instagram.com/hannes.soderquist/"
          target="_blank" rel="noopener noreferrer">@hannes.soderquist</a></dd></div>
        <div><dt>Code</dt><dd><a href="https://x.com/feelepxyz"
          target="_blank" rel="noopener noreferrer">@feelepxyz</a></dd></div>
        <div><dt>Source</dt><dd><a href="https://github.com/feelepxyz/dass"
          target="_blank" rel="noopener noreferrer"><svg class="source-icon" viewBox="0 0 24 24"
          aria-hidden="true"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.28-.36
          6.72-1.61 6.72-7.25a5.65 5.65 0 0 0-1.5-3.95 5.4 5.4 0 0 0-.14-2.95
          S17.9-.03 15 1.85a13.38 13.38 0 0 0-7 0C5.1-.03 3.92.35 3.92.35
          a5.4 5.4 0 0 0-.14 2.95 5.65 5.65 0 0 0-1.5 3.95c0 5.63 3.44 6.88
          6.72 7.25A4.8 4.8 0 0 0 8 18v4"/><path d="M8 19c-3 .9-5-1.5-5-1.5"/>
          </svg>GitHub</a></dd></div>
        <div><dt>Units</dt><dd>Millimetres</dd></div>
        <div><dt>Kerf</dt><dd>{fmt(kerf)} mm per cut</dd></div>
        <div><dt>Sheets</dt><dd>A-200 to A-400</dd></div>
      </dl>
    </div>
{story_nav("drawing")}
    <div class="view-grid" id="render">
      {gallery_html()}
      {viewer_html()}
    </div>
  </header>

  <section class="sheet" id="beams">
    <div class="sheet-head"><span class="sheet-no">Sheet A-200</span><h2>Structural timber</h2></div>
    <div class="note material-spec">
      <h3>Material</h3>
      <p>Frame timber, 45 × 45 × {fmt(beam_stock_length)} mm. Quantity: {
        len(beam_stocks)
    } lengths.</p>
      <p>The {len(beam_stocks)} beam stock lengths below are named B01 to B{
        len(
            beam_stocks
        ):02d}. Each cut diagram shows the marked beam pieces cut from that length.</p>
    </div>
    <p class="sheet-note">Cut every piece at one stop setting before you change the stop.
    A batch that reaches the end of a stock length continues on the next length.</p>
    <p class="sheet-note">These sheets are exact only for this material size. One {
        fmt(kerf)
    } mm kerf is used for every piece.</p>
    <p class="sheet-note">If your material ends are rough, shave a small amount off from each piece first.</p>
    <div class="stock-list">{beam_stock_html}</div>
  </section>

  <section class="sheet" id="panels">
    <div class="sheet-head"><span class="sheet-no">Sheet A-300</span><h2>Råspont (matchboard/V-groove cladding)</h2></div>
    <div class="note material-spec">
      <h3>Material</h3>
      <p>Råspont (matchboard/V-groove cladding), 120 × 23 × {
        fmt(cladding_stock_length)
    } mm. Quantity: {len(panel_stocks)} lengths.</p>
      <p>The {len(panel_stocks)} cladding stock lengths below are named P01 to P{
        len(
            panel_stocks
        ):02d}. Each cut diagram shows the marked boards cut from that length.</p>
    </div>
    <p class="sheet-note">The first {len(first_panel_stocks)} stock lengths release all
    twenty-three {
        fmt(first_panel_length)
    } blanks. Label the P01 to P03 remainders. Keep them for the final {
        fmt(last_panel_length)
    } pass. Fourteen side boards come next, then nine door boards, at one stop setting.</p>
    <p class="sheet-note">These sheets are exact only for this material size. One {
        fmt(kerf)
    } mm kerf is used for every piece.</p>
    <p class="sheet-note">If your material ends are rough, shave a small amount off from each piece first.</p>
    <div class="stock-list">{panel_stock_html}</div>
    <p class="sheet-note" id="fields">Gaps between boards change the joined width. Fix each board to its unit frame before you mark any final edge. Use the frame edge to set the circular-saw guide. Cut only after the boards are fixed. Sheet A-400 shows each estimated overhang and cut line.</p>
  </section>

  <section class="sheet" id="stacks">
    <div class="sheet-head"><span class="sheet-no">Sheet A-400</span><h2>Unit drawings and assembly</h2></div>
    <p class="sheet-note">Each drawing is an orthographic projection off the model. Use the Frame and Cladding controls to inspect the fastening layers and the fitted fields.</p>
    <p class="sheet-note">Black frame paths are measured 120 mm screws: they start on the source beam and finish in the centre of the receiving section. Diagonal paths follow the diagonal beam from its mitred end.</p>
    <p class="sheet-note"><span class="on-screen">Use the Frame and Cladding controls to
    change drawing emphasis. The printed drawing keeps every cut line, trim label, and
    notch note visible.</span><span class="on-paper">Each unit is drawn on its own sheet,
    with its assembly steps and its codes beside it.</span></p>
    <div class="note" id="hardware">
      <h3>Assembly hardware</h3>
      <p>Use these fasteners for the timber assembly.</p>
      <div class="table-scroll"><table>
        <thead><tr><th>Use</th><th>Fastener</th></tr></thead>
        <tbody>{hardware_rows}</tbody>
      </table></div>
    </div>
    <div class="drawing-grid">{"".join(module_cards)}</div>
  </section>

  <footer class="set-foot">
    <div class="set-foot-copy">
      <p>The checks are saved in this browser. Print removes the controls and keeps
      every code and dimension.</p>
      <button class="reset" type="button">Clear all checks</button>
    </div>
    <nav class="set-foot-nav" aria-label="Related pages">
      <a class="set-foot-link" href="how-its-going.html#story-nav">
        <span>How it's going</span>{story_arrow("right")}
      </a>
    </nav>
  </footer>
</main>
<script>
  const key = "dass-cut-guide-checks-v1";
  const saved = new Set(JSON.parse(localStorage.getItem(key) || "[]"));
  document.querySelectorAll("[data-check]").forEach(input => {{
    input.checked = saved.has(input.dataset.check);
    input.addEventListener("change", () => {{
      input.checked ? saved.add(input.dataset.check) : saved.delete(input.dataset.check);
      localStorage.setItem(key, JSON.stringify([...saved]));
    }});
  }});
  document.querySelector(".reset").addEventListener("click", () => {{
    saved.clear(); localStorage.removeItem(key);
    document.querySelectorAll("[data-check]").forEach(input => input.checked = false);
  }});
  document.querySelectorAll("[data-unit-face]").forEach(group => {{
    const unit = group.closest(".unit");
    const buttons = [...group.querySelectorAll("[data-face]")];
    buttons.forEach(button => button.addEventListener("click", () => {{
      unit.dataset.face = button.dataset.face;
      buttons.forEach(other => {{
        const active = other === button;
        other.classList.toggle("is-on", active);
        other.setAttribute("aria-pressed", String(active));
      }});
    }}));
  }});
{GALLERY_SCRIPT}
</script>
<script type="module">
{viewer_script(viewer_parts(design, boards))}
</script>
</body>
</html>"""


def started_html() -> str:
    def figure(index: int, loading: str = "eager") -> str:
        asset, _source, title, width, height = STARTED_GALLERY[index]
        return f"""
        <figure class="started-figure">
          <img src="started/{asset}" alt="{html.escape(title)}" width="{width}" height="{height}"
            loading="{loading}" decoding="async">
          <figcaption><span class="started-figure-title">{html.escape(title)}</span></figcaption>
        </figure>"""

    return f"""<!doctype html>
<!--
THESIS: The starting point is a record of the supplied design and the checks that brought its model into agreement; it refuses a generic project timeline.
OWN-WORLD: White sheets on a grey ground, Input Mono lettering, square rules, and the same red/blue drawing-set accents, with source drawings and comparison plates as evidence.
STORY: A supplied outdoor-toilet drawing becomes a reconciled parametric model ready for the workshop.
FIRST VIEWPORT: The project title, three-way phase navigation, and the first source drawing introduce the record before the comparison plates.
FORM: Companion project-notes sheet inside the established Swedish construction drawing set; source images stay whole and follow the README sequence.
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DASS · How it started</title>
{
        social_head(
            "DASS · How it started",
            "From Hannes Söderquist's outdoor-toilet drawing to a reconciled parametric model with Claude, Codex, and CadQuery.",
            "how-it-started.html",
        )
    }
  <style>{STYLE}</style>
</head>
<body>
<main class="set">
  <header class="masthead masthead-progress" id="top">
    <div class="masthead-top">
      <div>
        <span class="sheet-no">PROJECT NOTES</span>
        <h1>Can AI build a toilet yet?</h1>
      </div>
    </div>
{story_nav("started")}
  </header>

  <section class="sheet" id="started">
    <div class="sheet-head"><span class="sheet-no">Project notes 01</span><h2>How it started</h2></div>
    <div class="started-story">
      <p>I wanted to build a compact outdoor toilet for caravan living in the woods. My
      friend <a href="https://www.instagram.com/hannes.soderquist/" target="_blank"
      rel="noopener noreferrer">Hannes Söderquist</a> had drawings for one, but the original
      design uses 50 × 50 mm beams and 120 × 25 mm cladding, sizes that did not match the
      stock in the local shop.</p>
      {figure(0, "eager")}

      <p>I first asked Codex to copy the technical drawing into an editable, programmable
      parametric CAD model using CadQuery and related tools. All CAD edits were done from
      prompts only. The first generated versions had several geometry problems and did not
      match the source design, so I had to do a lot of nudging to keep material from
      clipping into other parts and creating impossible cuts.</p>
      {figure(1)}
      <div class="started-figure-pair">
        {figure(2)}
        {figure(3)}
      </div>

      <p>I then had Codex and Claude add specifications from the technical drawing and make
      comparison cut lists from the dimensions it specified. We kept going until the
      editable model matched the drawing. This was less like asking for a finished model
      and more like correcting a transcription until the geometry, dimensions, and cut
      schedules agreed.</p>

      <p>One cool side-effect of the CAD model was that Codex could run some basic
      structural analysis on the original drawing. It found that the floor boards did
      not have enough support, so we added support beams.</p>

      <p>Once the model matched the drawing, I asked it to change the beam and cladding
      dimensions to the material available in the local shop: 45 × 45 mm beams and
      120 × 23 mm Råspont (matchboard/V-groove cladding). I checked the shop supply and had
      it create detailed cut lists from the available stock. I also changed the shape
      slightly so that each interleaved cladding board has at least 10 mm of trim. The
      board ends therefore do not leave a lip outside the frame.</p>

      <p>From there, the cut schedules follow the material lengths in the shop. The
      optimizer groups equal-length cuts so that they can run in sequence with a stop
      block on the saw. This uses more material than a fully nested plan, but it avoids
      repeated measuring and small length differences between equal pieces.</p>

      <p>The same model then generates assembly instructions that treat the door, roof,
      side walls, back wall, floor, and seat as individual pieces.</p>

      <p>The <a href="cut-guide.html#story-nav">working drawing</a> contains the detailed
      drawings and cut lists for the current material sizes.</p>

      <p>A fastening review then found a join the drawings did not make explicit. A 120 mm
      screw from a vertical member into a rail can occupy the same corner as a screw driven
      from that rail into a diagonal. The door, side, and back diagonals now run corner to
      corner, with mitred ends stopped at the inner faces of the vertical members. The
      fastening audit models both screw paths and keeps this clearance as a regression check.</p>
    </div>
  </section>

  <footer class="set-foot">
    <p>The starting point is recorded beside the working drawing and the field notes.</p>
    <nav class="set-foot-nav" aria-label="Related pages">
      <a class="set-foot-link" href="cut-guide.html#story-nav">
        <span>Working drawing</span>{story_arrow("right")}
      </a>
    </nav>
  </footer>
</main>
</body>
</html>"""


def progress_html() -> str:
    photos = []
    for index, (asset, _source, title, caption) in enumerate(PROGRESS_GALLERY, 1):
        loading = "eager" if index == 1 else "lazy"
        priority = ' fetchpriority="high"' if index == 1 else ""
        photos.append(f"""
          <figure class="progress-photo">
            <div class="progress-photo-frame">
              <img src="progress/{asset}" alt="{html.escape(title)}" width="3024" height="4032"
                loading="{loading}" decoding="async"{priority}>
            </div>
            <figcaption>
              <span class="progress-photo-title">{index:02d} · {html.escape(title)}</span>
              <span class="progress-photo-note">{html.escape(caption)}</span>
            </figcaption>
          </figure>""")

    video_asset, poster_asset, video_title, video_caption = PROGRESS_VIDEO
    if CLOUDFLARE_STREAM_PLAYER_URL:
        video_player = f"""
              <iframe class="progress-video" src="{html.escape(CLOUDFLARE_STREAM_PLAYER_URL, quote=True)}"
                title="{html.escape(video_title, quote=True)}" width="720" height="1280"
                loading="lazy"
                allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture;"
                allowfullscreen></iframe>"""
    else:
        video_player = f"""
              <video class="progress-video" controls playsinline preload="none"
                poster="progress/{poster_asset}" width="720" height="1280"
                aria-label="{html.escape(video_title)}">
                <source src="progress/{video_asset}" type="video/mp4">
                <a href="progress/{video_asset}">Download the workshop video</a>
              </video>"""
    video = f"""
          <figure class="progress-video-figure">
            <div class="progress-video-frame">
{video_player}
            </div>
            <figcaption>
              <span class="progress-photo-title">Workshop clip · {html.escape(video_title)}</span>
              <span class="progress-photo-note">{html.escape(video_caption)}</span>
            </figcaption>
          </figure>"""

    return f"""<!doctype html>
<!--
THESIS: The progress page is a field-notes sheet beside the drawing set; it refuses a project dashboard and keeps the build evidence close to the work.
OWN-WORLD: White sheets on a grey ground, Input Mono lettering, square rules, and the same red/blue drawing-set accents, with photographs as the material record.
STORY: The drawing becomes stock on a saw, then marked pieces on the workshop bench.
FIRST VIEWPORT: The project title, phase navigation, and the first saw-setup photograph are visible before the second field note.
FORM: Companion field-notes sheet inside the established Swedish construction drawing set; supplied photographs and one workshop clip are ordered by build sequence.
-->
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DASS · How it's going</title>
{
        social_head(
            "DASS · How it's going",
            "Real-world build notes as the parametric outdoor-toilet drawing becomes labelled timber and workshop units.",
            "how-its-going.html",
        )
    }
  <style>{STYLE}</style>
</head>
<body>
<main class="set">
  <header class="masthead masthead-progress" id="top">
    <div class="masthead-top">
      <div>
        <span class="sheet-no">FIELD NOTES</span>
        <h1>Can AI build a toilet yet?</h1>
      </div>
    </div>
{story_nav("going")}
  </header>

  <section class="sheet" id="progress">
    <div class="sheet-head"><span class="sheet-no">Field notes 01</span><h2>How it's going</h2></div>
    <p class="sheet-note">Model 0.1.4 · cladding fixings are centred after trimming and clear the beam screws.</p>
    <div class="note model-changelog">
      <h3>Model changelog</h3>
      <ul>
        <li><time datetime="2026-08-02">2026-08-02 · 0.1.4</time> Terminal-board cladding fixings are centred after trimming, and edge fixings clear the modeled beam-screw paths.</li>
        <li><time datetime="2026-08-02">2026-08-02 · 0.1.3</time> The interactive line, textured, fallback, and print views share the in-situ render's perspective, scale, and position.</li>
        <li><time datetime="2026-08-02">2026-08-02 · 0.1.2</time> Stack H carries all eight beam screws, and Stack J plus the final open SVG use the same model-aligned isometric projection.</li>
        <li><time datetime="2026-08-02">2026-08-02 · 0.1.1</time> Seat-top boards run across the removable box, with outer supports and two additional frame screws, to improve integrity around the opening.</li>
        <li><time datetime="2026-08-02">2026-08-02 · 0.1.1</time> The seat box is removable at 852 mm, with fixed shell supports, so the box remains serviceable while its front and rear edges stay supported.</li>
        <li><time datetime="2026-07-31">2026-07-31 · 0.1.1</time> Diagonal brace ends and screw paths avoid the frame corners, so the fastening audit can report clear nominal paths.</li>
        <li><time datetime="2026-07-31">2026-07-31 · 0.1.0</time> The model gained fastening and angle checks, so workshop assembly can be checked against the measured frame.</li>
      </ul>
    </div>
    <div class="progress-grid">{"".join(photos[:3])}{video}{"".join(photos[3:])}</div>
  </section>

  <footer class="set-foot">
    <p>Progress follows the drawing. More field notes will be added as the build moves on.</p>
    <nav class="set-foot-nav" aria-label="Related pages">
      <a class="set-foot-link" href="how-it-started.html#story-nav">
        <span>How it started</span>{story_arrow("right")}
      </a>
    </nav>
  </footer>
</main>
<script>
  const workshopVideo = document.querySelector(".progress-video");
  if (workshopVideo instanceof HTMLVideoElement && "IntersectionObserver" in window) {{
    const pauseWhenOutOfView = new IntersectionObserver(([entry]) => {{
      if (!entry.isIntersecting && !workshopVideo.paused) workshopVideo.pause();
    }}, {{ threshold: 0.1 }});
    pauseWhenOutOfView.observe(workshopVideo);
  }}
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/cut-guide.html"))
    parser.add_argument("--beam-stock-length", type=float, default=4200)
    parser.add_argument("--cladding-stock-length", type=float, default=4500)
    parser.add_argument("--kerf", type=float, default=DEFAULT_KERF)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        guide_html(
            Design(),
            args.beam_stock_length,
            args.cladding_stock_length,
            args.kerf,
        )
    )
    args.output.with_name("how-it-started.html").write_text(started_html())
    args.output.with_name("how-its-going.html").write_text(progress_html())
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
