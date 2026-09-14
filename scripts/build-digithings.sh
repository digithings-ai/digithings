#!/usr/bin/env bash
# Build script for digithings.ai — run by Cloudflare Pages on every push.
# digithings.ai is now a Next.js static-export app (cloudflare/digithings-web);
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

# One binding installed by hand, and NOT because the lock is missing it (same guard
# as build-digiquant.sh).
#
# @next/swc-linux-x64-gnu IS locked (16.2.4, every platform) and must match the
# pinned next version exactly. Kept anyway, because here a missing @next/swc is not a
# clean error — next falls back to fetching it at build time via `yarn config get
# registry`, which crashes the yarn-less Cloudflare image. Cheap insurance on a live
# deploy path; do not remove it to tidy the list.
#
# @tailwindcss/oxide-linux-x64-gnu used to be installed here too, because the lock
# held oxide-darwin-arm64 alone. The lock now carries all eleven installable oxide
# platform entries with their `libc` fields, so the install above resolves the right
# one and @tailwindcss/postcss finds its binary.
if [ "$(uname -s)" = "Linux" ]; then
  echo "--- installing Linux native binding (Next SWC) ---"
  npm install \
    @next/swc-linux-x64-gnu@16.2.4 \
    --no-save --no-audit --no-fund
fi

echo "--- building digithings-web (Next.js static export) ---"
# Same-hostname digichat Container by default; override for Tunnel staging.
export NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN="${NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN:-https://digithings.ai}"
echo "NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=${NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN}"
# prebuild rewrites public/_headers frame-src from NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN
# The workspace's own `build` script passes --webpack: Turbopack (Next 16's
# build default) production-builds this home page into an intermittent React
# hydration error (#2244) that never reproduces under webpack -- a known,
# unresolved class of upstream Next.js/React bug (vercel/next.js#43159), not
# an app bug. `next dev` is untouched; it never reproduced this.
npm --workspace cloudflare/digithings-web run build

# Assemble dist/ from the static export (includes /og.png for the stable OG
# URL, and self-hosted fonts under /_next/static/media).
rm -rf dist
mkdir -p dist
cp -r cloudflare/digithings-web/out/. dist/
echo "digithings.ai" > dist/CNAME

# CSP frame-src must match the /chat iframe origin (Bugbot / embed cutover).
[ -f dist/_headers ] || { echo "ERROR: dist/_headers missing — CSP would not apply" >&2; exit 1; }
FRAME_SRC="$(node --input-type=module -e '
  import { frameSrcForCsp } from "./cloudflare/digithings-web/lib/security-headers.mjs";
  process.stdout.write(frameSrcForCsp());
')"
grep -F "frame-src ${FRAME_SRC}" dist/_headers >/dev/null \
  || { echo "ERROR: dist/_headers frame-src does not match NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN (${FRAME_SRC})" >&2; exit 1; }

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

# Public OpenAPI explorer (#2058): committed specs + Swagger UI assets must ship.
[ -f dist/docs/api/index.html ] || { echo "ERROR: dist/docs/api/index.html missing — OpenAPI index not exported" >&2; exit 1; }
[ -f dist/openapi/digigraph.json ] || { echo "ERROR: dist/openapi/digigraph.json missing — OpenAPI sync did not run" >&2; exit 1; }
[ -f dist/swagger-ui/swagger-ui-bundle.js ] || { echo "ERROR: dist/swagger-ui/swagger-ui-bundle.js missing — swagger-ui-dist not vendored" >&2; exit 1; }

# openwiki visualizer (#3696): static export of the repo wiki served at /openwiki/.
# `openwiki visualize --export` writes index.html + client.js + styles.css +
# client-lib.js + graph.json. Graph data loads via a relative ./graph.json URL,
# so the export is subpath-safe. Pinned CLI: the meta-CSP patch and the
# /openwiki/* _headers exception (lib/security-headers.mjs) depend on this
# generator's output shape — bump the pin deliberately, re-verify both.
echo "--- exporting openwiki visualizer to dist/openwiki ---"
npx --yes openwiki@0.5.0 visualize openwiki --export dist/openwiki
[ -f dist/openwiki/index.html ] || { echo "ERROR: dist/openwiki/index.html missing — openwiki export failed" >&2; exit 1; }
[ -f dist/openwiki/graph.json ] || { echo "ERROR: dist/openwiki/graph.json missing — openwiki export failed" >&2; exit 1; }
[ -f dist/openwiki/client.js ] || { echo "ERROR: dist/openwiki/client.js missing — openwiki export shape changed?" >&2; exit 1; }
[ -f dist/openwiki/client-lib.js ] || { echo "ERROR: dist/openwiki/client-lib.js missing — openwiki export shape changed?" >&2; exit 1; }
[ -f dist/openwiki/styles.css ] || { echo "ERROR: dist/openwiki/styles.css missing — openwiki export shape changed?" >&2; exit 1; }

# The exporter's own <meta> CSP allows only 'self' fonts, which would silently
# downgrade the wiki to fallback fonts under the /openwiki/* header. Widen just
# the two font directives (portable sed via temp file + mv; exact-match, fail
# closed if the generator's output shape ever changes).
META_TMP="$(mktemp)"
sed -e "s|style-src 'self' 'unsafe-inline'|style-src 'self' 'unsafe-inline' https://fonts.googleapis.com|" \
    -e "s|font-src 'self'|font-src 'self' https://fonts.gstatic.com|" \
    dist/openwiki/index.html > "$META_TMP"
grep -q "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" "$META_TMP" \
  || { echo "ERROR: openwiki meta-CSP style-src patch did not apply — generator output changed?" >&2; exit 1; }
grep -q "font-src 'self' https://fonts.gstatic.com" "$META_TMP" \
  || { echo "ERROR: openwiki meta-CSP font-src patch did not apply — generator output changed?" >&2; exit 1; }
mv "$META_TMP" dist/openwiki/index.html


# Cloudflare Pages Functions live at the PROJECT ROOT (this script's CWD = repo root),
# NOT inside the static output dir. Mirror from cloudflare/digithings-web/functions/
# (Phase 3: digivault /api/chat + /api/byok on free Pages — no Containers).
echo "--- mirroring Pages Functions to repo root ---"
rm -rf functions
if [ -d cloudflare/digithings-web/functions ] && [ -n "$(find cloudflare/digithings-web/functions -type f 2>/dev/null | head -1)" ]; then
  cp -r cloudflare/digithings-web/functions functions
  # Wrangler's functions bundler treats every file under functions/ as a route
  # candidate. Test files (e.g. test.test.ts, colocated next to test.ts per
  # this repo's convention) export no onRequest* handler today, so they don't
  # currently register as a route -- but that's an accident of what they
  # happen to export, not a guarantee. Strip them from the mirrored copy so
  # it stays true by construction (#2348).
  find functions -type f \( -name "*.test.ts" -o -name "*.test.tsx" \) -delete
else
  echo "ERROR: expected cloudflare/digithings-web/functions (digivault /api/chat)" >&2
  exit 1
fi
if [ ! -f functions/api/chat.ts ]; then
  echo "ERROR: functions/api/chat.ts missing after mirror" >&2
  exit 1
fi
if find functions -type f \( -name "*.test.ts" -o -name "*.test.tsx" \) 2>/dev/null | grep -q .; then
  echo "ERROR: test files still present under functions/ after exclusion (#2348)" >&2
  exit 1
fi

echo "--- dist/ contents ---"
ls -la dist/
