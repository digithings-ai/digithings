#!/bin/sh
# Wait until OCC seed oneshot finishes (or times out), then start digisearch.
# Avoids opening Chroma PersistentClient while CLI ingest holds the SQLite lock.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
SEED_MARKER="${DATA_CHROMA}/.occ_help_seeded"
SEED_SKIPPED="${DATA_CHROMA}/.occ_help_seed_skipped"

mkdir -p "$DATA_CHROMA"

i=0
while [ ! -f "$SEED_MARKER" ] && [ ! -f "$SEED_SKIPPED" ]; do
  i=$((i + 1))
  if [ "$i" -gt 180 ]; then
    echo "digithings-stack: seed wait timed out; starting digisearch"
    touch "$SEED_SKIPPED"
    break
  fi
  sleep 1
done

exec uvicorn digisearch.server:app --host 127.0.0.1 --port 8002
