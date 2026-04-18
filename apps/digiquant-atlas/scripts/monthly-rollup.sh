#!/bin/bash
# monthly-rollup.sh — Monthly synthesis (Supabase-first)
#
# Canonical artifact: JSON monthly_digest in Supabase `documents`.
#
# Usage: ./scripts/monthly-rollup.sh [--help]

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && {
  grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'
  exit 0
}

YEAR=$(date +%Y)
MONTH=$(date +%m)
MONTH_LABEL="${YEAR}-${MONTH}"

echo ""
echo "📆 Monthly synthesis — $MONTH_LABEL (Supabase documents)"
echo "========================================================"
echo ""
echo "1. Mine the month from Supabase: daily_snapshots + documents + portfolio_metrics."
echo ""
echo "2. Follow skills/monthly-synthesis/SKILL.md (JSON-first)."
echo ""
echo "3. Author JSON matching templates/schemas/monthly-digest.schema.json"
echo ""
echo "4. Publish:"
echo "   cat monthly.json | python3 scripts/validate_artifact.py -"
echo "   cat monthly.json | python3 scripts/publish_document.py --payload -"
echo "   Use stable document_key: monthly/${MONTH_LABEL}.json"
echo ""
echo "See RUNBOOK.md → Weekly/monthly rollups."
echo ""
