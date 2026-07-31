"""Generate piece schedules and kerf-aware beam/cladding stock cutting plans."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, fields, replace
from pathlib import Path

from .model import Design, build


@dataclass(frozen=True)
class CutPiece:
    name: str
    length: float
    width: float
    thickness: float
    finished_long: float | None = None
    finished_short: float | None = None
    gang_cut: str = ""
    panel_end_trim: float | None = None
    code: str = ""

    @property
    def profile(self) -> str:
        return f"{self.width:g}x{self.thickness:g}"


# Råspont stock: the nominal board, the width it covers once the tongue is
# housed, and the trim every joined field keeps for its terminal edge.
BOARD_WIDTH = 120.0
COVER_WIDTH = 110.0
MINIMUM_END_TRIM = 10.0
DEFAULT_KERF = 2.8


BEAM_CODES = {
    "front_post_left": "LSV1",
    "back_post_left": "LSV2",
    "left_bottom": "LSH1",
    "left_top": "LSH2",
    "left_brace": "LSD1",
    "front_post_right": "RSV1",
    "back_post_right": "RSV2",
    "right_bottom": "RSH1",
    "right_top": "RSH2",
    "right_brace": "RSD1",
    "front_bottom": "FBH1",
    "back_bottom": "BWH1",
    "back_top": "BWH2",
    "back_brace": "BWD1",
    "roof_front": "RBH1",
    "roof_back": "RBH2",
    "roof_left": "RBS1",
    "roof_right": "RBS2",
    "roof_middle": "RBC1",
    "floor_back_support": "FBB1",
    "floor_left_support": "FBS1",
    "floor_right_support": "FBS2",
    "seat_rail_1": "SBH1",
    "seat_rail_2": "SBH2",
    "seat_lower_rail": "SBH3",
    "seat_support_left": "SBS1",
    "seat_support_right": "SBS2",
    "door_left": "DBV1",
    "door_right": "DBV2",
    "door_bottom": "DBH1",
    "door_top": "DBH2",
    "door_brace": "DBD1",
}


def beam_pieces(design: Design) -> list[CutPiece]:
    """Return every modeled wood beam that uses a supported stock profile."""
    _, parts = build(design)
    return [
        CutPiece(
            part.name,
            part.length,
            part.width,
            part.thickness,
            code=BEAM_CODES[part.name],
        )
        for part in parts
        if part.material == "wood"
        and (part.width, part.thickness) in {
            (design.frame, design.frame),
            (design.roof_connector_width, design.roof_connector_thickness),
            (design.seat_support, design.seat_support),
        }
    ]


def cladding_pieces(
    design: Design,
    board_width: float = BOARD_WIDTH,
    cover_width: float = COVER_WIDTH,
    minimum_end_trim: float = MINIMUM_END_TRIM,
) -> list[CutPiece]:
    """Expand panels into full råspont boards, retaining a final trim allowance."""
    pieces: list[CutPiece] = []

    def code(prefix: str, index: int) -> str:
        if len(prefix) > 3 or not 1 <= index <= 99:
            raise ValueError("piece codes support at most three letters and two digits")
        return f"{prefix}{index}"

    def board_count(span: float) -> int:
        lip = board_width - cover_width
        count = math.ceil((span + minimum_end_trim - lip) / cover_width)
        assembled_width = count * cover_width + lip
        if assembled_width - span < minimum_end_trim - 1e-9:
            count += 1
        return count

    def panel(name: str, span: float, length: float, quantity: int = 1) -> None:
        count = board_count(span)
        end_trim = count * cover_width + board_width - cover_width - span
        for copy in range(1, quantity + 1):
            for index in range(count):
                suffix = f"{copy}." if quantity > 1 else ""
                pieces.append(CutPiece(
                    f"{name}_{suffix}{index + 1}",
                    length,
                    board_width,
                    design.cladding,
                    length,
                    length,
                    "",
                    end_trim,
                    code({
                        "door": "DCB",
                        "back_wall": "BWC",
                        "floor": "FCB",
                        "seat_top": "STB",
                        "seat_front": "SFB",
                    }[name], index + 1),
                ))

    panel("door", design.width, design.door_height)
    panel("back_wall", design.interior_width, design.back_height - design.leg_extension)

    side_span = design.plan_grid_depth
    side_count = board_count(side_span)
    side_end_trim = side_count * cover_width + board_width - cover_width - side_span
    for side in ("left_wall", "right_wall"):
        for index in range(side_count):
            start = min(index * cover_width, side_span)
            end = min((index + 1) * cover_width, side_span)
            long_point = design.door_height - design.side_fall * start / side_span
            short_point = design.door_height - design.side_fall * end / side_span
            pieces.append(CutPiece(
                f"{side}_{index + 1}",
                design.door_height,
                board_width,
                design.cladding,
                long_point,
                short_point,
                side,
                side_end_trim,
                code("LSC" if side == "left_wall" else "RSC", index + 1),
            ))

    panel("floor", design.interior_width, design.back_wall_front)
    panel("seat_top", design.interior_width, design.seat_depth)
    panel("seat_front", design.interior_width, design.seat_height - design.cladding)
    return pieces


def pack_stock(
    pieces: list[CutPiece],
    stock_length: float = 2400,
    kerf: float = DEFAULT_KERF,
) -> list[list[CutPiece]]:
    """Return a kerf-safe cutting sequence with identical lengths contiguous.

    One kerf is reserved for every released piece. This is conservative by one
    kerf only when the final piece consumes a stock length exactly, and it
    leaves every non-zero offcut usable without relying on a factory end.
    """
    if stock_length <= 0 or kerf < 0:
        raise ValueError("stock length must be positive and kerf non-negative")
    if any(piece.length <= 0 or piece.length + kerf > stock_length for piece in pieces):
        raise ValueError("every piece must have a positive length no longer than stock")
    ordered = sorted(
        pieces,
        key=lambda piece: (
            -round(piece.length, 1),
            not bool(piece.gang_cut),
            piece.code,
            piece.name,
        ),
    )
    stocks: list[list[CutPiece]] = []
    used = 0.0
    for piece in ordered:
        piece_usage = piece.length + kerf
        if not stocks or used + piece_usage > stock_length + 1e-9:
            stocks.append([])
            used = 0.0
        stocks[-1].append(piece)
        used += piece_usage
    return stocks


def panel_stock_plan(
    pieces: list[CutPiece],
    stock_length: float = 4500,
    kerf: float = DEFAULT_KERF,
    stock_limit: int = 12,
) -> list[list[CutPiece]]:
    """Return the batch sequence within the available cladding stock count."""
    if stock_limit <= 0:
        raise ValueError("cladding stock limit must be positive")
    side_sets = [
        [piece for piece in pieces if piece.gang_cut == gang_cut]
        for gang_cut in sorted({piece.gang_cut for piece in pieces if piece.gang_cut})
    ]
    if len(side_sets) != 2 or not side_sets[0] or len(side_sets[0]) != len(side_sets[1]):
        raise ValueError("the gang-cut workflow requires two equal side-panel sets")
    sides = side_sets[0] + side_sets[1]
    blank_lengths = {piece.length for piece in sides}
    if len(blank_lengths) != 1:
        raise ValueError("all side-panel gang-cut blanks must share one length")
    stocks = pack_stock(pieces, stock_length, kerf)
    while len(stocks) > stock_limit:
        compacted = [stock.copy() for stock in stocks[:-1]]
        for piece in stocks[-1]:
            piece_usage = piece.length + kerf
            candidates = []
            for index, stock in enumerate(compacted):
                remaining = stock_length - sum(
                    item.length + kerf for item in stock
                )
                if piece_usage <= remaining + 1e-9:
                    candidates.append((remaining - piece_usage, index))
            if not candidates:
                raise ValueError(
                    f"cladding pieces do not fit {stock_limit} stock lengths"
                )
            compacted[min(candidates)[1]].append(piece)

        moved_lengths = {round(piece.length, 1) for piece in stocks[-1]}
        for length in moved_lengths:
            slots = [
                (stock, index)
                for stock in compacted
                for index, piece in enumerate(stock)
                if round(piece.length, 1) == length
            ]
            members = sorted(
                (stock[index] for stock, index in slots),
                key=lambda piece: (piece.code, piece.name),
            )
            for (stock, index), piece in zip(slots, members):
                stock[index] = piece
        stocks = compacted
    return stocks


def write_schedule(pieces: list[CutPiece], path: Path) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow((
            "code", "piece", "blank_length_mm", "finished_long_mm", "finished_short_mm",
            "width_mm", "thickness_mm", "gang_cut", "panel_end_trim_mm",
        ))
        for piece in pieces:
            writer.writerow((
                piece.code,
                piece.name,
                round(piece.length, 1),
                round(piece.finished_long, 1) if piece.finished_long is not None else "",
                round(piece.finished_short, 1) if piece.finished_short is not None else "",
                round(piece.width, 1),
                round(piece.thickness, 1),
                piece.gang_cut,
                round(piece.panel_end_trim, 1) if piece.panel_end_trim is not None else "",
            ))


def write_stock_plan(
    groups: list[tuple[str, list[CutPiece], float]],
    path: Path,
    kerf: float,
) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow((
            "material", "stock", "stock_length_mm", "cuts", "piece_codes", "piece_lengths_mm",
            "kerf_mm", "used_mm", "waste_mm",
        ))
        for material, pieces, stock_length in groups:
            stocks = (
                panel_stock_plan(pieces, stock_length, kerf)
                if material.startswith("cladding_")
                else pack_stock(pieces, stock_length, kerf)
            )
            for index, stock in enumerate(stocks, 1):
                kerf_total = kerf * len(stock)
                used = sum(piece.length for piece in stock) + kerf_total
                writer.writerow((
                    material,
                    index,
                    stock_length,
                    len(stock),
                    " + ".join(piece.code or piece.name for piece in stock),
                    " + ".join(f"{piece.length:.1f}" for piece in stock),
                    round(kerf_total, 1),
                    round(used, 1),
                    round(stock_length - used, 1),
                ))


def write_stock_summary(
    groups: list[tuple[str, list[CutPiece], float]],
    path: Path,
    kerf: float,
) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("material", "stock_quantity", "stock_length_mm", "total_waste_mm"))
        for material, pieces, stock_length in groups:
            stocks = (
                panel_stock_plan(pieces, stock_length, kerf)
                if material.startswith("cladding_")
                else pack_stock(pieces, stock_length, kerf)
            )
            used = sum(
                sum(piece.length for piece in stock) + kerf * len(stock)
                for stock in stocks
            )
            writer.writerow((
                material,
                len(stocks),
                stock_length,
                round(len(stocks) * stock_length - used, 1),
            ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build"))
    parser.add_argument(
        "--stock-length",
        type=float,
        help="override both stock lengths (legacy convenience)",
    )
    parser.add_argument("--beam-stock-length", type=float, default=4200)
    parser.add_argument("--cladding-stock-length", type=float, default=4500)
    parser.add_argument("--kerf", type=float, default=DEFAULT_KERF)
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=MM",
        help="override any numeric Design parameter; may be repeated",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    overrides = {}
    parameter_names = {field.name for field in fields(Design)}
    for item in args.set:
        name, separator, value = item.partition("=")
        if not separator or name not in parameter_names:
            parser.error(
                f"--set must be NAME=MM where NAME is one of: "
                f"{', '.join(sorted(parameter_names))}"
            )
        try:
            overrides[name] = float(value)
        except ValueError:
            parser.error(f"--set {name} requires a numeric value, got {value!r}")
    design = replace(Design(), **overrides)
    if args.stock_length is not None:
        args.beam_stock_length = args.stock_length
        args.cladding_stock_length = args.stock_length
    beams = beam_pieces(design)
    cladding = cladding_pieces(design)
    write_schedule(beams, args.output / "beam-pieces.csv")
    write_schedule(cladding, args.output / "cladding-pieces.csv")

    beam_groups = [
        (
            f"beam_{profile}",
            [piece for piece in beams if piece.profile == profile],
            args.beam_stock_length,
        )
        for profile in sorted({piece.profile for piece in beams})
    ]
    stock_groups = beam_groups + [(
        f"cladding_120x{design.cladding:g}",
        cladding,
        args.cladding_stock_length,
    )]
    write_stock_plan(
        stock_groups,
        args.output / "stock-cut-plan.csv",
        args.kerf,
    )
    write_stock_summary(
        stock_groups,
        args.output / "stock-summary.csv",
        args.kerf,
    )
    print(f"Wrote piece schedules and stock plan to {args.output}")


if __name__ == "__main__":
    main()
