"""Generate a printable, model-derived cutting and assembly guide."""

from __future__ import annotations

import argparse
import html
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from dass import Design, box_at, build, side_panel
from generate_cutlists import (
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
    "seat_lower_rail": "seat lower front rail",
    "seat_support_left": "seat opening left bearer",
    "seat_support_right": "seat opening right bearer",
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
    ("F", "Floor deck", ("FBB", "FBS", "FCB")),
    ("G", "Shell joint", ("FBH",)),
    ("H", "Seat box", ("SB", "STB", "SFB")),
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
            f'<b>{html.escape(piece.code)}</b><span>{fmt(piece.length)}</span></div>'
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
        f'width:{max(0, waste) / stock_length * 100:.5f}%"><span>{fmt(waste)}</span></div>'
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
          role="img" aria-label="{stock_id}: {'; '.join(f'{p.code}, {fmt(p.length)} millimetres' for p in pieces)}; {fmt(waste)} millimetre offcut">
          {''.join(segments)}
        </div>
      </div>
    </article>"""


def _ordered_batches(groups):
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
            if angle is not None else "90° square"
        )
        # Which stock each code comes off is drawn on the stock bars below, so
        # the batch table carries the saw sequence and nothing else.
        rows.append(
            f"<tr><td class=\"pass\">{step}</td>"
            f"<td class=\"measure\">{fmt(length)}</td><td>{cut}</td>"
            f"<td class=\"marks\">{len(batch)} × "
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

    def __call__(self, point: tuple[float, float, float]) -> Point:
        return (self.u_sign * point[self.u_axis], self.v_sign * point[self.v_axis])


PLAN = View(0, 1, 1, -1, "front edge at the bottom", "plan")
FRONT = View(0, 1, 2, -1, "seen from outside the door", "front elevation")
REAR = View(0, -1, 2, -1, "seen from outside the back wall", "rear elevation")
LEFT = View(1, -1, 2, -1, "front edge to the right", "left elevation")
RIGHT = View(1, 1, 2, -1, "front edge to the left", "right elevation")


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


def outline(solid, view: View) -> list[Point]:
    """Exact projected profile of one part.

    Almost every part is a prism square to the plate, so its own largest face
    gives the profile in order — including the notch in a side field, which a
    convex hull would quietly fill in. Anything tilted out of the plate, such
    as a roof member seen in plan, falls back to its projected hull.
    """
    square_faces = [
        face for face in solid.Faces()
        if abs(face.normalAt().toTuple()[view.depth_axis]) > 0.999
    ]
    if square_faces:
        profile = max(square_faces, key=lambda face: face.Area())
        points = [view(vertex.toTuple()) for vertex in profile.outerWire().Vertices()]
        if len(points) > 2:
            return points
    return convex_hull([view(vertex.toTuple()) for vertex in solid.Vertices()])


def cross_section(solid, view: View, cut: float, slab: float = 0.4) -> list[Point]:
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

    def __init__(self, shapes: list[list[Point]], margin: float = 62.0, pad: float = 0.0):
        points = [point for shape in shapes for point in shape]
        self.umin = min(u for u, _ in points)
        self.vmin = min(v for _, v in points)
        u_span = max(u for u, _ in points) - self.umin
        v_span = max(v for _, v in points) - self.vmin
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

    def label(
        self,
        point: Point,
        text: str,
        css: str = "mark",
        turned: bool = False,
        anchor: str = "middle",
    ) -> None:
        x, y = self.at(point)
        turn = f' transform="rotate(-90 {x:.1f} {y:.1f})"' if turned else ""
        self.add(
            f'<text class="{css}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"'
            f'{turn}>{html.escape(text)}</text>'
        )

    def corner(self, text: str) -> None:
        """Note in the top margin, where nothing else is ever drawn."""
        self.add(
            f'<text class="note-text" x="14" y="28" text-anchor="start">'
            f'{html.escape(text)}</text>'
        )

    def leader(self, target: Point, seat: Point, text: str, anchor: str = "start") -> None:
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
        """Stamp a code mark inside a member, turned when the member is tall.

        Codes are red and underlined, as the reference set letters them.
        """
        us = [u for u, _ in points]
        vs = [v for _, v in points]
        wide = (max(us) - min(us)) * self.scale
        tall = (max(vs) - min(vs)) * self.scale
        if max(wide, tall) < 42:
            return
        turned = tall > wide * 1.4
        # A member sitting on the plate edge would push its code off the sheet,
        # so the mark is held inside the drawable width.
        reach = 0 if turned else len(text) * 5.5
        x = min(max(self.x(sum(us) / len(us)), reach + 4), self.WIDTH - reach - 4)
        middle = (self.umin + (x - self.margin) / self.scale, sum(vs) / len(vs))
        self.label(middle, text, "mark", turned=turned)

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
            x = max(x1, x2) + offset if offset > 0 else min(x1, x2) + offset
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
                self.add(
                    f'<text class="dim-text" x="{x - 8:.1f}" y="{mid:.1f}" '
                    f'text-anchor="middle" transform="rotate(-90 {x - 8:.1f} {mid:.1f})">'
                    f'{html.escape(measure)}</text>'
                )
        else:
            y = max(y1, y2) + offset if offset > 0 else min(y1, y2) + offset
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
                self.add(
                    f'<text class="dim-text" x="{(x1 + x2) / 2:.1f}" y="{y - 9:.1f}" '
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
            f'<svg class="{css}" viewBox="0 0 {self.WIDTH:.0f} {self.height:.0f}" '
            f'role="img" aria-label="{html.escape(title)}: {html.escape(caption)}">'
            f'{"".join(self.body)}'
            f'</svg>'
            f'<figcaption>'
            f'<span class="drawing-name">{html.escape(title.upper())}</span>'
            f'<span class="drawing-ref">{html.escape(number)} · '
            f'{html.escape(caption.upper())}</span>{aside}'
            f'</figcaption>'
            f'</figure>'
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


PANEL_SPECS = (
    ("door_panel", "DCB", "Door field", 0, "fixed to the inside face of the door frame"),
    ("left_wall", "LSC", "Left side field", 1, "gang-cut to the roof pitch after joining"),
    ("right_wall", "RSC", "Right side field", 1, "gang-cut to the roof pitch after joining"),
    ("back_wall", "BWC", "Back wall field", 0, "centred between the rear posts"),
    ("floor", "FCB", "Floor deck", 0, "lands on three bearers and the front rail"),
    ("seat_top", "STB", "Seat top", 0, "oval opening cut after joining"),
    ("seat_front", "SFB", "Seat front field", 0, "closes the seat box down to the floor"),
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
# Reference views: photoreal renders and the model itself
# ---------------------------------------------------------------------------

GALLERY = (
    ("In situ", (
        ("in-situ-open", "Open", ""),
        ("in-situ-closed", "Closed", "The same plate with everything shut."),
    )),
    ("Render", (
        ("open-hero", "Open", "Three-quarter view, door swung clear of the opening."),
        ("open-doorway", "Doorway", "Straight into the opening at standing height."),
        ("open-interior", "Interior", "Down onto the seat box, floor deck, and back wall."),
        ("closed-hero", "Closed", "Three-quarter view of the finished shell."),
        ("closed-rear-quarter", "Rear", "Back wall, rear posts, and the roof overhang."),
        ("closed-above", "Above", "The mono-pitch roof and its sheet overhangs."),
    )),
    ("Elevation", (
        ("flat-front", "Front", "Square-on front elevation, door closed."),
        ("flat-front-open", "Front open", "Square-on with the door swung, showing the opening."),
        ("flat-back", "Back", "Square-on rear elevation."),
        ("flat-left", "Left", "Square-on left side; the cladding falls to the rear."),
        ("flat-right", "Right", "Square-on right side, mirror of the left."),
        ("flat-top", "Top", "Orthographic plan of the roof sheet."),
    )),
)

FIRST_VIEW = GALLERY[0][1][0][0]


def gallery_html() -> str:
    groups = "".join(
        '<span class="pill-group"><i>{}</i>{}</span>'.format(
            html.escape(group),
            "".join(
                f'<button class="pill{" is-on" if name == FIRST_VIEW else ""}" type="button" '
                f'data-view="{name}" aria-pressed="{"true" if name == FIRST_VIEW else "false"}">'
                f'{html.escape(label)}</button>'
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
        f'{"src" if name == FIRST_VIEW else "data-src"}="web-renders/{name}.jpg" '
        f'alt="{html.escape(caption)}" data-caption="{html.escape(caption)}" decoding="async">'
        for group, views in GALLERY for name, _, caption in views
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
          <canvas class="viewer-canvas" aria-label="Interactive model of the finished building"></canvas>
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
        <figcaption>Drag to turn the model. Scroll to zoom. Click a piece to read its code
        and size.</figcaption>
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
const camera = new THREE.PerspectiveCamera(30, 1, 10, 40000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.enablePan = false;
controls.minDistance = 900;
controls.maxDistance = 9000;
controls.maxPolarAngle = Math.PI;
const IN_SITU_CAMERA = Object.freeze({
  aspect: 3 / 4,
  azimuth: -44,
  cameraHeight: 1300,
  distance: 4200,
  frameWidth: 2500,
  offsetX: 0,
});

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

const edgeInk = new THREE.LineBasicMaterial({ color: INK });
const edgeCode = new THREE.LineBasicMaterial({ color: CODE });
const plankInk = new THREE.LineBasicMaterial({ color: INK });

const lineMaterials = new Map();
function lineMaterialFor(key) {
  if (!lineMaterials.has(key)) {
    const tone = PARTS[key] ? PARTS[key].tone : "frame";
    lineMaterials.set(key, new THREE.MeshLambertMaterial({
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
  // The drawn finish wants flat light and no shadow; the material wants a sun.
  sky.intensity = wanted ? 1.5 : 2.6;
  sun.intensity = wanted ? 2.4 : 0;
  fill.intensity = wanted ? 0.7 : 0.35;
  ground.material.opacity = wanted ? 0.22 : 0;
  renderer.shadowMap.enabled = wanted;
  scene.environment = wanted ? environmentMap() : null;
  applyFinish();
  select(selected);
  draw();
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
  for (const group of groupByPart(root, PARTS).values()) {
    if (!group.planked) continue;
    for (const mesh of group.meshes) {
      if (mesh.geometry.index) mesh.geometry = mesh.geometry.toNonIndexed();
    }
    const frame = plankFrame(group);
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
        seams.renderOrder = 2;
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
  await setFinish(finish);
  if (!framed) {
    const box = new THREE.Box3().setFromObject(current);
    const centre = box.getCenter(new THREE.Vector3());
    const azimuth = THREE.MathUtils.degToRad(IN_SITU_CAMERA.azimuth);
    const direction = new THREE.Vector3(Math.sin(azimuth), 0, Math.cos(azimuth));
    const base = new THREE.Vector3(
      centre.x,
      box.min.y + IN_SITU_CAMERA.cameraHeight,
      centre.z,
    );
    camera.position.copy(base).addScaledVector(direction, IN_SITU_CAMERA.distance);
    controls.target.copy(base).addScaledVector(
      new THREE.Vector3(-direction.z, 0, direction.x),
      IN_SITU_CAMERA.offsetX * IN_SITU_CAMERA.frameWidth,
    );
    const horizontal = 2 * Math.atan(
      IN_SITU_CAMERA.frameWidth / 2 / IN_SITU_CAMERA.distance,
    );
    camera.fov = THREE.MathUtils.radToDeg(
      2 * Math.atan(Math.tan(horizontal / 2) / IN_SITU_CAMERA.aspect),
    );
    camera.aspect = IN_SITU_CAMERA.aspect;
    // The composite is a bottom-aligned square crop of its 3:4 photo plate.
    camera.setViewOffset(3, 4, 0, 1, 3, 3);
    camera.lookAt(controls.target);
    camera.updateProjectionMatrix();
    framed = true;
  }
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
  const hit = current ? raycaster.intersectObject(current, true)[0] : null;
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
canvas.addEventListener("pointerdown", (event) => { pressed = [event.clientX, event.clientY]; });
canvas.addEventListener("pointerup", (event) => {
  if (!pressed) return;
  const moved = Math.hypot(event.clientX - pressed[0], event.clientY - pressed[1]);
  pressed = null;
  if (moved > 5) return;
  select(pick(event), event);
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
      camera.aspect = IN_SITU_CAMERA.aspect;
      camera.updateProjectionMatrix();
    }
    ground.visible = camera.position.y >= ground.position.y;
    if (controls.update()) draw();
    renderer.render(scene, camera);
  });
}

controls.addEventListener("change", draw);
new ResizeObserver(draw).observe(frame);
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
        VIEWER_SCRIPT
        .replace("__PARTS__", json.dumps(parts, separators=(",", ":")))
        .replace("__ATLAS__", json.dumps(plank_atlas(), separators=(",", ":")))
    )


def bounds(shape: list[Point]) -> tuple[float, float, float, float]:
    return (
        min(u for u, _ in shape), min(v for _, v in shape),
        max(u for u, _ in shape), max(v for _, v in shape),
    )


def draw_field(
    plate: Plate,
    profile: list[Point],
    solid,
    panel: Panel,
    view: View,
    uid: str,
    label: bool = True,
) -> None:
    """Draw fixed cladding with its nominal on-frame trim still attached."""
    if panel.axis != view.u_axis:
        raise ValueError("the cladding trim must be visible in the unit view")
    plate.shape(profile, "field")
    box = solid.BoundingBox()
    lows = (box.xmin, box.ymin, box.zmin)
    highs = (box.xmax, box.ymax, box.zmax)
    run = ({view.u_axis, view.v_axis} - {panel.axis}).pop()

    terminal = view.u_sign * (lows[panel.axis] + panel.span)
    rough_terminal = view.u_sign * (lows[panel.axis] + panel.joined)
    terminal_points = [
        v for u, v in profile if math.isclose(u, terminal, abs_tol=1e-3)
    ]
    if len(terminal_points) < 2:
        terminal_points = [v for _, v in profile]
    trim_low, trim_high = min(terminal_points), max(terminal_points)
    trim = [
        (terminal, trim_low),
        (rough_terminal, trim_low),
        (rough_terminal, trim_high),
        (terminal, trim_high),
    ]
    plate.shape(trim, "trim")
    plate.line((terminal, trim_low), (terminal, trim_high), "cut")
    plate.label(
        ((terminal + rough_terminal) / 2, (trim_low + trim_high) / 2),
        f"EST. {fmt(panel.trim)} · CUT AFTER FIXING",
        "small",
        turned=True,
    )

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
        plate.label(
            (
                (cut_start[0] + rough_end[0] + cut_end[0]) / 3,
                (cut_start[1] + rough_end[1] + cut_end[1]) / 3,
            ),
            "MARK · GANG CUT AFTER FIXING",
            "small",
        )

    start = len(plate.body)
    for joint in board_joints(panel):
        ends = []
        for far in (False, True):
            point = [0.0, 0.0, 0.0]
            point[panel.axis] = lows[panel.axis] + joint
            point[run] = highs[run] + 20 if far else lows[run] - 20
            point[view.depth_axis] = (lows[view.depth_axis] + highs[view.depth_axis]) / 2
            ends.append(view(point))
        plate.line(*ends, "joint")
    joints = "".join(plate.body[start:])
    del plate.body[start:]
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{plate.x(u):.1f} {plate.y(v):.1f}"
        for index, (u, v) in enumerate(profile)
    )
    plate.add(f'<clipPath id="{uid}"><path d="{path} Z"/></clipPath>')
    plate.add(f'<g clip-path="url(#{uid})">{joints}</g>')
    if label:
        plate.corner(
            f"{panel.codes} · {panel.count} boards · fix rough, then trim to frame"
        )


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


def draw_members(plate: Plate, shapes: dict[str, list[Point]], members: tuple[str, ...]) -> None:
    for name in members:
        plate.shape(shapes[name], "member")
    for name in members:
        plate.code_in(shapes[name], BEAM_CODES.get(name, ""))


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
    plates: dict[str, str] = {}

    def shapes_for(view: View, *names: str) -> dict[str, list[Point]]:
        return {name: outline(parts[name], view) for name in names}

    # A · Roof unit, in plan, with the sheet it carries.
    members = ("roof_left", "roof_right", "roof_front", "roof_back", "roof_middle")
    shapes = shapes_for(PLAN, *members, "roof")
    plate = plate_for(shapes, members, ("roof",))
    draw_members(plate, shapes, members)
    frame_box = bounds([point for name in members for point in shapes[name]])
    sheet = bounds(shapes["roof"])
    plate.dim((sheet[0], sheet[3]), (sheet[2], sheet[3]), 40)
    plate.dim((frame_box[0], frame_box[1]), (frame_box[2], frame_box[1]), -40)
    plate.dim((sheet[2], sheet[1]), (sheet[2], sheet[3]), 40)
    plate.corner("sheet ghosted · slope beams foreshortened, cut them to the batch length")
    plates["A"] = plate.svg(
        "A-401", "Roof unit", PLAN.short,
        note=f"{PLAN.caption} · built flat, then hung",
    )

    # B · Door unit, seen from outside, with the field on its inner face.
    members = ("door_left", "door_right", "door_bottom", "door_top", "door_brace")
    shapes = shapes_for(FRONT, *members, "door_panel")
    plate = plate_for(shapes, members)
    draw_field(plate, shapes["door_panel"], parts["door_panel"], fields["door_panel"], FRONT, "door-field")
    draw_members(plate, shapes, members)
    frame_box = bounds([point for name in members for point in shapes[name]])
    field_box = bounds(shapes["door_panel"])
    plate.dim((frame_box[0], frame_box[1]), (frame_box[2], frame_box[1]), -40)
    plate.dim((frame_box[0], frame_box[1]), (frame_box[0], frame_box[3]), -40)
    plate.dim((field_box[2], field_box[1]), (field_box[2], field_box[3]), 40)
    plates["B"] = plate.svg(
        "A-402", "Door unit", FRONT.short,
        note=f"{FRONT.caption} · hatched edge is the estimated on-frame trim",
    )

    # C and D · Side units, each seen from outside its own wall.
    for letter, number, side, view in (
        ("C", "A-403", "left", LEFT), ("D", "A-404", "right", RIGHT)
    ):
        members = (
            f"front_post_{side}", f"back_post_{side}",
            f"{side}_bottom", f"{side}_top", f"{side}_brace",
        )
        wall = f"{side}_wall"
        field = fields[wall]
        shapes = shapes_for(view, *members, wall)
        plate = plate_for(shapes, members)
        draw_field(plate, shapes[wall], parts[wall], field, view, f"{side}-field")
        draw_members(plate, shapes, members)
        field_box = bounds(shapes[wall])
        post = bounds(shapes[f"front_post_{side}"])
        plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 40)
        plate.dim(
            (post[0] if side == "right" else post[2], field_box[1]),
            (post[0] if side == "right" else post[2], field_box[3]),
            -40 if side == "right" else 40,
        )
        notch = view((
            0,
            design.frame / 2,
            design.leg_extension + design.frame / 2,
        ))
        notch_note = view((
            0,
            design.frame + 130,
            design.leg_extension + design.frame + 80,
        ))
        plate.leader(
            notch,
            notch_note,
            f"{fmt(design.frame)} × {fmt(design.frame)} NOTCH",
            "start" if view.u_sign > 0 else "end",
        )
        fall = (
            (field.pieces[0].finished_long or field.blank)
            - (field.pieces[-1].finished_short or field.blank)
        )
        plates[letter] = plate.svg(
            number, f"{side.title()} side unit", view.short,
            note=f"{view.caption} · {fmt(fall)} fall over {fmt(field.span)} · "
            f"{fmt(design.frame)} × {fmt(design.frame)} bottom-front notch",
        )

    # E · Back unit, seen from outside, between the two rear posts.
    members = ("back_bottom", "back_top", "back_brace")
    ghosts = ("back_post_left", "back_post_right")
    shapes = shapes_for(REAR, *members, *ghosts, "back_wall")
    plate = plate_for(shapes, members, ghosts)
    draw_field(plate, shapes["back_wall"], parts["back_wall"], fields["back_wall"], REAR, "back-field")
    draw_members(plate, shapes, members)
    posts = bounds([point for name in ghosts for point in shapes[name]])
    field_box = bounds(shapes["back_wall"])
    plate.dim((posts[0], posts[1]), (posts[2], posts[1]), -40)
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 40)
    plate.dim((posts[0], field_box[3]), (field_box[0], field_box[3]), 84)
    plate.dim((posts[2], field_box[1]), (posts[2], field_box[3]), 36)
    plates["E"] = plate.svg(
        "A-405", "Back unit", REAR.short,
        note=f"{REAR.caption} · posts ghosted · trim after the boards are fixed",
    )

    # F · Floor deck, in plan, on its three bearers.
    members = ("floor_back_support", "floor_left_support", "floor_right_support")
    shapes = shapes_for(PLAN, *members, "floor", "front_bottom")
    plate = plate_for(shapes, members, ("front_bottom",))
    draw_field(plate, shapes["floor"], parts["floor"], fields["floor"], PLAN, "floor-field")
    draw_members(plate, shapes, members)
    field_box = bounds(shapes["floor"])
    rail = bounds(shapes["front_bottom"])
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 44)
    plate.dim((field_box[0], field_box[1]), (field_box[0], field_box[3]), -40)
    plate.label(
        ((rail[0] + rail[2]) / 2, rail[1] + (rail[3] - rail[1]) / 2),
        "FBH1 · FRONT EDGE LANDS HERE LAST", "small",
    )
    plates["F"] = plate.svg(
        "A-406", "Floor deck", PLAN.short,
        note=f"{PLAN.caption} · trim on the bearers before fitting the deck",
    )

    # G · Shell joint, cut through the lower rails so every landing shows.
    cut = design.leg_extension + design.frame / 2
    names = (
        "front_post_left", "front_post_right", "back_post_left", "back_post_right",
        "front_bottom", "back_bottom", "left_bottom", "right_bottom",
        "floor_back_support", "floor_left_support", "floor_right_support",
        "left_wall", "right_wall", "back_wall", "door_left", "door_right",
        "door_bottom", "door_panel",
    )
    sections = {name: cross_section(parts[name], PLAN, cut) for name in names}
    sections = {name: shape for name, shape in sections.items() if shape}
    plate = Plate(list(sections.values()), margin=66, pad=26)
    # Sectioned material is hatched, as a cut plane is drawn.
    for name in ("left_wall", "right_wall", "back_wall", "door_panel"):
        plate.shape(sections[name], "cut-field")
    for name, shape in sections.items():
        if name not in {"left_wall", "right_wall", "back_wall", "door_panel"}:
            plate.shape(shape, "cut-member")
    for name, shape in sections.items():
        plate.code_in(shape, BEAM_CODES.get(name, ""))
    posts = bounds(sections["back_post_left"] + sections["back_post_right"])
    front_post = bounds(sections["front_post_left"])
    left_field = bounds(sections["left_wall"])
    middle = (design.width / 2, -design.depth / 2)
    shell = bounds([point for shape in sections.values() for point in shape])
    plate.dim((posts[0], posts[1]), (posts[2], posts[1]), -40)
    plate.dim((shell[0], front_post[3]), (shell[0], posts[1]), -34)
    plate.leader(
        ((front_post[0] + front_post[2]) / 2, middle[1]), (middle[0] * 0.62, middle[1]),
        f"{fmt(design.frame)} FRAME", "start",
    )
    plate.leader(
        ((left_field[0] + left_field[2]) / 2, middle[1] + 90),
        (middle[0] * 0.62, middle[1] + 90),
        f"{fmt(design.cladding)} FIELD INSIDE IT", "start",
    )
    plates["G"] = plate.svg(
        "A-407", "Shell joint", f"plan section at {fmt(cut)}",
        note="every landing shown, measured off the ground",
    )

    # H · Seat box, in plan, with everything the top has to clear.
    members = ("seat_rail_1", "seat_rail_2", "seat_support_left", "seat_support_right")
    shapes = shapes_for(PLAN, *members, "seat_top")
    plate = plate_for(shapes, members)
    draw_field(plate, shapes["seat_top"], parts["seat_top"], fields["seat_top"], PLAN, "seat-field", label=False)
    for name in members:
        plate.shape(shapes[name], "under")
        plate.code_in(shapes[name], BEAM_CODES.get(name, ""))
    centre = (design.width / 2, -(design.back_wall_front - design.seat_depth / 2))
    plate.add(
        f'<ellipse class="opening" cx="{plate.x(centre[0]):.1f}" cy="{plate.y(centre[1]):.1f}" '
        f'rx="{design.seat_hole_width / 2 * plate.scale:.1f}" '
        f'ry="{design.seat_hole_depth / 2 * plate.scale:.1f}"/>'
    )
    field_box = bounds(shapes["seat_top"])
    hole_u = design.seat_hole_width / 2
    hole_v = design.seat_hole_depth / 2
    plate.dim((field_box[0], field_box[3]), (field_box[2], field_box[3]), 44)
    plate.dim((field_box[2], field_box[1]), (field_box[2], field_box[3]), 40)
    plate.label(
        centre,
        f"{fmt(design.seat_hole_width)} × {fmt(design.seat_hole_depth)}",
        "small",
    )
    plate.corner(f"{fields['seat_top'].codes} · joined, then the opening is cut")
    plates["H"] = plate.svg(
        "A-408", "Seat box", PLAN.short,
        note=f"{PLAN.caption} · trim the fixed top before cutting its opening",
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
    .note { margin:36px 0; padding:20px 24px; border:1px solid var(--line); }
    .note h3 { color:var(--code-deep); margin-bottom:12px; }
    .note p + p { margin-top:12px; }
    .note ol { margin:12px 0 0; padding-left:22px; }
    .note ol li { margin-bottom:10px; max-width:66ch; }
    .note ol li:last-child { margin-bottom:0; }

    /* Drawings. One caption under each, centred, the way the set captions them. */
    .drawing { margin:0; }
    .plate { display:block; width:100%; height:auto; background:var(--sheet); }
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
    .plate .cut-member { fill:url(#hatch); stroke:var(--line); stroke-width:var(--section); vector-effect:non-scaling-stroke; }
    .plate .field { fill:var(--grey-faint); stroke:var(--line); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .cut-field { fill:var(--grey-pale); stroke:var(--line); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .blank { fill:#fafafa; stroke:var(--grey-mid); stroke-width:var(--object); vector-effect:non-scaling-stroke; }
    .plate .ghost { fill:none; stroke:var(--grey-mid); stroke-width:var(--hair); stroke-dasharray:10 6; vector-effect:non-scaling-stroke; }
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
    .plate .small { fill:var(--dim-ink); font-size:12px; }
    .plate .note-text { fill:var(--grey-dark); font-size:12px; }
    .plate .dim-text { fill:var(--dim-ink); font-size:12px; letter-spacing:.04em; }

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
    .stock-piece.is-gang { background:repeating-linear-gradient(45deg,transparent 0 5px,var(--grey-pale) 5px 6px); }
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
    .viewer-canvas { display:block; width:100%; height:100%; touch-action:none; }
    .viewer-status {
      position:absolute; left:0; right:0; bottom:0; margin:0; padding:9px 12px;
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
      display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between;
      gap:20px; margin-top:clamp(24px,4vw,56px); padding:24px clamp(24px,3vw,48px);
      background:var(--sheet); border:1px solid var(--line);
    }
    .set-foot p { font-size:var(--t-small); color:var(--grey-dark); }
    .reset {
      margin-top:20px; border:1px solid var(--line); background:none; color:var(--ink);
      padding:11px 18px; font-size:var(--t-fine); letter-spacing:.14em; text-transform:uppercase; cursor:pointer;
    }
    .reset:hover, .reset:focus-visible { background:var(--code); border-color:var(--code); color:#fff; outline:0; }

    @media (max-width:1080px) { .view-grid, .drawing-grid { grid-template-columns:1fr; } }
    @media (max-width:720px) {
      :root { --t-fine:.6rem; --t-small:.68rem; --t-mark:.73rem; --t-note:.8rem; }
      .masthead-top { grid-template-columns:1fr; gap:28px; }
      /* One row per group, pills wrapping inside it, so nothing sits off-screen. */
      .view-controls { flex-direction:column; }
      .pill-group { flex-wrap:wrap; width:100%; }
      .pill-group + .pill-group { border-left:0; border-top:1px solid var(--grey-pale); }
      .pill-group i { flex:0 0 100%; padding:10px 12px 2px; }
      .pill { padding:10px 12px; }
    }
    @media print {
      @page { size:A4 landscape; margin:9mm; }
      body { background:#fff; font-size:8.4pt; }
      .set { width:100%; padding:0; }
      .sheet, .masthead { border:0; padding:0 0 6mm; margin:0; }
      .sheet { break-before:page; }
      .view-controls, .reset, .viewer, .viewer-status, .set-foot { display:none; }
      .view-grid { grid-template-columns:1fr; }
      /* The frame is square on screen; on paper it must not eat a whole sheet. */
      .view-frame { aspect-ratio:auto; height:auto; border:0; background:none; text-align:center; }
      .shot { position:static; width:auto; height:auto; max-width:100%; max-height:96mm; }
      .shot:not(.is-on) { display:none; }
      .gallery figcaption { padding-top:8px; }
      /* Keep the title block and main views on one sheet. */
      .masthead { break-after:page; }
      .masthead .view-grid { margin-top:5mm; }
      .masthead .view-frame { max-height:65mm; }
      .masthead h1 { margin-bottom:8px; }
      caption { padding-bottom:7px; }
      th, td { padding:6px 10px; }
      .title-block dt, .title-block dd { padding:5px 10px; }
      .note { margin:16px 0; padding:12px 16px; }
      .sheet-head { margin-bottom:20px; }
      .sheet-head h2 { padding-bottom:10px; }
      .sheet-note { margin-top:12px; }
      .table-scroll, .stock-list { margin-top:18px; }
      .stock-scroll, .table-scroll { overflow:visible; }
      .stock-track { min-width:0; height:auto; }
      /* A plate sized only by column width runs taller than the page, which
         leaves whole sheets blank. Give every drawing a height it must fit. */
      .drawing .plate { width:100%; height:74mm; }
      /* A4 landscape is narrower than the 1080px breakpoint, so the grid would
         otherwise fall to one column and print one drawing per sheet. */
      .drawing-grid { grid-template-columns:1fr 1fr; gap:8mm 7mm; margin-top:8mm; }
      .drawing figcaption { padding-top:6px; }
      .drawing-note { margin-top:5px; }
      .unit-face { display:none; }
      .code-strip { padding-top:7px; }
      .stack-check { margin-top:8px; padding-top:7px; }
      .drawing, .unit, .stock, .note { break-inside:avoid; }
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
    beam_lookup = {
        piece.code: f"B{stock:02d}"
        for stock, group in enumerate(beam_stocks, 1)
        for piece in group
    }
    panel_lookup = {
        piece.code: f"P{stock:02d}"
        for stock, group in enumerate(panel_stocks, 1)
        for piece in group
    }
    all_pieces = beams + boards
    code_map = {piece.code: piece for piece in all_pieces}
    first_panel_length = round(design.door_height, 1)
    last_panel_length = min(round(piece.length, 1) for piece in boards)
    remaining_boards = [
        piece for piece in boards
        if round(piece.length, 1) != first_panel_length
    ]
    roof_slope = math.hypot(design.roof_run, design.roof_rise)
    roof_plan_depth = (
        (roof_slope + 2 * design.frame) * design.roof_run / roof_slope
        + design.frame * design.roof_rise / roof_slope
    )
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
            f"Mark {fmt(field.pieces[0].finished_long or field.blank)} at the front "
            f"and {fmt(field.pieces[-1].finished_short or field.blank)} at the rear. "
            "Set the circular-saw guide and make one gang cut after the boards are fixed.",
            f"Use the rear frame edge to set the circular-saw guide. Cut the estimated "
            f"{fmt(field.trim)} overhang, then cut the {fmt(design.frame)} × "
            f"{fmt(design.frame)} bottom-front notch.",
            "Do not pre-cut the roof reliefs. Hang and close the roof, then cut only to the scribe.",
        )
    unit_steps = {
        "A": (
            "Lay RBH1 and RBH2 around RBS1 and RBS2. Center RBC1. Match the diagonals, then fasten the frame.",
            f"Center the metal sheet with {fmt(roof_side_overhang)} at each side and "
            f"{fmt(roof_end_overhang)} at the front and rear.",
            "Fit the moving hinge leaf. After the shell is square, fit the fixed leaf and hang the roof.",
        ),
        "B": (
            "Build the DBV and DBH frame. Fit DBD1 and match the diagonals.",
            "Fix DCB1 to DCB9 on the inside face. Align DCB1 with the left frame edge.",
            f"Use the right frame edge to set the circular-saw guide. Cut the estimated "
            f"{fmt(fields['door_panel'].trim)} overhang after the boards are fixed.",
            f"Cut the two top reliefs shown. Fit the moving hinge leaves, then hang the door "
            f"with a {fmt(design.hinge_gap)} gap after the shell is square.",
        ),
        "C": side_steps["C"],
        "D": side_steps["D"],
        "E": (
            "Build BWH1 and BWH2 with BWD1. Install this bare frame between the two side units.",
            "Fix BWC1 to BWC8 inside the side cladding. Align BWC1 with the left landing mark.",
            f"Use the right landing mark to set the circular-saw guide. Cut the estimated "
            f"{fmt(fields['back_wall'].trim)} overhang after the boards are fixed.",
        ),
        "F": (
            "Build the three-sided bearer frame from FBS1, FBS2, and FBB1.",
            "Fix FCB1 to FCB8 to the bearers. Align FCB1 with the left bearer edge.",
            f"Use the right bearer edge to set the circular-saw guide. Cut the estimated "
            f"{fmt(fields['floor'].trim)} overhang after the boards are fixed.",
            "Lower the deck into the square shell. Fasten its front edge to FBH1.",
        ),
        "G": (
            "Brace the left and right units upright. Install the back frame between them.",
            f"Install FBH1 across the front at the {fmt(design.leg_extension)} leg datum.",
            "Match the shell diagonals before the final fasteners. Then install the floor deck.",
        ),
        "H": (
            "Install SBH3, SBH1, SBH2, SBS1, and SBS2 after the shell and floor are fixed.",
            "Fix SFB1 to SFB8 to the seat front. Trim the fixed field from the frame landing.",
            "Fix STB1 to STB8 to the top frame. Use its right edge to set the circular-saw guide.",
            f"Cut the estimated {fmt(fields['seat_top'].trim)} overhang. Then cut the "
            f"{fmt(design.seat_hole_width)} × {fmt(design.seat_hole_depth)} opening.",
            "Make sure that the opening clears both bearers and rails. Seal every fresh cladding cut.",
        ),
    }
    module_cards = []
    for letter, title, prefixes in MODULES:
        codes = [
            code for code in code_map
            if any(code.startswith(prefix) for prefix in prefixes)
        ]
        codes.sort()
        steps = "".join(f"<li>{step}</li>" for step in unit_steps[letter])
        face_controls = (
            f'<div class="unit-face" data-unit-face="{letter}" role="group" '
            f'aria-label="{title} drawing layer">'
            '<button class="is-on" type="button" data-face="frame" '
            'aria-pressed="true">Frame</button>'
            '<button type="button" data-face="cladding" '
            'aria-pressed="false">Cladding</button></div>'
            if letter in "BCDEFH" else ""
        )
        module_cards.append(f"""
          <article class="unit" id="unit-{letter.lower()}" data-face="frame">
            <header><span class="unit-letter">Stack {letter}</span><div><h3>{title}</h3></div>{face_controls}</header>
            {plates[letter]}
            <div class="unit-steps"><h4>Assembly</h4><ol>{steps}</ol></div>
            <div class="code-strip">{''.join(f'<b class="code">{code}</b>' for code in codes)}</div>
            <label class="stack-check"><input type="checkbox" data-check="unit-{letter.lower()}"> Unit complete</label>
          </article>""")

    beam_stock_html = "".join(
        stock_bar(
            f"B{index:02d}", stock, beam_stock_length, kerf, design.frame * 2
        )
        for index, stock in enumerate(beam_stocks, 1)
    )
    panel_stock_html = "".join(
        stock_bar(
            f"P{index:02d}", stock, cladding_stock_length, kerf, BOARD_WIDTH * 2
        )
        for index, stock in enumerate(panel_stocks, 1)
    )
    first_panel_stocks = [
        stock for stock in panel_stocks
        if any(round(piece.length, 1) == first_panel_length for piece in stock)
    ]
    reused_tail_stocks = [
        f"P{index:02d}"
        for index, stock in enumerate(panel_stocks, 1)
        if any(round(piece.length, 1) == first_panel_length for piece in stock)
        and any(round(piece.length, 1) == last_panel_length for piece in stock)
    ]
    panel_blank_rows = []
    for index, stock in enumerate(first_panel_stocks, 1):
        blanks = [
            piece for piece in stock
            if round(piece.length, 1) == first_panel_length
        ]
        later = [
            piece for piece in stock
            if round(piece.length, 1) != first_panel_length
        ]
        available = cladding_stock_length - sum(
            piece.length + kerf for piece in blanks
        )
        disposition = (
            f"keep for {fmt(later[0].length)}"
            if later else "terminal offcut"
        )
        panel_blank_rows.append(
            f"<tr><td>P{index:02d}</td>"
            f"<td class=\"marks\">{' '.join(f'<b>{piece.code}</b>' for piece in blanks)}</td>"
            f"<td><span class=\"measure\">{fmt(available)}</span> · {disposition}</td></tr>"
        )
    panel_blank_rows = "".join(panel_blank_rows)

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
        <p class="masthead-sub">Outdoor toilet drawn from a parametric model using claude and codex.</p>
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
        <div><dt>Kerf</dt><dd>{fmt(kerf)} per cut</dd></div>
        <div><dt>Sheets</dt><dd>A-200 to A-400</dd></div>
      </dl>
    </div>
    <div class="view-grid">
      {gallery_html()}
      {viewer_html()}
    </div>
  </header>

  <section class="sheet" id="beams">
    <div class="sheet-head"><span class="sheet-no">Sheet A-200</span><h2>Structural timber</h2></div>
    <p class="sheet-note"><b>Material:</b> Frame timber, 45 × 45 ×
    {fmt(beam_stock_length)} mm. Quantity: {len(beam_stocks)} lengths.</p>
    <div class="note">
      <h3>Caution · verify the stock first</h3>
      <p>Make sure that your stock matches the material. These sheets are exact only for
      this material size. One {fmt(kerf)} mm kerf is used for every piece.</p>
    </div>
    <p class="sheet-note">Cut every piece at one stop setting before you change the stop.
    A batch that reaches the end of a stock length continues on the next length.</p>
    <div class="table-scroll"><table>
      <caption>Batch order · A-200</caption>
      <thead><tr><th>Pass</th><th>Stop</th><th>Saw setup</th><th>Mark these pieces</th></tr></thead>
      <tbody>{cut_batches(beams, beam_lookup, design)}</tbody>
    </table></div>
    <div class="note">
      <h3>Brace rule</h3>
      <p>LSD1 and RSD1 are cut at {brace_angle(design, code_map["LSD1"]):.1f}° at both ends.
      BWD1 and DBD1 are cut at {brace_angle(design, code_map["BWD1"]):.1f}° at both ends.</p>
      <p>These are long-point lengths. Keep each pair of end cuts parallel. Turn the
      workpiece, not the saw setting, to make the parallelogram.</p>
    </div>
    <div class="stock-list">{beam_stock_html}</div>
  </section>

  <section class="sheet" id="panels">
    <div class="sheet-head"><span class="sheet-no">Sheet A-300</span><h2>Råspont</h2></div>
    <p class="sheet-note"><b>Material:</b> Råspont, 120 × 23 ×
    {fmt(cladding_stock_length)} mm. Quantity: {len(panel_stocks)} lengths.</p>
    <div class="note">
      <h3>Caution · verify the stock first</h3>
      <p>Make sure that your stock matches the material. These sheets are exact only for
      this material size. One {fmt(kerf)} mm kerf is used for every piece.</p>
    </div>
    <p class="sheet-note">The first {len(first_panel_stocks)} stock lengths release all
    twenty-three {fmt(first_panel_length)} blanks. Fourteen side boards come first, then nine
    door boards, at one stop setting.</p>
    <div class="note">
      <h3>Operation A · release every {fmt(first_panel_length)} blank</h3>
      <div class="table-scroll"><table>
        <thead><tr><th>Stock</th><th>Codes, cut in this order</th><th>Available after the batch</th></tr></thead>
        <tbody>{panel_blank_rows}</tbody>
      </table></div>
      <ol>
        <li>Set the stop once. Cut all twenty-three blanks from P01 onward. Mark each code
        immediately. When a stock length ends, continue at the same setting on the next one.</li>
        <li>Label the P01 to P03 remainders. Keep them for the final {fmt(last_panel_length)} pass.</li>
        <li>Move every marked blank to its unit stack. Do not join or trim loose cladding.</li>
      </ol>
    </div>
    <div class="note">
      <h3>Operation B · cut the remaining pieces</h3>
      <p>Change the stop only once per row. Cut every piece in that row, then move to the
      next stop. The final {fmt(last_panel_length)} row uses the labeled
      {' / '.join(reused_tail_stocks)} remainders.</p>
      <div class="table-scroll"><table>
        <caption>Batch order · A-300 operation B</caption>
        <thead><tr><th>Pass</th><th>Stop</th><th>Saw setup</th><th>Mark these pieces</th></tr></thead>
        <tbody>{cut_batches(remaining_boards, panel_lookup, design)}</tbody>
      </table></div>
    </div>
    <div class="stock-list">{panel_stock_html}</div>
    <div class="note" id="fields">
      <h3>Do not trim loose cladding</h3>
      <p>Gaps between boards change the joined width. Fix each board to its unit frame before
      you mark any final edge.</p>
      <p>Use the frame edge to set the circular-saw guide. Cut only after the boards are fixed.
      Sheet A-400 shows each estimated overhang and cut line.</p>
    </div>
  </section>

  <section class="sheet" id="stacks">
    <div class="sheet-head"><span class="sheet-no">Sheet A-400</span><h2>Unit drawings and assembly</h2></div>
    <p class="sheet-note">Each drawing is an orthographic projection off the model. Solid
    members are the frame. Tinted fields are cladding. Hatching shows the nominal material
    left for an on-frame cut.</p>
    <p class="sheet-note">Use the Frame and Cladding controls to change drawing emphasis.
    The printed drawing keeps every cut line, trim label, and notch note visible.</p>
    <div class="drawing-grid">{''.join(module_cards)}</div>
  </section>

  <footer class="set-foot">
    <p>The checks are saved in this browser. Print removes the controls and keeps
    every code and dimension.</p>
    <button class="reset" type="button">Clear all checks</button>
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
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
