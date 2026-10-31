#!/usr/bin/env bash
# Refuse a digithings.lock that points at a path, a branch head or a non-sha.
set -euo pipefail
source "$(dirname "$0")/env.sh"
kind="$(lock kind)"
case "$kind" in
  git-sha)
    sha="$(lock sha)"; ref="$(lock ref)"
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "lock: sha must be a full 40-char sha" >&2; exit 1; }
    [ "$ref" = develop ] || [ "$ref" = main ] || { echo "lock: interim pins must be on develop or main, not '$ref'" >&2; exit 1; }
    ;;
  release) grep -Eq '^(image|pypi|npm)\.' "$CLIENT_DIR/digithings.lock" || { echo "lock: no artifacts listed" >&2; exit 1; } ;;
  *) echo "lock: unknown kind '$kind'" >&2; exit 1 ;;
esac
[ ! -f "$CLIENT_DIR/.link" ] || echo "note: linked to $(cat "$CLIENT_DIR/.link") (make unlink before committing)" >&2
echo "lock OK ($kind)"
