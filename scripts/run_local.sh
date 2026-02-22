#!/usr/bin/env bash
# Start DigiQuant and DigiGraph locally on dedicated ports (no conflict with Docker 8000/8001).
# Run from repo root. Requires: .venv with digiquant[nautilus] + test data (run fetch_nautilus_test_data.py once).
# For LLM: set OPENAI_API_BASE and OPENAI_API_KEY in .env, or run LiteLLM separately on 4000.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
PYTHONPATH="${ROOT}/digiquant/src:${ROOT}/digigraph/src:${ROOT}"
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

# Ensure Nautilus test data exists (so backtest returns real results, not 503)
if [ -x "$ROOT/.venv/bin/python" ]; then
  "$ROOT/.venv/bin/python" -c "from nautilus_trader.test_kit.providers import TestDataProvider; p = TestDataProvider(); assert p.read_csv_ticks('binance/ethusdt-trades.csv') is not None" 2>/dev/null || {
    echo "Nautilus test data missing. Run: $ROOT/.venv/bin/python digiquant/scripts/fetch_nautilus_test_data.py"
    exit 1
  }
fi

# Avoid "address already in use"
for port in "$DQ_PORT" "$DG_PORT"; do
  if lsof -i :$port -t >/dev/null 2>&1; then
    echo "Port $port is in use. Stop the process using it or set DQ_PORT/DG_PORT and try again."
    lsof -i :$port 2>/dev/null | head -3
    exit 1
  fi
done

echo "Starting DigiQuant on http://127.0.0.1:$DQ_PORT ..."
env PYTHONPATH="$PYTHONPATH" $UVICORN digiquant.server:app --host 127.0.0.1 --port "$DQ_PORT" &
DQ_PID=$!
sleep 1
echo "Starting DigiGraph on http://127.0.0.1:$DG_PORT ..."
env PYTHONPATH="$PYTHONPATH" DIGIQUANT_URL="http://127.0.0.1:$DQ_PORT" $UVICORN digigraph.server:app --host 127.0.0.1 --port "$DG_PORT" &
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
    echo "Test workflow:"
    echo "  curl -s -X POST http://127.0.0.1:$DG_PORT/workflow -H 'Content-Type: application/json' -d '{\"prompt\":\"Build me a mean-reversion stat-arb on tech\",\"session_id\":\"local\"}' | python3 -m json.tool"
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
