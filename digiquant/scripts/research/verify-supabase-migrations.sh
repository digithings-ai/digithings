#!/usr/bin/env bash
# verify-supabase-migrations.sh — Fast CI guard on the `core` migration chain:
# config.toml present, every file named NNN_name.sql, no duplicate numeric prefix.
#
# Runs as the first step of .github/workflows/test-digiquant.yml (before the uv
# sync, so it fails in seconds) and as `make supabase-migrations-check`. The
# `digiquant/**` path filter in ci.yml covers digiquant/supabase/migrations/**,
# so any PR touching the chain runs this.
#
# It does NOT verify ordering. `find | sort` feeds the loop already sorted, so
# the "not in version order" branch below is unreachable belt-and-braces — don't
# document this script as an order check.
#
# Duplicate prefixes are a hard failure with no exemptions. The old `025`
# collision was resolved by renumbering `025_trading_calendar.sql` to
# `126_trading_calendar.sql` (#3923); do not reintroduce a grandfather list.
# `.github/workflows/db-migrate.yml` enforces the same uniqueness at apply time.
set -euo pipefail
# This file lives at digiquant/scripts/research/, so the digiquant/ package root —
# which is what holds supabase/ — is two levels up, not one (#1807).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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
prev_base=""
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
    echo "❌ Migrations not in version order: $base after $prev_base" >&2
    exit 1
  fi
  if [[ "$ver" == "$prev" ]]; then
    rm -f "$tmp"
    echo "❌ Duplicate migration prefix ${ver}: ${prev_base} and ${base}" >&2
    echo "   Rename one to the next unused prefix (keep the highest numbered file)," >&2
    echo "   then update any docs/tests that name the old filename." >&2
    exit 1
  fi
  prev="$ver"
  prev_base="$base"
done <"$tmp"
rm -f "$tmp"

if [[ "$count" -eq 0 ]]; then
  echo "❌ No .sql files in $MIG" >&2
  exit 1
fi

echo "✅ ${count} migration file(s) under supabase/migrations; config.toml present; prefixes unique"
