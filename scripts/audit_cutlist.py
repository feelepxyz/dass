"""Compare the reconciled cut list, drawing callouts, and modeled CAD parts."""

import csv
import math
from collections import defaultdict
from pathlib import Path

from dass import Design, build

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "cutlist-audit.md"
CSV_OUTPUT = ROOT / "build" / "cutlist-side-by-side.csv"

# Reconciled transcription from cutlist.png plus the user's label/quantity corrections.
IMAGE_CUTLIST = {
    "V1": (4, 1150, "50×50"),
    "V2": (2, 1050, "50×50"),
    "D1": (2, 1209, "50×50; -36° both ends"),
    "D2": (1, 1274.8, "50×50; door diagonal"),
    "HK1": (4, 750, "50×50"),
    "HK2": (2, 833, "50×50"),
    "HL1": (5, 850, "50×50"),
    "HL2": (2, 950, "50×50"),
}

# Reconciled extraction from the labeled dimensions in drawing-sides.png.
DRAWING_CUTLIST = {
    "V1": (4, 1150, "front + rear structural uprights"),
    "V2": (2, 1050, "door uprights"),
    "D1": (2, 1209, "side diagonals"),
    "D2": (1, 1274.8, "door diagonal"),
    "HK1": (4, 750, "side/floor rails"),
    "HK2": (2, 833, "sloped side top rails"),
    "HL1": (5, 850, "cross rails"),
    "HL2": (2, 950, "door cross rails"),
}


def main() -> None:
    _, parts = build(Design())
    structural = set(IMAGE_CUTLIST)
    cad: dict[str, list[float]] = defaultdict(list)
    for part in parts:
        if part.category in structural:
            cad[part.category].append(part.length)

    lines = [
        "# Cut-list audit",
        "",
        "| Part | reconciled cut list | reconciled drawing | generated CAD | Result |",
        "|---|---|---|---|---|",
    ]
    csv_rows = [
        (
            "part",
            "image_quantity",
            "image_length_mm",
            "cad_quantity",
            "cad_length_mm",
            "result",
        )
    ]
    errors: list[str] = []
    for name, (image_quantity, image_length, _) in IMAGE_CUTLIST.items():
        drawing_quantity, drawing_length, _ = DRAWING_CUTLIST[name]
        cad_lengths = cad.get(name, [])
        cad_quantity = len(cad_lengths)
        cad_length_text = (
            ", ".join(f"{value:.1f}" for value in sorted(cad_lengths)) or "—"
        )
        values = (
            f"{image_quantity} × {image_length}",
            f"{drawing_quantity} × {drawing_length}",
            f"{cad_quantity} parts: {cad_length_text}",
        )
        matches = (
            image_quantity == drawing_quantity == cad_quantity
            and image_length == drawing_length
            and all(
                math.isclose(length, image_length, abs_tol=0.5)
                for length in cad_lengths
            )
        )
        result = "match" if matches else "ERROR"
        if not matches:
            errors.append(
                f"{name}: image={values[0]}, drawing={values[1]}, CAD={values[2]}"
            )
        lines.append(f"| {name} | {values[0]} | {values[1]} | {values[2]} | {result} |")
        csv_rows.append(
            (name, image_quantity, image_length, cad_quantity, cad_length_text, result)
        )

    lines.extend(("", "## Notes", ""))
    lines.append("- The source image specifies 50×50 stock for every row.")
    lines.append(
        "- User reconciliation assigns V1 to four structural uprights, V2 to two door uprights, and D2 to the single door diagonal."
    )
    lines.append(
        "- The image specifies −36° cuts at both D1 ends and −40° cuts at both D2 ends."
    )
    lines.append(
        "- CAD quantities are derived from the model, not copied from either reference table."
    )
    lines.append(
        "- Exact side-frame corner geometry gives D1 = 1210.4 mm and a 38.3° cut."
    )
    lines.append(
        "- Exact 850 × 950 mm door opening geometry gives D2 = 1274.8 mm and a 41.8° cut."
    )
    if errors:
        lines.extend(("", "## Errors", "", *(f"- {error}" for error in errors)))
    else:
        lines.append(
            "- No discrepancies were found among the eight labeled structural stock rows."
        )
    OUTPUT.write_text("\n".join(lines) + "\n")
    with CSV_OUTPUT.open("w", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(csv_rows)
    print(f"Wrote {OUTPUT} and {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
