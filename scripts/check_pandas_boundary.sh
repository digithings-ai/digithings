#!/usr/bin/env bash
# Fail when new `import pandas` appears outside the documented digiquant allowlist (REM-132).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

command -v rg >/dev/null || {
  echo "::error::ripgrep not found — pandas boundary gate cannot run"
  exit 1
}

ALLOWLIST=(
  "digiquant/src/digiquant/nautilus_runner.py"
  "digiquant/src/digiquant/tearsheet.py"
  "digiquant/src/digiquant/charts/returns.py"
  "digiquant/src/digiquant/charts/drawdown.py"
  "digiquant/src/digiquant/charts/equity.py"
  "digiquant/scripts/atlas/preload-history.py"
  "digiquant/src/digiquant/strategies/bollinger_mr.py"
  "digiquant/src/digiquant/strategies/macd_trend.py"
  # SDCA walk-forward evaluator: BarDataWrangler boundary, same as nautilus_runner (#3174 / #3253).
  "digiquant/src/digiquant/strategies/sdca/nautilus_evaluator.py"
  # Operator ad-hoc Yahoo fetch; yfinance returns pandas DataFrames (#1719).
  "digiquant/scripts/fetch_real_ohlcv.py"
  # Sandbox shim: re-exports pandas_ta_classic for agent image acceptance (#396).
  "digiquant/sandbox/pandas_ta/__init__.py"
)

violations=()
while IFS= read -r line; do
  file="${line%%:*}"
  rel="${file#./}"
  allowed=false
  for a in "${ALLOWLIST[@]}"; do
    if [[ "$rel" == "$a" ]]; then
      allowed=true
      break
    fi
  done
  if [[ "$allowed" == false ]]; then
    violations+=("$rel")
  fi
done < <(rg -n '^(import pandas|from pandas)' --glob '*.py' digiquant/)

if ((${#violations[@]} > 0)); then
  echo "pandas import outside allowlist (see digiquant/AGENTS.md):"
  printf '  %s\n' "${violations[@]}"
  exit 1
fi

echo "pandas boundary OK (${#ALLOWLIST[@]} allowlisted paths)"
