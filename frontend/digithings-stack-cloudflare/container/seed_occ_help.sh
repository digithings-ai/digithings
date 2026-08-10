#!/bin/sh
# One-shot OCC Chroma seed. Runs under supervisord *after* digikey/digigraph bind
# and *before* digisearch opens PersistentClient (avoids SQLite lock + CF port delay).
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
SEED_MARKER="${DATA_CHROMA}/.occ_help_seeded"
SEED_SKIPPED="${DATA_CHROMA}/.occ_help_seed_skipped"

mkdir -p "$DATA_CHROMA"

if [ -f "$SEED_MARKER" ] || [ -f "$SEED_SKIPPED" ]; then
  echo "digithings-stack: occ_help seed already done/skipped"
  exit 0
fi

if [ ! -d /seed/occ_help ]; then
  echo "digithings-stack: no /seed/occ_help; skipping"
  touch "$SEED_SKIPPED"
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

echo "digithings-stack: seeding occ_help index from /seed/occ_help (post-edge, pre-digisearch)"
if CHROMA_PATH="$DATA_CHROMA" DIGISEARCH_ALLOW_STUB=0 \
  digisearch ingest --index occ_help /seed/occ_help; then
  touch "$SEED_MARKER"
  rm -f "$SEED_SKIPPED"
  echo "digithings-stack: occ_help seed complete"
  exit 0
fi

echo "digithings-stack: WARN occ_help seed failed (continuing boot; digisearch will start)"
echo "digithings-stack: re-seed later: CHROMA_PATH=$DATA_CHROMA digisearch ingest --index occ_help /seed/occ_help"
touch "$SEED_SKIPPED"
exit 0
