# Repository Guidelines

## Project Structure & Module Organization

The main Python modules are in the repository root. `dass.py` defines the
parametric CadQuery model. `generate_cutlists.py` and `generate_build_guide.py`
create workshop documents. `render_photo.py` creates model images and GLB
files.

Tests use the root-level `test_*.py` pattern. Browser rendering code is in
`render/`. Deployment and asset scripts are in `scripts/`. Source assets are
in `fonts/`, `textures/`, and `background.jpg`. Generated files go in `build/`
or a named `build-*` variant directory.

Regenerate the files from source. Do not edit them by hand.

## Build, Test, and Development Commands

- `uv sync` installs the Python 3.11 or newer environment.
- `uv run python -m unittest discover -v` runs all Python tests.
- `uv run dass.py` creates the default CAD model and cut list in `build/`.
- `uv run generate_cutlists.py` creates the CSV cut schedules.
- `uv run generate_build_guide.py` creates `build/cut-guide.html`.
- `(cd render && npm install)` installs the render dependencies.
- `uv run render_photo.py` creates all reference images and GLB files.
- `uv run scripts/build_web_assets.py` stages the guide assets in `build/`.
- `uv run python -m http.server 8000 --directory build` serves the guide at
  <http://localhost:8000/cut-guide.html>. The page uses ES modules and an
  import map, so opening the file directly does not work.
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
