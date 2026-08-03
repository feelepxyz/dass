# DASS

## A small outdoor toilet, drawn from a parametric model

[Open the interactive cut guide and model](https://feelep.xyz/dass)

| Attribution | Detail |
| --- | --- |
| Design source | Hannes Söderquist's outdoor toilet design |
| CAD | CadQuery and Python |
| Text-to-CAD reference | [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) |
| Current material | 45 × 45 mm beams and 120 × 23 mm Råspont (matchboard/V-groove cladding) |

![Open in-situ render](build/web-renders/in-situ-open.jpg)

This repository contains the parametric model, the browser cut guide, and the
source material for a small outdoor toilet. The live guide shows the open and
closed model, the unit drawings, and the workshop cut sequence.

## Current release

Version `0.1.4` centres terminal-board cladding screws on the material left after
trimming and keeps the fixing marks clear of beam-screw paths. Read the
[full changelog](CHANGELOG.md).

## Run the guide

```sh
uv sync
uv run serve-guide
```

This builds the cut schedules, the guide and progress pages, the GLB models the
viewer loads, and the browser assets, then serves them and opens
<http://localhost:8000/cut-guide.html>. It uses HTTP because the guide loads ES
modules, the GLB models, and its textures, which a `file://` page cannot read.
It installs the renderer's Node dependencies the first time, and it moves to the
next free port if 8000 is taken.

Leave it running. When you save a source file it rebuilds the parts of the guide
that read it and the open page reloads itself.

| Option | Effect |
| --- | --- |
| `--port 8080` | Prefer this port instead of 8000 |
| `--renders` | Re-photograph the model first; minutes of headless Chromium |
| `--page how-its-going.html` | Open a different page |
| `--page how-it-started.html` | Open the project history page |
| `--no-open` | Leave the browser alone |

The photorealistic images are the one thing a save does not rebuild. Make them
when the model changes:

```sh
uv run render-photo
```

Each step also runs on its own; `AGENTS.md` lists them.

The deploy command rebuilds the guide and publishes the Worker:

```sh
./scripts/deploy-cut-guide.sh
```

The main Python commands accept parameter overrides. For example:

```sh
uv run dass --set width=1050 --set seat_depth=550
uv run render-photo --views open-hero --skip-build
```

## Git hooks

`prek` checks each commit and runs the tests before each push:

```sh
prek install          # once, after cloning
prek run --all-files  # run every hook now
```

The commit hooks run `ruff format`, `ruff check`, and `ty`, and they cover shell
scripts, file hygiene, and YAML, JSON, and TOML syntax. The push hook runs the
`pytest` suite, which takes about half a minute. They skip `.agents/`, `build/`,
and `.cache/`, which hold vendored and generated files. Bypass them with
`git commit --no-verify` when you must.

GitHub Actions runs the same four checks on every push and pull request, on
Python 3.11 and 3.14.

## Worktrees

`wta <branch>` opens a worktree with the agent and the guide server already
running, from the hooks in `.config/wt.toml`:

```sh
wta fix-seat        # new worktree off the default branch
wt list             # what is checked out where
wt remove           # tear the worktree and its panes down
```

The guide pane runs `serve-guide --no-open`. It takes the next free port, so
several worktrees can serve their own guide at the same time.

## Model

The current design has a 990 × 815 mm outside envelope. It uses 45 × 45 mm
frame stock and 120 × 23 mm interleaved Råspont (matchboard/V-groove cladding). Each board has 110 mm of
effective cover and a 10 mm trim allowance.

The door is nine covers wide. Each side is seven covers deep. The rear wall,
floor, seat top, and seat front use the fitted spans from the frame. The roof
uses a 1050 × 1085 mm metal sheet over a hinged 45 mm timber frame.

The model is the dimensional source of truth. The cut-list generator derives
the piece schedules and the stop-block sequence from that model. It reserves a
kerf for each released piece and keeps equal-length cuts together.

The guide treats the roof, door, side walls, back wall, floor, and seat as
separate units. This keeps the drawings, part codes, and workshop order tied to
the geometry.

## Unit drawings

These images show the guide's line finish. They show the frame and model edges,
without the photoreal material finish or assembly instructions.

![Open frame model](docs/verification/guide/shots/viewer-line.png)

The open frame model shows the roof, door, left and right side units, back wall,
floor deck, and seat box as separate pieces around the same model datum.

![Roof unit drawing](docs/verification/guide/shots/unit-1440.png)

The roof unit is a hinged rectangular frame with two slope beams, two cross
beams, and one middle connector.

![Panel unit drawings](docs/verification/guide/shots/panels-1440.png)

The panel sheet shows the door field, both side fields, the back field, floor
deck, seat top, and seat front. The fields are fitted to their frames in the
CAD model and receive their final trim on the unit.

- Roof: hinged timber frame with a middle connector and metal sheet.
- Door: full-height frame with a diagonal brace and notched top corners.
- Side walls: left and right sloped frames with gang-cut cladding fields.
- Back wall: fitted frame and cladding field between the side skins.
- Floor: front-to-back deck with two edge bearers.
- Seat: box, opening, rails, and supports around the oval seat hole.

## Evolution

The project started with [Hannes Söderquist](https://www.instagram.com/hannes.soderquist/)'s
design for an outdoor toilet. The original drawing uses 50 × 50 mm beams and
120 × 25 mm cladding.

![Original side drawing](docs/original-drawing/drawing-sides.png)

I asked Claude and Codex to build a CAD model with CadQuery and build123d. The
first generated versions had several geometry problems and did not match the
source design. I did not edit any of the CAD drawings directly. Instead, I gave
Codex the goal of continuing until the model aligned with the measurements in
the drawing, and supplied measurements from the drawing as model specifications,
such as how long each beam should be. I had to do a lot of nudging to make sure
no material clipped into another part and created impossible cuts.

![Early open-model validation](docs/verification/evolution/validation-open-final_20260730T101806Z.png)

![Seat-section comparison](docs/verification/evolution/overlay-seat-section.png)

![Door-front comparison](docs/verification/evolution/overlay-door-front.png)

One cool side-effect of the CAD model was that Codex could run some basic
structural analysis on the original drawing. It found that the floor boards did
not have enough support, so we added support beams.

The next step was to adapt the design to material available in the local shop:
45 × 45 mm beams and 120 × 23 mm Råspont (matchboard/V-groove cladding). I also changed the shape slightly
so that each interleaved cladding board has at least 10 mm of trim. The board
ends therefore do not leave a lip outside the frame.

From there, the cut schedules follow the material lengths in the shop. The
optimizer groups equal-length cuts so that they can run in sequence with a
stop block on the saw. This uses more material than a fully nested plan, but it
avoids repeated measuring and small length differences between equal pieces.

The same model then generates assembly instructions that treat the door, roof,
side walls, back wall, floor, and seat as individual pieces.

## Assembly hardware

Use these fasteners for the timber assembly:

| Use | Fastener |
| --- | --- |
| Frame beams and braces | 6 × 120 mm sunk wood screws |
| Beam-to-beam support joints, for example floor supports | 6 × 90 mm sunk wood screws |
| Råspont (matchboard/V-groove cladding) to beams | 2.8 × 60 mm nails or 6 × 60 mm sunk wood screws |

Do not use the cladding fasteners for beam joints.

## Geometry notes

The design reconciles the supplied drawing with the material change in a few
important ways:

- The earlier 950 × 850 mm reference envelope becomes 990 × 815 mm outside the
  45 mm frame, so the exposed cladding fields fit 110 mm cover modules.
- The side fields fall 100 mm over 800 mm. The roof falls 125 mm over its clear
  833 mm run. The side fields are relieved around the roof frame after fixing.
- The back field fits between the side skins. The side skins therefore close the
  rear corners instead of leaving a cladding overlap behind them.
- The braces use one angled cut at each end. Their long-point lengths come from
  the exact corner-to-corner geometry. Their mitred ends stop at the inner
  faces of the vertical members, and the fastening audit checks the modeled
  screw paths.
- The floor has two edge bearers. The seat opening has a support bearer on each
  side, between the seat rails.

The tests check the default model, the wider design variant, the 45 × 45 mm
material variant, clearances, hinge movement, brace geometry, board fields, and
cut-plan capacity.

## Web media and renders

Source web media lives in `web/media/`. This includes the Input Mono font, the
wood texture maps, and `background.jpg`, which is the forest clearing used by
the in-situ render.

The photoreal renderer writes its generated images and GLB variants to
`build/renders/`. The web asset step converts those images to the files served
from `build/web-renders/` and stages the browser textures, font, vendor modules,
and model files beside the guide.

The progress page uses the local browser-ready MP4 by default. To use a
Cloudflare Stream upload instead, export the Stream customer code and video UID
before building or deploying:

    DASS_CLOUDFLARE_STREAM_CUSTOMER_CODE=... \
    DASS_CLOUDFLARE_STREAM_VIDEO_ID=... \
    ./scripts/deploy-cut-guide.sh

When both values are set, the page uses Cloudflare's responsive Stream Player
iframe and the local video pair is not staged for deployment.

Use `docs/original-drawing/` for supplied drawings and render targets. Use
`docs/verification/` for retained geometry checks, drawing comparisons, guide
screenshots, inspection records, and evolution images.

## Model changelog

Version 0.1.4 (2026-08-02) centres terminal cladding fixings after trimming and
keeps them clear of beam-screw paths. Read the [full changelog](CHANGELOG.md)
for the dated model history.
