#!/bin/sh
# Wait until Chroma seed oneshot finishes (or times out), then start digisearch.
# Avoids opening Chroma PersistentClient while CLI ingest holds the SQLite lock.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"

# DIGI_VECTORIZE_ACTIVE is computed once in entrypoint.sh (whitespace-trimmed
# the same way digisearch's Python side trims) and exported before supervisord
# starts this program; default to unconfigured (0) under set -u if it were
# ever missing, which reproduces today's behaviour of waiting for the marker.
if [ "${DIGI_VECTORIZE_ACTIVE:-0}" = "1" ]; then
  echo "digithings-stack: Vectorize configured; starting digisearch without seed wait"
  exec uvicorn digisearch.server:app --host 127.0.0.1 --port 8002
fi

SEED_VER="v3"
SEED_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_VER}"
SEED_FAILED="${DATA_CHROMA}/.stack_chroma_seed_failed_${SEED_VER}"

mkdir -p "$DATA_CHROMA"

# Only SEED_MARKER means "seeded successfully". SEED_FAILED (seed_chroma.sh
# exited nonzero) is NOT treated as done — we still wait out the readiness
# window below, but log this loudly since it means the corpus is missing or
# partial and digisearch is about to open on an unseeded/stale Chroma volume.
i=0
while [ ! -f "$SEED_MARKER" ]; do
  if [ -f "$SEED_FAILED" ]; then
    echo "digithings-stack: WARN chroma seed ${SEED_VER} FAILED; digisearch will start unseeded/partial"
    break
  fi
  i=$((i + 1))
  if [ "$i" -gt 180 ]; then
    echo "digithings-stack: WARN chroma seed wait timed out (no success or failure marker); starting digisearch anyway"
    break
  fi
  sleep 1
done

exec uvicorn digisearch.server:app --host 127.0.0.1 --port 8002
