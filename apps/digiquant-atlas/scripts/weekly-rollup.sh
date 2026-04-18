#!/bin/bash
# weekly-rollup.sh — Weekly rollup (Supabase-first)
#
# Canonical artifact: JSON weekly_digest in Supabase `documents` (not local weekly markdown).
# This script prints the operator prompt and stable document_key only.
#
# Usage: ./scripts/weekly-rollup.sh [--help]

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && {
  grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'
  exit 0
}

YEAR=$(date +%Y)
WEEK=$(date +%V)
WEEK_LABEL="${YEAR}-W${WEEK}"

echo ""
echo "📅 Weekly rollup — $WEEK_LABEL (Supabase documents)"
echo "===================================================="
echo ""
echo "1. Read prior week from Supabase:"
echo "   - daily_snapshots for dates in this ISO week"
echo "   - documents (digest, deltas, sector notes) as needed"
echo ""
echo "2. Author JSON matching templates/schemas/weekly-digest.schema.json"
echo ""
echo "3. Publish:"
echo "   cat weekly.json | python3 scripts/validate_artifact.py -"
echo "   cat weekly.json | python3 scripts/publish_document.py --payload -"
echo "   Use stable document_key: weekly/${WEEK_LABEL}.json"
echo ""
echo "4. Validate: python3 scripts/validate_db_first.py --validate-mode full"
echo ""
echo "See RUNBOOK.md → Weekly/monthly rollups."
echo ""
