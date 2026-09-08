#!/bin/bash
# Re-materialize a week into Supabase using the DB-first pipeline:
# - Sunday baseline + Mon delta: data/agent-cache/daily/<date>/snapshot.json → convert_snapshot_v1 → materialize_snapshot
# - Later weekdays with empty snapshot.json: legacy DIGEST-DELTA.md → legacy_delta_to_ops → materialize (ops on prior day)
#
# Usage (from repo root):
#   ./scripts/backfill-db-first-digest.sh 2026-04-05 2026-04-06 2026-04-07
#
# Args: baseline Sunday date, then delta dates in order (each delta after the first chains on the previous calendar day).
set -e

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "Backfill DB-first digest into Supabase."
  echo ""
  echo "Usage:"
  echo "  $0 <baseline-yyyy-mm-dd> <delta-yyyy-mm-dd> [more-delta-dates...]"
  echo ""
  echo "Notes:"
  echo "  - Reads snapshot.json (if rich), else delta-request.json, else DIGEST-DELTA.md"
  echo "  - Writes to Supabase via scripts/materialize_snapshot.py"
  exit 0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY="python3"; fi
TMP="${TMPDIR:-/tmp}"

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <baseline-yyyy-mm-dd> <delta-yyyy-mm-dd> [more-delta-dates...]" >&2
  exit 1
fi

BASELINE="$1"
shift
BASE_JSON="${ROOT}/data/agent-cache/daily/${BASELINE}/snapshot.json"
if [[ ! -f "$BASE_JSON" ]]; then
  echo "Missing ${BASE_JSON}" >&2
  exit 1
fi

echo "== Baseline ${BASELINE} (convert + push)"
"$PY" scripts/convert_snapshot_v1.py --in "$BASE_JSON" --out "${TMP}/v1-digest-${BASELINE}.json"
"$PY" scripts/materialize_snapshot.py --date "$BASELINE" --snapshot "${TMP}/v1-digest-${BASELINE}.json"

PREV="$BASELINE"
for D in "$@"; do
  SNAP="${ROOT}/data/agent-cache/daily/${D}/snapshot.json"
  DELTA_JSON="${ROOT}/data/agent-cache/daily/${D}/delta-request.json"
  # Prefer a rich snapshot.json; stub files (regime shell only) should not beat delta-request.json.
  if [[ -f "$SNAP" ]] && "$PY" -c "
import json,sys
d=json.load(open(sys.argv[1],encoding='utf-8'))
reg=d.get('regime') or {}
pos=d.get('positions') or []
nar=d.get('narrative') or {}
rich=bool((isinstance(reg,dict) and str(reg.get('summary') or '').strip()) or pos)
if not rich and isinstance(nar,dict):
    rich=any(bool(nar.get(k)) for k in nar)
sys.exit(0 if rich else 1)
" "$SNAP" 2>/dev/null; then
    echo "== Delta ${D} (full legacy snapshot.json → convert + push)"
    "$PY" scripts/convert_snapshot_v1.py --in "$SNAP" --out "${TMP}/v1-digest-${D}.json"
    "$PY" scripts/materialize_snapshot.py --date "$D" --snapshot "${TMP}/v1-digest-${D}.json"
  elif [[ -f "$DELTA_JSON" ]]; then
    echo "== Delta ${D} (delta-request.json; baseline snapshot row ${PREV})"
    "$PY" scripts/materialize_snapshot.py \
      --date "$D" \
      --baseline-date "$PREV" \
      --ops "$DELTA_JSON"
  else
    DELTA_MD="${ROOT}/data/agent-cache/daily/${D}/DIGEST-DELTA.md"
    if [[ ! -f "$DELTA_MD" ]]; then
      echo "No rich snapshot, no delta-request.json, and no DIGEST-DELTA.md for ${D}" >&2
      exit 1
    fi
    echo "== Delta ${D} (legacy DIGEST-DELTA.md ops; load snapshot row ${PREV})"
    OUT_OPS="${ROOT}/data/agent-cache/daily/${D}/delta-request.json"
    "$PY" scripts/legacy_delta_to_ops.py \
      --date "$D" \
      --baseline-date "$BASELINE" \
      --delta-md "$DELTA_MD" \
      --out "${TMP}/delta-request-${D}.json"
    mkdir -p "${ROOT}/data/agent-cache/daily/${D}"
    cp "${TMP}/delta-request-${D}.json" "$OUT_OPS"
    echo "   → wrote $OUT_OPS (for update_tearsheet + Research Library)"
    "$PY" scripts/materialize_snapshot.py \
      --date "$D" \
      --baseline-date "$PREV" \
      --ops "$OUT_OPS"
  fi
  PREV="$D"
done

echo "✅ Backfill complete for: ${BASELINE} $*"
