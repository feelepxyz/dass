"""Create repeatable drawing crops and red-line overlays for visual validation."""

from pathlib import Path

from PIL import Image

from dass import Design, build, render


ROOT = Path(__file__).parent
OUTPUT = ROOT / "build" / "drawing-comparison"


def red_line_overlay(
    render_path: Path,
    crop_path: Path,
    output_path: Path,
    drawing_outline: tuple[int, int, int, int],
    render_outline: tuple[int, int, int, int],
) -> None:
    base = Image.open(render_path).convert("RGBA")
    drawing = Image.open(crop_path).convert("L").crop(drawing_outline)
    left, top, right, bottom = render_outline
    drawing = drawing.resize((right - left, bottom - top))
    # Preserve the drawing's dark construction lines while dropping its white paper.
    alpha = drawing.point(lambda value: max(0, min(190, (220 - value) * 4)))
    lines = Image.new("RGBA", drawing.size, (220, 25, 25, 0))
    lines.putalpha(alpha)
    red = Image.new("RGBA", base.size, (220, 25, 25, 0))
    red.alpha_composite(lines, (left, top))
    Image.alpha_composite(base, red).convert("RGB").save(output_path)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    drawing = Image.open(ROOT / "drawing-sides.png")
    crops = {
        # Tight crops around the model outlines, excluding titles and most callouts.
        "door-front": (90, 80, 475, 555),
        "side-frame": (1455, 75, 1780, 570),
        "seat-section": (2105, 80, 2470, 570),
    }
    crop_paths: dict[str, Path] = {}
    for name, bounds in crops.items():
        path = OUTPUT / f"drawing-{name}.png"
        drawing.crop(bounds).save(path)
        crop_paths[name] = path

    design = Design()
    _, closed_parts = build(design, door_angle=0, roof_visible=False)
    front_render = OUTPUT / "render-door-front.png"
    render(
        closed_parts,
        design,
        front_render,
        size=(735, 960),
        eye=(design.width / 2, -3000, design.front_height / 2),
        target=(design.width / 2, 0, design.front_height / 2),
    )
    red_line_overlay(
        front_render,
        crop_paths["door-front"],
        OUTPUT / "overlay-door-front.png",
        drawing_outline=(10, 35, 375, 455),
        render_outline=(50, 50, 685, 910),
    )

    section_names = {
        "front_post_left", "back_post_left", "left_bottom", "left_top",
        "floor", "seat_front", "seat_top", "seat_rail_1", "seat_rail_2",
        "seat_lower_rail",
    }
    section_parts = [part for part in closed_parts if part.name in section_names]
    section_render = OUTPUT / "render-seat-section.png"
    render(
        section_parts,
        design,
        section_render,
        size=(720, 975),
        eye=(3000, design.depth / 2, design.front_height / 2),
        target=(0, design.depth / 2, design.front_height / 2),
    )
    red_line_overlay(
        section_render,
        crop_paths["seat-section"],
        OUTPUT / "overlay-seat-section.png",
        drawing_outline=(35, 35, 350, 490),
        render_outline=(50, 50, 670, 925),
    )
    print(f"Wrote drawing crops and overlays to {OUTPUT}")


if __name__ == "__main__":
    main()
