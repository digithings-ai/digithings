#!/usr/bin/env bash
# Local previews for Surfaces 1.0 review. Canonical list: docs/surfaces/surfaces.md.
# The digiquant app is the Brief desk at /app on the digiquant site (/app/brief
# redirects to /app). There is no separate digiquant app server any more.
#
# Usage: scripts/preview_surfaces.sh            # start everything
#        DASHBOARD_API_SUPABASE_URL=... DASHBOARD_API_SUPABASE_KEY=... scripts/preview_surfaces.sh
#          (point the local data API at a local PostgREST, e.g. a restored snapshot;
#           unset = stub doubles, see apps/dashboard-api/wrangler.local.toml)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${PREVIEW_LOG_DIR:-$ROOT/.preview-logs}"
mkdir -p "$LOG"

start() { # name dir cmd...
  local name=$1 dir=$2; shift 2
  (cd "$dir" && nohup "$@" >"$LOG/$name.log" 2>&1 &)
}

VARS=()
if [ -n "${DASHBOARD_API_SUPABASE_URL:-}" ]; then
  VARS=(--var "SUPABASE_URL:${DASHBOARD_API_SUPABASE_URL}" --var "SUPABASE_SERVICE_ROLE_KEY:${DASHBOARD_API_SUPABASE_KEY:-}")
fi
start dashboard-api "$ROOT/apps/dashboard-api" npx wrangler dev --config wrangler.local.toml \
  --persist-to "$ROOT/.local_d1" --port 8788 "${VARS[@]}"
start digiquant-web  "$ROOT/apps/digiquant-web"  npx next dev --hostname 127.0.0.1 -p 4020
start digichat       "$ROOT/apps/digichat"       npx next dev --hostname 127.0.0.1 -p 3000
start digithings-web "$ROOT/apps/digithings-web" npx next dev --hostname 127.0.0.1 -p 4040
start design         "$ROOT/packages/design"     python3 -m http.server 4030 --bind 127.0.0.1

cat <<LINKS
digithings site      http://localhost:4040/
digiquant site       http://localhost:4020/
digiquant app (Brief desk)  http://localhost:4020/app   (press ? for shortcuts)
digichat             http://localhost:3000/
design kit           http://localhost:4030/
data API (local)     http://localhost:8788/healthz
logs: $LOG
LINKS
