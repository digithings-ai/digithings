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

# DIG-3701: a container image build COPYs from image-packages/ (gitignored),
# so the docker build fails "failed to compute cache key ... not found" unless
# this ran first. Neither this script nor the (disabled) CI lane did it, which
# is how digiquant-runner stayed on its 2026-10-01 image while every gate
# stayed green. Never-again step, not an optimisation.
if grep -q '^\[\[containers\]\]' "apps/$APP/wrangler.toml"; then
  if [ -d image-packages ]; then
    echo "--- image inputs present ($(find image-packages -type f 2>/dev/null | wc -l | tr -d ' ') files) — verifying they match the sources ---"
    # DIG-4423: the directory existing is not evidence that it is current. On
    # 2026-10-18 a digigraph/src-only change deployed green three times while the
    # packaged digigraph wheel was dated the previous day and contained none of
    # the change. The check is content-based on purpose — checkout stamps every
    # source mtime with "now", so an mtime rule would refuse a clean tree and
    # force a repackage (see the layer-digest note below).
    if ! python3 scripts/package_r5_image_inputs.py --check-only; then
      echo "ABORT: image-packages/ does not match the packaged sources (drift above)."
      echo "  Deploying now would build an image around stale wheels/npm packages."
      echo "  Fix, then re-run this deploy:"
      echo "    rm -rf image-packages && python3 scripts/package_r5_image_inputs.py"
      exit 1
    fi
    echo "--- skipping packaging ---"
    echo "    Packaging rewrites file mtimes, which changes the container image layer"
    echo "    digests; a retry would then re-upload ~8 layers instead of finding them"
    echo "    already in the registry. Delete image-packages/ to force a rebuild."
  else
    echo "--- packaging image inputs (scripts/package_r5_image_inputs.py) ---"
    python3 scripts/package_r5_image_inputs.py
  fi
fi

# Local Docker gate (Chris, 2026-10-18): build the container image HERE first, so
# a broken image -- a missing packaged dependency, a bad COPY -- fails in a minute
# locally instead of after a full Cloudflare deploy attempt. This is not theoretical:
# on 2026-10-18 the digichat dry run passed (28 tests, clean typecheck) and the live
# deploy then died inside `next build` because packages/ui had gained an import of
# @digithings/hero-banner that the image never packaged.
# The deploy then rebuilds the same Dockerfile and Docker reuses these layers,
# so the gate costs seconds.
# NOTE: this must be `docker build`, NOT `wrangler containers build` -- that command
# requires a file literally named `Dockerfile` inside its PATH argument, and these
# images live under `infra/docker/` as `Dockerfile.<app>`.
if grep -q '^\[\[containers\]\]' "apps/$APP/wrangler.toml"; then
  img=$(sed -n 's/^[[:space:]]*image[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "apps/$APP/wrangler.toml" | head -1)
  ctx=$(sed -n 's/^[[:space:]]*image_build_context[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' "apps/$APP/wrangler.toml" | head -1)
  [ -n "$img" ] || { echo "ABORT: [[containers]] declared but no image path in apps/$APP/wrangler.toml"; exit 1; }
  [ -n "$ctx" ] || ctx=$(dirname "$img")
  echo "--- local image build gate: docker build -f $img $ctx (from apps/$APP) ---"
  ( cd "apps/$APP" && "${DOCKER_BIN:-/usr/local/bin/docker}" build -f "$img" -t "local-gate-$APP:latest" "$ctx" )
  echo "--- local image build gate PASSED ($APP) ---"
fi

# DIG-3229: prefer the app's OWN deploy script when it defines one.
# digithings-stack-cloudflare deploys via `node scripts/deploy.mjs`, which injects
# --var STACK_CONTAINER_REV:<commit> and then verifies /_stack/meta reports the id
# that commit implies. Deploying it with a bare command still serves traffic but
# ships the LEGACY container id (shared-v18) and cannot guarantee eviction.
if node -e "process.exit(require('./apps/$APP/package.json').scripts && require('./apps/$APP/package.json').scripts.deploy ? 0 : 1)" 2>/dev/null; then
  echo "--- using apps/$APP's own deploy script (pins the container id) ---"
  npm run deploy --workspace "$PKG"
else
  (cd "apps/$APP" && npm exec -- wrangler deploy)
fi
echo "DEPLOYED $APP (approved by $LOCAL_DEPLOY_APPROVED_BY). Verify the Worker before closing out."
