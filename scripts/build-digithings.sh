#!/usr/bin/env bash
# Build script for digithings.ai — run by Cloudflare Pages on every push.
set -euo pipefail

mkdir -p dist/design/assets
cp -r frontend/digithings/. dist/
cp -r frontend/design dist/design
# REM-083: ship OG asset at stable absolute URL path
if [ -f frontend/digithings/public/og.png ]; then
  cp frontend/digithings/public/og.png dist/design/assets/og.png
fi

echo "--- dist/ contents ---"
ls -la dist/
