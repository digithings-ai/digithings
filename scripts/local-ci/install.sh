#!/bin/sh
# Install or repoint the local-ci launchd job at a checkout of this repository.
#
#   scripts/local-ci/install.sh --dry-run          # print the plist, change nothing
#   scripts/local-ci/install.sh ~/Code/digithings  # write it and start the job
#   scripts/local-ci/install.sh --self-update ~/Code/digithings-ci
#
# The checkout given here becomes both the runner's location and LOCAL_CI_MAIN, the
# tree the checks run against. Pass a dedicated clone on develop, not the working tree.
#
# --self-update says that the runner may keep that checkout on origin/develop by
# itself. It is refused unless the checkout is a real clone on develop: a working
# tree belongs to a person, and the runner must not move it (DIG-5135).
#
# The install is staged: the new plist is rendered and linted before the live job is
# touched, the previous plist is kept, and a failed bootstrap puts it back. A gate that
# disappears because an installer half-finished is the failure this script exists to
# prevent (DIG-4490 review).
set -eu
: "${HOME:?install.sh: HOME is empty; refusing to install outside a user tree}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LABEL=ai.digithings.local-ci
CHECKOUT=""
DRY=0
ALLOW_WT=0
SELF_UPDATE_OPT=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --allow-worktree) ALLOW_WT=1 ;;
    --self-update) SELF_UPDATE_OPT=1 ;;
    -*) echo "install.sh: unknown option: $arg" >&2; exit 2 ;;
    *) CHECKOUT="$arg" ;;
  esac
done
if [ -z "$CHECKOUT" ]; then
  CHECKOUT=$(CDPATH= cd -- "$HERE/../.." && pwd)
fi
CHECKOUT=$(CDPATH= cd -- "$CHECKOUT" && pwd)
if [ -f "$CHECKOUT/.git" ] && [ "$ALLOW_WT" != 1 ]; then
  echo "install.sh: $CHECKOUT is a linked worktree (.git is a file)." >&2
  echo "install.sh: point the daemon at a dedicated clone on develop, or pass --allow-worktree." >&2
  exit 1
fi
SCRIPT="$CHECKOUT/scripts/local-ci/local_ci.py"
if [ ! -f "$SCRIPT" ]; then
  echo "install.sh: no runner at $SCRIPT" >&2
  exit 1
fi
if ! git -C "$CHECKOUT" rev-parse --verify -q HEAD > /dev/null 2>&1; then
  echo "install.sh: $CHECKOUT is not a git checkout; the runner fetches and needs one" >&2
  exit 1
fi
BRANCH=$(git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
if [ "$BRANCH" != "develop" ]; then
  echo "install.sh: warning: $CHECKOUT is on '$BRANCH', not develop" >&2
fi
# Paths go through sed; escape the three characters that would change the pattern.
esc() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
OUT=$(sed -e "s|__CHECKOUT__|$(esc "$CHECKOUT")|g" -e "s|__HOME__|$(esc "$HOME")|g" "$HERE/$LABEL.plist.template")
if [ "$DRY" = 1 ]; then
  printf '%s\n' "$OUT"
  exit 0
fi
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
BACKUP="$DEST.bak.$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.config/digithings/logs/local-ci"
printf '%s\n' "$OUT" > "$DEST.staged"
if ! plutil -lint "$DEST.staged" > /dev/null; then
  echo "install.sh: the rendered plist does not lint; nothing changed" >&2
  rm -f "$DEST.staged"
  exit 1
fi
if [ -f "$DEST" ]; then
  cp "$DEST" "$BACKUP"
  echo "install.sh: previous plist saved as $BACKUP"
fi
mv "$DEST.staged" "$DEST"
# The runner may only keep its own checkout current when this install named that
# checkout as the runner's own. That is the operator's call (--self-update) and
# it is refused for a working tree and for a linked worktree: a linked worktree
# is a checkout somebody else works in, and a working tree is somebody's work
# (DIG-5135).
MARKER="$HOME/.config/digithings/state/local-ci-runner.json"
mkdir -p "$HOME/.config/digithings/state"
SELF_UPDATE=false
if [ "$SELF_UPDATE_OPT" = 1 ] && [ -d "$CHECKOUT/.git" ] && [ "$BRANCH" = "develop" ]; then
  SELF_UPDATE=true
elif [ "$SELF_UPDATE_OPT" = 1 ]; then
  echo "install.sh: --self-update needs a real clone on develop; $CHECKOUT is not one" >&2
fi
# The marker is JSON, so a path with a backslash or a quote in it has to be
# escaped: a malformed marker is a marker the runner cannot read, and the
# runner then never moves the checkout the operator marked.
json_esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
MARKER_BACKUP=""
if [ -f "$MARKER" ]; then
  MARKER_BACKUP="$MARKER.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$MARKER" "$MARKER_BACKUP"
fi
printf '{"main": "%s", "self_update": %s}\n' "$(json_esc "$CHECKOUT")" "$SELF_UPDATE" > "$MARKER.staged"
mv "$MARKER.staged" "$MARKER"
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
if ! launchctl bootstrap "gui/$(id -u)" "$DEST"; then
  echo "install.sh: bootstrap failed; restoring the previous job" >&2
  # The marker belongs to the job that is not running any more: put the old
  # one back rather than leaving the runner with a marker for a checkout that
  # is no longer its own.
  if [ -n "$MARKER_BACKUP" ] && [ -f "$MARKER_BACKUP" ]; then
    cp "$MARKER_BACKUP" "$MARKER"
  else
    rm -f "$MARKER"
  fi
  if [ -f "$BACKUP" ]; then
    cp "$BACKUP" "$DEST"
    launchctl bootstrap "gui/$(id -u)" "$DEST" \
      || echo "install.sh: restore failed too - $LABEL is NOT running" >&2
  else
    echo "install.sh: there was no previous plist; $LABEL is NOT running" >&2
  fi
  exit 1
fi
echo "install.sh: installed $LABEL from $CHECKOUT"
echo "install.sh: the runner may update this checkout by itself: $SELF_UPDATE"
echo "install.sh: note - this installs the runner only; dt-daemon-liveness (digiforge) keeps it loaded"
