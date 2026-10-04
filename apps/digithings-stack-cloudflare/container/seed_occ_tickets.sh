#!/bin/sh
# Backfill the Zammad ticket corpus into the `occ_tickets` digisearch index.
#
# Separate from seed_chroma.sh because this corpus has a different shape: it
# comes from the live Zammad API rather than markdown baked into the image, it
# needs a credential, and it can take minutes. Both scripts write the same
# unseeded-marker convention so start_digisearch.sh can arm one guard across
# every corpus the boot failed to populate (#5045).
#
# Ordering: runs after seed_chroma.sh and before digisearch opens the Chroma
# PersistentClient, because both writers hold the same SQLite lock. supervisord
# priority only orders the spawn, so the settle-wait below is what actually
# enforces it — same reason start_digisearch.sh polls for a marker.
#
# Credential: ZAMMAD_API_TOKEN, supplied as a Cloudflare secret. Never baked
# into the image and never logged — only its presence is checked.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
TICKET_INDEX="occ_tickets"

# Must match seed_chroma.sh's tag exactly; see the SEED_TAG comment there.
SEED_VER="v5"
SEED_PROVIDER="$(printf '%s' "${DIGISEARCH_EMBEDDING_PROVIDER:-all-MiniLM-L6-v2-384}" \
  | tr -c 'A-Za-z0-9._-' '_')"
SEED_TAG="${SEED_VER}_${SEED_PROVIDER}"

CHROMA_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_TAG}"
CHROMA_FAILED="${DATA_CHROMA}/.stack_chroma_seed_failed_${SEED_TAG}"
TICKET_MARKER="${DATA_CHROMA}/.stack_occ_tickets_seeded_${SEED_TAG}"
# Names the index, so start_digisearch.sh can union it into the guard.
TICKET_UNSEEDED="${DATA_CHROMA}/.stack_occ_tickets_unseeded_${SEED_TAG}"

# Vectorize is a remote index: CHROMA_PATH is unset by entrypoint.sh and this
# script's whole Chroma path would be wrong. Mirrors seed_chroma.sh's bypass.
if [ "${DIGI_VECTORIZE_ACTIVE:-0}" = "1" ]; then
  echo "digithings-stack: Vectorize configured; skipping occ_tickets backfill"
  mkdir -p "$DATA_CHROMA" 2>/dev/null || true
  : > "$TICKET_MARKER"
  exit 0
fi

mkdir -p "$DATA_CHROMA"

# Already done this boot — nothing to do.
if [ -f "$TICKET_MARKER" ]; then
  echo "digithings-stack: occ_tickets already backfilled (${SEED_TAG})"
  exit 0
fi

# Wait for seed_chroma.sh to settle so we never race it for the SQLite lock.
# Bound the wait: a seed that dies without writing either marker must not pin
# this program open forever.
i=0
while [ ! -f "$CHROMA_MARKER" ] && [ ! -f "$CHROMA_FAILED" ]; do
  i=$((i + 1))
  if [ "$i" -gt 900 ]; then
    echo "digithings-stack: ERROR chroma seed ${SEED_TAG} never settled; skipping occ_tickets backfill to avoid racing the seed for the DB lock"
    : > "$TICKET_UNSEEDED"
    printf '%s' "$TICKET_INDEX" > "$TICKET_UNSEEDED"
    exit 1
  fi
  sleep 1
done

# Not configured is a legitimate state: local compose and any deployment that
# does not set ZAMMAD_API_TOKEN still need the markdown corpora. Non-fatal, so
# the container boots and digithings_docs / occ_help still serve. The corpus is
# still recorded as unpopulated, because that is the truth — a tenant that fans
# out to occ_tickets without credentials then gets an explicit
# "corpus_not_seeded" instead of a confident empty answer.
if [ -z "${ZAMMAD_API_TOKEN:-}" ]; then
  echo "digithings-stack: occ_tickets backfill skipped (ZAMMAD_API_TOKEN not set)"
  printf '%s' "$TICKET_INDEX" > "$TICKET_UNSEEDED"
  : > "$TICKET_MARKER"
  exit 0
fi

# The script pins DIGISEARCH_EMBEDDING_PROVIDER to the multilingual model id and
# verifies the collection's model stamp afterwards, so the vectors it writes are
# the ones the query path will compare against. CHROMA_PATH is already exported.
echo "digithings-stack: backfilling ${TICKET_INDEX} from Zammad (${SEED_TAG})"
if python -m scripts.index_occ_tickets --index "$TICKET_INDEX"; then
  rm -f "$TICKET_UNSEEDED"
  : > "$TICKET_MARKER"
  echo "digithings-stack: occ_tickets backfill complete (${SEED_TAG})"
  exit 0
fi

# Expected to run and did not — the loud case.
echo "digithings-stack: ERROR occ_tickets backfill FAILED; queries against ${TICKET_INDEX} will error"
printf '%s' "$TICKET_INDEX" > "$TICKET_UNSEEDED"
exit 1
