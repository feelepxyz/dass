# Changelog

## 0.1.3 — Matched model viewport · 2026-08-02

- Matched the interactive model's camera, scale, and position to the in-situ
  render beside it. The line, textured, fallback, and print views now use the
  same level perspective and bottom square crop as the photographed model.

## 0.1.2 — Isometric drawing completion · 2026-08-02

- Completed the removable seat-box frame with the missing SBH2-to-SBS3 and
  SBH1-to-SBS4 screws. Stack H now shows all eight beam screws around the four
  side supports, so every rail-to-support joint is explicit in the workshop
  drawing.
- Corrected Stack J to a true isometric projection and aligned the visible back
  panel face with the side panel exactly as modeled. The support installation
  view now preserves one projection and the built corner relationship.
- Changed the model's line view to the drawing-set palette and a true
  orthographic isometric camera. Added matching open and closed SVG renders;
  the open final view shows the door open and roof lifted with opaque parts,
  black outlines, and no part labels.

## 0.1.1 — Seat-box integrity update · 2026-08-02

- Rotated the seat-top boards from front-to-back to left-to-right. The schedule
  is now five STB boards at 852 mm with a 60 mm end trim, so the opening is
  carried by fewer, wider boards and is less likely to weaken during sawing.
- Added SBS3 and SBS4 as 387 mm outer side supports, matching SBS1 and SBS2,
  to close the removable seat-box frame. Added the two requested 120 mm frame
  screws at the new rail-to-support joints.
- Added FBH1 to the shell-joint assembly as an installed fourth beam, with
  centred outside-side screws, so the front opening rail has explicit support.
- Made the seat box removable at 852 mm wide and added SBB1, SBB2, and SBF1 as
  fixed shell supports. This keeps the box serviceable while supporting the
  front and rear seat edges.
- Added A-409 and A-411 support views, model-derived screw overlays, centred
  code labels, and the corresponding front-support dimensions. These make the
  workshop positions visible in the same guide as the geometry.
- Corrected diagonal brace ends and their screw paths after finding corner
  clashes. The braces now preserve the frame envelope and the audit reports
  the measured screw-path clearance.
- Added dated model notes and the model version summary to the progress page.

## 0.1.0 — Public release 001 · 2026-07-31

This records the current package version as the first public release.

- Added a model-derived frame fastening audit covering 42 beam-to-beam
  connections and 84 nominal screw marks. The current layout has no overlapping
  screw marks. Cladding remains outside the audit because its fasteners are
  handled separately.
- Moved diagonal screw marks 90 mm in from each end so they clear the existing
  rail and post screw rows. No frame geometry adjustment was needed.
- Added finished-frame angle checks. Measure the side pitch, roof pitch, and
  diagonal cut angle on the assembled frame before final fastening, using the
  drawing and model values as the guide and scribing to the measured result if
  the frame has moved.
- Added a workshop stock-end clean-up pass before cutting beams and cladding
  planks.
