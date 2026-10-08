#!/usr/bin/env bash
# DIG-2409 VERIFY. Paste-ready. Read-only: it changes nothing.
#
# This is the COMBINED bundle: the two DIG-2232 write faults plus the DIG-1663
# run source-issue bind, all landing in one window on one restart.
#
# Three independent checks:
#   1. bytes   - sha256 of both live files is the recorded baseline or the
#                recorded combined value, and reports which.
#   2. parse   - both live files parse as ESM.
#   3. markers - all four fixes are present in the bytes actually on disk.
#
# On "applied or not": that is a STATE, not a failure. The window card has the
# operator run this script in three places - before applying, after applying, and
# after a rollback - so two of the three sanctioned states are "not applied".
# Treating that as a failure makes the tool cry wolf in its own happy path, so it
# reports the state and only fails when the tree is incoherent (a digest matching
# neither recorded value, a file that will not parse, or the two files disagreeing
# with each other).
#
# Pass --expect combined  (or --expect baseline) to assert a specific state. That
# is what the window card uses to make the post-apply step actually gate.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

expect=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --expect) expect="${2:-}"; shift 2 ;;
    --expect=*) expect="${1#*=}"; shift ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) bad "unknown argument: $1"; exit 2 ;;
  esac
done
if [[ -n "$expect" && "$expect" != "combined" && "$expect" != "baseline" ]]; then
  bad "--expect takes 'combined' or 'baseline', got '$expect'"
  exit 2
fi

log "DIG-2409 verify - pinned $PINNED_VERSION${expect:+ (expect $expect)}"
assert_pinned_install
assert_shas_recorded

status=0
declare -a found_state=()

log "1/3 bytes"
# routes/issues.js has a third known-good state: the DIG-2232 bundle alone
# (14c2048a...), which is what you get if DIG-2366's apply.sh was run by itself.
# It is coherent but INCOMPLETE - it is missing the DIG-1663 bind - so it is
# reported rather than treated as corruption.
DIG2232_ONLY_ISSUES_SHA="14c2048a88f18a5f55100e878559ccec1de0a4f98dff76050f3018f11fe879bb"
for f in "${FILES[@]}"; do
  live="$LIVE_DIST/$f"
  got=$(sha "$live")
  base=$(expected_sha baseline "$f")
  pat=$(expected_sha patched "$f")
  if [[ "$got" == "$pat" ]]; then
    ok "$f  COMBINED   $got"
    found_state+=("combined")
  elif [[ "$f" == "routes/issues.js" && "$got" == "$DIG2232_ONLY_ISSUES_SHA" ]]; then
    printf '     --    %s  DIG-2232-ONLY  %s  (faults 1+2 landed, DIG-1663 bind missing)\n' "$f" "$got"
    found_state+=("dig2232-only")
    status=1
  elif [[ "$got" == "$base" ]]; then
    ok "$f  BASELINE   $got  (hotpatch not applied)"
    found_state+=("baseline")
  else
    bad "$f  UNKNOWN    $got  (neither baseline $base nor combined $pat)"
    found_state+=("unknown")
    status=1
  fi
done

# Half-applied is the state that matters most, and it is invisible per-file.
if [[ "${#found_state[@]}" -gt 0 ]]; then
  uniq_states="$(printf '%s\n' "${found_state[@]}" | sort -u | tr '\n' ' ')"
  n_states="$(printf '%s\n' "${found_state[@]}" | sort -u | wc -l | tr -d ' ')"
  if [[ "$n_states" -gt 1 ]]; then
    bad "HALF-APPLIED: the two files are in different states ($uniq_states)"
    status=1
  fi
fi

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

markers_present=0
markers_expected=4

marker() { # <description> <file> <pattern>
  if grep -q "$3" "$2"; then
    ok "$1"
    markers_present=$((markers_present + 1))
  else
    printf '     --    %s\n' "$1"
  fi
}

marker "fault 1: resolveIssueDocumentKey wired into $(grep -c 'resolveIssueDocumentKey(db' "$DOC") request paths" "$DOC" 'resolveIssueDocumentKey'
marker "fault 1: id fallback predicate eq(documents.id, key)" "$DOC" 'eq(documents.id, key)'
marker "fault 2: 422 guard review_interaction_requires_in_review" "$ISS" 'review_interaction_requires_in_review'
marker "DIG-1663: run_source_issue_bound_on_checkout bind" "$ISS" 'run_source_issue_bound_on_checkout'

if [[ "$markers_present" -eq "$markers_expected" ]]; then
  ok "all $markers_expected fault markers present"
  state="combined"
elif [[ "$markers_present" -eq 0 ]]; then
  # The unmodified pinned bundle has none of them. That is a coherent state.
  ok "no fault markers - these are the unpatched pinned bytes"
  state="baseline"
else
  bad "PARTIAL PATCH: $markers_present of $markers_expected fault markers. The tree is neither the baseline nor the reviewed patch - stop and roll back."
  state="partial"
  status=1
fi

if [[ -n "$expect" ]]; then
  if [[ "$state" == "$expect" ]]; then
    ok "state matches the expectation (--expect $expect)"
  else
    bad "state is '$state', not the expected '$expect'"
    status=1
  fi
fi

log "result"
echo
if [[ $status -eq 0 ]]; then
  ok "verify passed - tree is coherent, state = $state"
else
  bad "verify FAILED - do not restart the server on this tree"
fi
exit $status