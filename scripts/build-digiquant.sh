#!/usr/bin/env bash
# Build script for digiquant.io — run by Cloudflare Pages on every push.
# Assembles three trees into dist/:
#   1. frontend/digiquant/   — the static digiquant.io landing site
#   2. frontend/design/      — shared design tokens consumed via ../design/...
#   3. frontend/olympus/out/ — the Olympus dashboard (Next.js static export,
#                              basePath /olympus → served at digiquant.io/olympus/)
set -euo pipefail

# 1. Static landing pages (digiquant.io root + atlas.html marketing page).
mkdir -p dist
cp -r frontend/digiquant/. dist/
cp -r frontend/design dist/design

# 2. Olympus dashboard. Cloudflare Pages provisions Node + npm; the workspace
# install is required so @digithings/design symlinks into Olympus's
# node_modules. Then `next build` honours `basePath: '/olympus'` and produces
# the static export under frontend/olympus/out/.
echo "--- installing workspaces ---"
npm install --prefer-offline --no-audit --no-fund --include=optional

# GHA/npm cache can omit platform optional deps (npm/cli#4828); Olympus build needs these on Linux.
if [ "$(uname -s)" = "Linux" ]; then
  echo "--- installing Linux native bindings (Tailwind/PostCSS) ---"
  npm install \
    lightningcss-linux-x64-gnu@1.32.0 \
    @tailwindcss/oxide-linux-x64-gnu@4.2.2 \
    --no-save --no-audit --no-fund
fi

echo "--- building Olympus dashboard ---"
npm --workspace frontend/olympus run build

echo "--- copying Olympus → dist/olympus/ ---"
mkdir -p dist/olympus
cp -r frontend/olympus/out/. dist/olympus/

# 3. Custom domain marker.
echo "digiquant.io" > dist/CNAME

echo "--- dist/ contents ---"
ls -la dist/
echo "--- dist/olympus/ contents ---"
ls -la dist/olympus/ | head -10
