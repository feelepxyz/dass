# 45×45 frame / 120×20 cladding comparison

## Purchase list (2.4 m stock, 2 mm saw kerf)

| Material | Baseline | 45×45 / 120×20 | Change |
|---|---:|---:|---:|
| 50×50 beam | 12 | 0 | −12 |
| 65×25 roof connector | 1 | 0 | −1 |
| 45×45 beam | 0 | 13 | +13 |
| 120×25 cladding | 21 | 0 | −21 |
| 120×20 cladding | 0 | 21 | +21 |
| Total 2.4 m lengths | 34 | 34 | 0 |

This is a generated feasible stock plan; the best-fit heuristic does not prove
that the counts are globally minimal. It includes 2 mm between consecutive cuts. It does not include
end-trimming allowance, damaged stock, grain selection, or spare material.
Buying one spare cladding board and one spare beam is prudent.

## Cut-list comparison

Both versions contain 27 beam pieces and 51 cladding pieces. The new frame uses
25.6823 linear metres of 45×45 timber, versus 25.4802 m of 50×50 plus 0.8500 m
of 65×25 in the baseline. The new cladding schedule totals 45.2624 linear
metres, versus 45.1524 m.

| Measure | Baseline | 45×45 / 120×20 | Change |
|---|---:|---:|---:|
| Beam volume | 0.06296 m³ | 0.05201 m³ | −17.4% |
| Cladding volume | 0.12848 m³ | 0.10413 m³ | −19.0% |
| Beam-stock waste | 4.142 m (50×50) + 1.550 m (65×25) | 5.490 m (45×45) | −0.202 m total |
| Cladding-stock waste | 5.188 m | 5.078 m | −0.110 m |

Lengths change because the outside envelope stays 950×850 mm while thinner
members increase the clear spans:

| Members | Baseline length | New length |
|---|---:|---:|
| D1 side braces (2) | 1210.4 | 1224.4 |
| D2 door brace (1) | 1274.8 | 1288.9 |
| HK1 side rails (4) | 750 | 760 |
| HK2 roof sides (2) | 842.3 | 842.3 |
| HL1 interior seat/floor rails (3) | 800 | 820 |
| HL1 front/back rails (2) | 850 | 860 |
| HL2 door/roof rails (4) | 950 | 950 |
| V1 posts (4) | 1150 | 1150 |
| V2 door posts (2) | 1050 | 1050 |
| Roof connector (1) | 850×65×25 | 860×45×45 |

All dimensions are millimetres. The detailed schedules and per-stock nesting
are in `beam-pieces.csv`, `cladding-pieces.csv`, and `stock-cut-plan.csv`.
For the sloping side walls, the cladding schedule gives each board's
conservative tall-edge blank length; it is not a build-ready bevel schedule
and does not give both edge heights. Narrow final boards are also counted as
separate stock lengths rather than being optimized as two-dimensional rip
offcuts.

## Preliminary structural sanity check

This is a calculation-level screening, not an engineered approval. It assumes
C24-quality dry structural timber, elastic modulus E = 11,000 N/mm², sound
stock, load paths as modeled, and competent structural fasteners. The model
does not specify fastener sizes, spacings, timber grade, preservative treatment,
foundation, ground anchorage, or site snow/wind zone, so connection capacity,
durability, and code compliance cannot be proven from the CAD.

### Checks that are comfortable

- **Roof framing under a 1.5 kN/m² screening snow load.** Treating a 950 mm
  45×45 cross-member as simply supported with a 466.5 mm tributary width gives
  0.700 kN/m line load, 0.079 kN·m peak moment, 5.20 N/mm² bending stress, and
  1.97 mm elastic deflection. The baseline 50×50 result is 3.79 N/mm² and
  1.30 mm. Member strength/stiffness is not the governing concern at this load.
- **Post compression/buckling.** A conservative pin-ended Euler screen for a
  1.15 m long 45×45 post gives about 28 kN critical load (baseline 50×50:
  43 kN), far above the few-kilonewton gravity load expected for this roof and
  one occupant. Real joints and eccentricity reduce this, but gravity
  compression is not a likely weak spot.
- **Racking geometry.** Both side walls have full diagonals. The shorter
  45×45 section still has ample axial capacity for modest lateral load,
  provided its end connections can transfer the force.

### Weak spots / unresolved items

1. **20 mm floor boards are the clearest local weakness.** For a deliberately
   harsh 1.5 kN point load carried by one 120 mm board over its conservative
   full 785 mm blank length
   span, simple-beam screening gives 36.8 N/mm² bending stress and 17.2 mm
   deflection. The actual CAD support geometry is about 740 mm centre-to-centre
   (34.7 N/mm² and 14.4 mm), so the weakness remains. If three
   tongue-and-groove boards share the load equally, the
   result drops to 12.3 N/mm² and 5.7 mm, but that load sharing should not be
   assumed without a diaphragm/detail that guarantees it. The baseline 25 mm
   board gives 23.3 N/mm² and 8.5 mm for one board. Add an intermediate floor
   joist/support or verify the actual floor-board span and grade before using
   20 mm boards.
2. **Seat top needs connection/load-sharing confirmation.** Its 500 mm span is
   much shorter (about 435 mm support-centre spacing) and is likely serviceable,
   but a concentrated occupant load can still land on one board. Ensure the
   front and rear rails support every board and the boards are positively tied
   together.
3. **Interior rail bearing/load paths are not resolved.** The floor back
   support and 820 mm seat rails end between the side framing, adjacent to the
   20 mm cladding, rather than bearing directly on the posts or side rails.
   Their vertical capacity therefore depends on unspecified end fasteners
   and/or load transfer through cladding. Add direct blocking, hangers, or
   bearing onto the primary frame, or engineer those connections explicitly.
4. **Wind stability depends on anchorage, not beam size.** A screening lateral
   pressure of 0.8 kN/m² on a 0.95×1.275 m face produces roughly 0.97 kN shear
   and 0.62 kN·m overturning moment. An unanchored lightweight cubicle can slide
   or overturn even though its individual beams are strong. Anchor all four
   legs to a suitable base and provide a positive shear path through brace
   connections.
5. **Roof uplift and hinge/latch capacity are unverified.** At the same
   0.8 kN/m² screening pressure the 1.05×1.085 m roof sees about 0.91 kN gross
   uplift, much more than its dead weight. The hinged roof needs rated positive
   latches/hold-downs on the opposite edge and hinge fixings designed for
   withdrawal.
6. **Back/front racking paths rely on cladding and connections.** The CAD has
   side diagonals, but no dedicated back-wall diagonal and the front is mostly
   a door. Treating 20 mm tongue-and-groove boards as a shear diaphragm requires
   a defined fastening pattern. Otherwise add discrete bracing or metal straps.
7. **Moisture and end grain matter outdoors.** The 100 mm timber legs are close
   to splash/ground exposure. Use durable or treated timber, isolate end grain
   from soil/concrete moisture, and detail drainage; decay would invalidate all
   strength assumptions.

## Conclusion

The 45×45 frame-member elastic screens are reasonable for a small, lightly loaded
toilet. The construction is **not yet demonstrated sound as drawn** because the
model omits the connection and anchorage design, the interior rails lack a
clear direct-bearing load path, and the 20 mm floor has a credible
concentrated-load weakness. The minimum practical resolution is a floor
intermediate support, direct bearing/hangers for interior rails, four positive
ground/base anchors, rated roof hold-downs, and explicit structural fastening
for braces/cladding. Site-specific snow/wind loads and Eurocode 5 modification,
moisture, connection, bearing, and combined-action checks remain outside this
screening.
