#!/usr/bin/env bash
# Start digikey, digiquant, digisearch, digitrace, digigraph (+ optional LiteLLM) on the same ports as Docker Compose
# (8005 digikey, 8000–8003, 4000). No containers. digichat: `make digichat-dev`.
#
# Prerequisites (repo-root .venv recommended):
#   pip install -e ./digibase \
#     -e ./digikey \
#     -e "./digiquant[nautilus]" \
#     -e ./digillm \
#     -e "./digigraph[dev]" \
#     -e ./digisearch \
#     -e "./digitrace[tracing]"
# Optional: pip install 'litellm[proxy]'  (or set OPENAI_API_BASE in .env to a real OpenAI-compatible URL)
#
# Usage: ./scripts/run_stack_local.sh
# Stop:  ./scripts/stop_stack_local.sh
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
PIDFILE="$ROOT/.local_stack_pids"
LLM_PORT="${LLM_PORT:-4000}"
PORT_QUANT="${PORT_QUANT:-8001}"
PORT_SEARCH="${PORT_SEARCH:-8002}"
PORT_SMITH="${PORT_SMITH:-8003}"
PORT_GRAPH="${PORT_GRAPH:-8000}"
PORT_DK="${PORT_DK:-8005}"
PORT_D1API="${PORT_D1API:-8787}"

if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

# Prefer venv interpreter + ``python -m uvicorn`` (avoids broken shebangs on relocated venvs).
if [ -x "${ROOT}/.venv/bin/python3" ]; then
  PYTHON="${ROOT}/.venv/bin/python3"
elif [ -x "${ROOT}/.venv/bin/python" ]; then
  PYTHON="${ROOT}/.venv/bin/python"
else
  PYTHON="python3"
fi

PYTHONPATH="${ROOT}/digibase/src:${ROOT}/digikey/src:${ROOT}/digiquant/src:${ROOT}/digigraph/src:${ROOT}/digisearch/src:${ROOT}/digitrace/src:${ROOT}"
export PYTHONPATH

DATA_DIR="${DIGIQUANT_DATA_DIR:-$ROOT/digiquant/data}"
export DIGIQUANT_DATA_DIR="$DATA_DIR"
mkdir -p "$DATA_DIR"
if [ -z "$(ls -A "$DATA_DIR"/*.csv 2>/dev/null || true)" ]; then
  echo "No CSV in $DATA_DIR — creating tiny synthetic OHLCV sample..."
  "$PYTHON" -c "
from pathlib import Path
import os
from digiquant.data.loader import generate_synthetic_ohlcv
d = Path(os.environ['DIGIQUANT_DATA_DIR'])
for s in ['AAPL','MSFT','GOOGL','NVDA','META']:
    generate_synthetic_ohlcv([s], freq='1d').write_csv(d / f'{s}.csv')
" || { echo "Failed: install digiquant in .venv first."; exit 1; }
fi

for p in "$PORT_DK" "$PORT_QUANT" "$PORT_SEARCH" "$PORT_SMITH" "$PORT_GRAPH" "$PORT_D1API"; do
  if lsof -i ":$p" -t >/dev/null 2>&1; then
    echo "Port $p is already in use. Stop that process or set PORT_* overrides."
    lsof -i ":$p" 2>/dev/null | head -3
    exit 1
  fi
done

rm -f "$PIDFILE"
append_pid() { echo "$1" >> "$PIDFILE"; }

export DIGIKEY_DATABASE_URL="${DIGIKEY_DATABASE_URL:-sqlite:///${ROOT}/.local_digikey.sqlite}"
# dev only: host-native stack has no Redis blocklist and no stable PEM, so opt in
# explicitly rather than relying on the (now prod-safe) Compose defaults.
export DIGIKEY_ALLOW_EPHEMERAL_KEY="${DIGIKEY_ALLOW_EPHEMERAL_KEY:-1}"
export DIGIKEY_REQUIRE_BLOCKLIST="${DIGIKEY_REQUIRE_BLOCKLIST:-0}"
export DIGIKEY_ALLOW_DEV_GLOBAL="${DIGIKEY_ALLOW_DEV_GLOBAL:-1}"
echo "Starting digikey on http://127.0.0.1:${PORT_DK} ..."
"$PYTHON" -m uvicorn digikey.server:app --host 127.0.0.1 --port "$PORT_DK" &
append_pid $!
sleep 2
if ! curl -sf "http://127.0.0.1:${PORT_DK}/health" >/dev/null; then
  echo "digikey health failed. PIDs in $PIDFILE — ./scripts/stop_stack_local.sh"
  exit 1
fi

export DIGIKEY_JWKS_URL="http://127.0.0.1:${PORT_DK}/.well-known/jwks.json"
export DIGIKEY_ISSUER="${DIGIKEY_ISSUER:-http://127.0.0.1:${PORT_DK}}"
export DIGIKEY_AUDIENCE="${DIGIKEY_AUDIENCE:-digi-ecosystem}"

if curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null 2>&1; then
  echo "LiteLLM already healthy on http://127.0.0.1:${LLM_PORT}"
else
  if command -v litellm >/dev/null 2>&1; then
    if lsof -i ":$LLM_PORT" -t >/dev/null 2>&1; then
      echo "Port $LLM_PORT is in use but not healthy as LiteLLM. Free it or set LLM_PORT."
      exit 1
    fi
    echo "Starting LiteLLM on http://127.0.0.1:${LLM_PORT} ..."
    (
      cd "$ROOT"
      export CONFIG_FILE_PATH="$ROOT/config/litellm.yaml"
      litellm --config "$ROOT/config/litellm.yaml" --port "$LLM_PORT" \
        >>"$ROOT/.litellm-local.log" 2>&1
    ) &
    append_pid $!
    ok=0
    for _ in $(seq 1 45); do
      sleep 1
      if curl -sf "http://127.0.0.1:${LLM_PORT}/health" >/dev/null; then
        ok=1
        break
      fi
    done
    if [ "$ok" != 1 ]; then
      echo "LiteLLM did not become healthy (see .litellm-local.log). Set OPENAI_API_BASE in .env if you use another router."
    fi
  else
    echo "Note: litellm not in PATH. Set OPENAI_API_BASE in .env (e.g. https://api.openai.com/v1) or: pip install 'litellm[proxy]'"
  fi
fi

# .env may set OPENAI_API_BASE for Docker (host.docker.internal → Ollama on the Mac).
# This script runs Uvicorn on the host; that hostname often breaks LLM calls — use loopback.
case "${OPENAI_API_BASE:-}" in
  *host.docker.internal*)
    OPENAI_API_BASE="${OPENAI_API_BASE//host.docker.internal/127.0.0.1}"
    echo "Note: host-local stack — OPENAI_API_BASE uses 127.0.0.1 (not host.docker.internal): $OPENAI_API_BASE"
    ;;
esac

export OPENAI_API_BASE="${OPENAI_API_BASE:-http://127.0.0.1:${LLM_PORT}/v1}"
export DIGI_CONFIG_PATH="${DIGI_CONFIG_PATH:-$ROOT/config}"
export DIGI_ALLOWED_ORIGINS="${DIGI_ALLOWED_ORIGINS:-http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:8000}"
export DIGI_MODEL_MODES_FILE="${DIGI_MODEL_MODES_FILE:-model_modes.local.yaml}"
if [ -z "${CHROMA_PATH:-}" ]; then
  export DIGISEARCH_ALLOW_STUB="${DIGISEARCH_ALLOW_STUB:-1}"
fi

echo "Starting digiquant on http://127.0.0.1:${PORT_QUANT} ..."
env PYTHONPATH="$PYTHONPATH" DIGIQUANT_DATA_DIR="$DIGIQUANT_DATA_DIR" \
  DIGIKEY_JWKS_URL="$DIGIKEY_JWKS_URL" DIGIKEY_ISSUER="$DIGIKEY_ISSUER" DIGIKEY_AUDIENCE="$DIGIKEY_AUDIENCE" \
  "$PYTHON" -m uvicorn digiquant.server:app --host 127.0.0.1 --port "$PORT_QUANT" &
append_pid $!
sleep 1

echo "Starting digisearch on http://127.0.0.1:${PORT_SEARCH} ..."
env PYTHONPATH="$PYTHONPATH" \
  DIGIKEY_JWKS_URL="$DIGIKEY_JWKS_URL" DIGIKEY_ISSUER="$DIGIKEY_ISSUER" DIGIKEY_AUDIENCE="$DIGIKEY_AUDIENCE" \
  CHROMA_PATH="${CHROMA_PATH:-}" DIGISEARCH_ALLOW_STUB="${DIGISEARCH_ALLOW_STUB:-}" \
  "$PYTHON" -m uvicorn digisearch.server:app --host 127.0.0.1 --port "$PORT_SEARCH" &
append_pid $!
sleep 1

echo "Starting digitrace on http://127.0.0.1:${PORT_SMITH} ..."
env PYTHONPATH="$PYTHONPATH" \
  "$PYTHON" -m uvicorn digitrace.server:app --host 127.0.0.1 --port "$PORT_SMITH" &
append_pid $!
sleep 1

echo "Starting digigraph on http://127.0.0.1:${PORT_GRAPH} ..."
env PYTHONPATH="$PYTHONPATH" \
  DIGIQUANT_URL="http://127.0.0.1:${PORT_QUANT}" \
  DIGIQUANT_DATA_DIR="$DIGIQUANT_DATA_DIR" \
  DIGISEARCH_URL="http://127.0.0.1:${PORT_SEARCH}" \
  DIGITRACE_URL="http://127.0.0.1:${PORT_SMITH}" \
  OPENAI_API_BASE="$OPENAI_API_BASE" \
  DIGI_CONFIG_PATH="$DIGI_CONFIG_PATH" \
  DIGI_MODEL_MODES_FILE="$DIGI_MODEL_MODES_FILE" \
  DIGI_ALLOWED_ORIGINS="$DIGI_ALLOWED_ORIGINS" \
  DIGIKEY_JWKS_URL="$DIGIKEY_JWKS_URL" DIGIKEY_ISSUER="$DIGIKEY_ISSUER" DIGIKEY_AUDIENCE="$DIGIKEY_AUDIENCE" \
  LITELLM_PROXY_API_KEY="${LITELLM_PROXY_API_KEY:-}" \
  "$PYTHON" -m uvicorn digigraph.server:app --host 127.0.0.1 --port "$PORT_GRAPH" &
append_pid $!
sleep 2

# DIG-2901 (supabase exit 13): local dashboard-api on persisted local D1.
# Schema-only until ticket 0 (DIG-2888 snapshot) exists; seeded after.
# Local-only config (no prod bindings, no Supabase vars, never deployed).
D1_STARTED=0
D1_PERSIST_DIR="${D1_PERSIST_DIR:-$ROOT/.local_d1}"
SNAPSHOT_DIR="${SUPABASE_EXIT_SNAPSHOT_DIR:-$HOME/Backups/supabase-exit}"
if ! command -v wrangler >/dev/null 2>&1 && [ ! -x "$ROOT/apps/dashboard-api/node_modules/.bin/wrangler" ]; then
  echo "Note: wrangler not found — skipping local D1 dashboard-api (schema-only parity unavailable)."
  echo "  Install with: npm install --workspace dashboard-api (or npm i -g wrangler)"
else
  if [ -x "$ROOT/apps/dashboard-api/node_modules/.bin/wrangler" ]; then
    WRANGLER="$ROOT/apps/dashboard-api/node_modules/.bin/wrangler"
  else
    WRANGLER="wrangler"
  fi
  mkdir -p "$D1_PERSIST_DIR"
  echo "Starting dashboard-api (local D1, persist-to $D1_PERSIST_DIR) on http://127.0.0.1:${PORT_D1API} ..."
  (
    cd "$ROOT/apps/dashboard-api"
    "$WRANGLER" dev --config wrangler.local.toml --persist-to "$D1_PERSIST_DIR" \
      --port "$PORT_D1API" >>"$ROOT/.dashboard-api-local.log" 2>&1
  ) &
  append_pid $!
  D1_STARTED=1
  ok_d1=0
  for _ in $(seq 1 30); do
    sleep 1
    if curl -sf "http://127.0.0.1:${PORT_D1API}/healthz" >/dev/null; then
      ok_d1=1
      break
    fi
  done
  if [ "$ok_d1" != 1 ]; then
    echo "dashboard-api local did not become healthy (see .dashboard-api-local.log). Continuing without D1 parity."
    D1_STARTED=0
  elif ls "$SNAPSHOT_DIR"/*/d1-seed.sql >/dev/null 2>&1; then
    # Ticket 0 snapshot exists and ticket 5 (DIG-2893) produced a seed file:
    # apply it to the LOCAL db only. Never any other target.
    SEED_FILE="$(ls "$SNAPSHOT_DIR"/*/d1-seed.sql 2>/dev/null | head -1)"
    echo "Snapshot seed found ($SEED_FILE) — applying to LOCAL D1 only ..."
    (cd "$ROOT/apps/dashboard-api" && "$WRANGLER" d1 execute dashboard-local \
      --local --file "$SEED_FILE" >>"$ROOT/.dashboard-api-local.log" 2>&1) \
      || echo "Seed apply failed (see .dashboard-api-local.log). Local D1 stays schema-only."
  else
    echo "No snapshot seed in $SNAPSHOT_DIR — local D1 stays schema-only (ticket 0 pending)."
  fi
fi

ok=1
curl -sf "http://127.0.0.1:${PORT_QUANT}/health" >/dev/null || ok=0
curl -sf "http://127.0.0.1:${PORT_SEARCH}/health" >/dev/null || ok=0
curl -sf "http://127.0.0.1:${PORT_SMITH}/health" >/dev/null || ok=0
curl -sf "http://127.0.0.1:${PORT_GRAPH}/health" >/dev/null || ok=0
if [ "$D1_STARTED" = 1 ]; then
  curl -sf "http://127.0.0.1:${PORT_D1API}/healthz" >/dev/null || ok=0
fi

if [ "$ok" != 1 ]; then
  echo "Health check failed for one or more services. PIDs in $PIDFILE — run ./scripts/stop_stack_local.sh"
  exit 1
fi

echo ""
echo "Local stack is up (standard ports, no Docker)."
echo "  digikey:    http://127.0.0.1:${PORT_DK}/health  (issue keys: python -m digikey.cli issue-key ...)"
echo "  LiteLLM:    http://127.0.0.1:${LLM_PORT}/health   (OPENAI_API_BASE=$OPENAI_API_BASE)"
echo "  digiquant:  http://127.0.0.1:${PORT_QUANT}/health"
echo "  digisearch: http://127.0.0.1:${PORT_SEARCH}/health"
echo "  digitrace:  http://127.0.0.1:${PORT_SMITH}/health"
echo "  digigraph:  http://127.0.0.1:${PORT_GRAPH}/health"
echo "  dashboard-api (local D1, schema-only until ticket 0): http://127.0.0.1:${PORT_D1API}/healthz"
echo ""
echo "digichat (Next.js, hot reload):"
echo "  make digichat-dev"
echo "  See docs/LOCAL_STACK.md — set DIGIKEY_URL=http://127.0.0.1:${PORT_DK} , DIGIGRAPH_INTERNAL_URL=http://127.0.0.1:${PORT_GRAPH}"
echo ""
echo "Stop: ./scripts/stop_stack_local.sh"
