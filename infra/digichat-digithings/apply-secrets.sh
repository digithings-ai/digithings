#!/usr/bin/env bash
# Rotate digithings DigiChat ACA secrets + env. Never prints secret values.
set -euo pipefail

: "${AUTH_SECRET:?set AUTH_SECRET}"
: "${DIGITHINGS_SUPABASE_URL:?set DIGITHINGS_SUPABASE_URL}"
: "${DIGITHINGS_SUPABASE_ANON_KEY:?set DIGITHINGS_SUPABASE_ANON_KEY}"
: "${DIGITHINGS_OPENROUTER_API_KEY:?set DIGITHINGS_OPENROUTER_API_KEY}"

APP="${ACA_NAME:-digichat}"
RG="${ACA_RG:-digithings-rg}"
PUBLIC_ORIGIN="${AUTH_URL:-https://chat.digithings.ai}"

EMBED_TOKEN="${DIGICHAT_EMBED_TOKEN:-$(openssl rand -hex 32)}"
export EMBED_TOKEN

TENANTS=$(python3 - <<'PY'
import json, os
print(json.dumps({
  "digithings.ai": {
    "slug": "digithings",
    "aliases": ["www.digithings.ai"],
    "gateMode": "ungated",
    "showByok": True,
    "showStatusBar": True,
    "layout": "page",
    "activityDetail": "full",
    "attribution": False,
    "token": os.environ["EMBED_TOKEN"],
    "backend": {
      "type": "digivault",
      "supabaseUrlEnv": "DIGITHINGS_SUPABASE_URL",
      "supabaseAnonKeyEnv": "DIGITHINGS_SUPABASE_ANON_KEY",
      "openRouterKeyEnv": "DIGITHINGS_OPENROUTER_API_KEY",
    },
  }
}))
PY
)

az containerapp secret set \
  --name "$APP" \
  --resource-group "$RG" \
  --secrets \
    "auth-secret=${AUTH_SECRET}" \
    "embed-tenants=${TENANTS}" \
    "digithings-supabase-url=${DIGITHINGS_SUPABASE_URL}" \
    "digithings-supabase-anon-key=${DIGITHINGS_SUPABASE_ANON_KEY}" \
    "digithings-openrouter-api-key=${DIGITHINGS_OPENROUTER_API_KEY}" \
  --output none

az containerapp update \
  --name "$APP" \
  --resource-group "$RG" \
  --set-env-vars \
    "AUTH_SECRET=secretref:auth-secret" \
    "AUTH_URL=${PUBLIC_ORIGIN}" \
    "DIGICHAT_EMBED_ENABLED=1" \
    "DIGICHAT_EMBED_TENANTS=secretref:embed-tenants" \
    "DIGITHINGS_SUPABASE_URL=secretref:digithings-supabase-url" \
    "DIGITHINGS_SUPABASE_ANON_KEY=secretref:digithings-supabase-anon-key" \
    "DIGITHINGS_OPENROUTER_API_KEY=secretref:digithings-openrouter-api-key" \
  --output none

echo "Secrets applied on ${APP} (${RG}). AUTH_URL=${PUBLIC_ORIGIN}"
echo "Schema token rotated (not printed). Export DIGICHAT_EMBED_TOKEN to keep a fixed value."
