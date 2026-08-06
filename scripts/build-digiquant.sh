#!/usr/bin/env bash
# Build script for digiquant.io — run by Cloudflare Pages on every push.
# Assembles into dist/:
#   1. frontend/digiquant-web/out/ — the digiquant.io landing (Next.js static
#      export, root domain, no basePath) → dist/ root
#   2. frontend/olympus/out/       — the Olympus dashboard (basePath /olympus)
#      → dist/olympus/
# The digiquant-web export ships public/_headers (root /* security headers +
# /olympus* CSP), so it governs both surfaces. Olympus is unchanged.
set -euo pipefail

# Anchor to the repo root so the rm/cp below never touch another cwd's dist/.
cd "$(dirname "$0")/.."

rm -rf dist
mkdir -p dist

echo "--- installing workspaces ---"
npm install --prefer-offline --no-audit --no-fund --include=optional

# Two bindings installed by hand; build-digithings.sh carries the full rationale.
#
# @tailwindcss/oxide is genuinely absent from the root lock — oxide-darwin-arm64
# 4.2.2 is its sole platform entry.
#
# @next/swc-linux-x64-gnu is locked, but kept deliberately: it must match the pinned
# next version exactly, and if next can't find it, it fetches it at build time via
# `yarn config get registry`, which crashes the yarn-less CF image ("Failed to get
# registry from yarn"). Insurance on a live deploy path; do not tidy it away.
#
# lightningcss-linux-x64-gnu was dropped (#1940 removed it from CI for the same
# reason): the lock has it twice over — 1.33.0 hoisted to the root, 1.32.0 nested
# under the root lightningcss — and pinning 1.32.0 at the root overwrote the hoisted
# 1.33.0 that vite's lightningcss 1.33.0 resolves to. Latent, not active: the builds
# below are `next build` only, never vitest, so nothing here loads vite's
# lightningcss — unlike the CI lanes #1940 fixed. The old npm/cli#4828 rationale
# never covered it; that issue is the npm *cache* dropping optionals, and the install
# above already passes --include=optional against a lock that carries them.
if [ "$(uname -s)" = "Linux" ]; then
  echo "--- installing Linux native bindings (Next SWC + Tailwind/PostCSS) ---"
  npm install \
    @next/swc-linux-x64-gnu@16.2.4 \
    @tailwindcss/oxide-linux-x64-gnu@4.2.2 \
    --no-save --no-audit --no-fund
fi

# REM-037: committed static portfolio JSON must not ship (Supabase is primary).
if [ -f frontend/olympus/public/dashboard-data.json ]; then
  echo "ERROR: frontend/olympus/public/dashboard-data.json must not be committed (REM-037)."
  echo "       Remove the file; portfolio data comes from Supabase at runtime."
  exit 1
fi

# Olympus inlines NEXT_PUBLIC_* into the static bundle at build time. Fail
# PRODUCTION deploys when the Supabase vars are missing (preview/local may proceed).
if [ "${CF_PAGES:-}" = "1" ]; then
  if [ -z "${NEXT_PUBLIC_SUPABASE_URL:-}" ] || [ -z "${NEXT_PUBLIC_SUPABASE_ANON_KEY:-}" ]; then
    case "${CF_PAGES_BRANCH:-}" in
      develop|main)
        echo "ERROR: production Pages build requires NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY (set them in the Pages project env)." >&2
        exit 1
        ;;
      *)
        echo "WARNING: NEXT_PUBLIC_SUPABASE_* not set — preview build will render the 'Supabase is not configured' banner." >&2
        ;;
    esac
  fi
fi

# 1. digiquant.io landing (Next.js static export) → dist/ root.
echo "--- building digiquant-web (Next.js static export) ---"
npm --workspace frontend/digiquant-web run build
cp -r frontend/digiquant-web/out/. dist/

# 2. Olympus dashboard (basePath /olympus) → dist/olympus/.
echo "--- building Olympus dashboard ---"
npm --workspace frontend/olympus run build
mkdir -p dist/olympus
cp -r frontend/olympus/out/. dist/olympus/

# 3. Custom domain marker.
echo "digiquant.io" > dist/CNAME

# 4. Deploy build stamp (#1759). Pages serves a frozen deploy with a 200 and no
# `last-modified`, so without a stamp in the export every smoke probe passes
# forever and a Pages project that stopped building is invisible from outside.
echo "--- writing dist/build-info.json ---"
bash scripts/write-build-info.sh dist/build-info.json digiquant.io

# Sanity: landing, a subsystem page, the root _headers, and Olympus must exist.
[ -f dist/index.html ] || { echo "ERROR: dist/index.html missing — digiquant-web did not export" >&2; exit 1; }
[ -f dist/subsystems/atlas/index.html ] || { echo "ERROR: subsystem pages missing" >&2; exit 1; }
[ -f dist/_headers ] || { echo "ERROR: dist/_headers missing — CSP would not apply" >&2; exit 1; }
[ -f dist/olympus/index.html ] || { echo "ERROR: dist/olympus/index.html missing — Olympus did not export" >&2; exit 1; }
[ -f dist/build-info.json ] || { echo "ERROR: dist/build-info.json missing — the deploy freshness probe would report every deploy as unstamped (#1759)" >&2; exit 1; }

echo "--- dist/ contents ---"
ls -la dist/
echo "--- dist/olympus/ contents ---"
ls -la dist/olympus/ | head -10
