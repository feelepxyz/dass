# Frame fastening audit

This is a beam screw-layout and collision check, not a structural screw-sizing calculation.
Cladding is excluded because its fasteners are listed separately.

## Assembly hardware

| Use | Fastener |
|---|---|
| Frame beams and braces | 6 × 120 mm sunk wood screws |
| Beam-to-beam support joints, for example floor supports | 6 × 90 mm sunk wood screws |
| Råspont (matchboard/V-groove cladding) to beams | 2.8 × 60 mm nails or 6 × 60 mm sunk wood screws |

- Beam-to-beam connections: 53
- Nominal screw marks: 82
- Screw-mark overlaps: 0
- Screw-path collisions: 0
- Result: PASS

## Angle checks

| Check | Use | Drawing guide | Model guide | Run × rise |
|---|---|---:|---:|---:|
| SIDE-PITCH | finished side-frame pitch | 7.4° | 7.4° | 770 × 100 mm |
| ROOF-PITCH | finished roof-beam pitch | 8.8° | 8.8° | 803 × 125 mm |
| D1 | side diagonal saw cut | 36.0° | 34.9° | 725 × 960 mm |
| D2 | back and door diagonal saw cut | 40.0° | 41.2° | 900 × 960 mm |

## Screw marks

| Mark | From beam | Into beam | Face | Source station | Target station / end | Lane / position |
|---|---|---|---|---:|---:|---:|
| F01-1 | LSV1 (front_post_left) | FBH1 (front_bottom) | front | 45.0 mm | 122.5 mm | 12.0 mm |
| F01-2 | LSV1 (front_post_left) | FBH1 (front_bottom) | front | 45.0 mm | 122.5 mm | 33.0 mm |
| F02-1 | RSV1 (front_post_right) | FBH1 (front_bottom) | front | 45.0 mm | 122.5 mm | 12.0 mm |
| F02-2 | RSV1 (front_post_right) | FBH1 (front_bottom) | front | 45.0 mm | 122.5 mm | 33.0 mm |
| F03-1 | LSV2 (back_post_left) | BWH1 (back_bottom) | rear | 45.0 mm | 122.5 mm | 12.0 mm |
| F03-2 | LSV2 (back_post_left) | BWH1 (back_bottom) | rear | 45.0 mm | 122.5 mm | 33.0 mm |
| F04-1 | RSV2 (back_post_right) | BWH1 (back_bottom) | rear | 45.0 mm | 122.5 mm | 12.0 mm |
| F04-2 | RSV2 (back_post_right) | BWH1 (back_bottom) | rear | 45.0 mm | 122.5 mm | 33.0 mm |
| F05-1 | LSV2 (back_post_left) | BWH2 (back_top) | rear | 45.0 mm | 1127.5 mm | 12.0 mm |
| F05-2 | LSV2 (back_post_left) | BWH2 (back_top) | rear | 45.0 mm | 1127.5 mm | 33.0 mm |
| F06-1 | RSV2 (back_post_right) | BWH2 (back_top) | rear | 45.0 mm | 1127.5 mm | 12.0 mm |
| F06-2 | RSV2 (back_post_right) | BWH2 (back_top) | rear | 45.0 mm | 1127.5 mm | 33.0 mm |
| F07-1 | LSV1 (front_post_left) | LSH1 (left_bottom) | side | 45.0 mm | 122.5 mm | 12.0 mm |
| F07-2 | LSV1 (front_post_left) | LSH1 (left_bottom) | side | 45.0 mm | 122.5 mm | 33.0 mm |
| F08-1 | LSV2 (back_post_left) | LSH1 (left_bottom) | side | 45.0 mm | 122.5 mm | 12.0 mm |
| F08-2 | LSV2 (back_post_left) | LSH1 (left_bottom) | side | 45.0 mm | 122.5 mm | 33.0 mm |
| F09-1 | LSV1 (front_post_left) | LSH2 (left_top) | side | 45.0 mm | 1127.5 mm | 12.0 mm |
| F09-2 | LSV1 (front_post_left) | LSH2 (left_top) | side | 45.0 mm | 1127.5 mm | 33.0 mm |
| F10-1 | LSV2 (back_post_left) | LSH2 (left_top) | side | 45.0 mm | 1127.5 mm | 12.0 mm |
| F10-2 | LSV2 (back_post_left) | LSH2 (left_top) | side | 45.0 mm | 1127.5 mm | 33.0 mm |
| F11-1 | RSV1 (front_post_right) | RSH1 (right_bottom) | side | 45.0 mm | 122.5 mm | 12.0 mm |
| F11-2 | RSV1 (front_post_right) | RSH1 (right_bottom) | side | 45.0 mm | 122.5 mm | 33.0 mm |
| F12-1 | RSV2 (back_post_right) | RSH1 (right_bottom) | side | 45.0 mm | 122.5 mm | 12.0 mm |
| F12-2 | RSV2 (back_post_right) | RSH1 (right_bottom) | side | 45.0 mm | 122.5 mm | 33.0 mm |
| F13-1 | RSV1 (front_post_right) | RSH2 (right_top) | side | 45.0 mm | 1127.5 mm | 12.0 mm |
| F13-2 | RSV1 (front_post_right) | RSH2 (right_top) | side | 45.0 mm | 1127.5 mm | 33.0 mm |
| F14-1 | RSV2 (back_post_right) | RSH2 (right_top) | side | 45.0 mm | 1127.5 mm | 12.0 mm |
| F14-2 | RSV2 (back_post_right) | RSH2 (right_top) | side | 45.0 mm | 1127.5 mm | 33.0 mm |
| F15-1 | LSV1 (front_post_left) | LSD1 (left_brace) | side | 45.0 mm | 1105.0 mm | 12.0 mm |
| F15-2 | LSV1 (front_post_left) | LSD1 (left_brace) | side | 45.0 mm | 1105.0 mm | 33.0 mm |
| F16-1 | LSV2 (back_post_left) | LSD1 (left_brace) | side | 45.0 mm | 145.0 mm | 12.0 mm |
| F16-2 | LSV2 (back_post_left) | LSD1 (left_brace) | side | 45.0 mm | 145.0 mm | 33.0 mm |
| F17-1 | RSV1 (front_post_right) | RSD1 (right_brace) | side | 45.0 mm | 1105.0 mm | 12.0 mm |
| F17-2 | RSV1 (front_post_right) | RSD1 (right_brace) | side | 45.0 mm | 1105.0 mm | 33.0 mm |
| F18-1 | RSV2 (back_post_right) | RSD1 (right_brace) | side | 45.0 mm | 145.0 mm | 12.0 mm |
| F18-2 | RSV2 (back_post_right) | RSD1 (right_brace) | side | 45.0 mm | 145.0 mm | 33.0 mm |
| F19-1 | LSV2 (back_post_left) | BWD1 (back_brace) | rear | 45.0 mm | 145.0 mm | 12.0 mm |
| F19-2 | LSV2 (back_post_left) | BWD1 (back_brace) | rear | 45.0 mm | 145.0 mm | 33.0 mm |
| F20-1 | RSV2 (back_post_right) | BWD1 (back_brace) | rear | 45.0 mm | 1105.0 mm | 12.0 mm |
| F20-2 | RSV2 (back_post_right) | BWD1 (back_brace) | rear | 45.0 mm | 1105.0 mm | 33.0 mm |
| F21-1 | FBB1 (floor_back_support) | BWH1 (back_bottom) | inside-back | 45.0 mm | 168.0 mm | 22.5 mm |
| F21-2 | FBB1 (floor_back_support) | BWH1 (back_bottom) | inside-back | 45.0 mm | 822.0 mm | 22.5 mm |
| F22-1 | FBS2 (floor_right_support) | RSH1 (right_bottom) | inside-side | 45.0 mm | 145.0 mm | 22.5 mm |
| F22-2 | FBS2 (floor_right_support) | RSH1 (right_bottom) | inside-side | 45.0 mm | 602.0 mm | 22.5 mm |
| F23-1 | FBS1 (floor_left_support) | LSH1 (left_bottom) | inside-side | 45.0 mm | 145.0 mm | 22.5 mm |
| F23-2 | FBS1 (floor_left_support) | LSH1 (left_bottom) | inside-side | 45.0 mm | 602.0 mm | 22.5 mm |
| F24-1 | LSH1 (left_bottom) | FBH1 (front_bottom) | outside-side | 45.0 mm | beam end centre | beam centre |
| F25-1 | RSH1 (right_bottom) | FBH1 (front_bottom) | outside-side | 45.0 mm | beam end centre | beam centre |
| F26-1 | RBH1 (roof_front) | RBS1 (roof_left) | slope-front | 45.0 mm | beam end centre | beam centre |
| F27-1 | RBH1 (roof_front) | RBS2 (roof_right) | slope-front | 45.0 mm | beam end centre | beam centre |
| F28-1 | RBH2 (roof_back) | RBS1 (roof_left) | slope-rear | 45.0 mm | beam end centre | beam centre |
| F29-1 | RBH2 (roof_back) | RBS2 (roof_right) | slope-rear | 45.0 mm | beam end centre | beam centre |
| F30-1 | RBS1 (roof_left) | RBC1 (roof_middle) | slope-middle | 45.0 mm | beam end centre | beam centre |
| F31-1 | RBS2 (roof_right) | RBC1 (roof_middle) | slope-middle | 45.0 mm | beam end centre | beam centre |
| F32-1 | FBB1 (floor_back_support) | FBS2 (floor_right_support) | top | 45.0 mm | beam end centre | beam centre |
| F33-1 | FBB1 (floor_back_support) | FBS1 (floor_left_support) | top | 45.0 mm | beam end centre | beam centre |
| F34-1 | SBH2 (seat_rail_2) | SBS1 (seat_support_left) | underside | 45.0 mm | beam end centre | beam centre |
| F35-1 | SBH2 (seat_rail_2) | SBS2 (seat_support_right) | underside | 45.0 mm | beam end centre | beam centre |
| F36-1 | SBH1 (seat_rail_1) | SBS1 (seat_support_left) | underside | 45.0 mm | beam end centre | beam centre |
| F37-1 | SBH1 (seat_rail_1) | SBS2 (seat_support_right) | underside | 45.0 mm | beam end centre | beam centre |
| F38-1 | SBH1 (seat_rail_1) | SBS3 (seat_support_outer_left) | underside | 45.0 mm | beam end centre | beam centre |
| F39-1 | SBH2 (seat_rail_2) | SBS3 (seat_support_outer_left) | underside | 45.0 mm | beam end centre | beam centre |
| F40-1 | SBH1 (seat_rail_1) | SBS4 (seat_support_outer_right) | underside | 45.0 mm | beam end centre | beam centre |
| F41-1 | SBH2 (seat_rail_2) | SBS4 (seat_support_outer_right) | underside | 45.0 mm | beam end centre | beam centre |
| F42-1 | left_wall (left_wall) | SBB1 (seat_box_support_front) | outside-side | 45.0 mm | beam end centre | beam centre |
| F43-1 | right_wall (right_wall) | SBB1 (seat_box_support_front) | outside-side | 45.0 mm | beam end centre | beam centre |
| F44-1 | left_wall (left_wall) | SBB2 (seat_box_support_rear) | outside-side | 45.0 mm | beam end centre | beam centre |
| F45-1 | right_wall (right_wall) | SBB2 (seat_box_support_rear) | outside-side | 45.0 mm | beam end centre | beam centre |
| F46-1 | left_wall (left_wall) | SBF1 (seat_floor_support) | outside-side | 45.0 mm | beam end centre | beam centre |
| F47-1 | right_wall (right_wall) | SBF1 (seat_floor_support) | outside-side | 45.0 mm | beam end centre | beam centre |
| F48-1 | DBV1 (door_left) | DBH1 (door_bottom) | door | 45.0 mm | 122.5 mm | 12.0 mm |
| F48-2 | DBV1 (door_left) | DBH1 (door_bottom) | door | 45.0 mm | 122.5 mm | 33.0 mm |
| F49-1 | DBV2 (door_right) | DBH1 (door_bottom) | door | 45.0 mm | 122.5 mm | 12.0 mm |
| F49-2 | DBV2 (door_right) | DBH1 (door_bottom) | door | 45.0 mm | 122.5 mm | 33.0 mm |
| F50-1 | DBV1 (door_left) | DBH2 (door_top) | door | 45.0 mm | 1127.5 mm | 12.0 mm |
| F50-2 | DBV1 (door_left) | DBH2 (door_top) | door | 45.0 mm | 1127.5 mm | 33.0 mm |
| F51-1 | DBV2 (door_right) | DBH2 (door_top) | door | 45.0 mm | 1127.5 mm | 12.0 mm |
| F51-2 | DBV2 (door_right) | DBH2 (door_top) | door | 45.0 mm | 1127.5 mm | 33.0 mm |
| F52-1 | DBV1 (door_left) | DBD1 (door_brace) | door | 45.0 mm | 1105.0 mm | 12.0 mm |
| F52-2 | DBV1 (door_left) | DBD1 (door_brace) | door | 45.0 mm | 1105.0 mm | 33.0 mm |
| F53-1 | DBV2 (door_right) | DBD1 (door_brace) | door | 45.0 mm | 145.0 mm | 12.0 mm |
| F53-2 | DBV2 (door_right) | DBD1 (door_brace) | door | 45.0 mm | 145.0 mm | 33.0 mm |

## Workshop notes

- Fit every diagonal corner to corner and trim its ends flush with the receiving member faces.
- Drive the 6 × 120 mm diagonal screws from the vertical members at a slight angle.
- Measure the finished frame before final fastening and use the measured angle for the scribe.
- Do not use the cladding fastener pattern for beam screws.
- Measure the finished frame side and roof pitch with a bevel gauge; record the actual value before final screws.
