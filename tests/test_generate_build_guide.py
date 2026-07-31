from collections import Counter
from html import escape

import pytest

from dass import Design
from dass.build_guide import (
    FRONT,
    GALLERY,
    PLAN,
    cross_section,
    fmt,
    guide_html,
    module_plates,
    outline,
    panels,
    progress_html,
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
    assert len(plans[0][1]) == 8
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
    assert "<dd>2.8 per cut</dd>" in document
    assert "do not pre-cut the roof reliefs" in document.lower()
    assert "--stock-aspect:46.666667" in document
    assert "--stock-aspect:18.750000" in document
    assert "<h3>Operation B · cut the remaining pieces</h3>" in document
    assert "run every beam in a serial pass" in document
    assert "run every plank in a serial pass" in document
    assert "Frame fastening and finished-angle check" in document
    assert "84 nominal beam screw marks" in document
    assert "Do not use the cladding fastener pattern" in document
    assert "6 × 120 mm sunk wood screws" in document
    assert "6 × 90 mm sunk wood screws" in document
    assert "2.8 × 60 mm nails or 6 × 60 mm sunk wood screws" in document
    assert "Every diagonal runs corner to corner" in document


def test_masthead_names_the_project_and_credits_its_sources(guide_document):
    document = guide_document

    assert '<span class="sheet-no">WORKING DRAWING</span>' in document
    assert "<h1>Can AI build a toilet yet?</h1>" in document
    assert (
        "Outdoor toilet drawn from a parametric model using claude and codex."
        in document
    )
    assert "https://www.instagram.com/hannes.soderquist/" in document
    assert "https://x.com/feelepxyz" in document
    assert "@feelepxyz" in document
    assert "https://github.com/feelepxyz/dass" in document
    assert 'class="source-icon"' in document
    assert "controls.maxPolarAngle = Math.PI;" in document
    assert "ground.visible = camera.position.y >= ground.position.y;" in document
    assert "camera.setViewOffset(3, 4, 0, 1, 3, 3);" in document
    assert "azimuth: -44" in document
    assert "frameWidth: 2500" in document
    assert "offsetX: 0" in document
    assert "addPlankLines(gltf.scene);" in document
    assert "ATLAS.coverMm" in document
    assert "isPlankSeam" in document
    assert 'id="method"' not in document
    assert "Material schedule" not in document
    assert document.count("Caution · verify the stock first") == 2
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
    assert "I asked Claude and Codex to build a CAD model" in document
    assert "until the model aligned with the measurements in the" in document
    assert "I did not edit any of the CAD drawings directly" in document
    assert "how long each beam should be" in document
    assert "created impossible cuts" in document
    assert "the floor boards did" in document
    assert "not have enough support" in document
    assert "The same model then generates assembly instructions" in document
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
        in document
    )
    assert "Latest model finding · diagonal fastening" in document
    assert "angled screw paths" in document
    assert "resulting clearance" in document
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
    assert 'loading="eager"' in document
    assert 'loading="lazy"' in document


def test_cladding_is_trimmed_on_its_unit_after_fixing(guide_document, plates):
    document = guide_document

    assert "bench layout" not in document
    assert "Trim the field to drawing" not in document
    assert "Frame and cladding registration" not in document
    assert "Do not trim loose cladding" in document
    assert "circular-saw guide" in document
    for letter in "BCDEFH":
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
    assert "LSH1, RSH1, and BWH1 100 mm above ground" in document


def test_lengths_read_as_drawing_numbers():
    # The reference set spaces thousands; a bare 1315.1 is not what a
    # drawing letters, and the register depends on this shape too.
    assert fmt(1315.1) == "1 315.1"
    assert fmt(4200) == "4 200"
    assert fmt(854) == "854"


def test_printed_set_takes_the_drawn_model_over_the_photographs(guide_document):
    document = guide_document

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
        ".started-figure, .started-figure-pair, .progress-photo { break-inside:avoid; }"
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
    assert '<div class="note">\n      <h3>Operation A' in document


def test_html_carries_every_reference_view_and_its_model_assets(guide_document):
    document = guide_document

    for _, views in GALLERY:
        for name, _, _ in views:
            assert f"web-renders/{name}.jpg" in document
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
        "seat_top": design.interior_width,
        "seat_front": design.interior_width,
    }
    assert set(fields) == set(spans)
    for key, span in spans.items():
        panel = fields[key]
        assert panel.span == almost(span, 6)
        assert panel.joined - panel.trim == almost(span, 6)
        assert len(panel.pieces) == panel.count


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


def test_every_stack_gets_a_plate_carrying_its_own_codes(plates):
    assert set(plates) == set("ABCDEFGH")
    for letter, codes in (
        ("A", ("RBH1", "RBS1", "RBC1")),
        ("B", ("DBV1", "DBD1", "DCB1")),
        ("C", ("LSV1", "LSD1", "LSC1")),
        ("E", ("BWH1", "BWD1", "BWC1")),
        ("H", ("SBH1", "SBS1", "STB1")),
    ):
        for code in codes:
            assert code in plates[letter]


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
