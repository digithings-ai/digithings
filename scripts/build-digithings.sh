#!/usr/bin/env bash
# Build script for digithings.ai — run by Cloudflare Pages on every push.
# digithings.ai is now a Next.js static-export app (frontend/digithings-web);
# this builds it and assembles dist/. (Was copy-only for the legacy static site.)
#
# NOTE: the Cloudflare Pages project for digithings.ai must run this script with
# a Node build environment (build command: `bash scripts/build-digithings.sh`,
# output dir: `dist`, NODE_VERSION=22) — a one-time dashboard change at cutover.
set -euo pipefail

# Anchor to repo root so dist/ is always created there.
cd "$(dirname "$0")/.."

echo "--- installing workspaces ---"
npm install --prefer-offline --no-audit --no-fund --include=optional

# GHA/npm cache can omit platform optional deps (npm/cli#4828); Next + Tailwind v4
# need these on Linux (same guard as build-digiquant.sh). @next/swc must match the
# pinned next version exactly; if it's absent, next tries to download it at build
# time via `yarn config get registry`, which crashes in the yarn-less CF image.
if [ "$(uname -s)" = "Linux" ]; then
  echo "--- installing Linux native bindings (Next SWC + Tailwind/PostCSS) ---"
  npm install \
    @next/swc-linux-x64-gnu@16.2.4 \
    lightningcss-linux-x64-gnu@1.32.0 \
    @tailwindcss/oxide-linux-x64-gnu@4.2.2 \
    --no-save --no-audit --no-fund
fi

echo "--- building digithings-web (Next.js static export) ---"
npm --workspace frontend/digithings-web run build

# Assemble dist/ from the static export (includes /design/assets/og.png for the
# stable OG URL, and self-hosted fonts under /_next/static/media).
rm -rf dist
mkdir -p dist
cp -r frontend/digithings-web/out/. dist/
echo "digithings.ai" > dist/CNAME

# Deploy build stamp (#1759). Cloudflare Pages serves a frozen deploy with a 200
# and no `last-modified`, so without a stamp in the export every smoke probe
# passes forever and a Pages project that stopped building is invisible from
# outside — exactly how digiquant.io went nine days unnoticed. Written after
# dist/ is assembled because the `rm -rf dist` above would delete it.
echo "--- writing dist/build-info.json ---"
bash scripts/write-build-info.sh dist/build-info.json digithings.ai

# Sanity: landing must exist and carry the module manifest (the per-module pages
# were folded into the home-page terminal manifest, so /modules/* no longer exists).
# Match the aria-label, not an implementation class — the pane is the shared
# <TerminalManifest> primitive since #1416 (was app-local .dt-manifest markup).
[ -f dist/index.html ] || { echo "ERROR: dist/index.html missing — build did not export" >&2; exit 1; }
grep -q 'aria-label="digithings module manifest"' dist/index.html || { echo "ERROR: module manifest missing from home page" >&2; exit 1; }
[ -f dist/build-info.json ] || { echo "ERROR: dist/build-info.json missing — the deploy freshness probe would report every deploy as unstamped (#1759)" >&2; exit 1; }

# Cloudflare Pages Functions live at the PROJECT ROOT (this script's CWD = repo root),
# NOT inside the static output dir. Mirror any remaining Functions from
# frontend/digithings-web/functions/ (Phase 3 retired /api/chat).
echo "--- mirroring Pages Functions to repo root (if any) ---"
rm -rf functions
if [ -d frontend/digithings-web/functions ] && [ -n "$(find frontend/digithings-web/functions -type f 2>/dev/null | head -1)" ]; then
  cp -r frontend/digithings-web/functions functions
else
  echo "No Pages Functions to mirror (Phase 3: /api/chat retired)."
fi
# Must NOT reintroduce the retired chat Function
if [ -f functions/api/chat.ts ]; then
  echo "ERROR: functions/api/chat.ts must stay deleted (Phase 3)" >&2
  exit 1
fi

echo "--- dist/ contents ---"
ls -la dist/
