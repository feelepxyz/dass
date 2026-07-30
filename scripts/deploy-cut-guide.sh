#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

uv run generate_cutlists.py
uv run generate_build_guide.py
uv run scripts/build_web_assets.py

deploy_dir=$(mktemp -d)
trap 'rm -rf -- "${deploy_dir:?}"' EXIT

cp build/cut-guide.html "$deploy_dir/index.html"
cp -R build/fonts "$deploy_dir/fonts"
cp -R build/textures "$deploy_dir/textures"
cp -R build/web-renders "$deploy_dir/web-renders"
cp -R build/vendor "$deploy_dir/vendor"

# The model viewer loads the same GLB variants the renderer photographs.
mkdir -p "$deploy_dir/renders"
cp build/renders/dass-open.glb build/renders/dass-closed.glb "$deploy_dir/renders/"

npx --yes wrangler@4.116.0 deploy \
  --name dass-cut-guide \
  --assets "$deploy_dir" \
  --domain canaibuildatoiletyet.com \
  --compatibility-date 2026-07-30
