#!/bin/sh
# Profile A stack entrypoint — start supervisord immediately (ports must open).
# Cloudflare Containers probes :8000; blocking here causes error 1101 / port-not-ready.
# OCC Chroma seed runs as a supervisord oneshot *before* digisearch (see supervisord.conf).
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
DATA_VAULT="${DIGIVAULT_ROOT:-/data/vault}"

mkdir -p "$DATA_CHROMA" "$DATA_VAULT" /data/digikey /var/log/supervisor

# Stable digikey issuer defaults for CF custom domains (overridable via envVars).
export DIGIKEY_ISSUER="${DIGIKEY_ISSUER:-https://key.digithings.ai}"
export DIGIKEY_JWKS_URL="${DIGIKEY_JWKS_URL:-http://127.0.0.1:8005/.well-known/jwks.json}"
export DIGIVAULT_URL="${DIGIVAULT_URL:-http://127.0.0.1:8004}"
export DIGISEARCH_URL="${DIGISEARCH_URL:-http://127.0.0.1:8002}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-http://127.0.0.1:4000/v1}"
export DIGI_CONFIG_PATH="${DIGI_CONFIG_PATH:-/app/config}"
export CHROMA_PATH="$DATA_CHROMA"
export DIGIVAULT_ROOT="$DATA_VAULT"
export DIGIKEY_DATABASE_URL="${DIGIKEY_DATABASE_URL:-sqlite:////data/digikey.db}"
export DIGIKEY_BLOCKLIST_REDIS_URL="${DIGIKEY_BLOCKLIST_REDIS_URL:-redis://127.0.0.1:6379/0}"
export DIGIKEY_REQUIRE_BLOCKLIST="${DIGIKEY_REQUIRE_BLOCKLIST:-0}"
export PYTHONPATH="/app/digikey/src:/app/digigraph/src:/app/digisearch/src:/app/digivault/src:/app/digibase/src:/app/digillm/src:/app/digismith/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="/usr/local/bin:$PATH"

# Container envVars may mangle multiline PEMs — accept base64-wrapped secret.
if [ -n "${DIGIKEY_PRIVATE_KEY_PEM:-}" ] && ! printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | grep -q "BEGIN"; then
  DIGIKEY_PRIVATE_KEY_PEM=$(printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | base64 -d 2>/dev/null || true)
  export DIGIKEY_PRIVATE_KEY_PEM
fi
if [ -z "${DIGIKEY_PRIVATE_KEY_PEM:-}" ] || ! printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | grep -q "BEGIN"; then
  echo "digithings-stack: WARN DIGIKEY_PRIVATE_KEY_PEM missing/invalid; enabling ephemeral key for this boot"
  export DIGIKEY_ALLOW_EPHEMERAL_KEY=1
fi

# Copy OCC vault seed notes (idempotent — do not overwrite operator edits).
if [ -d /seed/vault/clients/online-compliance-center ]; then
  mkdir -p "$DATA_VAULT/clients/online-compliance-center"
  for f in /seed/vault/clients/online-compliance-center/*; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    dest="$DATA_VAULT/clients/online-compliance-center/$base"
    if [ ! -f "$dest" ]; then
      cp "$f" "$dest"
    fi
  done
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/digithings.conf
