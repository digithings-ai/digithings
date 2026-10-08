#!/usr/bin/env bash
# DIG-2409 ROLLBACK. Paste-ready. Restores the original bytes and re-verifies
# sha256, so the operator can prove the restore rather than assume it.
#
# Restore source, in order of preference:
#   1. $HP_DIR/rollback-originals/  written by apply.sh at apply time
#   2. $HP_DIR/baseline/            the byte-for-byte copies taken before any work
# Both are sha256-checked against the recorded baseline, so a wrong or truncated
# source cannot be restored silently.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

log "DIG-2409 rollback - pinned $PINNED_VERSION"
assert_pinned_install
assert_shas_recorded

BACKUP_DIR="$HERE/rollback-originals"

log "choosing restore source"
pick_source() {
  local rel="$1" flat
  flat="$(echo "$rel" | tr '/' '_')"
  if [[ -f "$BACKUP_DIR/$flat" ]]; then
    echo "$BACKUP_DIR/$flat"
  else
    echo "$BASELINE_DIR/$rel"
  fi
}

log "restoring original bytes"
status=0
for f in "${FILES[@]}"; do
  src="$(pick_source "$f")"
  want=$(expected_sha baseline "$f")
  got=$(sha "$src")
  if [[ "$got" != "$want" ]]; then
    bad "$f: restore source $src has sha256 $got, recorded baseline is $want. Refusing to restore."
    status=1
    continue
  fi
  cp -p "$src" "$LIVE_DIST/$f"
  ok "restored $f  from $src"
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