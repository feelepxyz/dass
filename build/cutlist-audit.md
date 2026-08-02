# Cut-list audit

| Part | reconciled cut list | reconciled drawing | generated CAD | Result |
|---|---|---|---|---|
| V1 | 4 × 1150 | 4 × 1150 | 4 parts: 1150.0, 1150.0, 1150.0, 1150.0 | match |
| V2 | 2 × 1050 | 2 × 1050 | 2 parts: 1050.0, 1050.0 | match |
| D1 | 2 × 1209 | 2 × 1209 | 2 parts: 1203.0, 1203.0 | ERROR |
| D2 | 1 × 1274.8 | 1 × 1274.8 | 2 parts: 1315.9, 1315.9 | ERROR |
| HK1 | 4 × 750 | 4 × 750 | 4 parts: 725.0, 725.0, 725.0, 725.0 | ERROR |
| HK2 | 2 × 833 | 2 × 833 | 2 parts: 812.7, 812.7 | ERROR |
| HL1 | 5 × 850 | 5 × 850 | 4 parts: 852.0, 852.0, 900.0, 900.0 | ERROR |
| HL2 | 2 × 950 | 2 × 950 | 4 parts: 900.0, 900.0, 990.0, 990.0 | ERROR |

## Notes

- The source image specifies 50×50 stock for every row.
- User reconciliation assigns V1 to four structural uprights, V2 to two door uprights, and D2 to the single door diagonal.
- The image specifies −36° cuts at both D1 ends and −40° cuts at both D2 ends.
- CAD quantities are derived from the model, not copied from either reference table.
- Exact 850 × 950 mm door opening geometry gives D2 = 1274.8 mm and a 41.8° cut.

## Errors

- D1: image=2 × 1209, drawing=2 × 1209, CAD=2 parts: 1203.0, 1203.0
- D2: image=1 × 1274.8, drawing=1 × 1274.8, CAD=2 parts: 1315.9, 1315.9
- HK1: image=4 × 750, drawing=4 × 750, CAD=4 parts: 725.0, 725.0, 725.0, 725.0
- HK2: image=2 × 833, drawing=2 × 833, CAD=2 parts: 812.7, 812.7
- HL1: image=5 × 850, drawing=5 × 850, CAD=4 parts: 852.0, 852.0, 900.0, 900.0
- HL2: image=2 × 950, drawing=2 × 950, CAD=4 parts: 900.0, 900.0, 990.0, 990.0
