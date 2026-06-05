#!/usr/bin/env bash
# Fail when new `import pandas` appears outside the documented DigiQuant allowlist (REM-132).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ALLOWLIST=(
  "digiquant/src/digiquant/nautilus_runner.py"
  "digiquant/src/digiquant/tearsheet.py"
  "digiquant/src/digiquant/charts/returns.py"
  "digiquant/src/digiquant/charts/drawdown.py"
  "digiquant/src/digiquant/charts/equity.py"
  "digiquant/scripts/atlas/preload-history.py"
  "digiquant/src/digiquant/strategies/bollinger_mr.py"
  "digiquant/src/digiquant/strategies/macd_trend.py"
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
done < <(rg -n '^(import pandas|from pandas)' --glob '*.py' digiquant/ 2>/dev/null || true)

if ((${#violations[@]} > 0)); then
  echo "pandas import outside allowlist (see digiquant/AGENTS.md):"
  printf '  %s\n' "${violations[@]}"
  exit 1
fi

echo "pandas boundary OK (${#ALLOWLIST[@]} allowlisted paths)"
