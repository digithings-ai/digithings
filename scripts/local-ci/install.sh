#!/bin/sh
# Install or repoint the local-ci launchd job at a checkout of this repository.
#
#   scripts/local-ci/install.sh --dry-run          # print the plist, change nothing
#   scripts/local-ci/install.sh ~/Code/digithings  # write it and start the job
#
# The checkout given here becomes both the runner's location and LOCAL_CI_MAIN, the
# tree the checks run against. Pass a dedicated clone on develop, not the working tree.
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LABEL=ai.digithings.local-ci
CHECKOUT=""
DRY=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    -*) echo "install.sh: unknown option: $arg" >&2; exit 2 ;;
    *) CHECKOUT="$arg" ;;
  esac
done
if [ -z "$CHECKOUT" ]; then
  CHECKOUT=$(CDPATH= cd -- "$HERE/../.." && pwd)
fi
CHECKOUT=$(CDPATH= cd -- "$CHECKOUT" && pwd)
if [ -f "$CHECKOUT/.git" ] && [ "${2:-}" != "--allow-worktree" ]; then
  echo "install.sh: $CHECKOUT is a linked worktree (.git is a file)." >&2
  echo "install.sh: point the daemon at a dedicated clone on develop, or pass --allow-worktree." >&2
  exit 1
fi
SCRIPT="$CHECKOUT/scripts/local-ci/local_ci.py"
if [ ! -f "$SCRIPT" ]; then
  echo "install.sh: no runner at $SCRIPT" >&2
  exit 1
fi
OUT=$(sed -e "s|__CHECKOUT__|$CHECKOUT|g" -e "s|__HOME__|$HOME|g" "$HERE/$LABEL.plist.template")
if [ "$DRY" = 1 ]; then
  printf '%s\n' "$OUT"
  exit 0
fi
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.config/digithings/logs/local-ci"
printf '%s\n' "$OUT" > "$DEST"
plutil -lint "$DEST" > /dev/null
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "install.sh: installed $LABEL from $CHECKOUT"
