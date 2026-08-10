#!/bin/sh
# Wait until Chroma seed oneshot finishes (or times out), then start digisearch.
# Avoids opening Chroma PersistentClient while CLI ingest holds the SQLite lock.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
SEED_VER="v3"
SEED_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_VER}"
SEED_SKIPPED="${DATA_CHROMA}/.stack_chroma_seed_skipped_${SEED_VER}"

mkdir -p "$DATA_CHROMA"

i=0
while [ ! -f "$SEED_MARKER" ] && [ ! -f "$SEED_SKIPPED" ]; do
  i=$((i + 1))
  if [ "$i" -gt 180 ]; then
    echo "digithings-stack: chroma seed wait timed out; starting digisearch"
    touch "$SEED_SKIPPED"
    break
  fi
  sleep 1
done

exec uvicorn digisearch.server:app --host 127.0.0.1 --port 8002
