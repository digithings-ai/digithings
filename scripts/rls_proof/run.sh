#!/usr/bin/env bash
# ============================================================================
# RLS isolation proof harness - vanilla PostgreSQL (no Docker / Supabase CLI)
# ============================================================================
# Applies:
#   1) 00_supabase_shim.sql
#   2) digiquant/supabase/migrations/*.sql (lexicographic sort, top-level)
#   (099/102–105 now live in digiquant/supabase/migrations/ — applied by the main glob)
#   4) cutover/900_drop_anon_read_cutover.sql  (post-cutover state)
#   5) 01_seed.sql
#   6) 02_proof.sql
#
# Usage:
#   ./scripts/rls_proof/run.sh
#   DB_NAME=rls_proof ./scripts/rls_proof/run.sh
#   LOG=/opt/cursor/artifacts/rls_isolation_proof.log ./scripts/rls_proof/run.sh
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROOF_DIR="$ROOT/scripts/rls_proof"
MIG_DIR="$ROOT/digiquant/supabase/migrations"
CUTOVER="$MIG_DIR/cutover/900_drop_anon_read_cutover.sql"

DB_NAME="${DB_NAME:-rls_proof}"
if [[ "$DB_NAME" == "postgres" || "$DB_NAME" == "template1" ]]; then
  echo "ERROR: DB_NAME must not be 'postgres' or 'template1' (refusing to drop/recreate a system database)." >&2
  exit 1
fi
PGUSER="${PGUSER:-postgres}"
LOG_FINAL="${LOG:-/opt/cursor/artifacts/rls_isolation_proof.log}"
# Write to local disk first; copy to LOG_FINAL at end (artifacts mount can flake).
LOG="${LOG_TMP:-/tmp/rls_isolation_proof.log}"
PSQL=(sudo -u "$PGUSER" psql -v ON_ERROR_STOP=1 -d "$DB_NAME")

mkdir -p "$(dirname "$LOG")" "$(dirname "$LOG_FINAL")"
: >"$LOG"

log() {
  echo "$@" | tee -a "$LOG"
}

run_sql_file() {
  local label="$1"
  local file="$2"
  log ""
  log "----------------------------------------------------------------------"
  log "APPLY: $label"
  log "FILE:  $file"
  log "----------------------------------------------------------------------"
  if ! "${PSQL[@]}" -f "$file" >>"$LOG" 2>&1; then
    log "FAIL applying $label ($file)"
    cp -f "$LOG" "$LOG_FINAL" 2>/dev/null || cat "$LOG" >"$LOG_FINAL" || true
    exit 1
  fi
  log "OK: $label"
}

log "=== digithings RLS isolation proof ==="
log "date: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "repo: $ROOT"
log "db:   $DB_NAME"
log "pg:   $(sudo -u "$PGUSER" psql -d "$DB_NAME" -Atc 'SELECT version()' | head -1)"
log ""

log "Recreating database $DB_NAME ..."
sudo -u "$PGUSER" psql -v ON_ERROR_STOP=1 -d postgres >>"$LOG" 2>&1 <<EOF
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${DB_NAME}";
CREATE DATABASE "${DB_NAME}";
EOF

run_sql_file "supabase-compat shim" "$PROOF_DIR/00_supabase_shim.sql"

log ""
log "=== Migration source: origin/develop top-level digiquant/supabase/migrations/*.sql ==="
mapfile -t DEVELOP_MIGS < <(find "$MIG_DIR" -maxdepth 1 -name '*.sql' | sort)
log "count: ${#DEVELOP_MIGS[@]}"
for f in "${DEVELOP_MIGS[@]}"; do
  base="$(basename "$f")"
  # 097 backfills olympus_profile_config.workspace_id via UPDATE, but 075 installed
  # an append-only trigger that rejects UPDATE. Wrap with session_replication_role=
  # replica (superuser-only) without editing the migration. Documented harness delta.
  if [[ "$base" == "097_workspaces_tenant_columns.sql" ]]; then
    wrap="/var/tmp/rls_097_wrap.sql"
    {
      printf '%s\n' 'SET session_replication_role = replica;'
      printf '\\i %s\n' "$f"
      printf '%s\n' 'SET session_replication_role = origin;'
    } >"$wrap"
    chmod a+r "$wrap"
    log ""
    log "----------------------------------------------------------------------"
    log "APPLY: develop/${base}  [HARNESS WRAP: session_replication_role=replica]"
    log "FILE:  $f"
    log "NOTE:  075 append-only trigger blocks 097 workspace_id UPDATE; wrap only."
    log "----------------------------------------------------------------------"
    if ! "${PSQL[@]}" -f "$wrap" >>"$LOG" 2>&1; then
      rm -f "$wrap"
      log "FAIL applying develop/${base} ($f)"
      cp -f "$LOG" "$LOG_FINAL" 2>/dev/null || cat "$LOG" >"$LOG_FINAL" || true
      exit 1
    fi
    rm -f "$wrap"
    log "OK: develop/${base} (wrapped)"
    continue
  fi
  run_sql_file "develop/${base}" "$f"
done

run_sql_file "cutover/900_drop_anon_read_cutover.sql (STAGED)" "$CUTOVER"
run_sql_file "seed" "$PROOF_DIR/01_seed.sql"

log ""
log "=== PROOF MATRIX EXECUTION ==="
set +e
"${PSQL[@]}" -f "$PROOF_DIR/02_proof.sql" >>"$LOG" 2>&1
proof_rc=$?
set -e

log ""
if [[ $proof_rc -eq 0 ]]; then
  log "=== OVERALL: PASS (exit 0) ==="
else
  log "=== OVERALL: FAIL (exit ${proof_rc}) — inspect rls_proof_results / FAIL lines above ==="
fi

log "Log written to $LOG"
cp -f "$LOG" "$LOG_FINAL" 2>/dev/null || cat "$LOG" >"$LOG_FINAL" || true
log "Copied to $LOG_FINAL ($(wc -c <"$LOG") bytes)"
exit "$proof_rc"
