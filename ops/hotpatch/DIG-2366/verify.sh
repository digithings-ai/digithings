#!/usr/bin/env bash
# DIG-2366 VERIFY. Paste-ready. Read-only: it changes nothing.
#
# Three independent checks:
#   1. bytes   - sha256 of both live files is either the recorded baseline or the
#                recorded patched value, and reports which.
#   2. parse   - both live files parse as ESM.
#   3. markers - the fault-1 id fallback and the fault-2 422 guard are present
#                in the bytes that are actually on disk.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

log "DIG-2366 verify - pinned $PINNED_VERSION"
assert_pinned_install

status=0

log "1/3 bytes"
for f in "${FILES[@]}"; do
  live="$LIVE_DIST/$f"
  got=$(sha "$live")
  base=$(expected_sha baseline "$f")
  pat=$(expected_sha patched "$f")
  if [[ "$got" == "$pat" ]]; then
    ok "$f  PATCHED    $got"
  elif [[ "$got" == "$base" ]]; then
    ok "$f  BASELINE   $got  (hotpatch not applied)"
  else
    bad "$f  UNKNOWN    $got  (neither baseline $base nor patched $pat)"
    status=1
  fi
done

log "2/3 parse"
TMPP="$(mktemp -d)"
trap 'rm -rf "$TMPP"' EXIT
for f in "${FILES[@]}"; do
  cp "$LIVE_DIST/$f" "$TMPP/$(basename "$f" .js).mjs"
  if node --check "$TMPP/$(basename "$f" .js).mjs" 2>/dev/null; then
    ok "$f  parses as ESM"
  else
    bad "$f  does not parse"
    status=1
  fi
done

log "3/3 fault markers"
DOC="$LIVE_DIST/services/documents.js"
ISS="$LIVE_DIST/routes/issues.js"

if grep -q 'resolveIssueDocumentKey' "$DOC"; then
  n=$(grep -c 'resolveIssueDocumentKey(db' "$DOC")
  ok "fault 1 present: resolveIssueDocumentKey wired into $n request paths"
else
  bad "fault 1 absent: no resolveIssueDocumentKey in services/documents.js"
  status=1
fi

if grep -q 'eq(documents.id, key)' "$DOC"; then
  ok "fault 1 present: id fallback predicate eq(documents.id, key)"
else
  bad "fault 1 absent: no documents.id fallback predicate"
  status=1
fi

if grep -q 'review_interaction_requires_in_review' "$ISS"; then
  ok "fault 2 present: 422 guard review_interaction_requires_in_review"
else
  bad "fault 2 absent: no 422 guard in routes/issues.js"
  status=1
fi

log "result"
if [[ $status -eq 0 ]]; then
  ok "verify passed"
else
  bad "verify FAILED"
fi
exit $status