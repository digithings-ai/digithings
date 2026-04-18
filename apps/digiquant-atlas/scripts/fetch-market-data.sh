#!/bin/bash
# fetch-market-data.sh — Run both fetch scripts and validate scratch JSON
# Fetches quotes (technicals) and macro data (yield curve, VIX, FX) for a given date.
# Both scripts are free / no API keys — all yfinance + US Treasury public XML.
#
# Usage:
#   ./scripts/fetch-market-data.sh              # today
#   ./scripts/fetch-market-data.sh 2026-04-06   # specific date
#   ./scripts/fetch-market-data.sh --preload    # force full 2yr cache rebuild
#
# Scratch files (gitignored, under data/agent-cache/daily/YYYY-MM-DD/data/):
#   quotes.json         quotes-summary.md
#   macro.json          macro-summary.md

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATE="${1:-$(date +%Y-%m-%d)}"
DATA_DIR="$REPO_ROOT/data/agent-cache/daily/$DATE/data"
CACHE_DIR="$REPO_ROOT/data/price-history"

# ── flags ────────────────────────────────────────────────────────────────────
PRELOAD=false
for arg in "$@"; do
    case "$arg" in
        --preload) PRELOAD=true ;;
    esac
done

# ── Python resolution: prefer venv with yfinance/pandas-ta ───────────────────
# Check common locations in order:
#   1. DIGIQUANT_PYTHON env var (user override)
#   2. Local .venv in this repo
#   3. ../digithings/.venv (companion repo with data science packages)
#   4. System python3
if [ -n "${DIGIQUANT_PYTHON:-}" ]; then
    PYTHON="$DIGIQUANT_PYTHON"
elif [ -x "$REPO_ROOT/.venv/bin/python3" ] && "$REPO_ROOT/.venv/bin/python3" -c "import yfinance" 2>/dev/null; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
elif [ -x "$(dirname "$REPO_ROOT")/digithings/.venv/bin/python3" ]; then
    PYTHON="$(dirname "$REPO_ROOT")/digithings/.venv/bin/python3"
else
    PYTHON="python3"
fi

echo "╔════════════════════════════════════════════╗"
echo "║  fetch-market-data.sh — $DATE  ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "  Python: $PYTHON"
echo ""

# ── dependency check ─────────────────────────────────────────────────────────
echo "[ Checking dependencies ]"
"$PYTHON" -c "import yfinance" 2>/dev/null || {
    echo "  ⚠️  yfinance not found in $PYTHON"
    echo "       Run: pip install -r requirements.txt  (or set DIGIQUANT_PYTHON=...)"
    echo ""
    echo "  💡 Sandbox/CI alternative: Use MCP-based data fetch instead."
    echo "     Follow skills/mcp-data-fetch/SKILL.md to fetch data via FRED, Alpha Vantage,"
    echo "     CoinGecko, and Frankfurter MCP tools."
    exit 1
}
"$PYTHON" -c "import pandas_ta" 2>/dev/null || {
    echo "  ⚠️  pandas-ta not found in $PYTHON"
    echo "       Run: pip install pandas-ta  (or set DIGIQUANT_PYTHON=...)"
    echo ""
    echo "  💡 Sandbox/CI alternative: Use MCP-based data fetch instead."
    echo "     Follow skills/mcp-data-fetch/SKILL.md"
    exit 1
}
"$PYTHON" -c "import requests" 2>/dev/null || {
    echo "  ⚠️  requests not found in $PYTHON"
    echo "       Run: pip install requests"
    exit 1
}
echo "  ✅ Dependencies OK"
echo ""

# ── ensure daily folder exists ───────────────────────────────────────────────
mkdir -p "$DATA_DIR"

# ── price-history cache ──────────────────────────────────────────────────────
# If --preload flag set, or cache dir is empty/missing, run preload-history.py
# to seed the per-ticker CSV cache. Daily runs then only fetch latest quotes.
if [ "$PRELOAD" = true ]; then
    echo "[ Pre-flight: Preloading price history cache (--preload) ]"
    "$PYTHON" scripts/preload-history.py --period 2y
    echo ""
elif [ ! -d "$CACHE_DIR" ] || [ -z "$(ls -A "$CACHE_DIR" 2>/dev/null)" ]; then
    echo "[ Pre-flight: No price-history cache found — running initial preload (2y) ]"
    "$PYTHON" scripts/preload-history.py --period 2y
    echo ""
else
    CACHE_COUNT=$(ls "$CACHE_DIR"/*.csv 2>/dev/null | wc -l | tr -d ' ')
    echo "  Price-history cache: $CACHE_COUNT tickers cached in data/price-history/"
fi
echo ""

# ── fetch quotes ─────────────────────────────────────────────────────────────
echo "[ Phase 1/2: Quotes + Technicals ]"
cd "$REPO_ROOT"
"$PYTHON" scripts/fetch-quotes.py "$DATE"
echo ""

# ── fetch macro ──────────────────────────────────────────────────────────────
echo "[ Phase 2/2: Macro Data (Yield Curve, VIX, FX, Commodities, Crypto) ]"
"$PYTHON" scripts/fetch-macro.py "$DATE"
echo ""

# ── validate scratch files ───────────────────────────────────────────────────
echo "[ Validation ]"
ERRORS=0

for FILE in quotes.json quotes-summary.md macro.json macro-summary.md; do
    FPATH="$DATA_DIR/$FILE"
    if [ ! -f "$FPATH" ]; then
        echo "  ❌ Missing: $FILE"
        ERRORS=$((ERRORS + 1))
    elif [ ! -s "$FPATH" ]; then
        echo "  ❌ Empty:   $FILE"
        ERRORS=$((ERRORS + 1))
    else
        SIZE=$(wc -c < "$FPATH")
        if [ "$SIZE" -lt 500 ]; then
            echo "  ⚠️  Suspiciously small ($SIZE bytes): $FILE"
        else
            echo "  ✅ OK: $FILE ($SIZE bytes)"
        fi
    fi
done

echo ""
if [ "$ERRORS" -gt 0 ]; then
    echo "❌ fetch-market-data.sh — $ERRORS validation error(s). Check output above."
    exit 1
fi

# ── summary ──────────────────────────────────────────────────────────────────
TICKER_COUNT=$(python3 -c "
import json, sys
try:
    d = json.load(open('$DATA_DIR/quotes.json'))
    print(d.get('success_count', '?'))
except Exception as e:
    print('?')
" 2>/dev/null)

YIELD_STATUS=$(python3 -c "
import json
try:
    d = json.load(open('$DATA_DIR/macro.json'))
    yields = d.get('yield_curve', {}).get('yields', {})
    print(f'{len(yields)} maturities' if yields else 'unavailable')
except Exception:
    print('unavailable')
" 2>/dev/null)

echo "✅ fetch-market-data.sh complete — $DATE"
echo "   Quotes:      $TICKER_COUNT tickers with technicals"
echo "   Yield Curve: $YIELD_STATUS"
echo "   Scratch dir: data/agent-cache/daily/$DATE/data/"
echo ""
echo "  → Agent: read quotes-summary.md and macro-summary.md in that folder (or prefer Supabase price_technicals)"
echo "    before web-searching for prices or yields."
