# Cut-list audit

| Part | reconciled cut list | reconciled drawing | generated CAD | Result |
|---|---|---|---|---|
| V1 | 4 × 1150 | 4 × 1150 | 4 parts: 1150.0, 1150.0, 1150.0, 1150.0 | match |
| V2 | 2 × 1050 | 2 × 1050 | 2 parts: 1050.0, 1050.0 | match |
| D1 | 2 × 1209 | 2 × 1209 | 2 parts: 1209.3, 1209.3 | match |
| D2 | 1 × 1274.8 | 1 × 1274.8 | 2 parts: 1273.8, 1273.8 | ERROR |
| HK1 | 4 × 750 | 4 × 750 | 4 parts: 750.0, 750.0, 750.0, 750.0 | match |
| HK2 | 2 × 833 | 2 × 833 | 2 parts: 842.3, 842.3 | ERROR |
| HL1 | 5 × 850 | 5 × 850 | 5 parts: 800.0, 800.0, 800.0, 850.0, 850.0 | ERROR |
| HL2 | 2 × 950 | 2 × 950 | 4 parts: 850.0, 850.0, 950.0, 950.0 | ERROR |

## Notes

- The source image specifies 50×50 stock for every row.
- User reconciliation assigns V1 to four structural uprights, V2 to two door uprights, and D2 to the single door diagonal.
- The image specifies −36° cuts at both D1 ends and −40° cuts at both D2 ends.
- CAD quantities are derived from the model, not copied from either reference table.
- Exact side-frame corner geometry gives D1 = 1210.4 mm and a 38.3° cut.
- Exact 850 × 950 mm door opening geometry gives D2 = 1274.8 mm and a 41.8° cut.

## Errors

- D2: image=1 × 1274.8, drawing=1 × 1274.8, CAD=2 parts: 1273.8, 1273.8
- HK2: image=2 × 833, drawing=2 × 833, CAD=2 parts: 842.3, 842.3
- HL1: image=5 × 850, drawing=5 × 850, CAD=5 parts: 800.0, 800.0, 800.0, 850.0, 850.0
- HL2: image=2 × 950, drawing=2 × 950, CAD=4 parts: 850.0, 850.0, 950.0, 950.0
