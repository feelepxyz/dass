---
name: DASS Drawing Set
description: A construction drawing set for building the parametric outdoor toilet.
colors:
  sheet: "#ffffff"
  field: "#f2f2f0"
  ink: "#151515"
  line: "#000000"
  timber: "#7f7f7f"
  grey-dark: "#5a5a5a"
  grey-mid: "#959595"
  grey-light: "#b7b7b7"
  grey-pale: "#e6e6e6"
  code: "#bb261a"
  code-deep: "#8f1c13"
  dim: "#63a4f5"
  dim-ink: "#1668c4"
typography:
  lettering:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.72rem"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "0.08em"
    textTransform: "uppercase"
  sheet-title:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "clamp(1.5rem, 3.2vw, 2.6rem)"
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: "0.02em"
    textTransform: "uppercase"
  note:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.83rem"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "0"
  caption:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.7rem"
    fontWeight: 400
    letterSpacing: "0.14em"
    textTransform: "uppercase"
  fine:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.62rem"
    fontWeight: 400
    letterSpacing: "0.14em"
    textTransform: "uppercase"
  mark:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.76rem"
    fontWeight: 400
    letterSpacing: "0.06em"
  doc-title:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "clamp(1.7rem, 4.2vw, 3rem)"
    fontWeight: 400
    letterSpacing: "0.01em"
    textTransform: "uppercase"
  drawing-mark:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "16px"
    fontWeight: 400
    letterSpacing: "0.08em"
  drawing-detail:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    letterSpacing: "0.06em"
  drawing-dimension:
    fontFamily: "InputMono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    letterSpacing: "0.04em"
strokes:
  hairline: "0.5px"
  object: "0.8px"
  section: "1.4px"
  border: "1px"
spacing:
  tick: "4px"
  unit: "8px"
  field: "20px"
  sheet: "40px"
  gap: "72px"
components:
  code-mark:
    textColor: "{colors.code}"
    textDecoration: "underline"
  dimension:
    lineColor: "{colors.dim}"
    textColor: "{colors.dim-ink}"
---

# Design System: DASS Drawing Set

## Overview

**Creative North Star: "The Drawing Set"**

The guide is a construction drawing set, in the convention of the Swedish
`arbetsritning` that `drawing-sides.png` comes from. White sheets carry thin
black line work, grey cut timber, red part codes on leader lines, and blue
dimension chains. Every figure is a numbered drawing with a centred uppercase
caption beneath it. Tables and stock diagrams are sheet content drawn to the
same line weights, not web components wearing a new skin.

The document does not decorate itself. It has the authority of a drawing that
someone builds from.

## Colors

The sheet is white. Line work and lettering are black. Cut timber reads as flat
grey. Two inks carry meaning and nothing else carries them:

- **Red `#bb261a`** is part codes, and only part codes. A code is red wherever
  it appears: on a leader, in a table, on a stock bar, in the register.
- **Blue** is dimensions and measured detail, and only those. Lines take
  `#63a4f5`, faithful to the reference. Numerals take `#1668c4`.

The blue split is deliberate. The reference blue is a print ink at drawing
scale; at screen text sizes it holds about 2.4:1, so numerals darken to reach
4.5:1 while the lines keep the reference value. Never set body or numeral text
in `#63a4f5`.

Dark red `#8f1c13` sets sheet titles. Greys run `#5a5a5a` `#7f7f7f` `#959595`
`#b7b7b7` `#e6e6e6` for timber fill, hatching, rules, and inactive states.

## Typography

Input Mono Regular is the only face, at one weight. This is correct for the
world: drawing lettering is monoline, and a set has no bold. Hierarchy comes
from size, color, case, letterspacing, and rules.

Uppercase with open tracking carries all lettering: sheet titles, drawing
captions, table headers, codes, dimensions, title blocks, controls, labels.

Instruction prose stays sentence case in the same face. Drawing sets letter
their labels in capitals and set their specification notes in sentence case,
and a workshop instruction has to survive one read with gloves on. Never set a
paragraph in capitals.

The font has 210 glyphs and no `→`. Sequences use `·` between terms.

The page letters at four steps plus two display steps: `0.62rem` fine,
`0.7rem` caption, `0.76rem` mark, `0.83rem` note, then the sheet title and the
document title, both fluid. Mobile shifts the four lettering steps down one
notch by redefining the tokens, never by restyling a rule.

Inside a drawing the steps sit close on purpose — `16px` for a code, `13px` for
a detail note, `12px` for a dimension, all in the plate's 1000-unit space. CAD
lettering is near-uniform by convention; rank inside a drawing comes from ink
colour and from what the text is attached to, not from size. Do not open these
steps up to satisfy a contrast ratio meant for page type.

## Layout

One sheet per phase, separated by generous quiet. Each sheet opens with a rule,
its number, its title, and one title block. Drawings sit inside the sheet with
their own caption and drawing number beneath, centred.

Title blocks are per sheet, never per figure. A set repeats its project stamp
once per sheet and numbers the drawings inside it; repeating the stamp under
every figure would print the same four facts sixteen times.

Text never touches a rule. Minimum 20px between any lettering and the line
below it, 40px above a sheet title. More space above a heading than below it.

## Elevation & Depth

The system is flat. There are no shadows, no fills that are not a material, and
no rounded corners. Depth is line weight: hairline for dimensions, thin for
objects, thicker for what the section plane cuts.

## Shapes

Every corner is square. Dashed lines mean an object that belongs to another
drawing, or a cut not yet made. Cut timber is solid grey. Joined cladding is a
pale tint with its board joints ruled across it.

## Line weights

Four tiers, `vector-effect: non-scaling-stroke` throughout:

| Tier | Width | Carries |
|---|---|---|
| Hairline | 0.5px | dimensions, leaders, board joints, hatching |
| Object | 0.8px | member outlines, field edges, blanks |
| Section | 1.4px | the cut plane, gang cuts, openings |
| Border | 1px | sheet rules, table rules, title blocks |

## Components

**Code mark.** Red, uppercase, underlined when it sits on a leader — the
reference underlines every code. Leaders are hairline red with a small dot at
the target.

**Dimension.** Blue chain with tick serifs, the numeral centred and clear of
the line. Values are measured off the model, never typed. Thousands are spaced
(`1 085`), matching the reference.

**Stock bar.** A scaled diagram of one stock length: pieces drawn in place with
their code and length, saw ticks at each cut, the terminal offcut hatched.

**Title block.** One per sheet. Project, sheet number, issue date, units.

## Do's and Don'ts

### Do:

- **Do** put a dimension on the drawing it belongs to, and write it once.
- **Do** keep red for codes and blue for dimensions, with no exceptions.
- **Do** letter in capitals and write instructions in sentence case.
- **Do** keep every drawing legible in black and white.

### Don't:

- **Don't** print the same number in two places on one sheet.
- **Don't** use a weight axis; the face has one weight and needs none.
- **Don't** add fills, shadows, rounded corners, or accent colors.
- **Don't** put a title block under every figure.
