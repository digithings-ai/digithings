#!/bin/bash
# status.sh — DB-first project health (Supabase validation + optional memory summary)
# Usage: ./scripts/status.sh [YYYY-MM-DD]

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

DATE=${1:-$(date +%Y-%m-%d)}

echo "DB-first status (Supabase):"
python3 scripts/validate_db_first.py --date "$DATE"

echo ""
echo "── Memory files (ROLLING.md) ────────"
TOTAL_MEM=$(find memory/ -name "ROLLING.md" 2>/dev/null | wc -l | tr -d ' ')
echo "  Total ROLLING.md files: $TOTAL_MEM"

echo ""
echo "── Commands (DB-first) ──────────────"
echo "  python3 scripts/run_db_first.py   Metrics refresh, execute-at-open, validate_db_first"
echo "  ./scripts/new-day.sh              Same entrypoint as run_db_first.py"
echo "  ./scripts/weekly-rollup.sh        Weekly digest → Supabase (prompt)"
echo "  ./scripts/monthly-rollup.sh       Monthly digest → Supabase (prompt)"
echo "  ./scripts/fetch-market-data.sh    Optional local quotes/macro cache (gitignored)"
echo "  ./scripts/git-commit.sh           Commit config/memory (scratch under data/agent-cache/ is gitignored)"
echo "  ./scripts/watchlist-check.sh      Quick watchlist prompt"
echo "  ./scripts/thesis.sh               Thesis helpers"
echo ""
