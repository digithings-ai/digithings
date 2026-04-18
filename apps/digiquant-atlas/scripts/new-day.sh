#!/bin/bash
# new-day.sh — Supabase-first daily entry (replaces markdown tree scaffolding)
#
# Historical behavior used a local daily markdown tree. Canonical
# flow is JSON → materialize_snapshot / publish_document → Supabase; this script
# only runs the DB-first entrypoint so operators keep the same command name.
#
# Usage: ./scripts/new-day.sh [args passed through to run_db_first.py]
#   ./scripts/new-day.sh --dry-run
#   ./scripts/new-day.sh --date 2026-04-11 --delta

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && {
  grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'
  exit 0
}

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo ""
echo "📊 digiquant-atlas — Supabase-first (no local digest markdown tree)"
echo "   Entry: python3 scripts/run_db_first.py"
echo ""

exec python3 "$ROOT/scripts/run_db_first.py" "$@"
