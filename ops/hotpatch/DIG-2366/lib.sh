#!/usr/bin/env bash
# DIG-2366 hotpatch - shared config and helpers.
#
# Baseline: ~/.paperclip/cli/installs/npm/2026.1001.0/node_modules/@paperclipai/server/dist
# Nothing in here changes the symlink ~/.paperclip/cli/current, restarts the
# server, or runs an install or upgrade.

set -euo pipefail

PINNED_VERSION="2026.1001.0"
# CLI_ROOT defaults to the live store. The rehearsal and the failure-path tests
# override it to point the whole toolchain at a clone; nothing else changes.
CLI_ROOT="${DIG2366_CLI_ROOT:-$HOME/.paperclip/cli}"
INSTALL_DIR="$CLI_ROOT/installs/npm/$PINNED_VERSION"
LIVE_DIST="$INSTALL_DIR/node_modules/@paperclipai/server/dist"
CURRENT_LINK="$CLI_ROOT/current"
INSTALL_JSON="$CLI_ROOT/install.json"

HP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$HP_DIR/baseline"
PATCHED_DIR="$HP_DIR/patched"
PATCH_FILE="$HP_DIR/DIG-2366.patch"
SHA_FILE="$HP_DIR/SHA256SUMS"

# The two files, as relative paths inside the bundle tree.
FILES=(
  "services/documents.js"
  "routes/issues.js"
)

log()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m  %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; }

sha() { shasum -a 256 "$1" | awk '{print $1}'; }

# Assert the running instance is still the pinned build, so we never patch a
# tree that is not the one the window card describes.
assert_pinned_install() {
  local version channel link_target
  version=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$INSTALL_JSON") \
    || { bad "cannot read $INSTALL_JSON. Stop."; return 1; }
  channel=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["channel"])' "$INSTALL_JSON")
  link_target=$(readlink "$CURRENT_LINK" 2>/dev/null) \
    || { bad "$CURRENT_LINK is missing or is not a symlink. Stop."; return 1; }
  if [[ "$version" != "$PINNED_VERSION" ]]; then
    bad "install.json says version $version, expected $PINNED_VERSION. Stop."
    return 1
  fi
  ok "install.json: version $version channel $channel"
  if [[ "$link_target" != "installs/npm/$PINNED_VERSION" ]]; then
    bad "current -> $link_target, expected installs/npm/$PINNED_VERSION. Stop."
    return 1
  fi
  ok "current -> $link_target (unchanged)"
  [[ -d "$LIVE_DIST" ]] || { bad "live dist missing: $LIVE_DIST"; return 1; }
  ok "live dist present"
}

expected_sha() {
  # expected_sha <baseline|patched> <relpath>
  #
  # Read from the recorded SHA256SUMS rather than by re-hashing the trees, so a
  # corrupted or swapped patched/ file cannot quietly redefine what "patched"
  # means. assert_shas_recorded() is what keeps the two in step.
  awk -v want="$1/$2" '$2 == want { print $1 }' "$SHA_FILE"
}

# The recorded digests and the files on disk must agree. If they do not, either
# a tree was rebuilt or the record was edited by hand, and every other check in
# this toolchain is answering against a lie.
assert_shas_recorded() {
  local rel want got
  for rel in "${FILES[@]}"; do
    for kind in baseline patched; do
      want="$(awk -v k="$kind/$rel" '$2 == k { print $1 }' "$SHA_FILE")"
      if [ -z "$want" ]; then
        bad "$kind/$rel is missing from SHA256SUMS. Stop."
        return 1
      fi
      if [ "$kind" = baseline ]; then got="$(sha "$BASELINE_DIR/$rel")"; else got="$(sha "$PATCHED_DIR/$rel")"; fi
      if [ "$want" != "$got" ]; then
        bad "$kind/$rel on disk is $got but SHA256SUMS records $want. Stop."
        return 1
      fi
    done
  done
  ok "SHA256SUMS matches all four files on disk"
}