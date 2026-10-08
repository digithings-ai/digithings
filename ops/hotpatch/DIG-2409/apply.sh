#!/usr/bin/env bash
# DIG-2409 APPLY. Paste-ready. Run from anywhere.
#
# What it does: overwrites exactly two files inside the pinned bundle tree with
# the patched bytes from this directory. Nothing else. It does not touch the
# `current` symlink, does not restart the server, does not run an install or an
# upgrade.
#
# Prerequisite: none, and in particular you do NOT need to stop the server first.
# Node loads a module once, so a running process keeps serving the OLD bytes from
# memory and never re-reads these files. Between apply and restart the instance
# therefore behaves exactly as it does today, which is not a new risk. Follow the
# apply with the window card's restart step (`paperclipai service restart`, which
# drains in-flight runs) and the new bytes load. Stopping the server first is the
# cold route: a full boot instead of the measured 4s hot restart, for no gain.
#
# This script deliberately does not restart anything - the window card owns that.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

log "DIG-2409 apply - pinned $PINNED_VERSION"
assert_pinned_install
assert_shas_recorded

log "pre-flight: staged bytes are present"
for f in "${FILES[@]}"; do
  [[ -f "$PATCHED_DIR/$f" ]] || { bad "missing $PATCHED_DIR/$f"; exit 1; }
  ok "patched/$f  $(expected_sha patched "$f")"
done

log "backing up the live bytes (rollback source)"
BACKUP_DIR="$HERE/rollback-originals"
mkdir -p "$BACKUP_DIR"
for f in "${FILES[@]}"; do
  live="$LIVE_DIST/$f"
  [[ -f "$live" ]] || { bad "missing live file $live"; exit 1; }
  # Stage into a temp name and only promote it into rollback-originals/ once its
  # digest matches the recorded baseline. Copying straight into rollback-originals/
  # and checking afterwards would leave the untrusted bytes there when we abort
  # below, which destroys the rollback source for the files already staged in this
  # same loop. On the live install the refusal path is the NORMAL path, so that
  # damage is guaranteed rather than unlikely.
  slot="$BACKUP_DIR/$(echo "$f" | tr '/' '_')"
  tmp="$slot.incoming.$$"
  cp -p "$live" "$tmp"
  got=$(sha "$tmp")
  want=$(expected_sha baseline "$f")
  if [[ "$got" != "$want" ]]; then
    rm -f "$tmp"
    bad "$f: live sha256 $got != recorded baseline $want. The baseline drifted; stop and re-stage."
    bad "$f: rollback-originals left untouched, so any previous good backup is still usable."
    exit 1
  fi
  mv -f "$tmp" "$slot"
  ok "$f  backed up  $got"
done

log "applying"
for f in "${FILES[@]}"; do
  cp "$PATCHED_DIR/$f" "$LIVE_DIST/$f"
  got=$(sha "$LIVE_DIST/$f")
  want=$(expected_sha patched "$f")
  [[ "$got" == "$want" ]] || { bad "$f did not land ($got != $want)"; exit 1; }
  ok "$f  applied  $got"
done

log "apply complete"
echo "Rollback source: $BACKUP_DIR"
echo "Verify with: $HERE/verify.sh"
echo "Roll back with: $HERE/rollback.sh"
echo
echo "NOT DONE BY THIS SCRIPT: restart the server. The window card owns that step."