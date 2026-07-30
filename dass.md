# Small outdoor toilet

The parametric source is `dass.py`; all dimensions are millimetres. Generate
closed/open renders, STEP and GLB CAD files, and a CSV cut list with:

```sh
uv run dass.py
uv run dass.py --output build-wide --set width=1050 --set seat_depth=550
uv run generate_cutlists.py
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

`generate_cutlists.py` expands the modeled beams and 120 × 25 mm timber
cladding fields into individual pieces, then writes a 2400 mm stock plan with
a 2 mm saw kerf. The metal roof is listed separately and is not packed as
timber. The defaults can be changed with `--stock-length` and `--kerf`.

## Source reconciliation

The supplied sources use several dimension domains:

- Elevations and the cut list define a 950 × 850 outside post envelope made
  from 50 × 50 stock, yielding 850 mm front/back and 750 mm side clear spans.
- The plan labels 900 × 800 between post centrelines: each equals its outside
  envelope minus one 50 mm post. This reconciles the plan with the elevations.
- Walls are 25 mm `råspont` (tongue-and-groove cladding).
- Written finished panels: side walls 2 × 800 × 1175 maximum (sloping down),
  back wall 850 × 1050 above the 100 mm feet and door 950 × 1175. The fitted
  interior panels are floor 775 × 800, seat top 500 × 800, and seat front
  395 × 800.
- The 950 × 1050 door frame starts at the same 100 mm datum as the wall
  framing. Its 950 × 1175 cladding starts at the frame's bottom edge and is
  fastened to the inside of the frame; its hinge straps join the inside
  cladding face to the structural upright. The rear wall reaches 1150 mm, and
  the roof falls 125 mm over the
  833 mm clear run.
- The roof frame is 950 × 933 overall: two 950 mm HL2 cross-members enclose two
  HK2 side members with an 833 mm horizontal run. All roof members are
  coplanar with the roof; an 850 × 65 × 25 mm middle member connects the side
  beams. A centered 1050 × 1085 mm metal sheet and the frame lift together on
  a hinge on the outside face of the fixed rear support.
- Reference 50 × 50 cut-list stock: V1 4 × 1150, V2 2 × 1050,
  D1 2 × 1209 (−36° ends), D2 1 × 1274.8, HK1 4 × 750,
  HK2 2 × 833, HL1 5 × 850, and HL2 2 × 950.

The generated `build/cutlist.csv` follows the actual modeled parts. Run
`uv run audit_cutlist.py` to regenerate `build/cutlist-audit.md` and
`build/cutlist-side-by-side.csv`, which compare those parts with the reconciled
source labels and quantities.

Exact corner-to-corner brace geometry gives D1 = 1210.4 mm at 38.3° and
D2 = 1274.8 mm at 41.8°. The audit reports remaining geometric differences
instead of forcing the CAD metadata to match.
