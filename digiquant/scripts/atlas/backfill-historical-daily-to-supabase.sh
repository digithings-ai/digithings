#!/usr/bin/env bash
# Copy daily folders from LEGACY_ROOT into data/agent-cache/daily/, materialize snapshots into Supabase for a date range,
# then run update_tearsheet so documents / NAV / metrics align with the scratch tree.
#
# Typical use (after populating LEGACY_ROOT or using SKIP_COPY=1):
#   LEGACY_ROOT=/path/to/export/with/YYYY-MM-DD-dirs ./scripts/backfill-historical-daily-to-supabase.sh
#   SKIP_COPY=1 ./scripts/backfill-historical-daily-to-supabase.sh   # data/agent-cache/daily already filled
#
# Prerequisites:
#   - config/supabase.env with SUPABASE_URL + SUPABASE_SERVICE_KEY
#   - pip install -r requirements.txt
#   - Unless SKIP_COPY=1: LEGACY_ROOT must be a directory whose children include YYYY-MM-DD folders to copy
#
# Environment overrides:
#   LEGACY_ROOT   — required unless SKIP_COPY=1 (directory containing daily YYYY-MM-DD subfolders)
#   BASELINE_DATE — default: 2026-04-05 (Sunday baseline for that week)
#   LAST_DATE     — default: 2026-04-08 (last day to materialize)
#   SKIP_COPY=1   — do not copy from LEGACY_ROOT (use existing data/agent-cache/daily only)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi

BASELINE_DATE="${BASELINE_DATE:-2026-04-05}"
LAST_DATE="${LAST_DATE:-2026-04-08}"
SKIP_COPY="${SKIP_COPY:-0}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '1,40p' "$0"
  exit 0
fi

if [[ "$SKIP_COPY" != "1" ]]; then
  if [[ -z "${LEGACY_ROOT:-}" ]]; then
    echo "❌ LEGACY_ROOT is required unless you set SKIP_COPY=1." >&2
    echo "   Example: LEGACY_ROOT=/path/to/daily-export ./scripts/backfill-historical-daily-to-supabase.sh" >&2
    exit 1
  fi
  if [[ ! -d "$LEGACY_ROOT" ]]; then
    echo "❌ LEGACY_ROOT is not a directory: $LEGACY_ROOT" >&2
    exit 1
  fi
fi

echo "== backfill-historical-daily-to-supabase"
echo "    BASELINE_DATE=$BASELINE_DATE LAST_DATE=$LAST_DATE SKIP_COPY=$SKIP_COPY"
if [[ "$SKIP_COPY" != "1" ]]; then
  echo "    LEGACY_ROOT=$LEGACY_ROOT"
fi

# Dates between baseline and last (inclusive), ISO order.
ALL_DATES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && ALL_DATES+=("$line")
done < <(
  "$PY" - <<'PY' "$BASELINE_DATE" "$LAST_DATE"
import sys
from datetime import date, timedelta

def parse(s):
    y, m, d = map(int, s.split("-"))
    return date(y, m, d)

a, b = parse(sys.argv[1]), parse(sys.argv[2])
if b < a:
    raise SystemExit("LAST_DATE must be >= BASELINE_DATE")
cur = a
while cur <= b:
    print(cur.isoformat())
    cur += timedelta(days=1)
PY
)

DELTA_DATES=()
for d in "${ALL_DATES[@]}"; do
  if [[ "$d" != "$BASELINE_DATE" ]]; then
    DELTA_DATES+=("$d")
  fi
done

if [[ ${#DELTA_DATES[@]} -eq 0 ]]; then
  echo "No delta dates between baseline and LAST_DATE." >&2
  exit 1
fi

if [[ "$SKIP_COPY" != "1" ]]; then
  echo "== Copy LEGACY_ROOT → data/agent-cache/daily (skip dates with no source folder)"
  for d in "${ALL_DATES[@]}"; do
    src="$LEGACY_ROOT/$d"
    if [[ ! -d "$src" ]]; then
      echo "   (no folder for $d under LEGACY_ROOT — using data/agent-cache/daily/$d if present)"
      continue
    fi
    dst="$ROOT/data/agent-cache/daily/$d"
    mkdir -p "$dst"
    cp -R "$src"/. "$dst/"
    echo "   copied $d"
  done
else
  echo "== SKIP_COPY=1 — using data/agent-cache/daily as-is"
fi

echo "== Materialize digest chain: baseline $BASELINE_DATE then ${DELTA_DATES[*]}"
BF=( "$ROOT/scripts/backfill-db-first-digest.sh" "$BASELINE_DATE" "${DELTA_DATES[@]}" )
"${BF[@]}"

echo "== update_tearsheet (documents, positions, metrics, benchmarks)"
"$PY" "$ROOT/scripts/update_tearsheet.py"

echo ""
echo "✅ Backfill finished. Suggested checks:"
echo "   $PY scripts/validate_db_first.py --mode full"
echo "   Open frontend Research Library for dates $BASELINE_DATE … $LAST_DATE"
