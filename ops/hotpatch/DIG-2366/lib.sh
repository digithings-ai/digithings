#!/usr/bin/env bash
# DIG-2366 hotpatch - shared config and helpers.
#
# Baseline: ~/.paperclip/cli/installs/npm/2026.1001.0/node_modules/@paperclipai/server/dist
# Nothing in here changes the symlink ~/.paperclip/cli/current, restarts the
# server, or runs an install or upgrade.

set -euo pipefail

PINNED_VERSION="2026.1001.0"
CLI_ROOT="$HOME/.paperclip/cli"
INSTALL_DIR="$CLI_ROOT/installs/npm/$PINNED_VERSION"
LIVE_DIST="$INSTALL_DIR/node_modules/@paperclipai/server/dist"
CURRENT_LINK="$CLI_ROOT/current"
INSTALL_JSON="$CLI_ROOT/install.json"

HP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASELINE_DIR="$HP_DIR/baseline"
PATCHED_DIR="$HP_DIR/patched"
PATCH_FILE="$HP_DIR/DIG-2366.patch"

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
  version=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$INSTALL_JSON")
  channel=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["channel"])' "$INSTALL_JSON")
  link_target=$(readlink "$CURRENT_LINK")
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
  sha "$([[ $1 == baseline ]] && echo "$BASELINE_DIR/$2" || echo "$PATCHED_DIR/$2")"
}