#!/bin/bash
# smoke-test.sh — Fast sanity check: every script must exit 0 when called with --help
# (or with no-op flags). Requires the same deps as the app (pip install -r requirements.txt);
# CI installs them in .github/workflows/ci.yml before running this script.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
ERRORS=()

run_check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✅ $label"
    PASS=$((PASS + 1))
  else
    local code=$?
    echo "  ❌ $label (exit $code)"
    FAIL=$((FAIL + 1))
    ERRORS+=("$label")
  fi
}

echo "╔══════════════════════════════════════════╗"
echo "║  smoke-test.sh — Script sanity checks    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "── Bash scripts (--help) ─────────────────────────────"
for script in scripts/*.sh; do
  name=$(basename "$script")
  # Skip self to prevent infinite recursion
  [[ "$name" == "smoke-test.sh" ]] && continue
  # check-types-sync.sh and validate-frontmatter.sh are validate-only, call directly
  if [[ "$name" == "check-types-sync.sh" || "$name" == "validate-frontmatter.sh" ]]; then
    run_check "$name" bash "$script"
  else
    run_check "$name" bash "$script" --help
  fi
done

echo ""
echo "── Python scripts (--help) ───────────────────────────"
# Prefer repo venv only when it can import core deps (avoid broken/partial venvs).
PYTHON="python3"
if [[ -n "${DIGIQUANT_PYTHON:-}" ]]; then
  PYTHON="$DIGIQUANT_PYTHON"
elif [[ -x "${REPO_ROOT}/.venv/bin/python3" ]] \
  && "${REPO_ROOT}/.venv/bin/python3" -c "import numpy, requests" 2>/dev/null; then
  PYTHON="${REPO_ROOT}/.venv/bin/python3"
fi

for script in \
  scripts/audit_config_references.py \
  scripts/backfill_execution_prices.py \
  scripts/backfill-supabase.py \
  scripts/compute-technicals.py \
  scripts/convert_snapshot_v1.py \
  scripts/execute_at_open.py \
  scripts/fetch-macro.py \
  scripts/fetch-quotes.py \
  scripts/fill-entry-prices.py \
  scripts/generate-snapshot.py \
  scripts/ingest_crypto_fng.py \
  scripts/ingest_fred.py \
  scripts/ingest_fx_frankfurter.py \
  scripts/ingest_treasury_curve.py \
  scripts/legacy_delta_to_ops.py \
  scripts/materialize_snapshot.py \
  scripts/migrate_md_outputs_to_json.py \
  scripts/preload-history.py \
  scripts/publish_document.py \
  scripts/refresh_performance_metrics.py \
  scripts/repair_supabase_portfolio_data.py \
  scripts/retrofit_delta_requests.py \
  scripts/run_db_first.py \
  scripts/update_tearsheet.py \
  scripts/validate_artifact.py \
  scripts/validate_db_first.py \
  scripts/verify_supabase_canonical.py; do
  run_check "$(basename $script)" "$PYTHON" "$script" --help
done

echo ""
echo "═══════════════════════════════════════════"
echo "  Results: ${PASS} passed, ${FAIL} failed"
if [[ ${FAIL} -gt 0 ]]; then
  echo ""
  echo "  Failed:"
  for e in "${ERRORS[@]}"; do echo "    • $e"; done
  echo "═══════════════════════════════════════════"
  exit 1
fi
echo "═══════════════════════════════════════════"
