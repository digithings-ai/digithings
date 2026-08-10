#!/bin/bash
# check-types-sync.sh — Verify database.types.ts has entries for all Supabase tables.
# Exits 1 with a warning if the migration file count differs from the TypeScript type count.
set -e

MIGRATIONS_DIR="supabase/migrations"
TYPES_FILE="frontend/lib/database.types.ts"

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
  echo "❌ Missing: $MIGRATIONS_DIR" >&2; exit 1
fi
if [[ ! -f "$TYPES_FILE" ]]; then
  echo "❌ Missing: $TYPES_FILE" >&2; exit 1
fi

# Extract base table names from SQL migrations (skip partition variants like _default, _y2025, etc.)
sql_tables=$(grep -hE "^CREATE TABLE (IF NOT EXISTS )?[a-z_]+" "$MIGRATIONS_DIR"/*.sql 2>/dev/null \
  | sed -E 's/CREATE TABLE (IF NOT EXISTS )?//' \
  | awk '{print $1}' \
  | grep -vE '_(default|partitioned|y[0-9]{4})$' \
  | grep -vE '^(daily_snapshots_new|documents_new)$' \
  | tr '[:upper:]' '[:lower:]' \
  | sort -u)

# Tables created in an early migration then dropped later (CREATE line remains; TS omits them).
# Examples: 016 sec_recent_filings → 017 drop; 001 benchmark_history → 010 drop (use price_history).
SQL_RETIRED_TABLES="sec_recent_filings benchmark_history"
for t in $SQL_RETIRED_TABLES; do
  sql_tables=$(printf '%s\n' "$sql_tables" | grep -vxF "$t" || true)
done
sql_tables=$(echo "$sql_tables" | sed '/^$/d' | sort -u)

# Extract table keys from the Tables block only (not Views / nested Row shapes).
ts_tables=$(awk '
  /^    Tables: \{/ { in_tables = 1; next }
  /^    Views: \{/ { in_tables = 0; next }
  in_tables && /^      [a-z_]+: \{$/ {
    gsub(/:/, "", $1)
    print $1
  }
' "$TYPES_FILE" | sort -u)

sql_count=$(echo "$sql_tables" | grep -c . || true)
ts_count=$(echo "$ts_tables" | grep -c . || true)

echo "📋 Supabase migration tables ($sql_count): $(echo $sql_tables | tr '\n' ' ')"
echo "📋 TypeScript types tables  ($ts_count): $(echo $ts_tables | tr '\n' ' ')"

if [[ "$sql_count" -ne "$ts_count" ]]; then
  echo ""
  echo "⚠️  DRIFT DETECTED — $sql_count SQL tables vs $ts_count TS types"
  echo "   Missing from TS: $(comm -23 <(echo "$sql_tables") <(echo "$ts_tables") | tr '\n' ' ')"
  echo "   Missing from SQL: $(comm -13 <(echo "$sql_tables") <(echo "$ts_tables") | tr '\n' ' ')"
  echo "   Update frontend/lib/database.types.ts to reflect the current schema."
  exit 1
fi

echo ""
echo "✅ database.types.ts is in sync with migrations ($ts_count tables)"
