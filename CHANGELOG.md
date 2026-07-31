# Changelog

## Unreleased

- A fastening review found that the original diagonal ends shared the door,
  side, and back rail corners. A 120 mm screw from a vertical member into a
  rail could therefore clash with the screw driven from that rail into the
  diagonal.
- Recalculated all four diagonal end pairs as full corner-to-corner braces.
  Their mitred end faces stop on the inner faces of the vertical members, so
  the stock does not extend into or merge with the adjoining beams. The
  fastening model now records screw direction and 120 mm centerlines, uses a
  slight diagonal screw angle, detects path collisions after the source member,
  and regression-tests the eight vertical-member-to-diagonal connections.
- Recorded the finding in the evolution and field-notes pages.

## 0.1.0 — Public release 001 · 2026-07-31

This records the current package version as the first public release.

- Added a model-derived frame fastening audit covering 42 beam-to-beam
  connections and 84 nominal screw marks. The current layout has no overlapping
  screw marks. Cladding remains outside the audit because it is nailed.
- Moved diagonal screw marks 90 mm in from each end so they clear the existing
  rail and post screw rows. No frame geometry adjustment was needed.
- Added finished-frame angle checks. Measure the side pitch, roof pitch, and
  diagonal cut angle on the assembled frame before final fastening, using the
  drawing and model values as the guide and scribing to the measured result if
  the frame has moved.
- Added a workshop stock-end clean-up pass before cutting beams and cladding
  planks.
