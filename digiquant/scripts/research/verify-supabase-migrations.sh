#!/usr/bin/env bash
# verify-supabase-migrations.sh — Fast CI guard on the `core` Supabase stack:
#   1. config.toml present
#   2. every migrations/*.sql named NNN_name.sql, no duplicate numeric prefix
#   3. [db].major_version pinned to the production Postgres major (17)
#   4. migrations/cutover/*.sql named NNN_name.sql, no prefix collision with the
#      develop chain, and listed exactly once in the declared CUTOVER_ORDER below
#
# Runs as the first step of .github/workflows/test-digiquant.yml (before the uv
# sync, so it fails in seconds) and as `make supabase-migrations-check`. The
# `digiquant/**` path filter in ci.yml covers digiquant/supabase/migrations/**,
# so any PR touching the chain runs this.
#
# It does NOT apply anything. A green run here says nothing about whether the SQL
# executes; the apply proof is `scripts/rls_proof/run.sh` (real postgres, runs
# the whole develop chain then stages cutover 900).
#
# It does NOT verify develop-chain ordering. `find | sort` feeds the loop already
# sorted, so the "not in version order" branch below is unreachable
# belt-and-braces — don't document this script as an order check.
#
# What it DOES pin about ordering: cutover order is *declared*, not inferred.
# No numeric rule can rank the cutover files: 113 fills a gap reserved out of
# the develop chain (it sorts BELOW develop migration 142, by design), while 900
# sorts above every develop file. Only the exact-prefix collision check is
# numeric, and it is the one that can be wrong here. CUTOVER_ORDER is therefore
# the single source of truth and the check is bidirectional: every on-disk
# cutover file appears in it exactly once, and every entry names a file that
# exists. Adding, renaming or deleting a cutover file fails until the manifest
# is updated in the same change.
#
# Cutover 900 is applied-and-proved after the develop chain by
# scripts/rls_proof/run.sh; cutover 113 currently has no apply harness. That is
# a real gap, not something this filename guard can close.
#
# Duplicate prefixes are a hard failure with no exemptions. The old `025`
# collision was resolved by renumbering `025_trading_calendar.sql` to
# `111_trading_calendar.sql` (#3923); do not reintroduce a grandfather list.
# `.github/workflows/db-migrate.yml` enforces the same uniqueness at apply time.
set -euo pipefail
# This file lives at digiquant/scripts/research/, so the digiquant/ package root —
# which is what holds supabase/ — is two levels up, not one (#1807).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIG="${ROOT}/supabase/migrations"
CUTOVER="${MIG}/cutover"
CFG="${ROOT}/supabase/config.toml"
# The Postgres major version the local stack must match. Production `core` runs
# PG17 (see the self-host reference stack plan, gap item 2); `supabase start`
# silently provisions a different image when this drifts, and every local
# migration proof then runs on a different server than production.
REQUIRED_DB_MAJOR=17

if [[ ! -f "$CFG" ]]; then
  echo "❌ Missing $CFG (run: npx supabase init --yes in repo root)" >&2
  exit 1
fi
if [[ ! -d "$MIG" ]]; then
  echo "❌ Missing $MIG" >&2
  exit 1
fi

# --- 3. Postgres major version pin -------------------------------------------
# Read major_version from the [db] table only: `[db.pooler]` is a separate table
# and the bare prefix "[db" would match it.
db_major="$(awk '
  /^[[:space:]]*\[/ { section = $0; gsub(/[[:space:]]/, "", section); next }
  section == "[db]" && /^[[:space:]]*major_version[[:space:]]*=/ {
    sub(/^[^=]*=[[:space:]]*/, "")
    gsub(/^["'\'']|["'\'']$/, "")
    gsub(/[[:space:]]/, "")
    print
  }
' "$CFG")"
if [[ -z "$db_major" ]]; then
  echo "❌ No major_version in the [db] table of $CFG" >&2
  echo "   supabase start would pick its own default image and drift from prod." >&2
  exit 1
fi
if [[ "$db_major" != "$REQUIRED_DB_MAJOR" ]]; then
  echo "❌ [db].major_version is ${db_major}, expected ${REQUIRED_DB_MAJOR}" >&2
  echo "   Local and prod must run the same Postgres major (plan gap item 2)." >&2
  exit 1
fi

# --- 1/2. develop chain -------------------------------------------------------
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

# --- 4. cutover chain ---------------------------------------------------------
# Declared application order. One entry per file, no duplicates.
CUTOVER_ORDER=(
  "113_drop_legacy_book_uniques.sql"
  "900_drop_anon_read_cutover.sql"
)

cutover_count=0
if [[ ! -d "$CUTOVER" ]]; then
  echo "❌ Missing $CUTOVER" >&2
  echo "   The CUTOVER_ORDER manifest below is the source of truth;" >&2
  echo "   deleting the directory is drift, not a clean tree." >&2
  exit 1
fi

for base in "${CUTOVER_ORDER[@]}"; do
  if [[ ! -f "${CUTOVER}/${base}" ]]; then
    echo "❌ CUTOVER_ORDER names ${base}, which is not in ${CUTOVER}" >&2
    echo "   The manifest is the source of truth; fix the manifest or the file." >&2
    exit 1
  fi
done

ctmp="$(mktemp)"
find "$CUTOVER" -maxdepth 1 -name '*.sql' -print | sort >"$ctmp"
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  cutover_count=$((cutover_count + 1))
  base="$(basename "$f")"
  if [[ ! "$base" =~ ^[0-9]{3}_[a-zA-Z0-9_-]+\.sql$ ]]; then
    rm -f "$ctmp"
    echo "❌ Bad cutover name (expected NNN_name.sql): $base" >&2
    exit 1
  fi
  listed=0
  for want in "${CUTOVER_ORDER[@]}"; do
    if [[ "$base" == "$want" ]]; then
      listed=$((listed + 1))
    fi
  done
  if [[ "$listed" -ne 1 ]]; then
    rm -f "$ctmp"
    echo "❌ Cutover ${base} appears ${listed}x in CUTOVER_ORDER, expected exactly 1" >&2
    echo "   Every cutover file must be declared once, in apply order." >&2
    exit 1
  fi
  ver="${base:0:3}"
  if [[ "$ver" == "$prev" ]]; then
    rm -f "$ctmp"
    echo "❌ Prefix ${ver} is used by both ${prev_base} and cutover/${base}" >&2
    exit 1
  fi
done <"$ctmp"
rm -f "$ctmp"

echo "✅ ${count} migration file(s) under supabase/migrations; config.toml present; [db].major_version=${db_major}; prefixes unique"
echo "✅ ${cutover_count} cutover file(s) declared exactly once in CUTOVER_ORDER"
