# Repository Guidelines

## Project Structure & Module Organization

The repository uses a `src/` layout for Python code:

Use `src/dass/` instead of a generic `lib/` directory. This is the common
installable package layout for modern Python projects.

- `src/dass/model.py` is the parametric CadQuery model.
- `src/dass/cutlists.py` creates the cut schedules.
- `src/dass/build_guide.py` creates the workshop guide.
- `src/dass/photo_render.py` creates model images and GLB files.
- `src/dass/serve.py` builds, serves, and watches the guide during development.
- `tests/` contains the `unittest` suite.
- `scripts/` contains audits, overlay generation, browser checks, and deploy
  helpers.
- `docs/original-drawing/` contains the supplied drawings and render targets.
- `docs/verification/` contains retained evidence, grouped by job: `geometry/`,
  `evolution/`, `guide/`, and `inspection/`.
- `web/media/` contains source textures, fonts, and the in-situ background.
- `web/render/` contains the browser renderer and its Node dependencies.
- `build/` is generated deployment and CAD output. Do not edit it by hand.

Keep one-off verification images and inspection files out of `build/`. Put new
evidence in the matching `docs/verification/` subfolder.

Regenerate generated files from source. Do not edit them by hand.

## Build, Test, and Development Commands

- `uv sync` installs the Python 3.11 or newer environment.
- `uv run serve-guide` builds the guide, serves it, and rebuilds it as you save.
  This is the command to use while you work on the guide. It installs the render
  dependencies if they are missing, writes the schedules, the pages, the viewer
  GLB files, and the browser assets, then opens
  <http://localhost:8000/cut-guide.html>. It steps to the next free port if that
  one is taken. Use `--renders` to re-photograph the model first, `--port` to
  choose a port, and `--no-open` to keep the browser closed. The commands below
  are the same steps, one at a time.
- `uv run python -m unittest discover -v` runs all Python tests.
- `uv run dass` creates the default CAD model and cut list in `build/`.
- `uv run generate-cutlists` creates the CSV cut schedules.
- `uv run generate-build-guide` creates `build/cut-guide.html`.
- `(cd web/render && npm install)` installs the render dependencies.
- `uv run render-photo` creates all reference images and GLB files.
- `uv run scripts/build_web_assets.py` stages the guide assets in `build/`.
- `uv run python scripts/audit_cutlist.py` writes the cut-list audit outputs.
- `uv run python scripts/make_overlays.py` writes drawing comparison evidence.
- `uv run python -m http.server 8000 --directory build` serves the guide at
  <http://localhost:8000/cut-guide.html>. The page uses ES modules and an
  import map, so opening the file directly does not work.
- `node scripts/check-print.mjs` proves the printed set keeps every drawing
  whole on one page and prints no empty sheet. It writes
  `docs/verification/guide/shots/cut-guide.pdf`.
- `./scripts/deploy-cut-guide.sh` rebuilds and deploys the Worker.

## Coding Style & Naming Conventions

Use four spaces for Python indentation. Keep imports in standard library,
third-party, and local groups. Use type annotations for new public functions
and data structures. Use `snake_case` for functions and variables,
`PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants.

No formatter or linter is configured.

Match nearby code and keep geometry formulas readable. Put physical dimensions
and reusable defaults on `Design`. Do not scatter numeric values.

## Testing Guidelines

The test suite uses `unittest`. The repository has no coverage threshold.

Name files `test_<area>.py` and methods `test_<behavior>`. Add a regression
test for geometry, cut-list, or guide changes. Make sure that dimensions,
clearances, part counts, and generated content are correct at the most direct
layer.

## Commit & Pull Request Guidelines

Use Conventional Commits with a focused scope, such as
`feat(dass): add floor support`. Keep each commit limited to one coherent
change.

In each pull request, explain the model or workshop impact. Link the relevant
issue. List the commands that you ran. Include images for visual changes.
Include generated files only when the source change requires them.
