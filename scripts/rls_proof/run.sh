#!/usr/bin/env bash
# ============================================================================
# RLS isolation proof harness — vanilla PostgreSQL (no Docker / Supabase CLI)
# ============================================================================
# Applies:
#   1) 00_supabase_shim.sql
#   2) digiquant/supabase/migrations/*.sql (numeric / lexicographic order, top-level)
#   3) vendor/t4_overlay/{099,102,103,104,105} from origin/cursor/t4-overlay-runs-3d52
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
T4_DIR="$PROOF_DIR/vendor/t4_overlay"
CUTOVER="$MIG_DIR/cutover/900_drop_anon_read_cutover.sql"

DB_NAME="${DB_NAME:-rls_proof}"
PGUSER="${PGUSER:-postgres}"
LOG="${LOG:-/opt/cursor/artifacts/rls_isolation_proof.log}"
PSQL=(sudo -u "$PGUSER" psql -v ON_ERROR_STOP=1 -d "$DB_NAME")

mkdir -p "$(dirname "$LOG")"
: >"$LOG"

log() { echo "$@" | tee -a "$LOG"; }

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

# Recreate DB for a clean proof
log "Recreating database $DB_NAME ..."
sudo -u "$PGUSER" psql -v ON_ERROR_STOP=1 -d postgres >>"$LOG" 2>&1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS $DB_NAME;
CREATE DATABASE $DB_NAME;
SQL

# ---------------------------------------------------------------------------
# 1) Shim
# ---------------------------------------------------------------------------
run_sql_file "supabase-compat shim" "$PROOF_DIR/00_supabase_shim.sql"

# ---------------------------------------------------------------------------
# 2) Develop top-level migrations (001…101; gaps OK)
# ---------------------------------------------------------------------------
log ""
log "=== Migration source: origin/develop top-level digiquant/supabase/migrations/*.sql ==="
mapfile -t DEVELOP_MIGS < <(find "$MIG_DIR" -maxdepth 1 -name '*.sql' | sort)
log "count: ${#DEVELOP_MIGS[@]}"
for f in "${DEVELOP_MIGS[@]}"; do
  base="$(basename "$f")"
  run_sql_file "develop/$base" "$f"
done

# ---------------------------------------------------------------------------
# 3) T4 overlay migrations (unmerged branch)
# ---------------------------------------------------------------------------
log ""
log "=== Migration source: origin/cursor/t4-overlay-runs-3d52 (vendored) ==="
log "Applied AFTER develop 101, BEFORE cutover 900:"
for base in \
  099_broker_connections.sql \
  102_kairos_broker_mirror.sql \
  103_notification_prefs.sql \
  104_workspace_provider_credentials.sql \
  105_documents_workspace_id.sql
do
  run_sql_file "t4_overlay/$base" "$T4_DIR/$base"
done

# ---------------------------------------------------------------------------
# 4) Cutover (post-cutover privacy state)
# ---------------------------------------------------------------------------
run_sql_file "cutover/900_drop_anon_read_cutover.sql (STAGED)" "$CUTOVER"

# ---------------------------------------------------------------------------
# 5) Seed
# ---------------------------------------------------------------------------
run_sql_file "seed" "$PROOF_DIR/01_seed.sql"

# ---------------------------------------------------------------------------
# 6) Proof matrix
# ---------------------------------------------------------------------------
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
  log "=== OVERALL: FAIL (exit $proof_rc) — inspect proof_results / FAIL lines above ==="
fi

log "Log written to $LOG"
exit "$proof_rc"
