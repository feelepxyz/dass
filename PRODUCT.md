# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is the owner-builder fabricating a small outdoor toilet from
standard timber and Råspont (matchboard/V-groove cladding) stock. The guide is used in a workshop while
measuring, cutting, marking, stacking, and later assembling parts.

## Product Purpose

Turn the parametric CAD model into an exact, printable stock-cut and assembly
guide. Success means every blank can be cut once, marked with a unique short
code, and stacked by build unit. Final cladding edges are cut on the fixed unit.

## Positioning

The guide keeps stock planning, physical cut order, part marking, and
modular construction instructions tied to one parametric dimensional source of
truth.

## Operating Context

- Metric workshop measurements in millimetres.
- 45 × 45 × 4200 mm structural timber.
- 120 × 23 × 4500 mm Råspont (matchboard/V-groove cladding) with 110 mm effective cover.
- 2.8 mm saw kerf.
- All 1175 mm side and door blanks are cut at one stop setting before the
  smaller batches. Side boards are fixed to their frames before their slope
  and terminal edges are cut.
- The final guide must work on screen and as a printed shop-floor packet.

## Capabilities and Constraints

- The CAD `Design` defaults and generated model are the dimensional authority.
- Every timber and cladding piece needs a stable, logical uppercase code.
- Stock plans must include kerf and prove that no stock length is exceeded.
- The cladding plan must fit the available twelve stock lengths; three labeled
  early remainders return only for the final 397 mm batch.
- Roof, door, both side walls, back wall, and floor should be buildable as
  standalone units where the geometry permits. The seat box is installed after
  the shell is assembled.
- The 1050 × 1085 mm metal roof sheet and hardware are identified separately
  from the timber stock optimization.

## Assembly hardware

| Use | Fastener |
| --- | --- |
| Frame beams and braces | 6 × 120 mm sunk wood screws |
| Beam-to-beam support joints, for example floor supports | 6 × 90 mm sunk wood screws |
| Råspont (matchboard/V-groove cladding) to beams | 2.8 × 60 mm nails or 6 × 60 mm sunk wood screws |

## Evidence on Hand

- Parametric CAD source: `src/dass/model.py`.
- Cut-list source and optimizer: `src/dass/cutlists.py`.
- Existing generated STEP, GLB, PNG, and CSV artifacts under `build/`.
- Reconciled source notes and fit rules: `README.md`.
- Reference drawings: `docs/original-drawing/`.

## Product Principles

- Model-derived dimensions beat copied dimensions.
- A cut is not complete until the piece is coded and assigned to a stack.
- The physical cutting sequence matters as much as theoretical nesting.
- Reusable offcuts stay visible and traceable.
- Construction is organized around stable standalone modules.
