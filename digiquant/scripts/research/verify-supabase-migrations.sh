#!/usr/bin/env bash
# verify-supabase-migrations.sh — Fast CI guard on the `core` Supabase stack:
#   1. config.toml present
#   2. every migrations/engine/*.sql and migrations/prod/*.sql named
#      NNN_name.sql, prefixes globally unique across both dirs, each dir in
#      version order and non-empty, no stray top-level *.sql
#   3. [db].major_version pinned to the production Postgres major (17)
#   4. migrations/cutover/*.sql named NNN_name.sql, no prefix collision with the
#      develop chain, and listed exactly once in the declared CUTOVER_ORDER below
#   5. engine/ self-containment: every public relation an engine file reads is
#      created by an engine file or in EXTERNAL_RELS (verified, documented)
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

# Layered chain (D-Q6′, DIG-3694): `engine/` holds the migrations for tables
# the open pipeline uses (R0 self-host schema); `prod/` holds the house-only
# remainder (R2). Apply order is engine-then-prod, each in filename order;
# `scripts/self_host_migrations_check.sh` and `scripts/rls_proof/run.sh`
# implement exactly that order, and the engine self-containment check below
# is what makes engine-first apply sound. NNN prefixes stay globally unique
# across both dirs (extension of the #3923 rule). One deliberate exception:
# `engine/001_initial_schema.sql` also creates the base book-table shells
# (positions, nav_history, portfolio_metrics, position_events,
# benchmark_history) because the engine tables it defines must exist before
# any engine ALTER; prod migrations shape the books afterwards. R0 self-host
# therefore creates those shells empty — filename/ledger stability wins over
# re-splitting 001.
# --- 1/2. layered chain ------------------------------------------------------
ENGINE="${MIG}/engine"
PROD="${MIG}/prod"
for d in "$ENGINE" "$PROD"; do
  if [[ ! -d "$d" ]]; then
    echo "❌ Missing $d (D-Q6′ layering: engine/ then prod/)" >&2
    exit 1
  fi
done
tmp="$(mktemp)"
find "$ENGINE" "$PROD" -maxdepth 1 -name '*.sql' -print | sort >"$tmp"
count=0
seen_prefixes="$(mktemp)"
for dir in "$ENGINE" "$PROD"; do
  prev=""
  prev_base=""
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    count=$((count + 1))
    base="$(basename "$f")"
    if [[ ! "$base" =~ ^[0-9]{3}_[a-zA-Z0-9_-]+\.sql$ ]]; then
      rm -f "$tmp" "$seen_prefixes"
      echo "❌ Bad migration name (expected NNN_name.sql): $base" >&2
      exit 1
    fi
    ver="${base:0:3}"
    if [[ -n "$prev" && "$ver" < "$prev" ]]; then
      rm -f "$tmp" "$seen_prefixes"
      echo "❌ Migrations not in version order in $(basename "$dir")/: $base after $prev_base" >&2
      exit 1
    fi
    if grep -qxF "$ver" "$seen_prefixes" 2>/dev/null; then
      rm -f "$tmp" "$seen_prefixes"
      echo "❌ Duplicate migration prefix ${ver} across engine/ and prod/: $base" >&2
      echo "   Prefixes are globally unique (D-Q6′ one-definition-per-table);" >&2
      echo "   rename one to the next unused prefix." >&2
      exit 1
    fi
    echo "$ver $base" >>"$seen_prefixes"
    prev="$ver"
    prev_base="$base"
  done < <(find "$dir" -maxdepth 1 -name '*.sql' -print | sort)
done
rm -f "$tmp"

if [[ "$count" -eq 0 ]]; then
  rm -f "$seen_prefixes"
  echo "❌ No .sql files in $ENGINE or $PROD" >&2
  exit 1
fi

# No stray top-level files: the chain lives in engine/ and prod/ only
# (cutover/ is handled below and is the only other allowed subdir).
strays="$(find "$MIG" -maxdepth 1 -name '*.sql' -print)"
if [[ -n "$strays" ]]; then
  rm -f "$seen_prefixes"
  echo "❌ Top-level migration file(s) outside engine/ and prod/:" >&2
  echo "$strays" >&2
  echo "   Classify each file into engine/ (open-pipeline tables) or prod/ (house-only)." >&2
  exit 1
fi
engine_count="$(find "$ENGINE" -maxdepth 1 -name '*.sql' | wc -l | tr -d ' ')"
prod_count="$(find "$PROD" -maxdepth 1 -name '*.sql' | wc -l | tr -d ' ')"

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
  if grep -qxF "$ver" "$seen_prefixes" 2>/dev/null; then
    rm -f "$ctmp" "$seen_prefixes"
    echo "❌ Prefix ${ver} is used by both the layered chain and cutover/${base}" >&2
    exit 1
  fi
done <"$ctmp"
rm -f "$ctmp"

# --- 5. engine self-containment ----------------------------------------------
# Engine-first apply is sound only if no engine/ file reads a relation that a
# prod/ file creates. The test is a set difference: relations referenced by
# engine/ that are created ONLY in prod/ fail. Prose and builtin calls can
# never appear in the created sets, so they cannot false-positive; a genuinely
# misspelled table is caught instead by the scratch-DB apply proof
# (scripts/self_host_migrations_check.sh), not here.
rel_names() {
  # An empty match set is a legitimate result (rc=1 from grep); mask it so
  # `set -e` + `pipefail` cannot abort here. Empty output, not an error.
  for f in "$2"/*.sql; do join_cont "$f"; done \
    | grep -oEi "$1" \
    | grep -oEi '(public\.)?"?[a-z_][a-z_0-9]*$' | tr -d '"' \
    | tr '[:upper:]' '[:lower:]' | sort -u || true
}
# SQL here splits some statements across lines
# (`CREATE TABLE IF NOT EXISTS` then the name on the next line), so join a
# line that ends with a trigger keyword with its continuation before matching.
join_cont() {
  awk '{ l = $0; while (l ~ /(CREATE[ \t]+(TABLE|VIEW)([ \t]+IF[ \t]+NOT[ \t]+EXISTS)?|FROM|JOIN|INTO|UPDATE|TABLE)$/) { if ((getline n) > 0) l = l " " n; else break } print l }' "$1"
}
created_engine="$(mktemp)"
created_prod="$(mktemp)"
rel_names 'CREATE[[:space:]]+(TABLE|VIEW)[[:space:]]+(IF[[:space:]]+NOT[[:space:]]+EXISTS[[:space:]]+)?(public\.)?"?[a-z_][a-z_0-9]*' "$ENGINE" >"$created_engine"
rel_names 'CREATE[[:space:]]+(TABLE|VIEW)[[:space:]]+(IF[[:space:]]+NOT[[:space:]]+EXISTS[[:space:]]+)?(public\.)?"?[a-z_][a-z_0-9]*' "$PROD" >"$created_prod"
referenced="$(mktemp)"
{
  rel_names '(FROM|JOIN|ALTER[[:space:]]+TABLE|DROP[[:space:]]+TABLE|INSERT[[:space:]]+INTO|DELETE[[:space:]]+FROM)[[:space:]]+(public\.)?"?[a-z_][a-z_0-9]*' "$ENGINE"
  rel_names 'UPDATE[[:space:]]+(public\.)?"?[a-z_][a-z_0-9]*' "$ENGINE"
  grep -hoEi 'ON[[:space:]]+(public\.)?"?[a-z_][a-z_0-9]*' "$ENGINE"/*.sql 2>/dev/null \
    | grep -viE 'ON[[:space:]]+(CONFLICT|COMMIT)' \
    | grep -oEi '"?[a-z_][a-z_0-9]*$' | tr -d '"' | tr '[:upper:]' '[:lower:]' | sort -u || true
} | sort -u >"$referenced"
prod_only="$(comm -23 "$created_prod" "$created_engine")"
violations=""
while IFS= read -r rel; do
  [[ -z "$rel" ]] && continue
  if printf '%s\n' "$prod_only" | grep -qxF "$rel"; then
    violations="${violations}public.${rel}
"
  fi
done <"$referenced"
rm -f "$created_engine" "$created_prod" "$referenced"
if [[ -n "$violations" ]]; then
  rm -f "$seen_prefixes"
  echo "❌ engine/ reads relation(s) created only in prod/:" >&2
  printf '%s' "$violations" | sed 's/^/   /' >&2
  echo "   Move the referencing file to prod/, or create the relation in engine/." >&2
  exit 1
fi
rm -f "$seen_prefixes"

echo "✅ ${engine_count} engine + ${prod_count} prod migration file(s); config.toml present; [db].major_version=${db_major}; prefixes globally unique; engine self-contained"
echo "✅ ${cutover_count} cutover file(s) declared exactly once in CUTOVER_ORDER"
