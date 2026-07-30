# Small outdoor toilet

The parametric source is `dass.py`; all dimensions are millimetres. Generate
closed/open renders, STEP and GLB CAD files, and a CSV cut list with:

```sh
uv run dass.py
uv run dass.py --output build-wide --set width=1050 --set seat_depth=550
uv run generate_cutlists.py
uv run generate_build_guide.py
uv run dass.py --output build-45x45-120x20 --set frame=45 --set cladding=20 \
  --set roof_connector_width=45 --set roof_connector_thickness=45
uv run generate_cutlists.py --output build-45x45-120x20 \
  --set frame=45 --set cladding=20 \
  --set roof_connector_width=45 --set roof_connector_thickness=45
```

Primary parameters live in the `Design` dataclass and may be edited together.
Every numeric parameter can also be overridden with repeatable `--set
NAME=VALUE`; derived spans, grid dimensions, braces, CAD, renders, and the CSV
cut list are regenerated together. `--door-angle` changes the open-door render.
`--roof-lift-angle` raises the complete roof assembly about its rear hinge.

The current design is 990 × 815 mm, framed in 45 × 45 mm stock and clad in
23 × 120 mm interleaved råspont. Each board covers 110 mm; the remaining
10 mm lip is included in the assembled width and sawn off only after the
field is fixed to its frame. The door is nine covers wide and each side is seven covers
deep, so both finish with exactly 10 mm to trim. The fitted 854 mm rear wall,
floor, seat top, and seat front each use eight boards and leave 36 mm to trim.

`generate_cutlists.py` expands those fields into full-width boards and writes
kerf-aware, stop-block-sequenced plans for 4200 mm beam stock and 4500 mm
cladding stock with a 2.8 mm kerf. One kerf is reserved for every released piece. Equal-length
cuts run as one batch across stock boundaries; the cladding plan reuses only
three labeled early remainders for the final 397 mm batch so the full job fits
the available twelve boards. The two sloping side walls are listed as
`left_wall` and `right_wall` gang-cut sets: cut all fourteen 1175 mm blanks
first, fix seven boards to each wall frame, then make one continuous angled cut
through each fixed field. Trim the terminal edge from the frame datum. The piece
CSV records each unique shop code and the
resulting long and short point of each side board. Shop codes use at most three
letters and two digits. Use `--beam-stock-length`,
`--cladding-stock-length`, and `--kerf` to change the stock assumptions;
`--stock-length` overrides both lengths.

`generate_build_guide.py` writes `build/cut-guide.html`, a screen and print
guide with batch-sequenced stock diagrams and unit drawings. Each unit drawing
contains its assembly steps and on-frame cladding cuts. It uses the existing
`build/renders/open-hero.png` assembly render.

## Source reconciliation

The supplied sources use several dimension domains:

- The earlier 950 × 850 / 50 × 50 reference has been adjusted to a
  990 × 815 outside envelope in 45 × 45 stock so the exposed cladding fields
  land on 110 mm råspont cover modules with a terminal trim allowance.
- The plan labels 900 × 800 between post centrelines: each equals its outside
  envelope minus one 50 mm post. This reconciles the plan with the elevations.
- Walls are 23 × 120 mm `råspont` with 110 mm effective cover.
- Written finished panels: side walls 2 × 800 × 1175 maximum (sloping down),
  back wall 850 × 1050 above the 100 mm feet and door 950 × 1175. The fitted
  interior panels are floor 775 × 800, seat top 500 × 800, and seat front
  395 × 800. The modelled back field is 800 × 1050, not the written 850: it is
  fitted between the two side skins rather than run behind them, so the side
  skins close the rear corners.
- The 950 × 1050 door frame starts at the same 100 mm datum as the wall
  framing. Its 950 × 1175 cladding starts at the frame's bottom edge and is
  fastened to the inside of the frame; its hinge straps join the inside
  cladding face to the structural upright. The rear wall reaches 1150 mm, and
  the roof falls 125 mm over the
  833 mm clear run.
- The roof frame is 950 × 933 overall: two 950 mm HL2 cross-members enclose two
  HK2 side members with an 833 mm horizontal run. All roof members are
  coplanar with the roof; an 850 × 65 × 25 mm middle member connects the side
  beams. In the closed position, the frame turns a further 3.28° until its side
  beams sit on the door cladding notches. A centered 1050 × 1085 mm metal sheet
  and the frame lift together on a hinge on the outside face of the fixed rear
  support.
- Reference 50 × 50 cut-list stock: V1 4 × 1150, V2 2 × 1050,
  D1 2 × 1209 (−36° ends), D2 1 × 1274.8, HK1 4 × 750,
  HK2 2 × 833, HL1 5 × 850, and HL2 2 × 950. The model carries D2 2 × 1274.8,
  because the back-wall brace crosses the same 850 × 950 opening as the door
  brace and is therefore the same cut. Its two HL2 door rails are 850, not 950:
  see the fit rules below.

## Fit and clearance

No two parts share volume except the hinge pins, which are modelled as
continuous barrels through the knuckles they pivot in.
`test_no_part_overlaps_another_except_hinge_pins` checks every part pair across
the default, wide, and 45 × 45 variants in both the closed and open states.

The rules that keep it that way:

- Verticals run full length and horizontals fit between them. This already held
  for the posts and the wall rails; the door frame now follows it too, so its
  1050 mm V2 stiles are full height and its HL2 rails are 850 mm, not 950 mm.
- The side cladding is notched 50 × 50 at its bottom front corner, where the
  front opening rail crosses its plane.
- The back cladding is fitted between the side skins.
- Braces take one angled saw cut per end. A bar centred on the corner-to-corner
  diagonal overshoots both boundaries at each corner, so clipping it leaves a
  notched point built from two faces. Each brace is instead tilted off the
  diagonal by `asin(size / span)`, which puts one long face through each corner:
  a single plane then trims each end and the finished piece is a parallelogram
  prism of exactly six faces that still fills the opening corner to corner. Of
  the two possible tilts the model takes the steeper, so the rails make both
  cuts and the brace bears on them. The side D1 braces and the back D2 brace
  all run low at the rear, so the bracing is continuous around the rear-left
  corner.
- Because both ends are mitred, a brace's longest edge falls short of the stock
  it is cut from. The cut list reports the long-point length,
  `sqrt(diagonal^2 - size^2)`, which stays within about a millimetre of the
  reference corner-to-corner figure: D1 1209.3 against 1209, D2 1273.8
  against 1274.8.
- The moving roof-hinge leaf is relieved where pitching would otherwise swing
  its outer bottom corner into the fixed rear rail.

Under the floor, two 50 × 50 bearers run front to back along the left and right
edges, between the front opening rail and the back support, carrying the long
edges of the front-to-back floor boards. The seat top is pierced by an oval
opening, `seat_hole_width` × `seat_hole_depth` (270 × 330 by default), centred
in the seat box and clear of both seat rails. Because that opening cuts the
middle seat boards, a `seat_support` bearer (45 × 45) runs down each side of it,
fitted between the two seat rails and flush under the boards.

## Side cladding and the roof line

The side cladding no longer parallels the roof. Its front edge stays at
`front_height`, but `side_back_lift` raises the back edge 25 mm to
`side_back_top`, so the fall is `side_fall` = 100 mm over 800 mm while the roof
still falls 125 mm over 833 mm. The bottom and back anchors are unchanged.

That lift pushes the back of each panel into the seated roof assembly. Both
panels are scribed after assembly and relieved around the roof frame and sheet.
Only about 6 mm of lift would clear the frame untouched. The relief keeps the
full 25 mm lift without changing the roof line or front height.

The roof's middle connector is 23 mm thick by default so it clears the raised
side panels without a notch. The 45 × 45 variants override it to 45 mm, which
hangs low enough to catch the panels, so there the notch covers it too.

The generated `build/cutlist.csv` follows the actual modeled parts. Run
`uv run audit_cutlist.py` to regenerate `build/cutlist-audit.md` and
`build/cutlist-side-by-side.csv`, which compare those parts with the reconciled
source labels and quantities.

Exact corner-to-corner brace geometry gives D1 = 1210.4 mm at 38.3° and
D2 = 1274.8 mm at 41.8°. The audit reports remaining geometric differences
instead of forcing the CAD metadata to match.

## Photo-realistic renders

`uv run render_photo.py` writes a set of lit renders to `build/renders`: hero
angles of the open and closed model, the six straight-on elevations, and two
shots composited into `background.jpg`. It builds the GLBs itself, then renders
them with three.js in headless Chromium — sky lighting, a sun with soft
shadows, screen-space ambient occlusion, and per-part wood grain.

```
uv run render_photo.py                          # every view, 1600 x 1200
uv run render_photo.py --views open-hero        # one view
uv run render_photo.py --list-views             # available view names
uv run render_photo.py --width 2400 --skip-build
```

The timber takes its grain from `textures/plywood_diff_4k.jpg` (`--texture`);
without it the script synthesises a pale birch sheet instead. Normal and
roughness maps are derived from whichever is used.

Cladding, floor and seat fields are one solid panel in CAD but råspont boards in
the workshop, so a single sheet of grain across them reads as plywood. The
script cuts that sheet into eight board-shaped strips — separate bands of the
photo, mirrored and re-toned, with the lap shadow baked into both edges — and
the renderer splits each panel back into 110 mm covers, clipping the geometry at
every joint so each board can take its own strip, laid either way round and at
its own tone. The roof is corrugated sheet, black on top and galvanised
underneath.

The two `in-situ-*` views place the model in the `background.jpg` clearing.
Their `frameWidth` sets the apparent size. Both views use one fixed camera
anchor, so the closed shell matches the open shell exactly. The guide uses a
lower square crop, and its interactive model starts from the same view.

Their lighting is matched to the photograph rather than staged. The plate is lit
from the camera's left and well above — the fence post at its right edge is
bright down its left face and dark down its right, and the birch trunks behind
it read the same way — so both shots put the sun there, and their `exposure`,
`envIntensity` and `sunIntensity` are set so the timber sits inside the
photograph's own tonal range instead of below it.

Camera angles and lighting for every view live in `VIEWS` in
`render/render.mjs`; `npm install` inside `render/` restores its two
dependencies.
