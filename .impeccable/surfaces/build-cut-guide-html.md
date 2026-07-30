---
version: 1
slug: "build-cut-guide-html"
primary_target: "build/cut-guide.html"
related_targets: ["generate_build_guide.py","render/materials.mjs"]
---

Scope: `build/cut-guide.html`, an offline screen and print drawing set, generated
by `generate_build_guide.py`.

Mode: Operate first, Read second. The owner-builder must cut, mark, stack, and
assemble without returning to the CAD model.

Audience and task: one workshop user working in millimetres with 45 x 45 x 4200
framing, 120 x 23 x 4500 raspont, and a 2.8 mm kerf.

Proof and content: model-derived part dimensions, exact stock-count proof,
unique part codes, stock diagrams, and numbered unit drawings. The header
contains the renders and model. Each cladded unit shows its on-frame trim and
assembly steps. Sheets run A-200 timber, A-300 raspont, and A-400 units.

Direction: the Swedish construction drawing set that `drawing-sides.png` comes
from, pinned by the user. White sheets on a grey ground, Input Mono at one
weight, four black line weights, red for part codes, blue for dimensions,
hatching for material the section plane cuts. Every figure is a numbered
drawing captioned beneath it; the title block appears once, on the masthead.
The memorable moment is the single-stop 1175 mm batch. The side fields are
fixed before their gang cut, terminal trim, and 45 mm notch.

Each number is written once in a table and once on the drawing it belongs to.
There is no part register: the stock bars carry the codes in cut order, the unit
drawings carry them on the geometry, and the model names any piece on click.

The model viewer opens line-shaded to match the sheets, with a TEXTURED toggle
that lazily loads the real timber. Both finishes run the same pipeline as the
photoreal renderer, shared through `render/materials.mjs`.

Constraints: every detail survives black-and-white printing; no required
information is hover-only; individual stock bars and wide tables may scroll
sideways but the document never does, at any width.

Unresolved: roof relief notches are deliberately scribed from the real completed
roof unit during dry fit instead of factory-cut from nominal CAD dimensions.
