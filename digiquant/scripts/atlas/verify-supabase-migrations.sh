#!/usr/bin/env bash
# verify-supabase-migrations.sh — Fast CI guard: config exists, migration naming/order sane.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIG="${ROOT}/supabase/migrations"
CFG="${ROOT}/supabase/config.toml"

if [[ ! -f "$CFG" ]]; then
  echo "❌ Missing $CFG (run: npx supabase init --yes in repo root)" >&2
  exit 1
fi
if [[ ! -d "$MIG" ]]; then
  echo "❌ Missing $MIG" >&2
  exit 1
fi

tmp="$(mktemp)"
find "$MIG" -maxdepth 1 -name '*.sql' -print | sort >"$tmp"
count=0
prev=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  count=$((count + 1))
  base="$(basename "$f")"
  if [[ ! "$base" =~ ^[0-9]{3}_[a-zA-Z0-9_-]+\.sql$ ]]; then
    rm -f "$tmp"
    echo "❌ Bad migration name (expected NNN_name.sql): $base" >&2
    exit 1
  fi
  ver="${base:0:3}"
  if [[ -n "$prev" && "$ver" < "$prev" ]]; then
    rm -f "$tmp"
    echo "❌ Migrations not in version order: $base after $prev" >&2
    exit 1
  fi
  if [[ "$ver" == "$prev" ]]; then
    rm -f "$tmp"
    echo "❌ Duplicate migration prefix: $ver" >&2
    exit 1
  fi
  prev="$ver"
done <"$tmp"
rm -f "$tmp"

if [[ "$count" -eq 0 ]]; then
  echo "❌ No .sql files in $MIG" >&2
  exit 1
fi

echo "✅ ${count} migration file(s) under supabase/migrations; config.toml present"
