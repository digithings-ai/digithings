#!/usr/bin/env bash
# DIG-2409 ROLLBACK. Paste-ready. Restores the original bytes and re-verifies
# sha256, so the operator can prove the restore rather than assume it.
#
# Restore source, in order of preference:
#   1. $HP_DIR/rollback-originals/  written by apply.sh at apply time
#   2. $HP_DIR/baseline/            the byte-for-byte copies taken before any work
# Every candidate is sha256-checked against the recorded baseline and the first
# candidate whose digest MATCHES wins. A candidate that exists but hashes wrong is
# rejected and the next one is tried, rather than aborting the whole rollback: a
# stale or hand-edited backup must not be able to strand the install half-patched.
# The chosen source is named in the log so the restore is auditable.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

log "DIG-2409 rollback - pinned $PINNED_VERSION"
assert_pinned_install
assert_shas_recorded

BACKUP_DIR="$HERE/rollback-originals"

log "choosing restore source"
# pick_source <rel> <expected-baseline-sha>
# Sets PICK_SRC to the chosen path on success; leaves it empty on failure.
# Diagnostics go to the log as the candidates are evaluated, so a rejected
# candidate is visible in the transcript rather than silently skipped.
PICK_SRC=""
pick_source() {
  local rel="$1" want="$2" flat cand got rejected=""
  flat="$(echo "$rel" | tr '/' '_')"
  for cand in "$BACKUP_DIR/$flat" "$BASELINE_DIR/$rel"; do
    if [[ ! -f "$cand" ]]; then
      continue
    fi
    got="$(sha "$cand")"
    if [[ "$got" == "$want" ]]; then
      [[ -n "$rejected" ]] && bad "$rel: ignoring bad candidate(s) $rejected"
      PICK_SRC="$cand"
      return 0
    fi
    rejected="$rejected $cand(sha256 $got)"
  done
  [[ -n "$rejected" ]] && bad "$rel: no candidate matches baseline $want; rejected:$rejected"
  [[ -z "$rejected" ]] && bad "$rel: no restore candidate found (looked in $BACKUP_DIR/$flat and $BASELINE_DIR/$rel)"
  PICK_SRC=""
  return 1
}

log "restoring original bytes"
status=0
for f in "${FILES[@]}"; do
  want=$(expected_sha baseline "$f")
  if ! pick_source "$f" "$want"; then
    bad "$f: refusing to restore. Live file is left exactly as it is."
    status=1
    continue
  fi
  cp -p "$PICK_SRC" "$LIVE_DIST/$f"
  ok "restored $f  from $PICK_SRC"
done

log "re-verifying sha256 of the restored live files"
for f in "${FILES[@]}"; do
  got=$(sha "$LIVE_DIST/$f")
  want=$(expected_sha baseline "$f")
  if [[ "$got" == "$want" ]]; then
    ok "$f  BASELINE  $got  (byte-identical to how we found it)"
  else
    bad "$f  got $got, expected baseline $want"
    status=1
  fi
done

log "result"
if [[ $status -eq 0 ]]; then
  ok "rollback complete, live tree is back to the recorded baseline"
else
  bad "rollback INCOMPLETE - do not restart the server"
fi
echo
echo "NOT DONE BY THIS SCRIPT: restart the server. The window card owns that step."
exit $status