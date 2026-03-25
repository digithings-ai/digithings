#!/usr/bin/env bash
# Start DigiQuant and DigiGraph locally on 18001 / 18000 (avoids Docker ports 8000/8001).
# For all services on standard ports 8000–8003 + LiteLLM 4000, use: ./scripts/run_stack_local.sh (or make stack-local)
# Run from repo root. Requires: .venv with digiquant[nautilus] + test data (run fetch_nautilus_test_data.py once).
# For LLM: set OPENAI_API_BASE and OPENAI_API_KEY in .env (and LITELLM_PROXY_API_KEY if LiteLLM uses LITELLM_MASTER_KEY), or run LiteLLM separately on 4000.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHONPATH="${ROOT}/digibase/src:${ROOT}/digiquant/src:${ROOT}/digigraph/src:${ROOT}/digismith/src:${ROOT}"
export PYTHONPATH

# Local-only ports (Docker uses 8000/8001)
DQ_PORT="${DQ_PORT:-18001}"
DG_PORT="${DG_PORT:-18000}"

# Prefer venv if present
if [ -x "${ROOT}/.venv/bin/uvicorn" ]; then
  UVICORN="${ROOT}/.venv/bin/uvicorn"
else
  UVICORN="python3 -m uvicorn"
fi

# Ensure OHLCV data dir exists (backtest requires data_path or data_dir)
DATA_DIR="${DATA_DIR:-$ROOT/digiquant/data}"
if [ ! -d "$DATA_DIR" ] || [ -z "$(ls -A "$DATA_DIR"/*.csv 2>/dev/null)" ]; then
  echo "Creating sample OHLCV data in $DATA_DIR ..."
  mkdir -p "$DATA_DIR"
  (cd "$ROOT" && PYTHONPATH="$PYTHONPATH" DIGIQUANT_DATA_DIR="$DATA_DIR" "$ROOT/.venv/bin/python" -c "
import os
from pathlib import Path
from digiquant.data.loader import generate_synthetic_ohlcv
d = Path(os.environ['DIGIQUANT_DATA_DIR'])
for s in ['AAPL','MSFT','GOOGL','NVDA','META']:
  generate_synthetic_ohlcv([s], freq='1d').write_csv(d / f'{s}.csv')
") 2>/dev/null || { echo "Failed to create sample data. Ensure .venv has digiquant."; exit 1; }
fi
export DIGIQUANT_DATA_DIR="$DATA_DIR"

# DigiGraph/DigiQuant require DigiKey JWT verification in production; for local runs point at DigiKey
# (same as Compose: http://127.0.0.1:8005) and send Authorization: Bearer <JWT> on API calls.
export DIGIKEY_JWKS_URL="${DIGIKEY_JWKS_URL:-http://127.0.0.1:8005/.well-known/jwks.json}"
export DIGIKEY_ISSUER="${DIGIKEY_ISSUER:-http://127.0.0.1:8005}"
export DIGIKEY_AUDIENCE="${DIGIKEY_AUDIENCE:-digi-ecosystem}"

# Avoid "address already in use"
for port in "$DQ_PORT" "$DG_PORT"; do
  if lsof -i :$port -t >/dev/null 2>&1; then
    echo "Port $port is in use. Stop the process using it or set DQ_PORT/DG_PORT and try again."
    lsof -i :$port 2>/dev/null | head -3
    exit 1
  fi
done

echo "Starting DigiQuant on http://127.0.0.1:$DQ_PORT (data: $DIGIQUANT_DATA_DIR) ..."
env PYTHONPATH="$PYTHONPATH" DIGIQUANT_DATA_DIR="$DIGIQUANT_DATA_DIR" \
  DIGIKEY_JWKS_URL="$DIGIKEY_JWKS_URL" DIGIKEY_ISSUER="$DIGIKEY_ISSUER" DIGIKEY_AUDIENCE="$DIGIKEY_AUDIENCE" \
  $UVICORN digiquant.server:app --host 127.0.0.1 --port "$DQ_PORT" &
DQ_PID=$!
sleep 1
echo "Starting DigiGraph on http://127.0.0.1:$DG_PORT ..."
env PYTHONPATH="$PYTHONPATH" DIGIQUANT_URL="http://127.0.0.1:$DQ_PORT" DIGIQUANT_DATA_DIR="$DIGIQUANT_DATA_DIR" \
  DIGIKEY_JWKS_URL="$DIGIKEY_JWKS_URL" DIGIKEY_ISSUER="$DIGIKEY_ISSUER" DIGIKEY_AUDIENCE="$DIGIKEY_AUDIENCE" \
  $UVICORN digigraph.server:app --host 127.0.0.1 --port "$DG_PORT" &
DG_PID=$!

# Wait for health
for i in 1 2 3 4 5; do
  sleep 1
  if curl -sf "http://127.0.0.1:$DQ_PORT/health" >/dev/null && curl -sf "http://127.0.0.1:$DG_PORT/health" >/dev/null; then
    echo ""
    echo "Local stack is up (local-only ports, no Docker conflict)."
    echo "  DigiQuant: http://127.0.0.1:$DQ_PORT"
    echo "  DigiGraph: http://127.0.0.1:$DG_PORT"
    echo ""
    echo "Ensure DigiKey is running (e.g. http://127.0.0.1:8005) and obtain a JWT; then test workflow:"
    echo "  curl -s -X POST http://127.0.0.1:$DG_PORT/workflow -H \"Authorization: Bearer \$JWT\" -H 'Content-Type: application/json' -d '{\"prompt\":\"Build me a mean-reversion stat-arb on tech\",\"session_id\":\"local\"}' | python3 -m json.tool"
    echo ""
    echo "Run e2e against local stack: DIGIGRAPH_URL=http://127.0.0.1:$DG_PORT DIGIQUANT_URL=http://127.0.0.1:$DQ_PORT pytest tests/test_e2e.py -v -m e2e"
    echo ""
    echo "To stop: kill $DQ_PID $DG_PID"
    exit 0
  fi
done
kill $DQ_PID $DG_PID 2>/dev/null || true
echo "Health check failed. Check logs above."
exit 1
