#!/bin/sh
# Profile A stack entrypoint — start supervisord immediately (ports must open).
# Cloudflare Containers probes :8000; blocking here causes error 1101 / port-not-ready.
# Chroma seed (digithings_docs + occ_help) runs as a supervisord oneshot *before*
# digisearch (see supervisord.conf / seed_chroma.sh).
#
# CRITICAL (Firecracker): supervisord must log to files, NOT /dev/stdout — ENXIO otherwise.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
DATA_VAULT="${DIGIVAULT_ROOT:-/data/vault}"

mkdir -p "$DATA_CHROMA" "$DATA_VAULT" /data/digikey /var/log/supervisor

# Stable digikey issuer defaults for CF custom domains (overridable via envVars).
export DIGIKEY_ISSUER="${DIGIKEY_ISSUER:-https://key.digithings.ai}"
export DIGIKEY_JWKS_URL="${DIGIKEY_JWKS_URL:-http://127.0.0.1:8005/.well-known/jwks.json}"
export DIGIVAULT_URL="${DIGIVAULT_URL:-http://127.0.0.1:8004}"
export DIGISEARCH_URL="${DIGISEARCH_URL:-http://127.0.0.1:8002}"
# Chat-only: never default digiquant URL (would trigger backtest_node / DATA_DIR errors).
export DIGIQUANT_URL="${DIGIQUANT_URL:-}"
export DIGISMITH_URL="${DIGISMITH_URL:-}"
export OPENAI_API_BASE="${OPENAI_API_BASE:-http://127.0.0.1:4000/v1}"
export DIGI_CONFIG_PATH="${DIGI_CONFIG_PATH:-/app/config}"
export DIGI_PROJECT_CONFIG="${DIGI_PROJECT_CONFIG:-/app/config/digiproject.yaml}"
export DIGI_WORKFLOW_PROFILE="${DIGI_WORKFLOW_PROFILE:-research_rag}"
export DIGI_ALLOWED_TOOLS="${DIGI_ALLOWED_TOOLS:-digisearch,digivault_search_notes}"
# "Is Vectorize configured?" must agree with digisearch's own Python check
# (os.environ.get(name, "").strip() truthiness, see
# digisearch/src/digisearch/search/_stub.py) byte-for-byte, or one side
# silently falls through to an also-unconfigured Chroma and serves empty
# results with no error (see issue discussion). A sed [[:space:]] rewrite
# can only ever *approximate* str.strip() -- it is ASCII-whitespace-only
# (or locale-dependent in ways that still don't match Python's Unicode
# whitespace table, e.g. U+00A0 NBSP survives sed's trim but not Python's),
# so the decision is delegated to python3 itself (already invoked below for
# PEM validation), which makes the two checks identical by construction
# instead of by approximation.
#
# Fail closed: if the python3 invocation errors, treat Vectorize as NOT
# configured -- the same "unconfigured" default this script has always had
# -- rather than risk skipping the Chroma seed on a value we could not
# actually evaluate.
if _digi_vectorize_check=$(python3 -c '
import os

account = os.environ.get("VECTORIZE_ACCOUNT_ID", "").strip()
token = os.environ.get("VECTORIZE_API_TOKEN", "").strip()
print("1" if (account and token) else "0")
' 2>/dev/null) && [ "$_digi_vectorize_check" = "1" ]; then
  DIGI_VECTORIZE_ACTIVE=1
else
  DIGI_VECTORIZE_ACTIVE=0
fi
# Computed once here and exported so seed_chroma.sh / start_digisearch.sh
# (both launched by supervisord below) read the same verdict instead of
# re-deriving it and risking drift between the three scripts.
export DIGI_VECTORIZE_ACTIVE

# Vectorize is a remote index: exporting CHROMA_PATH would make _stub.py's
# Chroma branch win and answer from an empty local index instead.
if [ "$DIGI_VECTORIZE_ACTIVE" = "1" ]; then
  unset CHROMA_PATH
  echo "digithings-stack: Vectorize configured; skipping local chroma"
else
  export CHROMA_PATH="$DATA_CHROMA"
fi
export DIGIVAULT_ROOT="$DATA_VAULT"
# D1 is selected by presence (digivault/src/digivault/server.py) -- all three
# must be non-empty for the D1 backend to be preferred over DIGIVAULT_ROOT.
export D1_ACCOUNT_ID="${D1_ACCOUNT_ID:-}"
export D1_API_TOKEN="${D1_API_TOKEN:-}"
export D1_DATABASE_MAP="${D1_DATABASE_MAP:-}"
export DIGIKEY_DATABASE_URL="${DIGIKEY_DATABASE_URL:-sqlite:////data/digikey.db}"
export DIGIKEY_BLOCKLIST_REDIS_URL="${DIGIKEY_BLOCKLIST_REDIS_URL:-redis://127.0.0.1:6379/0}"
export DIGIKEY_REQUIRE_BLOCKLIST="${DIGIKEY_REQUIRE_BLOCKLIST:-0}"
export PYTHONPATH="/app/digikey/src:/app/digigraph/src:/app/digisearch/src:/app/digivault/src:/app/digibase/src:/app/digillm/src:/app/digismith/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="/usr/local/bin:$PATH"

# Container envVars may mangle multiline PEMs — accept base64-wrapped secret,
# and expand literal \n sequences from secret stores.
if [ -n "${DIGIKEY_PRIVATE_KEY_PEM:-}" ] && ! printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | grep -q "BEGIN"; then
  DIGIKEY_PRIVATE_KEY_PEM=$(printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | base64 -d 2>/dev/null || true)
  export DIGIKEY_PRIVATE_KEY_PEM
fi
if [ -n "${DIGIKEY_PRIVATE_KEY_PEM:-}" ] && printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | grep -q '\\n'; then
  DIGIKEY_PRIVATE_KEY_PEM=$(printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | sed 's/\\n/\
/g')
  export DIGIKEY_PRIVATE_KEY_PEM
fi

# Validate PEM with cryptography; CF secrets often look like PEM but fail to deserialize.
pem_ok=0
if [ -n "${DIGIKEY_PRIVATE_KEY_PEM:-}" ] && printf '%s' "$DIGIKEY_PRIVATE_KEY_PEM" | grep -q "BEGIN"; then
  if python3 -c "from cryptography.hazmat.primitives.serialization import load_pem_private_key; load_pem_private_key(__import__('os').environ['DIGIKEY_PRIVATE_KEY_PEM'].encode(), password=None)" 2>/dev/null; then
    pem_ok=1
  fi
fi
if [ "$pem_ok" -ne 1 ]; then
  unset DIGIKEY_PRIVATE_KEY_PEM
  # Respect DIGIKEY_ALLOW_EPHEMERAL_KEY from wrangler/compose — never force
  # ephemeral when prod vars set ALLOW=0 (silent RS256 rotation on bad PEM).
  if [ "${DIGIKEY_ALLOW_EPHEMERAL_KEY:-0}" = "1" ]; then
    echo "digithings-stack: WARN DIGIKEY_PRIVATE_KEY_PEM missing/invalid; ephemeral key allowed for this boot"
  else
    echo "digithings-stack: ERROR DIGIKEY_PRIVATE_KEY_PEM missing/invalid and DIGIKEY_ALLOW_EPHEMERAL_KEY!=1; digikey will fail closed"
  fi
fi

# Copy vault seed notes. Files named seed-*.md are always refreshed from the
# image (dogfood corpus). Other filenames are copied only if missing so
# operator / docs_onboard notes are never overwritten.
for client_dir in /seed/vault/clients/*; do
  [ -d "$client_dir" ] || continue
  client=$(basename "$client_dir")
  mkdir -p "$DATA_VAULT/clients/$client"
  for f in "$client_dir"/*; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    dest="$DATA_VAULT/clients/$client/$base"
    case "$base" in
      seed-*.md|seed-*.markdown)
        cp "$f" "$dest"
        ;;
      *)
        if [ ! -f "$dest" ]; then
          cp "$f" "$dest"
        fi
        ;;
    esac
  done
done

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/digithings.conf
