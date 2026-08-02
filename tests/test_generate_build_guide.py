import math
import re
from collections import Counter
from html import escape
from pathlib import Path

import pytest

from dass import Design, box_at, build_guide
from dass.build_guide import (
    DEFAULT_ATLAS,
    FRONT,
    GALLERY,
    LEFT,
    PLAN,
    REAR,
    RIGHT,
    Panel,
    Plate,
    _drawing_screw_path,
    _face_center,
    _face_normal,
    _target_entry_face,
    cladding_board_centres,
    cladding_screw_layout,
    convex_hull,
    cross_section,
    cut_batches,
    draw_field,
    fmt,
    guide_html,
    module_plates,
    outline,
    panels,
    plank_atlas,
    progress_html,
    render_asset,
    started_html,
    viewer_parts,
)
from dass.cutlists import (
    BEAM_CODES,
    DEFAULT_KERF,
    CutPiece,
    pack_stock,
    panel_stock_plan,
)
from dass.fastening import SCREW_PATH_CLEARANCE_MM, analyze_frame_fastening
from tests.helpers import almost


@pytest.fixture(scope="module")
def guide_document(design: Design) -> str:
    return guide_html(design)


@pytest.fixture(scope="module")
def started_document() -> str:
    return started_html()


@pytest.fixture(scope="module")
def progress_document() -> str:
    return progress_html()


@pytest.fixture(scope="module")
def plates(design: Design, boards: list[CutPiece]) -> dict[str, str]:
    return module_plates(design, boards)


def test_plans_are_complete_and_kerf_safe(beams, boards):
    plans = (
        (beams, pack_stock(beams, 4200, DEFAULT_KERF), 4200),
        (boards, panel_stock_plan(boards, 4500, DEFAULT_KERF), 4500),
    )
    for pieces, stocks, stock_length in plans:
        assert Counter(piece.code for stock in stocks for piece in stock) == Counter(
            piece.code for piece in pieces
        )
        assert all(
            sum(piece.length + DEFAULT_KERF for piece in stock) <= stock_length
            for stock in stocks
        )
    assert len(plans[0][1]) == 9
    assert len(plans[1][1]) == 12


def test_panel_plan_releases_both_side_fields_before_other_panel_stock(boards):
    stocks = panel_stock_plan(boards, 4500, DEFAULT_KERF)

    assert [sum(bool(piece.gang_cut) for piece in stock) for stock in stocks[:5]] == [
        3,
        3,
        3,
        3,
        2,
    ]
    assert not any(piece.gang_cut for stock in stocks[5:] for piece in stock)
    assert [
        piece.code for stock in stocks[:5] for piece in stock if piece.gang_cut
    ] == [f"LSC{index}" for index in range(1, 8)] + [
        f"RSC{index}" for index in range(1, 8)
    ]
    for stock in stocks:
        square_cuts = [piece.length for piece in stock if not piece.gang_cut]
        assert square_cuts == sorted(square_cuts, reverse=True)


def test_stock_order_allows_global_longest_first_cut_batches(beams):
    stocks = pack_stock(beams, 4200, DEFAULT_KERF)

    for stock in stocks:
        assert [round(piece.length, 1) for piece in stock] == sorted(
            (round(piece.length, 1) for piece in stock), reverse=True
        )


def test_html_contains_every_code_and_required_shop_phases(
    guide_document, beams, boards
):
    document = guide_document

    for piece in beams + boards:
        assert piece.code in document
    for sheet in ("A-200", "A-300", "A-400"):
        assert f"Sheet {sheet}" in document
    assert "Sheet A-000" not in document
    assert "Sheet A-100" not in document
    assert "Sheet A-500" not in document
    assert "Structural timber" in document
    assert "Råspont (matchboard/V-groove cladding)" in document
    assert "Unit drawings" in document
    assert "Assembly" in document
    assert "<dd>2.8 mm per cut</dd>" in document
    assert "do not pre-cut the roof reliefs" in document.lower()
    assert "--stock-aspect:46.666667" in document
    assert "--stock-aspect:18.750000" in document
    assert "The 9 beam stock lengths below are named B01 to B09" in document
    assert "The 12 cladding stock lengths below are named P01 to P12" in document
    assert "Label the P01 to P03 remainders" in document
    assert "Fourteen side boards come next, then nine door boards" in document
    for removed in (
        "Caution · verify the stock first",
        "Brace rule",
        "Batch order · A-200",
        "Operation A · release",
        "Operation B · cut",
        "Workshop preparation · clean stock ends",
        "Do not trim loose cladding",
        "Solid members are the frame",
        "Frame fastening and finished-angle check",
    ):
        assert removed not in document
    assert document.count("If your material ends are rough") == 2
    assert "6 × 120 mm sunk wood screws" in document
    assert "6 × 90 mm sunk wood screws" in document
    assert "2.8 × 60 mm nails or 6 × 60 mm sunk wood screws" in document
    assert ".stock-piece.is-gang { background:var(--sheet); }" in document
    assert "repeating-linear-gradient(45deg" not in document


def test_masthead_names_the_project_and_credits_its_sources(guide_document):
    document = guide_document

    assert '<span class="sheet-no">WORKING DRAWING</span>' in document
    assert "<h1>Can AI build a toilet yet?</h1>" in document
    assert (
        "An experiment in re-drawing a technical drawing as an editable parametric CAD model with Claude and Codex."
        in document
    )
    assert "https://www.instagram.com/hannes.soderquist/" in document
    assert "https://x.com/feelepxyz" in document
    assert "@feelepxyz" in document
    assert "https://github.com/feelepxyz/dass" in document
    assert 'class="source-icon"' in document
    assert "controls.maxPolarAngle = Math.PI;" in document
    assert "ground.visible = camera.position.y >= ground.position.y;" in document
    renderer = (Path(__file__).parents[1] / "web/render/render.mjs").read_text()
    in_situ_camera = re.search(
        r"const IN_SITU_CAMERA = Object\.freeze\(\{.*?\n\}\);", renderer, re.DOTALL
    )
    assert in_situ_camera
    assert in_situ_camera.group() in document
    assert "new THREE.PerspectiveCamera" in document
    assert (
        "camera.setViewOffset(width, fullHeight, 0, offsetY, width, height);"
        in document
    )
    assert "const IN_SITU_CROP_FOCUS = 1.0;" in document
    assert (
        "camera.position.copy(anchor).addScaledVector(direction, IN_SITU_CAMERA.distance);"
        in document
    )
    assert "new THREE.MeshBasicMaterial" in document
    assert ".viewer-canvas { position:absolute; inset:0; z-index:1;" in document
    assert ".drawing-render { position:absolute; inset:0; z-index:0;" in document
    assert "addPlankLines(gltf.scene);" in document
    assert "ATLAS.coverMm" in document
    assert "isPlankSeam" in document
    assert 'id="method"' not in document
    assert "Material schedule" not in document
    assert document.count("Caution · verify the stock first") == 0
    assert "Frame timber, 45 × 45 ×" in document
    assert "Råspont (matchboard/V-groove cladding), 120 × 23 ×" in document
    assert "Cut every piece at one stop setting before you change the stop." in document
    assert (
        "The renders and the model show the same geometry as the cut lists."
        not in document
    )
    assert "Standing in the clearing with the door and roof open." not in document


@pytest.mark.parametrize(
    ("document_fixture", "canonical", "title"),
    [
        (
            "guide_document",
            "https://canaibuildatoiletyet.com/",
            "DASS · Can AI build a toilet yet?",
        ),
        (
            "started_document",
            "https://canaibuildatoiletyet.com/how-it-started.html",
            "DASS · How it started",
        ),
        (
            "progress_document",
            "https://canaibuildatoiletyet.com/how-its-going.html",
            "DASS · How it's going",
        ),
    ],
    ids=["guide", "started", "progress"],
)
def test_public_pages_include_canonical_social_metadata(
    request, document_fixture, canonical, title
):
    document = request.getfixturevalue(document_fixture)

    assert f'<link rel="canonical" href="{canonical}">' in document
    assert (
        f'<meta property="og:title" content="{escape(title, quote=True)}">' in document
    )
    assert (
        '<meta property="og:image" content="https://canaibuildatoiletyet.com/web-renders/in-situ-open.jpg">'
        in document
    )
    assert '<meta name="twitter:card" content="summary_large_image">' in document
    assert '<meta name="twitter:site" content="@feelepxyz">' in document


def test_story_navigation_links_the_drawing_and_progress_pages(guide_document):
    document = guide_document

    assert (
        'class="story-link story-link-start" href="how-it-started.html#story-nav"'
        in document
    )
    assert (
        'class="story-link story-link-drawing" href="#story-nav" aria-current="page"'
        in document
    )
    assert (
        'class="story-link story-link-going" href="how-its-going.html#story-nav"'
        in document
    )
    assert '<nav class="story-nav" id="story-nav"' in document
    assert "scroll-margin-top:16px;" in document
    assert ".story-link { justify-content:space-between; text-align:left; }" in document
    assert (
        ".story-link .story-link-copy { align-items:flex-start; order:1; }" in document
    )
    assert ".story-link .story-arrow { order:2; }" in document
    assert 'class="view-grid" id="render"' in document
    assert 'class="set-foot-copy"' in document
    assert document.index("The checks are saved in this browser") < document.index(
        'class="reset"'
    )
    assert 'class="set-foot-link" href="how-its-going.html#story-nav"' in document
    assert 'path d="M21 12H4m0 0 6 6m-6-6 6-6"' in document
    assert 'path d="M12 3v17m0 0 6-6m-6 6-6-6"' in document
    assert 'path d="M3 12h17m0 0-6-6m6 6-6 6"' in document


def test_started_page_carries_the_readme_story_without_section_name(started_document):
    document = started_document

    assert "<h2>How it started</h2>" in document
    assert "Evolution" not in document
    for asset in (
        "original-side-drawing.jpg",
        "validation-open.jpg",
        "seat-section-comparison.jpg",
        "door-front-comparison.jpg",
    ):
        assert f'src="started/{asset}"' in document
    assert 'href="https://www.instagram.com/hannes.soderquist/"' in document
    assert "I first asked Codex to copy the technical drawing" in document
    assert "All CAD edits were done from" in document
    assert "prompts only" in document
    assert "I then had Codex and Claude add specifications" in document
    assert "comparison cut lists" in document
    assert "editable model matched the drawing" in document
    assert "creating impossible cuts" in document
    assert "the floor boards did" in document
    assert "not have enough support" in document
    assert "The same model then generates assembly instructions" in document
    assert 'href="cut-guide.html#story-nav">working drawing</a>' in document
    assert "A fastening review then found a join" in document
    assert "models both screw paths" in document
    assert 'class="set-foot-link" href="cut-guide.html#story-nav"' in document
    assert "<span>Working drawing</span>" in document
    assert 'class="story-link story-link-start" href="#story-nav"' in document
    assert (
        'class="story-link story-link-drawing" href="cut-guide.html#story-nav"'
        in document
    )
    assert (
        'class="story-link story-link-going" href="how-its-going.html#story-nav"'
        in document
    )
    assert 'path d="M12 3v17m0 0 6-6m-6 6-6-6"' in document
    assert 'path d="M12 21V4m0 0 6 6m-6-6-6 6"' in document


def test_progress_page_uses_the_same_heading_and_supplied_photos(progress_document):
    document = progress_document

    assert "<h1>Can AI build a toilet yet?</h1>" in document
    assert "<h2>How it's going</h2>" in document
    assert (
        "Real-world progress following the drawing to build an outdoor toilet."
        not in document
    )
    assert "Model 0.1.4 · cladding fixings are centred after trimming" in document
    assert "<h3>Model changelog</h3>" in document
    assert "2026-08-02 · 0.1.4" in document
    assert "2026-08-02 · 0.1.3" in document
    assert "2026-08-02 · 0.1.2" in document
    assert "2026-08-02 · 0.1.1" in document
    assert "2026-07-31 · 0.1.0" in document
    assert "pauseWhenOutOfView" in document
    assert "angled screw paths" not in document
    assert "resulting clearance" not in document
    assert (
        '<p class="masthead-sub">Real-world progress following the drawing to build an outdoor toilet.</p>'
        not in document
    )
    assert 'class="title-block"' not in document
    assert (
        'class="story-link story-link-start" href="how-it-started.html#story-nav"'
        in document
    )
    assert (
        'class="story-link story-link-drawing" href="cut-guide.html#story-nav"'
        in document
    )
    assert 'class="story-link story-link-going" href="#story-nav"' in document
    assert 'path d="M21 12H4m0 0 6 6m-6-6 6-6"' in document
    assert 'path d="M12 3v17m0 0 6-6m-6 6-6-6"' in document
    assert 'path d="M12 21V4m0 0 6 6m-6-6-6 6"' in document
    assert 'class="set-foot-link" href="how-it-started.html#story-nav"' in document
    assert "<span>How it started</span>" in document
    assert "<span>Working drawing</span>" not in document
    assert 'path d="M3 12h17m0 0-6-6m6 6-6 6"' in document
    assert 'path d="M21 12H4m0 0 6 6m-6-6 6-6"' in document
    assert document.index("progress/saw-setup-for-beam-cuts.jpg") < document.index(
        "progress/beam-cuts.jpg"
    )
    assert document.index("progress/sorted-beam-cuts.jpg") < document.index(
        "progress/cutting.mp4"
    )
    assert document.index("progress/assembling-frames.jpg") > document.index(
        "progress/cutting.mp4"
    )
    for asset in (
        "progress/sorted-beam-cuts.jpg",
        "progress/assembling-frames.jpg",
        "progress/side-panel.jpg",
        "progress/assembling-side.jpg",
        "progress/sides.jpg",
        "progress/sides-and-floor.jpg",
        "progress/assembled-no-roof.jpg",
        "progress/closed-roof-unattached.jpg",
        "progress/assembled-no-roof-occupied.jpg",
    ):
        assert asset in document
    assert document.index("progress/assembled-no-roof.jpg") < document.index(
        "progress/closed-roof-unattached.jpg"
    )
    assert document.index("progress/closed-roof-unattached.jpg") < document.index(
        "progress/assembled-no-roof-occupied.jpg"
    )
    assert 'src="progress/cutting.mp4" type="video/mp4"' in document
    assert 'poster="progress/cutting-poster.jpg"' in document
    assert "Cutting the cladding batch" in document
    assert 'preload="none"' in document
    assert 'loading="eager"' in document
    assert 'loading="lazy"' in document


def test_progress_page_uses_cloudflare_stream_when_configured(monkeypatch):
    monkeypatch.setattr(
        build_guide,
        "CLOUDFLARE_STREAM_PLAYER_URL",
        "https://customer-example.cloudflarestream.com/video-uid/iframe",
    )

    document = build_guide.progress_html()

    assert (
        'src="https://customer-example.cloudflarestream.com/video-uid/iframe"'
        in document
    )
    assert 'loading="lazy"' in document
    assert 'type="video/mp4"' not in document


def test_cladding_is_trimmed_on_its_unit_after_fixing(guide_document, plates):
    document = guide_document

    assert "bench layout" not in document
    assert "Trim the field to drawing" not in document
    assert "Frame and cladding registration" not in document
    assert "Do not trim loose cladding" not in document
    assert "Trim the joined field to the 854 mm before fixing." in document
    assert (
        "Trim the joined field to the 852 mm seat-box width after fixing"
        not in document
    )
    assert (
        "Fix every board to SBF1 at floor level and SBB1 under the seat box. "
        "The two screw rows are shown on the drawing." in document
    )
    assert "circular-saw guide" in document
    for letter in "BCDEH":
        assert "CUT AFTER FIXING" in plates[letter]
        assert f'data-unit-face="{letter}"' in document
    for letter in "CD":
        assert "45 × 45 NOTCH" in plates[letter]
        assert "100 fall over 770" in plates[letter]
    for letter in "ABCDEFGH":
        assert f'data-check="unit-{letter.lower()}"' in document

    for letter in "CDE":
        assert 'class="dim-text"' in plates[letter]
        assert ">100</text>" in plates[letter]
    assert 'class="screw-layer screw-frame"' in plates["A"]
    for letter in "BCDEH":
        assert 'class="screw-layer screw-frame"' in plates[letter]
        assert 'class="screw-layer screw-cladding"' in plates[letter]
        assert 'class="screw-guide"' in plates[letter]
        assert "FROM" in plates[letter]
    assert plates["B"].count('class="screw-head"') >= 18
    assert plates["C"].count('class="screw-head"') >= 14
    # Eight frame screws plus two cladding rows across five seat-top boards.
    assert plates["H"].count('class="screw-head"') == 18
    assert "STB5" in plates["H"]
    assert "60 mm TRIM" in plates["H"]
    assert "SBS3" in plates["H"]
    assert "SBS4" in plates["H"]
    assert "Fix DCB1 to DCB9" in document
    assert (
        "Attach the left and right side units to the back unit with the indicated beam screws"
        in document
    )
    assert "Fix FCB1 to FCB8" in document
    assert "FCB1–FCB8 · 8 boards" not in plates["G"]
    assert "LSH1, RSH1, and BWH1 100 mm above ground" in document


def test_cladding_screws_centre_on_trimmed_boards_and_clear_frame_paths(
    design, boards, by_name
):
    parts = {name: part.solid for name, part in by_name.items()}
    fields = panels(boards)
    fastening = analyze_frame_fastening(design)
    units = {
        "door_panel": (FRONT, ("door_bottom", "door_top")),
        "left_wall": (LEFT, ("left_bottom", "left_top")),
        "right_wall": (RIGHT, ("right_bottom", "right_top")),
        "back_wall": (REAR, ("back_bottom", "back_top")),
        "floor": (PLAN, ("front_bottom", "floor_back_support")),
        "seat_top": (
            PLAN,
            ("seat_support_outer_left", "seat_support_outer_right"),
        ),
        "seat_front": (
            FRONT,
            ("seat_floor_support", "seat_box_support_front"),
        ),
    }
    layouts = {
        name: cladding_screw_layout(
            parts[name], fields[name], view, parts, members, fastening, design
        )
        for name, (view, members) in units.items()
    }

    assert all(
        mark.frame_clearance >= SCREW_PATH_CLEARANCE_MM
        for layout in layouts.values()
        for row in layout
        for mark in row.marks
    )

    floor_centres = cladding_board_centres(fields["floor"], design.interior_x)
    floor_last = layouts["floor"][0].marks[-1]
    assert floor_last.board_code == "FCB8"
    assert floor_last.point[fields["floor"].axis] == almost(floor_centres[-1])
    assert floor_centres[-1] == almost(880)

    seat_centres = cladding_board_centres(fields["seat_top"], design.seat_front_y)
    seat_last = layouts["seat_top"][0].marks[-1]
    assert seat_last.board_code == "STB5"
    assert seat_last.point[fields["seat_top"].axis] == almost(seat_centres[-1])
    assert seat_centres[-1] == almost(717)

    side_centres = cladding_board_centres(fields["left_wall"])
    side_first = layouts["left_wall"][0].marks[0].point[fields["left_wall"].axis]
    mirrored_first = layouts["right_wall"][0].marks[0].point[fields["right_wall"].axis]
    assert side_first > side_centres[0]
    assert abs(side_first - side_centres[1]) < abs(side_centres[0] - side_centres[1])
    assert mirrored_first == almost(side_first)

    for row in layouts["seat_top"]:
        member = parts[row.member_name].BoundingBox()
        assert row.station != (member.xmin + member.xmax) / 2


def test_shell_joint_precedes_cladding_only_floor_stack(guide_document, plates):
    document = guide_document

    assert document.index("<h3>Shell joint</h3>") < document.index(
        "<h3>Floor deck</h3>"
    )
    assert all(
        code in plates["F"] for code in ("FBB1", "FBS1", "FBS2", "LSH1", "RSH1", "BWH1")
    )
    assert plates["F"].count('class="screw-head"') == 8
    assert 'class="screw-layer screw-cladding"' not in plates["F"]
    assert 'class="screw-layer screw-frame"' not in plates["G"]
    assert 'class="screw-layer screw-cladding"' in plates["G"]
    assert plates["G"].count('class="screw-head"') == 16
    assert (
        'data-face="cladding"'
        in document[document.index('<article class="unit" id="unit-g"') :]
    )


def test_lengths_read_as_drawing_numbers():
    # The reference set spaces thousands; a bare 1315.1 is not what a
    # drawing letters, and the register depends on this shape too.
    assert fmt(1315.1) == "1 315.1"
    assert fmt(4200) == "4 200"
    assert fmt(854) == "854"


def test_printed_set_takes_the_drawn_model_over_the_photographs(guide_document):
    document = guide_document

    assert 'class="drawing-render"' in document
    assert "web-renders/drawing-open.svg" in document
    # The sheet prints a still because a live canvas does not print, and it
    # is always the drawn finish whatever the screen is showing. The image
    # is built by the script, so no empty <img> ever ships in the markup.
    assert '<img class="viewer-print"' not in document
    assert 'printShot.className = "viewer-print";' in document
    assert "function takePrintStill()" in document
    assert 'finish = "line";' in document
    assert 'window.addEventListener("beforeprint", takePrintStill);' in document
    # Print preview and print-to-PDF never fire beforeprint.
    assert 'window.matchMedia("print")' in document
    assert "has-print-model" in document
    # Photographs stay on screen; they only return if no still was taken.
    assert ".gallery, .viewer { display:none; }" in document
    assert "body:not(.has-print-model) .gallery { display:block; }" in document
    # The still ships with its own width and height, so a max-width and a
    # max-height would each be applied on their own and stretch the model
    # across the sheet. One stated side, and the other follows the ratio.
    assert (
        ".viewer-print { display:block; margin:0 auto; "
        "width:auto; height:104mm; max-width:100%; }"
    ) in document
    # The title sheet breaks to a new page, so the page margin is the air
    # under the model and the drawing keeps the height padding would cost.
    assert ".masthead { padding-bottom:0; break-after:page; }" in document


def test_printed_drawings_are_bound_by_the_page_and_never_split(guide_document):
    document = guide_document

    # A guessed plate height letterboxes the drawing to a fraction of its
    # column; the page has to set the size instead.
    assert "height:74mm" not in document
    assert ".unit .drawing .plate { flex:1 1 auto; min-height:0; }" in document
    # One unit per sheet: the drawing, its steps and its codes travel
    # together, under the same head of air every printed page opens with.
    # That air is the page box, not padding on the sheet: padding only
    # reaches the first page a sheet fragments onto, so a page carrying the
    # overflow of a sheet opened hard against the trim.
    assert "@page { size:A4 landscape; margin:14mm 9mm 10mm; }" in document
    assert "height:184mm; break-before:page;" in document
    assert ".sheet, .masthead { border:0; padding:0; margin:0; }" in document
    # Nothing may push an empty sheet out of the end of the set.
    assert ".sheet:last-of-type { break-after:auto; }" in document
    assert ".drawing, .unit, .stock, .note { break-inside:avoid; }" in document


@pytest.mark.parametrize(
    "document_fixture",
    ["started_document", "progress_document"],
    ids=["started", "progress"],
)
def test_printed_story_pages_keep_their_figures_whole_and_open_with_work(
    request, document_fixture
):
    document = request.getfixturevalue(document_fixture)

    # The story masthead is a title bar, not a title sheet: nothing is
    # drawn beside it, so a page of its own printed all but empty.
    assert ".masthead-progress { break-after:auto; padding-bottom:8mm; }" in document
    assert ".masthead-progress + .sheet { break-before:auto; }" in document
    # `break-inside` is only honoured while a block still fits the page,
    # so each figure is bound on its height before it is asked to stay
    # whole. Otherwise the image split and the caption was orphaned.
    assert (
        ".started-figure, .started-figure-pair, .progress-photo, .progress-video-figure { break-inside:avoid; }"
        in document
    )
    # The images ship with their own width and height, so one bound per
    # axis lets the other follow the ratio instead of stretching.
    assert (
        ".started-figure img { width:auto; height:auto; "
        "max-width:100%; max-height:118mm; margin:0 auto; }"
    ) in document
    assert (
        ".progress-photo-frame { width:auto; height:130mm; max-width:100%; margin:0 auto; }"
        in document
    )


def test_notes_hold_the_same_measure_as_the_prose_around_them(guide_document):
    document = guide_document

    # A note is prose in a box, so its border sits just clear of the text
    # rather than ruling the whole sheet.
    assert "p { margin:0; max-width:68ch; }" in document
    assert "max-width:calc(68ch + 2 * var(--note-pad) + 2px);" in document
    assert "--note-pad:24px;" in document
    assert "--note-pad:16px;" in document
    # The batch tables live inside notes and are wider than that measure.
    assert ".note:has(.table-scroll) { max-width:none; }" in document
    assert '<div class="note material-spec">' in document
    assert "Operation A" not in document


def test_html_carries_every_reference_view_and_its_model_assets(guide_document):
    document = guide_document

    for _, views in GALLERY:
        for name, _, _ in views:
            assert render_asset(name) in document
    for variant in ("open", "closed"):
        assert f'data-variant="{variant}"' in document
    assert '"three":"./vendor/three.module.min.js"' in document


def test_every_panel_finishes_at_its_modeled_span(design, boards):
    fields = panels(boards)
    spans = {
        "door_panel": design.width,
        "left_wall": design.plan_grid_depth,
        "right_wall": design.plan_grid_depth,
        "back_wall": design.interior_width,
        "floor": design.interior_width,
        "seat_top": design.seat_depth,
        "seat_front": design.interior_width,
    }
    assert set(fields) == set(spans)
    for key, span in spans.items():
        panel = fields[key]
        assert panel.span == almost(span, 6)
        assert panel.joined - panel.trim == almost(span, 6)
        assert len(panel.pieces) == panel.count
    assert fields["seat_top"].count == 5
    assert fields["seat_top"].blank == design.seat_box_width
    assert fields["seat_top"].trim == almost(60, 6)


def test_plates_project_the_model_rather_than_fixed_coordinates(design, by_name):
    post = outline(by_name["front_post_left"].solid, FRONT)
    assert len(post) == 4
    assert max(u for u, _ in post) - min(u for u, _ in post) == almost(design.frame)
    assert max(v for _, v in post) - min(v for _, v in post) == almost(
        design.front_post_height
    )

    # A diagonal brace is a parallelogram, never its bounding box.
    brace = outline(by_name["left_brace"].solid, FRONT)
    assert len(brace) == 4

    # The cladding sits inboard of the frame it covers, which is the one
    # relationship the registration plate exists to prove.
    cut = design.seat_height + design.leg_extension
    wall = cross_section(by_name["left_wall"].solid, PLAN, cut)
    frame = cross_section(by_name["front_post_left"].solid, PLAN, cut)
    assert max(u for u, _ in wall) - min(u for u, _ in wall) == almost(
        design.cladding, 3
    )
    assert min(u for u, _ in wall) >= max(u for u, _ in frame) - 1e-6


def test_every_stack_gets_a_plate_carrying_its_own_codes(plates, guide_document):
    assert set(plates) == set("ABCDEFGHIJK")
    for letter, codes in (
        ("A", ("RBH1", "RBS1", "RBC1")),
        ("B", ("DBV1", "DBD1")),
        ("C", ("LSV1", "LSD1")),
        ("E", ("BWH1", "BWD1")),
        ("H", ("SBH1", "SBS1", "SBS3")),
        ("I", ("SBB1", "SBB2")),
        ("J", ("SBB1", "SBF1")),
        ("K", ("SFB1",)),
    ):
        for code in codes:
            assert code in plates[letter]
    for code in ("DCB1", "LSC1", "BWC1", "STB1"):
        assert code in guide_document
    for code in ("FCB1", "STB1"):
        assert code in plates["G"] or code in plates["H"]
    assert "SFB1" in plates["K"]
    assert plates["K"].count('class="field"') == 8
    assert plates["K"].count('class="screw-head"') == 16
    assert plates["K"].count('class="cladding-code"') == 8
    assert all(f">SFB{index}</text>" in plates["K"] for index in range(1, 9))
    assert ">854</text>" in plates["K"]
    assert 'class="ghost"' in plates["K"]
    assert 'class="cladding-code"' in plates["G"]
    assert 'class="dominant-baseline"' not in plates["G"]
    assert 'dominant-baseline="middle"' in plates["E"]
    assert 'transform="rotate(' in plates["E"]
    assert 'data-face="left"' in guide_document
    assert "perspective-left" in plates["J"]
    assert "perspective-right" in plates["J"]


def test_seat_support_perspective_contains_only_supports_and_shell(plates):
    drawing = plates["J"]

    assert 'class="field"' not in drawing
    assert 'class="opening"' not in drawing
    assert 'class="ghost-edge"' in drawing
    assert 'class="member-edge"' in drawing
    assert "SBH1" not in drawing
    assert "SBH2" not in drawing
    assert "SBS1" not in drawing
    assert "SBS2" not in drawing
    assert "23 MM SIDE CLADDING" in drawing
    assert drawing.count(">352 mm</text>") == 4
    assert drawing.count(">477 mm</text>") == 2
    assert "397 - 45" not in drawing
    assert "ISOMETRIC PROJECTION" in drawing


@pytest.mark.parametrize("view", [build_guide.AXO_RIGHT, build_guide.AXO_LEFT])
def test_seat_support_views_are_true_isometric_projections(view):
    origin = view((0, 0, 0))
    projected_axes = [
        math.dist(origin, view(axis)) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    ]

    assert projected_axes == pytest.approx([math.sqrt(2 / 3)] * 3)


def test_seat_support_view_uses_the_modeled_inside_back_face(design, parts):
    solids = {part.name: part.solid for part in parts}
    plate = build_guide._seat_installation_perspective(
        design,
        solids,
        build_guide.analyze_frame_fastening(design),
        "right",
        build_guide.AXO_RIGHT,
    )
    back = solids["back_wall"]
    inside = build_guide.projected_face_at(
        back, build_guide.AXO_RIGHT, 1, back.BoundingBox().ymin
    )
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{plate.x(u):.1f} {plate.y(v):.1f}"
        for index, (u, v) in enumerate(inside)
    )

    assert f'<path class="ghost" d="{path} Z"/>' in plate.body


def test_rear_height_dimension_uses_the_outer_sbb2_corner(design, parts):
    solids = {part.name: part.solid for part in parts}
    plate = build_guide._seat_installation_perspective(
        design,
        solids,
        build_guide.analyze_frame_fastening(design),
        "right",
        build_guide.AXO_RIGHT,
    )
    dimensions = [item for item in plate.body if item.startswith('<path class="dim"')]
    rear = solids["seat_box_support_rear"].BoundingBox()
    floor_corner = plate.at(
        build_guide.AXO_RIGHT((rear.xmax, rear.ymax, design.floor_top))
    )
    beam_corner = plate.at(
        build_guide.AXO_RIGHT((rear.xmax, rear.ymax, design.seat_support_top))
    )

    assert len(dimensions) == 3
    assert f"M{floor_corner[0]:.1f} {floor_corner[1]:.1f}" in dimensions[1]
    assert f"M{beam_corner[0]:.1f} {beam_corner[1]:.1f}" in dimensions[1]


def test_viewer_names_every_modeled_part_with_its_cut_code(design, boards, parts):
    data = viewer_parts(design, boards)
    modeled = {part.name for part in parts}

    assert set(data) == modeled
    for name, code in BEAM_CODES.items():
        assert data[name]["code"] == code
    assert data["left_wall"]["code"] == "LSC1–LSC7"
    assert data["left_wall"]["size"] == "770 × 1 175 × 23"
    assert data["roof"]["tone"] == "roof"


def test_viewer_parts_carry_the_material_the_timber_pipeline_reads(design, boards):
    # The shared pipeline picks a role off `material`; when it is missing
    # every piece is dressed as wood and the roof sheet stops being metal.
    data = viewer_parts(design, boards)

    assert data["roof"]["material"] == "metal roof"
    assert data["roof_hinge_pin"]["material"] == "metal"
    assert data["front_post_left"]["material"] == "wood"
    assert all(part["material"] for part in data.values())


def test_cut_batches_can_drop_the_gang_cut_side_panels_from_the_table(design, boards):
    # The side fields are batched separately in their own gang-cut table, so
    # the shared square-cut table can be asked to exclude them.
    stock_lookup = {piece.code: "P01" for piece in boards}
    with_gang = cut_batches(boards, stock_lookup, design)
    without_gang = cut_batches(boards, stock_lookup, design, include_gang=False)

    assert "LSC1" in with_gang and "RSC1" in with_gang
    assert "LSC1" not in without_gang and "RSC1" not in without_gang
    # A non-gang-cut code is unaffected either way.
    assert "DCB1" in with_gang
    assert "DCB1" in without_gang


def test_cross_section_returns_nothing_outside_the_solids_extent(by_name):
    post = by_name["front_post_left"].solid.BoundingBox()
    assert cross_section(by_name["front_post_left"].solid, PLAN, post.zmax + 1000) == []


def test_convex_hull_returns_fewer_than_three_points_unchanged():
    # A hull needs three points to enclose anything; below that there is
    # nothing to wrap, so the point (or pair) is handed back as-is.
    assert convex_hull([(0, 0)]) == [(0, 0)]
    assert convex_hull([(0, 0), (1, 1)]) == [(0, 0), (1, 1)]


def test_outline_falls_back_to_the_convex_hull_for_a_cylindrical_end_face(by_name):
    # The hinge pin is a cylinder along x; viewed along that same axis (LEFT),
    # its flat end faces read as "square" but each is a circle whose wire
    # carries a single vertex, too few to return directly. outline() then
    # falls back to the hull of every vertex on the solid, exactly like
    # convex_hull() applied to the raw vertex list.
    pin = by_name["roof_hinge_pin"].solid
    expected = convex_hull([LEFT(vertex.toTuple()) for vertex in pin.Vertices()])
    assert outline(pin, LEFT) == expected


def test_plate_shape_skips_polygons_with_fewer_than_three_points():
    plate = Plate([[(0, 0), (10, 10)]])
    before = list(plate.body)

    plate.shape([(0, 0), (5, 5)], "field")

    assert plate.body == before


def test_plate_dim_omits_the_label_when_no_measure_text_is_given():
    plate = Plate([[(0, 0), (10, 10)]])

    plate.dim((0, 0), (0, 10), 5, text="")  # vertical
    plate.dim((0, 0), (10, 0), 5, text="")  # horizontal

    assert not any("dim-text" in markup for markup in plate.body)


def test_plate_dimensions_are_always_in_the_outer_margin():
    plate = Plate([[(0, 0), (100, 100)]])

    plate.dim((0, 0), (0, 50), 40, text="50 mm")
    plate.dim((0, 0), (50, 0), -40, text="50 mm")

    assert any("H982.0" in markup for markup in plate.body)
    assert any("V18.0" in markup for markup in plate.body)


def test_frame_screw_paths_use_receiving_ends_and_diagonal_axes(design, by_name):
    analysis = analyze_frame_fastening(design)
    shapes = {name: part.solid for name, part in by_name.items()}

    roof_mark = next(
        mark
        for mark in analysis.screws
        if mark.from_beam == "roof_back"
        and mark.into_beam == "roof_left"
        and mark.lane_mm == design.frame / 2
    )
    assert roof_mark.centered
    roof_head, roof_target = _drawing_screw_path(
        shapes[roof_mark.into_beam], shapes[roof_mark.from_beam], roof_mark, design
    )
    assert math.dist(roof_head, roof_target) == pytest.approx(design.screw_length)
    assert roof_target[0] == pytest.approx(design.frame / 2)
    assert roof_head[1] > roof_target[1]
    assert roof_head[2] < roof_target[2]

    connector_mark = next(
        mark
        for mark in analysis.screws
        if mark.from_beam == "roof_left" and mark.into_beam == "roof_middle"
    )
    connector_face = _target_entry_face(
        shapes[connector_mark.into_beam],
        shapes[connector_mark.from_beam],
        connector_mark,
    )
    _, connector_target = _drawing_screw_path(
        shapes[connector_mark.into_beam],
        shapes[connector_mark.from_beam],
        connector_mark,
        design,
    )
    connector_end = _face_center(connector_face)
    assert connector_target[1:] == pytest.approx(connector_end[1:])

    diagonal_mark = next(
        mark
        for mark in analysis.screws
        if mark.from_beam == "front_post_left"
        and mark.into_beam == "left_brace"
        and mark.lane_mm == 12
    )
    diagonal_head, diagonal_target = _drawing_screw_path(
        shapes[diagonal_mark.into_beam],
        shapes[diagonal_mark.from_beam],
        diagonal_mark,
        design,
    )
    assert math.dist(diagonal_head, diagonal_target) == pytest.approx(
        design.screw_length
    )
    assert diagonal_target[1] > diagonal_head[1]
    assert diagonal_target[2] < diagonal_head[2]


def test_shell_joint_screw_paths_leave_the_structure_outward(design, by_name):
    analysis = analyze_frame_fastening(design)
    shapes = {name: part.solid for name, part in by_name.items()}

    for mark in (screw for screw in analysis.screws if screw.position_axis is not None):
        head, target = _drawing_screw_path(
            shapes[mark.into_beam], shapes[mark.from_beam], mark, design
        )
        assert math.dist(head, target) == pytest.approx(design.screw_length)
        if mark.into_beam == "back_bottom":
            assert head[1] < target[1]
        elif mark.into_beam == "right_bottom":
            assert head[0] < target[0]
        elif mark.into_beam == "front_bottom":
            if mark.from_beam == "left_bottom":
                assert head[0] < target[0]
            else:
                assert mark.from_beam == "right_bottom"
                assert head[0] > target[0]
        elif (
            mark.into_beam.startswith("seat_box_support_")
            or mark.into_beam == "seat_floor_support"
        ):
            if mark.from_beam == "left_wall":
                assert head[0] < target[0]
            else:
                assert mark.from_beam == "right_wall"
                assert head[0] > target[0]
        else:
            assert mark.into_beam == "left_bottom"
            assert head[0] > target[0]


def test_centered_screw_marks_follow_the_receiving_beam_end_centres(design, by_name):
    analysis = analyze_frame_fastening(design)
    shapes = {name: part.solid for name, part in by_name.items()}

    for mark in (screw for screw in analysis.screws if screw.centered):
        face = _target_entry_face(shapes[mark.into_beam], shapes[mark.from_beam], mark)
        end = _face_center(face)
        normal = _face_normal(face)
        _, target = _drawing_screw_path(
            shapes[mark.into_beam], shapes[mark.from_beam], mark, design
        )
        delta = tuple(target[index] - end[index] for index in range(3))
        projection = sum(delta[index] * normal[index] for index in range(3))
        projected = tuple(normal[index] * projection for index in range(3))

        assert math.dist(end, target) == pytest.approx(design.frame / 2)
        assert delta == pytest.approx(projected)


def test_plank_atlas_falls_back_to_the_default_without_a_render_manifest(tmp_path):
    assert plank_atlas(tmp_path) == DEFAULT_ATLAS


def test_draw_field_rejects_a_panel_whose_axis_is_not_the_views_span_axis():
    panel = Panel(
        "door_panel", "DCB", "Door field", 0, (CutPiece("door_1", 900, 120, 23),)
    )

    # LEFT looks along the side walls (u_axis=1); a door-style panel (axis=0)
    # can never be the field drawn in that view. The raise happens before
    # `plate` or `solid` are read, so stand-ins for both are enough.
    stand_in = Plate([[(0.0, 0.0), (1.0, 1.0)]])
    with pytest.raises(ValueError, match="must be visible in the unit view"):
        draw_field(stand_in, [], box_at(0, 0, 0, 1, 1, 1), panel, LEFT, "test-field")


def test_draw_field_uses_the_full_profile_when_the_terminal_edge_has_no_match():
    panel = Panel(
        "door_panel", "DCB", "Door field", 0, (CutPiece("door_1", 900, 120, 23),)
    )
    solid = box_at(0, 0, 0, 120, 10, 10)
    # Only the point at u=120 (the panel's computed terminal edge) is a real
    # corner; fewer than two points land there, so the trim height must fall
    # back to the whole profile's v-range (0 to 100), not just that one point.
    profile = [(0.0, 0.0), (0.0, 5.0), (120.0, 100.0)]
    plate = Plate([profile])

    draw_field(plate, profile, solid, panel, FRONT, "test-field", label=False)

    trim_path = next(markup for markup in plate.body if 'class="trim"' in markup)
    assert f"{plate.y(0):.1f}" in trim_path
    assert f"{plate.y(100):.1f}" in trim_path
