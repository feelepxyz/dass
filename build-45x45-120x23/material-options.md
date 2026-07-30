# 45×45 frame / 120×23 cladding material options

All plans include a 2.8 mm kerf between pieces cut from the same stock length.
They are feasible best-fit plans, not proofs of minimum stock. Allow extra
length for squaring rough ends.

## Recalculated fitted dimensions

The 950×850 mm exterior envelope and 120 mm board coverage are unchanged.
Increasing the cladding thickness from 20 to 23 mm changes these fitted parts:

| Dimension | 120×20 | 120×23 |
|---|---:|---:|
| Clear interior width | 820 mm | 814 mm |
| Floor board length/depth | 785 mm | 782 mm |
| Seat top total width | 820 mm | 814 mm |
| Seat front board length/height | 400 mm | 397 mm |
| Floor diagonal beam | 1071.6 mm | 1065.1 mm |

Wall, door, and roof dimensions do not change. There are 28 beam pieces and
51 cladding pieces in every option.

## Purchase options

| Material | Stock length | Lengths to buy | Scheduled pieces/cuts | Total waste |
|---|---:|---:|---:|---:|
| 45×45 beam | 2.4 m | 13 | 28 | 4.435 m |
| 45×45 beam | 3.6 m | 8 | 28 | 2.021 m |
| 120×23 cladding | 3.6 m | 14 | 51 | 5.076 m |
| 120×23 cladding | 4.2 m | 12 | 51 | 5.070 m |
| 120×23 cladding | 5.4 m | 9 | 51 | 3.262 m |

Detailed per-board plans:

- `stock-2400/stock-cut-plan.csv` — use the `beam_45x45` rows.
- `stock-3600/stock-cut-plan.csv` — use either material's rows.
- `stock-4200/stock-cut-plan.csv` — use the `cladding_120x23` rows.
- `stock-5400/stock-cut-plan.csv` — use the `cladding_120x23` rows.

`beam-pieces.csv` and `cladding-pieces.csv` in any stock directory contain the
complete piece schedules independent of stock length.

## Recommendation

For easiest transport, buy **13 × 2.4 m 45×45 beams** and **14 × 3.6 m
120×23 cladding boards**. The 3.6 m cladding option buys exactly the same total
length as 12 × 4.2 m (50.4 m) and has essentially the same calculated waste,
so 4.2 m only reduces the number of boards carried.

If 3.6 m transport is acceptable for the frame, **8 × 3.6 m beams** saves
2.4 m of purchased timber over the 2.4 m option. Use **9 × 5.4 m cladding**
only when transport is easy and minimizing waste matters more than handling;
it saves 1.8 m of purchased cladding versus the 3.6/4.2 m options.

Buy at least one spare cladding board and one spare beam if stock defects,
grain selection, or cutting mistakes are likely.
