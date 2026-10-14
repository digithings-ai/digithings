#!/bin/sh
# One-shot Chroma seed for Profile A. Runs under supervisord *after* digigraph
# binds and *before* digisearch opens PersistentClient (SQLite lock + CF port delay).
#
# Seeds:
#   - digithings_docs  ← /seed/digithings_docs  (digithings.ai/chat)
#   - occ_help         ← /seed/occ_help         (digithings.ai/chat/occ)
#
# Marker version: bump SEED_VER when seed markdown changes. The marker name also
# folds in the embedding provider, so switching providers invalidates the seed
# instead of leaving the old model's vectors in place under a new model's
# queries — the two are the same dimension, so nothing detects that mismatch
# (see chroma.py::_assert_collection_model). shared-vN bump still recommended
# on CF.
set -eu

DATA_CHROMA="${CHROMA_PATH:-/data/chroma}"
# Seed markdown root. Overridable so the local compose stack and the shell tests
# can point at a checkout instead of the image-baked /seed.
SEED_ROOT="${DIGISEARCH_SEED_ROOT:-/seed}"

# DIGI_VECTORIZE_ACTIVE is computed once in entrypoint.sh (delegated to
# python3 so it agrees with digisearch's own os.environ.get(...).strip()
# check byte-for-byte) and exported before supervisord starts this oneshot;
# default to unconfigured (0) under set -u if it were ever missing, which
# reproduces today's behaviour of running the full seed.
if [ "${DIGI_VECTORIZE_ACTIVE:-0}" = "1" ]; then
  echo "digithings-stack: Vectorize configured; skipping chroma seed"
  exit 0
fi

SEED_VER="v5"
# Provider id goes into the marker so a provider change forces a re-seed.
# Sanitised to [A-Za-z0-9._-] because it becomes part of a filename; the
# default matches providers/minilm.py when DIGISEARCH_EMBEDDING_PROVIDER is unset.
SEED_PROVIDER="$(printf '%s' "${DIGISEARCH_EMBEDDING_PROVIDER:-all-MiniLM-L6-v2-384}" \
  | tr -c 'A-Za-z0-9._-' '_')"
SEED_TAG="${SEED_VER}_${SEED_PROVIDER}"
SEED_MARKER="${DATA_CHROMA}/.stack_chroma_seeded_${SEED_TAG}"
# Failure is NOT gated here: a failed run must retry on the next boot rather
# than being remembered as "done/skipped" forever.
SEED_FAILED="${DATA_CHROMA}/.stack_chroma_seed_failed_${SEED_TAG}"
# Comma-separated index names this boot failed to populate. start_digisearch.sh
# exports it into digisearch so a query against an index this boot could not
# seed fails loudly instead of returning zero hits it looks like an answer for.
UNSEEDED_LIST="${DATA_CHROMA}/.stack_chroma_unseeded_${SEED_TAG}"

# Legacy markers (v1 oneshot only seeded occ_help; v2-v4 were not
# provider-qualified) — ignore them, this tag always re-seeds.
mkdir -p "$DATA_CHROMA"

if [ -f "$SEED_MARKER" ]; then
  echo "digithings-stack: chroma seed ${SEED_TAG} already done"
  exit 0
fi

# Prefer edge readiness before heavy Chroma/embedding download (CF probes :8000).
i=0
while [ "$i" -lt 90 ]; do
  if curl -sf --connect-timeout 2 --max-time 5 "http://127.0.0.1:8000/healthz" >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

UNSEEDED=""

seed_index() {
  index_name="$1"
  seed_dir="$2"
  # A missing seed dir is a build error, not an empty corpus: both dirs ship in
  # the image, so their absence means the image is wrong. Counting it as a skip
  # is how a broken image reports a successful seed over an empty index (#5045).
  if [ ! -d "$seed_dir" ]; then
    echo "digithings-stack: ERROR seed dir ${seed_dir} is missing for index ${index_name}"
    return 1
  fi
  echo "digithings-stack: seeding ${index_name} from ${seed_dir}"
  # `digisearch ingest` exits non-zero when it records no result for any input
  # file (#5045), so an embed failure like a model download error propagates
  # here instead of reporting "Total chunks: 0" as success.
  CHROMA_PATH="$DATA_CHROMA" DIGISEARCH_ALLOW_STUB=0 \
    digisearch ingest --index "$index_name" "$seed_dir"
}

record_failure() {
  echo "digithings-stack: WARN $1 seed failed"
  if [ -z "$UNSEEDED" ]; then
    UNSEEDED="$1"
  else
    UNSEEDED="${UNSEEDED},$1"
  fi
}

seed_index digithings_docs "${SEED_ROOT}/digithings_docs" || record_failure digithings_docs
seed_index occ_help "${SEED_ROOT}/occ_help" || record_failure occ_help

if [ -z "$UNSEEDED" ]; then
  touch "$SEED_MARKER"
  rm -f "$SEED_FAILED" "$UNSEEDED_LIST" \
    "${DATA_CHROMA}/.occ_help_seeded" "${DATA_CHROMA}/.occ_help_seed_skipped" \
    "${DATA_CHROMA}/.digithings_docs_seeded" 2>/dev/null || true
  echo "digithings-stack: chroma seed ${SEED_TAG} complete (digithings_docs + occ_help)"
  exit 0
fi

# Fail closed: no SEED_MARKER is written, so start_digisearch.sh does not treat
# this as done, and the NEXT container boot retries from scratch. The index list
# is what lets digisearch fail a query loudly instead of returning zero hits it
# looks like an answer for.
printf '%s' "$UNSEEDED" > "$UNSEEDED_LIST"
echo "digithings-stack: ERROR chroma seed ${SEED_TAG} incomplete (${UNSEEDED}); will retry on next boot"
echo "digithings-stack: re-seed now: supervisorctl stop digisearch; rm -f ${SEED_MARKER}; /seed_chroma.sh"
touch "$SEED_FAILED"
exit 1
