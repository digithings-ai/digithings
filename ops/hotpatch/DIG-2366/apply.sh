#!/usr/bin/env bash
# DIG-2366 APPLY. Paste-ready. Run from anywhere.
#
# What it does: overwrites exactly two files inside the pinned bundle tree with
# the patched bytes from this directory. Nothing else. It does not touch the
# `current` symlink, does not restart the server, does not run an install or an
# upgrade.
#
# Prerequisite: the server is stopped for the window. Applying while the server
# is running gives you a half-patched process, because Node has already loaded
# the old bytes into memory. The window card carries the restart step; this
# script deliberately does not restart anything.

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$HERE/lib.sh"

log "DIG-2366 apply - pinned $PINNED_VERSION"
assert_pinned_install

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
  cp -p "$live" "$BACKUP_DIR/$(echo "$f" | tr '/' '_')"
  got=$(sha "$BACKUP_DIR/$(echo "$f" | tr '/' '_')")
  want=$(expected_sha baseline "$f")
  if [[ "$got" != "$want" ]]; then
    bad "$f: live sha256 $got != recorded baseline $want. The baseline drifted; stop and re-stage."
    exit 1
  fi
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