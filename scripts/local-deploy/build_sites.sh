#!/usr/bin/env bash
# Local replacement for the Pages build-check jobs in
# deploy-digiquant-cloudflare.yml and deploy-digithings-cloudflare.yml
# (both disabled on GitHub; Actions minutes exhausted).
#
# Runs the same build scripts Cloudflare Pages runs, in the same order the
# lanes run them, then the same dist assertions and the same freshness
# evaluator over the stamp the build just wrote.
#
# Usage: bash scripts/local-deploy/build_sites.sh [digiquant|digithings|all]
set -euo pipefail
cd "$(dirname "$0")/../.."

WHAT="${1:-all}"
case "$WHAT" in
  digiquant|digithings|all) ;;
  *) echo "Usage: $0 [digiquant|digithings|all]" >&2; exit 2 ;;
esac

run_digithings() {
  echo "--- pip install dry-run (Cloudflare runs pip install . first) ---"
  python3 -m pip install --dry-run --no-deps .
  echo "--- assemble dist/ (same as Cloudflare Pages) ---"
  bash scripts/build-digithings.sh
  echo "--- assert dist layout ---"
  test -f dist/index.html
  test -f dist/CNAME
  for band in architecture why open-source digiquant pricing faq contact; do
    grep -q "id=\"$band\"" dist/index.html \
      || { echo "ERROR: landing band #$band missing from dist/index.html" >&2; exit 1; }
  done
  grep -q digithings.ai dist/CNAME
  if grep -rq "fonts.googleapis.com" dist --exclude-dir=openwiki --exclude=_headers; then
    echo "ERROR: Google Fonts ref outside dist/openwiki in dist/ export" >&2; exit 1
  fi
  grep -q '^/openwiki/\*$' dist/_headers \
    || { echo "ERROR: dist/_headers missing /openwiki/* exception" >&2; exit 1; }
  echo "--- assert deploy build stamp ---"
  test -f dist/build-info.json
  python3 scripts/check_deploy_freshness.py \
    --url dist/build-info.json \
    --status 200 \
    --body-file dist/build-info.json \
    --max-age-hours 1
  echo "PASS digithings site build."
}

run_digiquant() {
  echo "--- assemble dist/ (same as Cloudflare Pages) ---"
  bash scripts/build-digiquant.sh
  echo "--- assert deploy build stamp ---"
  test -f dist/build-info.json
  python3 scripts/check_deploy_freshness.py \
    --url dist/build-info.json \
    --status 200 \
    --body-file dist/build-info.json \
    --max-age-hours 1
  echo "PASS digiquant site build."
}

case "$WHAT" in
  digithings) run_digithings ;;
  digiquant) run_digiquant ;;
  all) run_digithings; run_digiquant ;;
esac
