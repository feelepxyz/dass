"""Write the model-derived frame fastening audit."""

from pathlib import Path

from dass import Design
from dass.fastening import fastening_report

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "fastening-audit.md"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(fastening_report(Design()))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
