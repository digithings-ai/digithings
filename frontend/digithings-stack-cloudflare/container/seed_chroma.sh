#!/bin/sh
# One-shot Chroma seed for Profile A. Runs under supervisord *after* digigraph
# binds and *before* digisearch opens PersistentClient (SQLite lock + CF port delay).
#
# Seeds:
#   - digithings_docs  ← /seed/digithings_docs  (digithings.ai/chat)
#   - occ_help         ← /seed/occ_help         (digithings.ai/chat/occ)
#
# Marker version: bump SEED_VER when seed markdown changes so existing volumes
# re-ingest on the next Container boot (shared-vN bump still recommended on CF).
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
SEED_VER="v3"
SEED_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_VER}"
SEED_SKIPPED="${DATA_CHROMA}/.stack_chroma_seed_skipped_${SEED_VER}"

# Legacy markers (v1 oneshot only seeded occ_help) — ignore; v2 re-seeds both.
mkdir -p "$DATA_CHROMA"

if [ -f "$SEED_MARKER" ] || [ -f "$SEED_SKIPPED" ]; then
  echo "digithings-stack: chroma seed ${SEED_VER} already done/skipped"
  exit 0
fi

# Prefer edge readiness before heavy Chroma/embedding download (CF probes :8000).
i=0
while [ "$i" -lt 90 ]; do
  if curl -sf "http://127.0.0.1:8000/healthz" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

seed_index() {
  index_name="$1"
  seed_dir="$2"
  if [ ! -d "$seed_dir" ]; then
    echo "digithings-stack: no ${seed_dir}; skipping index ${index_name}"
    return 0
  fi
  echo "digithings-stack: seeding ${index_name} from ${seed_dir}"
  CHROMA_PATH="$DATA_CHROMA" DIGISEARCH_ALLOW_STUB=0 \
    digisearch ingest --index "$index_name" "$seed_dir"
}

ok=1
if ! seed_index digithings_docs /seed/digithings_docs; then
  echo "digithings-stack: WARN digithings_docs seed failed"
  ok=0
fi
if ! seed_index occ_help /seed/occ_help; then
  echo "digithings-stack: WARN occ_help seed failed"
  ok=0
fi

if [ "$ok" -eq 1 ]; then
  touch "$SEED_MARKER"
  rm -f "$SEED_SKIPPED" \
    "${DATA_CHROMA}/.occ_help_seeded" "${DATA_CHROMA}/.occ_help_seed_skipped" \
    "${DATA_CHROMA}/.digithings_docs_seeded" 2>/dev/null || true
  echo "digithings-stack: chroma seed ${SEED_VER} complete (digithings_docs + occ_help)"
  exit 0
fi

echo "digithings-stack: WARN chroma seed ${SEED_VER} incomplete (continuing boot)"
echo "digithings-stack: re-seed later: supervisorctl stop digisearch; rm -f ${SEED_MARKER} ${SEED_SKIPPED}; /seed_chroma.sh"
touch "$SEED_SKIPPED"
exit 0
