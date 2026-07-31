import unittest
from collections import Counter
from html import escape

from dass import Design, build
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
    beam_pieces,
    cladding_pieces,
    pack_stock,
    panel_stock_plan,
)


class BuildGuideTest(unittest.TestCase):
    def setUp(self):
        self.design = Design()
        self.kerf = DEFAULT_KERF
        self.beams = beam_pieces(self.design)
        self.boards = cladding_pieces(self.design)

    def test_plans_are_complete_and_kerf_safe(self):
        plans = (
            (self.beams, pack_stock(self.beams, 4200, self.kerf), 4200),
            (self.boards, panel_stock_plan(self.boards, 4500, self.kerf), 4500),
        )
        for pieces, stocks, stock_length in plans:
            self.assertEqual(
                Counter(piece.code for stock in stocks for piece in stock),
                Counter(piece.code for piece in pieces),
            )
            self.assertTrue(all(
                sum(piece.length + self.kerf for piece in stock) <= stock_length
                for stock in stocks
            ))
        self.assertEqual(len(plans[0][1]), 8)
        self.assertEqual(len(plans[1][1]), 12)

    def test_panel_plan_releases_both_side_fields_before_other_panel_stock(self):
        stocks = panel_stock_plan(self.boards, 4500, self.kerf)

        self.assertEqual(
            [sum(bool(piece.gang_cut) for piece in stock) for stock in stocks[:5]],
            [3, 3, 3, 3, 2],
        )
        self.assertFalse(any(
            piece.gang_cut for stock in stocks[5:] for piece in stock
        ))
        self.assertEqual(
            [piece.code for stock in stocks[:5] for piece in stock if piece.gang_cut],
            [f"LSC{index}" for index in range(1, 8)]
            + [f"RSC{index}" for index in range(1, 8)],
        )
        for stock in stocks:
            square_cuts = [piece.length for piece in stock if not piece.gang_cut]
            self.assertEqual(square_cuts, sorted(square_cuts, reverse=True))

    def test_stock_order_allows_global_longest_first_cut_batches(self):
        stocks = pack_stock(self.beams, 4200, self.kerf)

        for stock in stocks:
            self.assertEqual(
                [round(piece.length, 1) for piece in stock],
                sorted((round(piece.length, 1) for piece in stock), reverse=True),
            )

    def test_html_contains_every_code_and_required_shop_phases(self):
        document = guide_html(self.design)

        for piece in self.beams + self.boards:
            self.assertIn(piece.code, document)
        for sheet in ("A-200", "A-300", "A-400"):
            self.assertIn(f"Sheet {sheet}", document)
        self.assertNotIn("Sheet A-000", document)
        self.assertNotIn("Sheet A-100", document)
        self.assertNotIn("Sheet A-500", document)
        self.assertIn("Structural timber", document)
        self.assertIn("Råspont", document)
        self.assertIn("Unit drawings", document)
        self.assertIn("Assembly", document)
        self.assertIn("<dd>2.8 per cut</dd>", document)
        self.assertIn("do not pre-cut the roof reliefs", document.lower())
        self.assertIn("--stock-aspect:46.666667", document)
        self.assertIn("--stock-aspect:18.750000", document)
        self.assertIn('<h3>Operation B · cut the remaining pieces</h3>', document)
        self.assertIn("run every beam in a serial pass", document)
        self.assertIn("run every plank in a serial pass", document)
        self.assertIn("Frame fastening and finished-angle check", document)
        self.assertIn("84 nominal beam screw marks", document)
        self.assertIn("Do not use the cladding nail pattern", document)
        self.assertIn("Every diagonal runs corner to corner", document)

    def test_masthead_names_the_project_and_credits_its_sources(self):
        document = guide_html(self.design)

        self.assertIn("<span class=\"sheet-no\">WORKING DRAWING</span>", document)
        self.assertIn("<h1>Can AI build a toilet yet?</h1>", document)
        self.assertIn(
            "Outdoor toilet drawn from a parametric model using claude and codex.",
            document,
        )
        self.assertIn("https://www.instagram.com/hannes.soderquist/", document)
        self.assertIn("https://x.com/feelepxyz", document)
        self.assertIn("@feelepxyz", document)
        self.assertIn("https://github.com/feelepxyz/dass", document)
        self.assertIn('class="source-icon"', document)
        self.assertIn("controls.maxPolarAngle = Math.PI;", document)
        self.assertIn("ground.visible = camera.position.y >= ground.position.y;", document)
        self.assertIn("camera.setViewOffset(3, 4, 0, 1, 3, 3);", document)
        self.assertIn("azimuth: -44", document)
        self.assertIn("frameWidth: 2500", document)
        self.assertIn("offsetX: 0", document)
        self.assertIn("addPlankLines(gltf.scene);", document)
        self.assertIn("ATLAS.coverMm", document)
        self.assertIn("isPlankSeam", document)
        self.assertNotIn('id="method"', document)
        self.assertNotIn("Material schedule", document)
        self.assertEqual(document.count("Caution · verify the stock first"), 2)
        self.assertIn("Frame timber, 45 × 45 ×", document)
        self.assertIn("Råspont, 120 × 23 ×", document)
        self.assertIn(
            "Cut every piece at one stop setting before you change the stop.",
            document,
        )
        self.assertNotIn(
            "The renders and the model show the same geometry as the cut lists.",
            document,
        )
        self.assertNotIn(
            "Standing in the clearing with the door and roof open.",
            document,
        )

    def test_public_pages_include_canonical_social_metadata(self):
        pages = (
            (
                guide_html(self.design),
                "https://canaibuildatoiletyet.com/",
                "DASS · Can AI build a toilet yet?",
            ),
            (
                started_html(),
                "https://canaibuildatoiletyet.com/how-it-started.html",
                "DASS · How it started",
            ),
            (
                progress_html(),
                "https://canaibuildatoiletyet.com/how-its-going.html",
                "DASS · How it's going",
            ),
        )

        for document, canonical, title in pages:
            self.assertIn(f'<link rel="canonical" href="{canonical}">', document)
            self.assertIn(
                f'<meta property="og:title" content="{escape(title, quote=True)}">',
                document,
            )
            self.assertIn(
                '<meta property="og:image" content="https://canaibuildatoiletyet.com/web-renders/in-situ-open.jpg">',
                document,
            )
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', document)
            self.assertIn(
                '<meta name="twitter:site" content="@feelepxyz">',
                document,
            )

    def test_story_navigation_links_the_drawing_and_progress_pages(self):
        document = guide_html(self.design)

        self.assertIn('class="story-link story-link-start" href="how-it-started.html#story-nav"', document)
        self.assertIn('class="story-link story-link-drawing" href="#story-nav" aria-current="page"', document)
        self.assertIn('class="story-link story-link-going" href="how-its-going.html#story-nav"', document)
        self.assertIn('<nav class="story-nav" id="story-nav"', document)
        self.assertIn("scroll-margin-top:16px;", document)
        self.assertIn('class="view-grid" id="render"', document)
        self.assertIn('class="set-foot-copy"', document)
        self.assertLess(document.index("The checks are saved in this browser"), document.index('class="reset"'))
        self.assertIn('class="set-foot-link" href="how-its-going.html#story-nav"', document)
        self.assertIn('path d="M21 12H4m0 0 6 6m-6-6 6-6"', document)
        self.assertIn('path d="M12 3v17m0 0 6-6m-6 6-6-6"', document)
        self.assertIn('path d="M3 12h17m0 0-6-6m6 6-6 6"', document)

    def test_started_page_carries_the_readme_story_without_section_name(self):
        document = started_html()

        self.assertIn("<h2>How it started</h2>", document)
        self.assertNotIn("Evolution", document)
        for asset in (
            "original-side-drawing.jpg",
            "validation-open.jpg",
            "seat-section-comparison.jpg",
            "door-front-comparison.jpg",
        ):
            self.assertIn(f'src="started/{asset}"', document)
        self.assertIn(
            'href="https://www.instagram.com/hannes.soderquist/"',
            document,
        )
        self.assertIn("I asked Claude and Codex to build a CAD model", document)
        self.assertIn(
            "until the model aligned with the measurements in the",
            document,
        )
        self.assertIn("I did not edit any of the CAD drawings directly", document)
        self.assertIn("how long each beam should be", document)
        self.assertIn("created impossible cuts", document)
        self.assertIn("the floor boards did", document)
        self.assertIn("not have enough support", document)
        self.assertIn("The same model then generates assembly instructions", document)
        self.assertIn("A fastening review then found a join", document)
        self.assertIn("models both screw paths", document)
        self.assertIn('class="set-foot-link" href="cut-guide.html#story-nav"', document)
        self.assertIn("<span>Working drawing</span>", document)
        self.assertIn('class="story-link story-link-start" href="#story-nav"', document)
        self.assertIn('class="story-link story-link-drawing" href="cut-guide.html#story-nav"', document)
        self.assertIn('class="story-link story-link-going" href="how-its-going.html#story-nav"', document)
        self.assertIn('path d="M12 3v17m0 0 6-6m-6 6-6-6"', document)
        self.assertIn('path d="M12 21V4m0 0 6 6m-6-6-6 6"', document)

    def test_progress_page_uses_the_same_heading_and_supplied_photos(self):
        document = progress_html()

        self.assertIn("<h1>Can AI build a toilet yet?</h1>", document)
        self.assertIn("<h2>How it's going</h2>", document)
        self.assertIn(
            "Real-world progress following the drawing to build an outdoor toilet.",
            document,
        )
        self.assertIn("Latest model finding · diagonal fastening", document)
        self.assertIn("angled screw paths", document)
        self.assertIn("resulting clearance", document)
        self.assertNotIn(
            '<p class="masthead-sub">Real-world progress following the drawing to build an outdoor toilet.</p>',
            document,
        )
        self.assertNotIn('class="title-block"', document)
        self.assertIn('class="story-link story-link-start" href="how-it-started.html#story-nav"', document)
        self.assertIn('class="story-link story-link-drawing" href="cut-guide.html#story-nav"', document)
        self.assertIn('class="story-link story-link-going" href="#story-nav"', document)
        self.assertIn('path d="M21 12H4m0 0 6 6m-6-6 6-6"', document)
        self.assertIn('path d="M12 3v17m0 0 6-6m-6 6-6-6"', document)
        self.assertIn('path d="M12 21V4m0 0 6 6m-6-6-6 6"', document)
        self.assertIn('class="set-foot-link" href="how-it-started.html#story-nav"', document)
        self.assertIn("<span>How it started</span>", document)
        self.assertNotIn('<span>Working drawing</span>', document)
        self.assertIn('path d="M3 12h17m0 0-6-6m6 6-6 6"', document)
        self.assertIn('path d="M21 12H4m0 0 6 6m-6-6 6-6"', document)
        self.assertLess(
            document.index("progress/saw-setup-for-beam-cuts.jpg"),
            document.index("progress/beam-cuts.jpg"),
        )
        self.assertIn('loading="eager"', document)
        self.assertIn('loading="lazy"', document)

    def test_cladding_is_trimmed_on_its_unit_after_fixing(self):
        document = guide_html(self.design)
        plates = module_plates(self.design, self.boards)

        self.assertNotIn("bench layout", document)
        self.assertNotIn("Trim the field to drawing", document)
        self.assertNotIn("Frame and cladding registration", document)
        self.assertIn("Do not trim loose cladding", document)
        self.assertIn("circular-saw guide", document)
        for letter in "BCDEFH":
            self.assertIn("CUT AFTER FIXING", plates[letter])
            self.assertIn(f'data-unit-face="{letter}"', document)
        for letter in "CD":
            self.assertIn("45 × 45 NOTCH", plates[letter])
            self.assertIn("100 fall over 770", plates[letter])
        for letter in "ABCDEFGH":
            self.assertIn(f'data-check="unit-{letter.lower()}"', document)

    def test_lengths_read_as_drawing_numbers(self):
        # The reference set spaces thousands; a bare 1315.1 is not what a
        # drawing letters, and the register depends on this shape too.
        self.assertEqual(fmt(1315.1), "1 315.1")
        self.assertEqual(fmt(4200), "4 200")
        self.assertEqual(fmt(854), "854")

    def test_printed_set_takes_the_drawn_model_over_the_photographs(self):
        document = guide_html(self.design)

        # The sheet prints a still because a live canvas does not print, and it
        # is always the drawn finish whatever the screen is showing. The image
        # is built by the script, so no empty <img> ever ships in the markup.
        self.assertNotIn('<img class="viewer-print"', document)
        self.assertIn('printShot.className = "viewer-print";', document)
        self.assertIn("function takePrintStill()", document)
        self.assertIn('finish = "line";', document)
        self.assertIn('window.addEventListener("beforeprint", takePrintStill);', document)
        # Print preview and print-to-PDF never fire beforeprint.
        self.assertIn('window.matchMedia("print")', document)
        self.assertIn("has-print-model", document)
        # Photographs stay on screen; they only return if no still was taken.
        self.assertIn(".gallery, .viewer { display:none; }", document)
        self.assertIn("body:not(.has-print-model) .gallery { display:block; }", document)
        # The still ships with its own width and height, so a max-width and a
        # max-height would each be applied on their own and stretch the model
        # across the sheet. One stated side, and the other follows the ratio.
        self.assertIn(
            ".viewer-print { display:block; margin:0 auto; "
            "width:auto; height:104mm; max-width:100%; }",
            document,
        )
        # The title sheet breaks to a new page, so the page margin is the air
        # under the model and the drawing keeps the height padding would cost.
        self.assertIn(".masthead { padding-bottom:0; break-after:page; }", document)

    def test_printed_drawings_are_bound_by_the_page_and_never_split(self):
        document = guide_html(self.design)

        # A guessed plate height letterboxes the drawing to a fraction of its
        # column; the page has to set the size instead.
        self.assertNotIn("height:74mm", document)
        self.assertIn(".unit .drawing .plate { flex:1 1 auto; min-height:0; }", document)
        # One unit per sheet: the drawing, its steps and its codes travel
        # together, under the same head of air every printed page opens with.
        # That air is the page box, not padding on the sheet: padding only
        # reaches the first page a sheet fragments onto, so a page carrying the
        # overflow of a sheet opened hard against the trim.
        self.assertIn("@page { size:A4 landscape; margin:14mm 9mm 10mm; }", document)
        self.assertIn("height:184mm; break-before:page;", document)
        self.assertIn(".sheet, .masthead { border:0; padding:0; margin:0; }", document)
        # Nothing may push an empty sheet out of the end of the set.
        self.assertIn(".sheet:last-of-type { break-after:auto; }", document)
        self.assertIn(".drawing, .unit, .stock, .note { break-inside:avoid; }", document)

    def test_printed_story_pages_keep_their_figures_whole_and_open_with_work(self):
        for document in (started_html(), progress_html()):
            # The story masthead is a title bar, not a title sheet: nothing is
            # drawn beside it, so a page of its own printed all but empty.
            self.assertIn(".masthead-progress { break-after:auto; padding-bottom:8mm; }", document)
            self.assertIn(".masthead-progress + .sheet { break-before:auto; }", document)
            # `break-inside` is only honoured while a block still fits the page,
            # so each figure is bound on its height before it is asked to stay
            # whole. Otherwise the image split and the caption was orphaned.
            self.assertIn(
                ".started-figure, .started-figure-pair, .progress-photo { break-inside:avoid; }",
                document,
            )
            # The images ship with their own width and height, so one bound per
            # axis lets the other follow the ratio instead of stretching.
            self.assertIn(
                ".started-figure img { width:auto; height:auto; "
                "max-width:100%; max-height:118mm; margin:0 auto; }",
                document,
            )
            self.assertIn(
                ".progress-photo-frame { width:auto; height:130mm; max-width:100%; margin:0 auto; }",
                document,
            )

    def test_notes_hold_the_same_measure_as_the_prose_around_them(self):
        document = guide_html(self.design)

        # A note is prose in a box, so its border sits just clear of the text
        # rather than ruling the whole sheet.
        self.assertIn("p { margin:0; max-width:68ch; }", document)
        self.assertIn("max-width:calc(68ch + 2 * var(--note-pad) + 2px);", document)
        self.assertIn("--note-pad:24px;", document)
        self.assertIn("--note-pad:16px;", document)
        # The batch tables live inside notes and are wider than that measure.
        self.assertIn(".note:has(.table-scroll) { max-width:none; }", document)
        self.assertIn('<div class="note">\n      <h3>Operation A', document)

    def test_html_carries_every_reference_view_and_its_model_assets(self):
        document = guide_html(self.design)

        for _, views in GALLERY:
            for name, _, _ in views:
                self.assertIn(f"web-renders/{name}.jpg", document)
        for variant in ("open", "closed"):
            self.assertIn(f'data-variant="{variant}"', document)
        self.assertIn('"three":"./vendor/three.module.min.js"', document)

    def test_every_panel_finishes_at_its_modeled_span(self):
        fields = panels(self.boards)
        spans = {
            "door_panel": self.design.width,
            "left_wall": self.design.plan_grid_depth,
            "right_wall": self.design.plan_grid_depth,
            "back_wall": self.design.interior_width,
            "floor": self.design.interior_width,
            "seat_top": self.design.interior_width,
            "seat_front": self.design.interior_width,
        }
        self.assertEqual(set(fields), set(spans))
        for key, span in spans.items():
            panel = fields[key]
            self.assertAlmostEqual(panel.span, span, places=6)
            self.assertAlmostEqual(panel.joined - panel.trim, span, places=6)
            self.assertEqual(len(panel.pieces), panel.count)

    def test_plates_project_the_model_rather_than_fixed_coordinates(self):
        parts = {part.name: part.solid for part in build(self.design)[1]}

        post = outline(parts["front_post_left"], FRONT)
        self.assertEqual(len(post), 4)
        self.assertAlmostEqual(
            max(u for u, _ in post) - min(u for u, _ in post), self.design.frame,
        )
        self.assertAlmostEqual(
            max(v for _, v in post) - min(v for _, v in post),
            self.design.front_post_height,
        )

        # A diagonal brace is a parallelogram, never its bounding box.
        brace = outline(parts["left_brace"], FRONT)
        self.assertEqual(len(brace), 4)

        # The cladding sits inboard of the frame it covers, which is the one
        # relationship the registration plate exists to prove.
        cut = self.design.seat_height + self.design.leg_extension
        wall = cross_section(parts["left_wall"], PLAN, cut)
        frame = cross_section(parts["front_post_left"], PLAN, cut)
        self.assertAlmostEqual(
            max(u for u, _ in wall) - min(u for u, _ in wall), self.design.cladding, places=3,
        )
        self.assertGreaterEqual(min(u for u, _ in wall), max(u for u, _ in frame) - 1e-6)

    def test_every_stack_gets_a_plate_carrying_its_own_codes(self):
        plates = module_plates(self.design, self.boards)

        self.assertEqual(set(plates), set("ABCDEFGH"))
        for letter, codes in (
            ("A", ("RBH1", "RBS1", "RBC1")),
            ("B", ("DBV1", "DBD1", "DCB1")),
            ("C", ("LSV1", "LSD1", "LSC1")),
            ("E", ("BWH1", "BWD1", "BWC1")),
            ("H", ("SBH1", "SBS1", "STB1")),
        ):
            for code in codes:
                self.assertIn(code, plates[letter])

    def test_viewer_names_every_modeled_part_with_its_cut_code(self):
        data = viewer_parts(self.design, self.boards)
        modeled = {part.name for part in build(self.design)[1]}

        self.assertEqual(set(data), modeled)
        for name, code in BEAM_CODES.items():
            self.assertEqual(data[name]["code"], code)
        self.assertEqual(data["left_wall"]["code"], "LSC1–LSC7")
        self.assertEqual(data["left_wall"]["size"], "770 × 1 175 × 23")
        self.assertEqual(data["roof"]["tone"], "roof")

    def test_viewer_parts_carry_the_material_the_timber_pipeline_reads(self):
        # The shared pipeline picks a role off `material`; when it is missing
        # every piece is dressed as wood and the roof sheet stops being metal.
        data = viewer_parts(self.design, self.boards)

        self.assertEqual(data["roof"]["material"], "metal roof")
        self.assertEqual(data["roof_hinge_pin"]["material"], "metal")
        self.assertEqual(data["front_post_left"]["material"], "wood")
        self.assertTrue(all(part["material"] for part in data.values()))


if __name__ == "__main__":
    unittest.main()
