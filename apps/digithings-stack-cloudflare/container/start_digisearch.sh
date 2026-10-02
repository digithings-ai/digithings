#!/bin/sh
# Wait until Chroma seed oneshot finishes (or times out), then start digisearch.
# Avoids opening Chroma PersistentClient while CLI ingest holds the SQLite lock.
#
# Binds 0.0.0.0, not loopback: the Worker proxies to the container network
# address (e.g. 10.0.0.1:8002), so a 127.0.0.1 bind is unreachable — #4071.
# In-container callers keep using DIGISEARCH_URL=http://127.0.0.1:8002
# (0.0.0.0 includes loopback).
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"

# DIGI_VECTORIZE_ACTIVE is computed once in entrypoint.sh (delegated to
# python3 so it agrees with digisearch's own os.environ.get(...).strip()
# check byte-for-byte) and exported before supervisord starts this program;
# default to unconfigured (0) under set -u if it were ever missing, which
# reproduces today's behaviour of waiting for the marker.
if [ "${DIGI_VECTORIZE_ACTIVE:-0}" = "1" ]; then
  echo "digithings-stack: Vectorize configured; starting digisearch without seed wait"
  exec uvicorn digisearch.server:app --host 0.0.0.0 --port 8002
fi

# Must equal SEED_VER in seed_chroma.sh — the seeder writes the marker under
# this name and, on a version bump, deletes the previous one. If these drift,
# the wait below can never observe SEED_MARKER (seed_chroma.sh removes the old
# marker on every boot), so every boot silently burns the full readiness window
# and a real seed failure degrades to the generic timeout WARN instead of the
# loud SEED_FAILED one. tests/scripts/test_stack_seed_version_parity.py pins
# the two literals together so a bump cannot land in only one file.
SEED_VER="v5"
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

exec uvicorn digisearch.server:app --host 0.0.0.0 --port 8002
