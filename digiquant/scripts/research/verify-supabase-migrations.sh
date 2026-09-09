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
set -euo pipefail
# This file lives at digiquant/scripts/research/, so the digiquant/ package root —
# which is what holds supabase/ — is two levels up, not one (#1807).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIG="${ROOT}/supabase/migrations"
CFG="${ROOT}/supabase/config.toml"

# Prefix collisions that predate this guard and are already applied to prod.
# Keyed on the exact basename, never the bare prefix, so a *third* 025 still
# trips the check.
#
# 025_thesis_daily_fields.sql and 025_trading_calendar.sql were both applied on
# 2026-06-26 and are both recorded in `olympus_schema_migrations` under these
# names (verified against the live `core` project 2026-08-01). db-migrate.yml
# keys the ledger on the full filename, so renumbering either one mints a new
# ledger key for an already-applied file. Sorted order here matches the order
# prod applied them in, so the collision is inert. Leave them alone.
GRANDFATHERED_DUPES=("025_trading_calendar.sql")

if [[ ! -f "$CFG" ]]; then
  echo "❌ Missing $CFG (run: npx supabase init --yes in repo root)" >&2
  exit 1
fi
if [[ ! -d "$MIG" ]]; then
  echo "❌ Missing $MIG" >&2
  exit 1
fi

# A grandfathered entry whose file is gone is a stale exemption — fail rather
# than let it silently widen to some future collision.
#
# The `${a[@]+"${a[@]}"}` guard is not decoration: macOS ships bash 3.2, where
# expanding an empty array under `set -u` aborts with "unbound variable". Emptying
# the list is exactly what the error below tells you to do.
for g in ${GRANDFATHERED_DUPES[@]+"${GRANDFATHERED_DUPES[@]}"}; do
  if [[ ! -f "${MIG}/${g}" ]]; then
    echo "❌ Stale grandfathered duplicate: ${g} no longer exists; drop it from GRANDFATHERED_DUPES" >&2
    exit 1
  fi
done

tmp="$(mktemp)"
find "$MIG" -maxdepth 1 -name '*.sql' -print | sort >"$tmp"
count=0
grandfathered=0
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
    exempt=0
    for g in ${GRANDFATHERED_DUPES[@]+"${GRANDFATHERED_DUPES[@]}"}; do
      [[ "$base" == "$g" ]] && exempt=1 && break
    done
    if [[ "$exempt" -eq 0 ]]; then
      rm -f "$tmp"
      echo "❌ Duplicate migration prefix: $ver ($base) — use the next unused prefix" >&2
      exit 1
    fi
    grandfathered=$((grandfathered + 1))
  fi
  prev="$ver"
done <"$tmp"
rm -f "$tmp"

if [[ "$count" -eq 0 ]]; then
  echo "❌ No .sql files in $MIG" >&2
  exit 1
fi

suffix=""
[[ "$grandfathered" -gt 0 ]] && suffix=" (${grandfathered} grandfathered prefix collision(s))"
echo "✅ ${count} migration file(s) under supabase/migrations; config.toml present${suffix}"
