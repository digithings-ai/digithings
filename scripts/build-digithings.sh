#!/usr/bin/env bash
# Build script for digithings.ai — run by Cloudflare Pages on every push.
set -euo pipefail

# Anchor to the repo root so the rm/cp below never touch another cwd's dist/.
cd "$(dirname "$0")/.."

# Clean slate: a stale dist/ from a previous run would re-nest the design copy below.
rm -rf dist
mkdir -p dist/design/assets
cp -r frontend/digithings/. dist/
# Copy CONTENTS (trailing /.): `cp -r frontend/design dist/design` nests the package
# at dist/design/design/ because dist/design already exists (mkdir above), which
# 404s every stylesheet and ES module the pages reference via ../design/.
cp -r frontend/design/. dist/design/
# REM-083: ship OG asset at stable absolute URL path
if [ -f frontend/digithings/public/og.png ]; then
  cp frontend/digithings/public/og.png dist/design/assets/og.png
fi

# Fail the deploy if the design package didn't land where the pages reference it.
[ -f dist/design/tokens.css ] || { echo "ERROR: dist/design/tokens.css missing — design package not assembled" >&2; exit 1; }
[ ! -e dist/design/design ] || { echo "ERROR: design package nested at dist/design/design/" >&2; exit 1; }

echo "--- dist/ contents ---"
ls -la dist/
