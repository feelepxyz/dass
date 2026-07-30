"""Generate piece schedules and kerf-aware 2.4 m stock cutting plans."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass, fields, replace
from pathlib import Path

from dass import Design, build


@dataclass(frozen=True)
class CutPiece:
    name: str
    length: float
    width: float
    thickness: float

    @property
    def profile(self) -> str:
        return f"{self.width:g}x{self.thickness:g}"


def beam_pieces(design: Design) -> list[CutPiece]:
    """Return every modeled wood beam that uses a supported stock profile."""
    _, parts = build(design)
    return [
        CutPiece(part.name, part.length, part.width, part.thickness)
        for part in parts
        if part.material == "wood"
        and (part.width, part.thickness) in {
            (design.frame, design.frame),
            (design.roof_connector_width, design.roof_connector_thickness),
        }
    ]


def cladding_pieces(design: Design, board_width: float = 120) -> list[CutPiece]:
    """Expand finished 25 mm panels into individual vertical/longitudinal boards."""
    pieces: list[CutPiece] = []

    def panel(name: str, span: float, length: float, quantity: int = 1) -> None:
        board_count = math.ceil(span / board_width)
        for copy in range(1, quantity + 1):
            for index in range(board_count):
                width = min(board_width, span - index * board_width)
                suffix = f"{copy}." if quantity > 1 else ""
                pieces.append(CutPiece(
                    f"{name}_{suffix}{index + 1}",
                    length,
                    width,
                    design.cladding,
                ))

    panel("door", design.width, design.door_height)
    panel("back_wall", design.inner_width, design.back_height - design.leg_extension)

    side_span = design.plan_grid_depth
    side_count = math.ceil(side_span / board_width)
    for side in ("left_wall", "right_wall"):
        for index in range(side_count):
            position = index * board_width
            length = design.door_height - design.roof_rise * position / side_span
            pieces.append(CutPiece(
                f"{side}_{index + 1}",
                length,
                min(board_width, side_span - position),
                design.cladding,
            ))

    panel("floor", design.interior_width, design.back_wall_front)
    panel("seat_top", design.interior_width, design.seat_depth)
    panel("seat_front", design.interior_width, design.seat_height - design.cladding)
    return pieces


def pack_stock(
    pieces: list[CutPiece],
    stock_length: float = 2400,
    kerf: float = 2,
) -> list[list[CutPiece]]:
    """Best-fit decreasing one-dimensional stock nesting."""
    if stock_length <= 0 or kerf < 0:
        raise ValueError("stock length must be positive and kerf non-negative")
    if any(piece.length <= 0 or piece.length > stock_length for piece in pieces):
        raise ValueError("every piece must have a positive length no longer than stock")

    stocks: list[list[CutPiece]] = []
    for piece in sorted(pieces, key=lambda item: item.length, reverse=True):
        candidates = []
        for index, stock in enumerate(stocks):
            used = sum(item.length for item in stock) + kerf * max(0, len(stock) - 1)
            remaining = stock_length - used - (kerf if stock else 0) - piece.length
            if remaining >= -1e-9:
                candidates.append((remaining, index))
        if candidates:
            stocks[min(candidates)[1]].append(piece)
        else:
            stocks.append([piece])
    return stocks


def write_schedule(pieces: list[CutPiece], path: Path) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("piece", "length_mm", "width_mm", "thickness_mm"))
        for piece in pieces:
            writer.writerow((
                piece.name,
                round(piece.length, 1),
                round(piece.width, 1),
                round(piece.thickness, 1),
            ))


def write_stock_plan(
    groups: list[tuple[str, list[CutPiece]]],
    path: Path,
    stock_length: float,
    kerf: float,
) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow((
            "material", "stock", "stock_length_mm", "cuts", "pieces", "piece_lengths_mm",
            "kerf_mm", "used_mm", "waste_mm",
        ))
        for material, pieces in groups:
            for index, stock in enumerate(pack_stock(pieces, stock_length, kerf), 1):
                kerf_total = kerf * max(0, len(stock) - 1)
                used = sum(piece.length for piece in stock) + kerf_total
                writer.writerow((
                    material,
                    index,
                    stock_length,
                    len(stock),
                    " + ".join(piece.name for piece in stock),
                    " + ".join(f"{piece.length:.1f}" for piece in stock),
                    round(kerf_total, 1),
                    round(used, 1),
                    round(stock_length - used, 1),
                ))


def write_stock_summary(
    groups: list[tuple[str, list[CutPiece]]],
    path: Path,
    stock_length: float,
    kerf: float,
) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("material", "stock_quantity", "stock_length_mm", "total_waste_mm"))
        for material, pieces in groups:
            stocks = pack_stock(pieces, stock_length, kerf)
            used = sum(
                sum(piece.length for piece in stock) + kerf * max(0, len(stock) - 1)
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
    parser.add_argument("--stock-length", type=float, default=2400)
    parser.add_argument("--kerf", type=float, default=2)
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
    beams = beam_pieces(design)
    cladding = cladding_pieces(design)
    write_schedule(beams, args.output / "beam-pieces.csv")
    write_schedule(cladding, args.output / "cladding-pieces.csv")

    beam_groups = [
        (f"beam_{profile}", [piece for piece in beams if piece.profile == profile])
        for profile in sorted({piece.profile for piece in beams})
    ]
    stock_groups = beam_groups + [(f"cladding_120x{design.cladding:g}", cladding)]
    write_stock_plan(
        stock_groups,
        args.output / "stock-cut-plan.csv",
        args.stock_length,
        args.kerf,
    )
    write_stock_summary(
        stock_groups,
        args.output / "stock-summary.csv",
        args.stock_length,
        args.kerf,
    )
    print(f"Wrote piece schedules and stock plan to {args.output}")


if __name__ == "__main__":
    main()
