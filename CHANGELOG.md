# Changelog

## 0.1.7 — The model becomes a sheet of the set · 2026-08-08

- Put the model on a parallel projection in both finishes, at the elevation
  the unit sheets draw their assemblies on. The interactive model, both
  exported drawing renders, and the still that goes on paper now measure the
  same everywhere, so an edge carries the length it has on the building
  instead of shrinking with distance, and turning the material on no longer
  moves the building under the reader.
- Made timber white wherever it appears. The floor deck and the roof sheet
  were shaded for their material and read as grey beams beside the unit
  sheets; only a clad field carries a tone now, exactly as the sheets draw it.
- Took the photograph's film curve off the drawn model. It rolls white down to
  about four fifths, so on screen every white beam still landed grey against
  the sheet behind it and a timber barely told itself from a clad field. The
  drawing under the model changed the moment the model finished loading;
  drawn, it now carries the tones the exported drawing and the printed sheet
  carry, and nothing moves when it loads.
- Put the ground shadow back under the material finish. Its sun and its shadow
  map were switched on after the finish's shaders had already been built, so
  the shadow never reached the screen and the building floated; it stands on
  its shadow again.
- Gave the drawn model real line weights on screen. Its outlines were drawn
  one device pixel wide whatever weight they asked for, which is half a pixel
  on a retina display and left the object lines and the board joints
  indistinguishable; they are now drawn at their stated widths, so the edges
  and corners carry the drawing.
- Cleared those lines of the faces they edge. A drawn line is spread across the
  screen at the single depth its edge has, so where it lands on a face running
  away from the camera the depth test cut most of the stroke away. Inside the
  building, where every line meets a face at a shallow angle, the creases
  between the wall panels, the seat and the floor had faded to a broken
  hairline; they now carry the weight the exported drawing gives them.
- Cut the exported drawings around their own silhouette, at the heavier weight
  a sheet gives an outer edge, and filled that silhouette white. The drawings
  no longer depend on the colour of whatever they are laid over.
- Added measured dimensions to the drawn model: the ground the building
  covers, the side wall along it, and the door's width and height, drawn in
  the set's blue with architect's ticks. Every value is taken off the model as
  it is drawn, so no dimension can disagree with the geometry beside it.
- Cut the reference gallery back to the two photographs of the finished unit
  in its place. The studio renders, the drawing renders, and the six flat
  elevations were all the same geometry the reader can already turn in the
  viewer beside them.
- Cut the exported drawings to the drawing palette. The traced fills were
  carrying thousands of blended edge colours that no drawing ever asks for;
  they are now the flat tones of the set, which halved the file each reader
  downloads.

## 0.1.6 — Match the unit-drawing line finish · 2026-08-07

- Made the interactive line model and its exported drawing renders use white
  frame members, pale grey cladding, and lighter grey board joints so they
  read like the unit drawings.

## 0.1.5 — Unit drawings as a construction sequence · 2026-08-07

- Rebuilt sheet A-400 so every unit builds through its own numbered
  construction steps. Each step is a drawing of one operation rather than a
  line of prose: work already done drops back to a ghost, work the step
  touches goes solid, and a band under the drawing names the operation and the
  fastener or tool it takes. The steps replace about a thousand words of
  instruction with roughly three hundred.
- Kept a general arrangement only on the door and the two side units, which
  carry set-out no single step can show: the door reliefs, and the slope, trim
  and notch on either side. Every other unit is finished by its own last step,
  so its overall drawing was repeating what the steps already say. Dropped the
  repeated code strip under each unit for the same reason.
- Drew each frame coming together as an exploded isometric, with every member
  off its seat on the path it travels back down. Marking, cutting, fastening
  and setting-out steps stay orthographic, because a saw line, a trim and a
  notch lose precision in projection.
- Split the operations a single sentence used to carry. A side field is now
  clad, marked, gang-cut, trimmed and notched as five separate drawings, so
  no cut is made from a step that also asked for something else.
- Corrected the back unit build order: the back frame is clad and trimmed flat
  before it is set between the side units. Fitted first, the side skins stand
  in the way of the overhang the back field is cut from. The back frame also
  now states that nothing screws it together, since every fixing into it comes
  from a rear post.
- Corrected the floor deck order: the joined field is cut to the bearers
  before it is fixed, because once the boards are down there is no guide edge
  left to run the saw on.
- Added a screw step to the door, both side units and the seat box. A frame is
  driven, and checked square as it is driven, before anything is fixed to it.
  The seat box's eight beam screws are now drawn where they are made.
- Merged the two seat-support units, which drew the same bearers twice. The
  one that remains sets both beam tops off the finished deck and the inside
  back face, drives the outside screws, and then takes the box.
- Moved deliberately deferred work out of the numbered sequence into a hold
  pinned to its unit, so the roof reliefs and the hinge leaves can no longer
  be read as the next thing to do.
- Replaced the single unit checkbox with a tick per step and a progress count
  on each unit.
- Bound each general arrangement to the screen so a unit opens in one view,
  and stopped the layer toggle dimming a step drawing it was never aimed at.
- Reprinted the packet: a unit takes the sheets it needs, with its steps three
  across, no drawing split from its caption or its tick, and no empty sheet.

## 0.1.4 — Cladding screw clearance · 2026-08-02

- Centred cladding fixings on the material left after each field is trimmed,
  moving FCB8, STB5, and the other terminal-board screws away from cut edges.
- Shifted edge-board fixing marks and the seat-top screw lanes clear of the
  modeled beam-screw paths. The left and right side fields now move their first
  cladding fixings inward toward the second board.

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
