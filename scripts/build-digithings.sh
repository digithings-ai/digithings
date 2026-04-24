#!/usr/bin/env bash
# Build script for digithings.ai — run by Cloudflare Pages on every push.
set -euo pipefail

mkdir -p dist
cp -r frontend/digithings/. dist/
cp -r frontend/design dist/design

echo "--- dist/ contents ---"
ls -la dist/
