# DASS

The generated workshop cut guide is deployed to:

<https://dass-cut-guide.feelepxyz.workers.dev>

## Preview the cut guide locally

`build/` is laid out the way the Worker serves it, so any static server rooted
there works. Regenerate the page and its assets, then serve them:

```sh
uv run generate_cutlists.py
uv run generate_build_guide.py
uv run scripts/build_web_assets.py
uv run python -m http.server 8000 --directory build
```

The guide is at <http://localhost:8000/cut-guide.html> — `cut-guide.html`
rather than `index.html`, which is only the name it is deployed under. HTTP is
required: the page loads three.js through an import map and fetches the GLB
variants, and browsers block both over `file://`. The server also answers on
the machine's LAN address, which is how to open the guide on a phone at the
bench.

## Redeploy the cut guide

Authenticate once with `npx wrangler login`, then run:

```sh
./scripts/deploy-cut-guide.sh
```

The script regenerates the cut lists and the HTML guide, stages the browser
assets, and deploys the `dass-cut-guide` Worker.

## What gets deployed

`scripts/build_web_assets.py` stages everything the page loads beside itself,
so the guide keeps working offline in a workshop:

| Path | Source | Purpose |
| --- | --- | --- |
| `index.html` | `build/cut-guide.html` | the guide itself |
| `web-renders/*.jpg` | `build/renders/*.png` | reference views, re-encoded to 1400 px |
| `renders/dass-{open,closed}.glb` | `render_photo.py` | the model viewer's two variants |
| `vendor/**` | `render/node_modules/three` | three.js, resolved through the page's import map |

The renders and GLBs come from `render_photo.py`, which needs
`render/node_modules` (`npm install` inside `render/`) and a local Chromium.
Run it before deploying if the model has changed:

```sh
uv run render_photo.py               # every view
uv run render_photo.py --views open-hero --skip-build
```
