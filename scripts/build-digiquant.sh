#!/usr/bin/env bash
# Build script for digiquant.io — run by Cloudflare Pages on every push.
# Mirrors the assembly that deploy-digiquant.yml used to do locally.
set -euo pipefail

mkdir -p dist
cp -r frontend/digiquant/. dist/
cp -r frontend/design dist/design
echo "digiquant.io" > dist/CNAME

echo "--- dist/ contents ---"
ls -la dist/
