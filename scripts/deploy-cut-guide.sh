#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv run generate-cutlists
uv run generate-build-guide
node scripts/render-drawing.mjs
uv run scripts/build_web_assets.py

deploy_dir="$PWD/.deploy"
rm -rf -- "$deploy_dir"
trap 'rm -rf -- "${deploy_dir:?}"' EXIT
site_dir="$deploy_dir/dass"
mkdir -p "$site_dir"

cp build/cut-guide.html "$site_dir/index.html"
cp build/cut-guide.html "$site_dir/cut-guide.html"
cp build/how-it-started.html "$site_dir/how-it-started.html"
cp build/how-its-going.html "$site_dir/how-its-going.html"
cp -R build/fonts "$site_dir/fonts"
cp -R build/textures "$site_dir/textures"
cp -R build/web-renders "$site_dir/web-renders"
cp -R build/started "$site_dir/started"
cp -R build/progress "$site_dir/progress"
cp -R build/vendor "$site_dir/vendor"

# The model viewer loads the same GLB variants the renderer photographs.
mkdir -p "$site_dir/renders"
cp build/renders/dass-open.glb build/renders/dass-closed.glb "$site_dir/renders/"

npx --yes wrangler@4.116.0 deploy \
  --config wrangler.jsonc \
  --domain canaibuildatoiletyet.com \
  --compatibility-date 2026-07-30
