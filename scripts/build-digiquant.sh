#!/usr/bin/env bash
# Build script for digiquant.io — run by Cloudflare Pages on every push.
# Assembles into dist/:
#   1. frontend/digiquant-web/out/ — the digiquant.io landing (Next.js static
#      export, root domain, no basePath) → dist/ root
#   2. frontend/olympus/out/       — the dashboard (basePath /dashboard)
#      → dist/dashboard/ only. /olympus/ is retired (no twin, no 308).
# The digiquant-web export ships public/_headers (root /* security headers +
# /dashboard* CSP).
set -euo pipefail

# Anchor to the repo root so the rm/cp below never touch another cwd's dist/.
cd "$(dirname "$0")/.."

rm -rf dist
mkdir -p dist

echo "--- installing workspaces ---"
npm install --prefer-offline --no-audit --no-fund --include=optional

# One binding installed by hand; build-digithings.sh carries the full rationale.
#
# @next/swc-linux-x64-gnu is locked, but kept deliberately: it must match the pinned
# next version exactly, and if next can't find it, it fetches it at build time via
# `yarn config get registry`, which crashes the yarn-less CF image ("Failed to get
# registry from yarn"). Insurance on a live deploy path; do not tidy it away.
#
# @tailwindcss/oxide-linux-x64-gnu used to be installed here too; the root lock now
# carries every installable oxide platform entry, so the install above supplies it.
if [ "$(uname -s)" = "Linux" ]; then
  echo "--- installing Linux native binding (Next SWC) ---"
  npm install \
    @next/swc-linux-x64-gnu@16.2.4 \
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
# The workspace's own `build` script passes --webpack -- same rationale as
# digithings-web's build-digithings.sh (#2244): Turbopack production-builds
# this home page into an intermittent React hydration error; webpack does
# not. `next dev` is untouched; it never reproduced this.
npm --workspace frontend/digiquant-web run build
cp -r frontend/digiquant-web/out/. dist/

# 2. Dashboard (basePath /dashboard) → dist/dashboard/.
echo "--- building dashboard ---"
# T1 Pages gap: default Auth login UI on Cloudflare Pages without cutover 900
# (anon RLS remains until intentional human cutover). Explicit
# NEXT_PUBLIC_DASHBOARD_AUTH=0 keeps the classic pre-auth shell.
if [ "${CF_PAGES:-}" = "1" ] && [ -z "${NEXT_PUBLIC_DASHBOARD_AUTH:-}" ]; then
  export NEXT_PUBLIC_DASHBOARD_AUTH=1
fi
echo "NEXT_PUBLIC_DASHBOARD_AUTH=${NEXT_PUBLIC_DASHBOARD_AUTH:-<unset>}"
npm --workspace frontend/olympus run build
mkdir -p dist/dashboard
cp -r frontend/olympus/out/. dist/dashboard/

# 3. Custom domain marker.
echo "digiquant.io" > dist/CNAME

# 4. Deploy build stamp (#1759). Pages serves a frozen deploy with a 200 and no
# `last-modified`, so without a stamp in the export every smoke probe passes
# forever and a Pages project that stopped building is invisible from outside.
echo "--- writing dist/build-info.json ---"
bash scripts/write-build-info.sh dist/build-info.json digiquant.io

# Sanity: landing, a subsystem page, the root _headers, and the dashboard must exist.
[ -f dist/index.html ] || { echo "ERROR: dist/index.html missing — digiquant-web did not export" >&2; exit 1; }
[ -f dist/subsystems/research/index.html ] || { echo "ERROR: subsystem pages missing" >&2; exit 1; }
[ -f dist/_headers ] || { echo "ERROR: dist/_headers missing — CSP would not apply" >&2; exit 1; }
[ -f dist/dashboard/index.html ] || { echo "ERROR: dist/dashboard/index.html missing — dashboard did not export" >&2; exit 1; }
# Auth routes (T1) — trailingSlash export → login/index.html (fixes prod 404).
[ -f dist/dashboard/login/index.html ] || { echo "ERROR: dist/dashboard/login/index.html missing — Auth login route not exported" >&2; exit 1; }
[ -f dist/dashboard/auth/callback/index.html ] || { echo "ERROR: dist/dashboard/auth/callback/index.html missing — Auth callback route not exported" >&2; exit 1; }
# Settings (T3 + Observer IA). Cloudflare Pages sets CF_PAGES=1, and this script
# then defaults NEXT_PUBLIC_DASHBOARD_AUTH=1, so the static shell is the anonymous
# Observer view: Notifications | Billing | About. Pipeline/Keys testids are
# Custom+ only (`settingsTabsVisible('free')`) and MUST NOT be required on that
# path — requiring them is why #3266/#3273 never reached live digiquant.io
# (GitHub Actions omits CF_PAGES, auth stays off, tierFromSession returns
# enterprise, and the same greps pass there). Landed on main as #3275.
[ -f dist/dashboard/settings/index.html ] || { echo "ERROR: dist/dashboard/settings/index.html missing — Settings route not exported" >&2; exit 1; }
grep -q 'The desk, not the product' dist/dashboard/settings/index.html \
  || { echo "ERROR: settings export missing Observer IA heading" >&2; exit 1; }
grep -q 'settings-tab-notifications' dist/dashboard/settings/index.html \
  || { echo "ERROR: settings export missing Notifications tab marker" >&2; exit 1; }
grep -q 'settings-tab-billing' dist/dashboard/settings/index.html \
  || { echo "ERROR: settings export missing Billing tab marker" >&2; exit 1; }
grep -q 'settings-tab-about' dist/dashboard/settings/index.html \
  || { echo "ERROR: settings export missing About tab marker" >&2; exit 1; }
if [ "${NEXT_PUBLIC_DASHBOARD_AUTH:-}" != "1" ]; then
  grep -q 'settings-tab-pipeline' dist/dashboard/settings/index.html \
    || { echo "ERROR: settings export missing Pipeline tab marker — stale pre-T3 shell?" >&2; exit 1; }
  grep -q 'settings-tab-keys' dist/dashboard/settings/index.html \
    || { echo "ERROR: settings export missing Keys tab marker — BYOK surface not in export?" >&2; exit 1; }
fi
[ -f dist/build-info.json ] || { echo "ERROR: dist/build-info.json missing — the deploy freshness probe would report every deploy as unstamped (#1759)" >&2; exit 1; }

echo "--- dist/ contents ---"
ls -la dist/
echo "--- dist/dashboard/ contents ---"
ls -la dist/dashboard/ | head -10
