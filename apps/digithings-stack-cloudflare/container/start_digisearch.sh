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

SEED_VER="v5"
# Must match seed_chroma.sh's tag exactly; see the SEED_TAG comment there.
SEED_PROVIDER="$(printf '%s' "${DIGISEARCH_EMBEDDING_PROVIDER:-all-MiniLM-L6-v2-384}" \
  | tr -c 'A-Za-z0-9._-' '_')"
SEED_TAG="${SEED_VER}_${SEED_PROVIDER}"
SEED_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_TAG}"
SEED_FAILED="${DATA_CHROMA}/.stack_chroma_seed_failed_${SEED_TAG}"
UNSEEDED_LIST="${DATA_CHROMA}/.stack_chroma_unseeded_${SEED_TAG}"
# Same convention, written by seed_occ_tickets.sh for the ticket corpus.
TICKET_UNSEEDED="${DATA_CHROMA}/.stack_occ_tickets_unseeded_${SEED_TAG}"
TICKET_MARKER="${DATA_CHROMA}/.stack_occ_tickets_seeded_${SEED_TAG}"

mkdir -p "$DATA_CHROMA"

# Indexes this boot's seed could not populate, exported so digisearch refuses to
# answer from an empty collection instead of returning zero hits that read as
# "nothing relevant found". Empty (the default) means seeded, which keeps the
# guard inert for local compose and any bare digisearch process.
DIGISEARCH_UNSEEDED_INDEXES=""
export DIGISEARCH_UNSEEDED_INDEXES

# Arm the guard from whatever the seed recorded, then let the marker decide
# whether to wait. Arming first matters: a stale failure marker from an earlier
# boot must not suppress a freshly-written success marker's clean state.
if [ -f "$UNSEEDED_LIST" ]; then
  DIGISEARCH_UNSEEDED_INDEXES="$(cat "$UNSEEDED_LIST")"
fi

# Only SEED_MARKER means "seeded successfully" (SEED_FAILED means seed_chroma.sh
# exited nonzero). We still start digisearch either way: a hard refusal would
# take down web_search, the MCP server and every other index over one bad seed,
# and the container sleeps after 3 idle minutes, so the next cold start retries.
# Failing the unseeded index at query time keeps the blast radius on the corpus
# that is actually missing (#5045).
i=0
while [ ! -f "$SEED_MARKER" ]; do
  if [ -f "$SEED_FAILED" ]; then
    echo "digithings-stack: ERROR chroma seed ${SEED_TAG} FAILED (unseeded: ${DIGISEARCH_UNSEEDED_INDEXES:-unknown}); queries against those indexes will error"
    break
  fi
  i=$((i + 1))
  if [ "$i" -gt 600 ]; then
    # Unknown state: the seed may still be running or may have died without
    # writing either marker. Arm the guard for both seeded indexes rather than
    # guess — a loud, retryable error beats a confident empty answer.
    DIGISEARCH_UNSEEDED_INDEXES="digithings_docs,occ_help"
    echo "digithings-stack: ERROR chroma seed ${SEED_TAG} wait timed out (no success or failure marker); treating both seeded indexes as unseeded"
    break
  fi
  sleep 1
done

if [ -f "$SEED_MARKER" ]; then
  DIGISEARCH_UNSEEDED_INDEXES=""
fi

# Now wait for the ticket backfill to settle and fold its verdict in. Either
# marker means seed_occ_tickets.sh reached a decision (it writes both when it
# skips for a missing credential), so this cannot hang on an unconfigured
# deployment. A timeout here means the step never ran or died silently — treat
# occ_tickets as unpopulated rather than assuming a corpus exists (#5045).
j=0
while [ ! -f "$TICKET_MARKER" ] && [ ! -f "$TICKET_UNSEEDED" ]; do
  j=$((j + 1))
  if [ "$j" -gt 900 ]; then
    DIGISEARCH_UNSEEDED_INDEXES="${DIGISEARCH_UNSEEDED_INDEXES:+${DIGISEARCH_UNSEEDED_INDEXES},}occ_tickets"
    echo "digithings-stack: ERROR occ_tickets backfill never settled; treating occ_tickets as unseeded"
    break
  fi
  sleep 1
done

if [ -f "$TICKET_UNSEEDED" ]; then
  DIGISEARCH_UNSEEDED_INDEXES="${DIGISEARCH_UNSEEDED_INDEXES:+${DIGISEARCH_UNSEEDED_INDEXES},}occ_tickets"
fi

export DIGISEARCH_UNSEEDED_INDEXES

exec uvicorn digisearch.server:app --host 0.0.0.0 --port 8002
