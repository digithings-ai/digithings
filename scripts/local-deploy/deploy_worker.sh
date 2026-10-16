#!/usr/bin/env bash
# Local replacement for deploy-digithings-cron.yml and
# deploy-digiquant-runner.yml (both disabled on GitHub).
#
# DEFAULT IS DRY-RUN: test + typecheck, then `wrangler deploy --dry-run`.
# No Cloudflare credential is read, and nothing is deployed.
#
# A real deploy needs --live AND a named approval AND the Cloudflare
# credentials exported in the environment. This is the local form of
# "no prod deploy without Chris's OK":
#   LOCAL_DEPLOY_APPROVED_BY=Chris \
#     bash scripts/local-deploy/deploy_worker.sh digithings-cron --live
# (with CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID exported)
#
# Usage: bash scripts/local-deploy/deploy_worker.sh <app> [--live] [--yes]
#   <app> is the directory name under apps/ (digithings-cron, digiquant-runner,
#   dashboard-api, digichat-cloudflare, digithings-stack-cloudflare, ...).
set -euo pipefail
cd "$(dirname "$0")/../.."

LIVE=0; YES=0; APP=""
for a in "$@"; do
  case "$a" in
    --live) LIVE=1 ;;
    --yes) YES=1 ;;
    -*) echo "Unknown flag $a (want --live, --yes)." >&2; exit 2 ;;
    *) [ -z "$APP" ] || { echo "One app per run; got '$APP' and '$a'." >&2; exit 2; }; APP="$a" ;;
  esac
done
[ -n "$APP" ] || { echo "Usage: $0 <app> [--live] [--yes]" >&2; exit 2; }
[ -f "apps/$APP/wrangler.toml" ] || { echo "ERROR: apps/$APP/wrangler.toml not found." >&2; exit 1; }

LOGD="$HOME/.config/digithings/logs/local-deploy"
mkdir -p "$LOGD"
LOG="$LOGD/deploy-$APP-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee "$LOG") 2>&1
echo "deploy_worker: app=$APP live=$LIVE log=$LOG"

PKG="$(node -p "require('./apps/$APP/package.json').name")"
echo "package: $PKG"

echo "--- test + typecheck ---"
if node -e "const p=require('./apps/$APP/package.json'); process.exit(p.scripts&&p.scripts.test?0:1)"; then
  npm run test --workspace "$PKG"
else
  echo "(no test script for $PKG; skipping)"
fi
if node -e "const p=require('./apps/$APP/package.json'); process.exit(p.scripts&&p.scripts.typecheck?0:1)"; then
  npm run typecheck --workspace "$PKG"
else
  echo "(no typecheck script for $PKG; skipping)"
fi

if [ "$LIVE" -eq 0 ]; then
  echo "--- dry-run deploy (no credential, nothing deployed) ---"
  (cd "apps/$APP" && npm exec -- wrangler deploy --dry-run --containers-rollout=none --outdir "${TMPDIR:-/tmp}/wrangler-dry-run-$APP-$$")
  echo "PASS $APP dry-run. Re-run with --live plus LOCAL_DEPLOY_APPROVED_BY to deploy."
  exit 0
fi

: "${LOCAL_DEPLOY_APPROVED_BY:?--live needs LOCAL_DEPLOY_APPROVED_BY naming the approver (Chris for production).}"
: "${CLOUDFLARE_API_TOKEN:?--live needs CLOUDFLARE_API_TOKEN.}"
: "${CLOUDFLARE_ACCOUNT_ID:?--live needs CLOUDFLARE_ACCOUNT_ID.}"
if [ "$YES" -eq 0 ]; then
  printf "Deploy apps/%s live, approved by %s? [yes/NO] " "$APP" "$LOCAL_DEPLOY_APPROVED_BY"
  read -r ans
  [ "$ans" = "yes" ] || { echo "Aborted; nothing deployed."; exit 1; }
fi
echo "--- live deploy (approved by $LOCAL_DEPLOY_APPROVED_BY) ---"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
(cd "apps/$APP" && npm exec -- wrangler deploy)
echo "DEPLOYED $APP (approved by $LOCAL_DEPLOY_APPROVED_BY). Verify the Worker before closing out."
