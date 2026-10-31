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
# itself. It is refused unless the checkout is a dedicated clone: its own .git
# directory (not a linked worktree), on develop, a clean tree, and no commits
# of its own on top of origin/develop. A working tree belongs to a person, and
# the runner must not move it (DIG-5135).
#
# The checkout also has to be complete: the runner imports its helpers with a None
# fallback and refuses every tick when one is absent, so a stale checkout that still
# looks installable would leave the daemon running but the gate dark. The install asks
# the checkout's own import_preflight.py before it renders or writes anything, and
# refuses a tree whose modules do not all resolve (DIG-5585, DIG-5725).
#
# The install is staged: the new plist is rendered and linted before the live job is
# touched, the previous plist is kept, and a failed bootstrap puts it back. A gate that
# disappears because an installer half-finished is the failure this script exists to
# prevent (DIG-4490 review).
set -eu
: "${HOME:?install.sh: HOME is empty; refusing to install outside a user tree}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LABEL=ai.digithings.local-ci
# The interpreter the installed job runs. The install check below runs under the same
# one, so a module that resolves for the check is a module the daemon can import.
# A bare path, never flags: launch_guard.py refuses a job whose ProgramArguments do not
# unpack to exactly an interpreter and a script.
PYTHON=/usr/bin/python3
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
if [ ! -f "$CHECKOUT/scripts/local-ci/launch_guard.py" ]; then
  echo "install.sh: no launch_guard.py next to the runner; refusing to install a runner that cannot be guarded" >&2
  echo "install.sh: a checkout from before DIG-4796 installs a runner any seat can start" >&2
  exit 1
fi
# The runner refuses every tick when a module it imports is missing (exit 78), so a
# checkout that is missing one is a checkout that installs a dark gate. Refuse it here,
# before anything is written, and name what is missing (DIG-5585, DIG-5725).
PREFLIGHT="$CHECKOUT/scripts/local-ci/import_preflight.py"
if [ ! -f "$PREFLIGHT" ]; then
  echo "install.sh: no import_preflight.py next to the runner; refusing to install a checkout that cannot check its own imports" >&2
  echo "install.sh: the runner refuses every tick without it (exit 78, DIG-5585)" >&2
  exit 1
fi
# The plist runs the runner under this interpreter, so the check that decides whether
# the checkout is complete runs under it too: a module the check resolves elsewhere on
# the host is not a module the daemon will find.
if [ ! -x "$PYTHON" ]; then
  echo "install.sh: no python at $PYTHON; the job this would install could not start" >&2
  exit 1
fi
if "$PYTHON" "$PREFLIGHT" "$SCRIPT" > /dev/null; then
  :
else
  status=$?
  # The preflight writes the cause to stderr above: a missing module, a module that
  # does not parse, or an interpreter that cannot run it. Do not name a cause here
  # that it did not report - blaming the wrong thing is the failure this check
  # exists to stop (DIG-4674).
  echo "install.sh: refusing to install $CHECKOUT: the import check failed (exit $status); see the lines above" >&2
  echo "install.sh: a daemon installed from this checkout could refuse every tick (exit 78)" >&2
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
OUT=$(sed -e "s|__CHECKOUT__|$(esc "$CHECKOUT")|g" -e "s|__HOME__|$(esc "$HOME")|g" -e "s|__PYTHON__|$(esc "$PYTHON")|g" "$HERE/$LABEL.plist.template")
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
# The runner may only keep its own checkout current when this install named that
# checkout as the runner's own. That is the operator's call (--self-update) and
# it is refused for a linked worktree, for a checkout that is not on develop,
# for a tree with uncommitted changes and for a checkout that carries commits
# of its own: those are checkouts somebody works in, and the runner must not
# move them (DIG-5135).
MARKER="$HOME/.config/digithings/state/local-ci-runner.json"
mkdir -p "$HOME/.config/digithings/state"
SELF_UPDATE=false
if [ "$SELF_UPDATE_OPT" = 1 ]; then
  if [ ! -d "$CHECKOUT/.git" ]; then
    echo "install.sh: --self-update needs a dedicated clone; $CHECKOUT is a linked worktree" >&2
  elif [ "$BRANCH" != "develop" ]; then
    echo "install.sh: --self-update needs a clone on develop; $CHECKOUT is on '$BRANCH'" >&2
  elif [ -n "$(git -C "$CHECKOUT" status --porcelain 2>/dev/null)" ]; then
    echo "install.sh: --self-update needs a clean tree; $CHECKOUT has uncommitted changes" >&2
  elif ! git -C "$CHECKOUT" rev-parse --verify -q origin/develop > /dev/null 2>&1; then
    echo "install.sh: --self-update needs a clone with origin/develop; $CHECKOUT has none" >&2
  elif [ "$(git -C "$CHECKOUT" rev-list --count HEAD --not origin/develop 2>/dev/null || echo 1)" != "0" ]; then
    echo "install.sh: --self-update needs a clone with no commits of its own; $CHECKOUT has some" >&2
  else
    SELF_UPDATE=true
  fi
fi
# The marker is JSON, so a path with a backslash or a quote in it has to be
# escaped: a malformed marker is a marker the runner cannot read, and the
# runner then never moves the checkout the operator marked.
json_esc() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }
# The marker is staged before the plist is moved into place and moved into
# place only after the job is loaded. A marker that is written first and
# fails halfway leaves a new plist on disk with the old job still loaded, and
# the launch guard then refuses every later tick: the producer dies with only
# a shell error to show for it.
printf '{"main": "%s", "self_update": %s}\n' "$(json_esc "$CHECKOUT")" "$SELF_UPDATE" > "$MARKER.staged"
mv "$DEST.staged" "$DEST"
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
if ! launchctl bootstrap "gui/$(id -u)" "$DEST"; then
  echo "install.sh: bootstrap failed; restoring the previous job" >&2
  # The marker was never moved into place, so the marker that is still on disk
  # belongs to the job that is being restored: leave it alone.
  rm -f "$MARKER.staged"
  if [ -f "$BACKUP" ]; then
    cp "$BACKUP" "$DEST"
    launchctl bootstrap "gui/$(id -u)" "$DEST" \
      || echo "install.sh: restore failed too - $LABEL is NOT running" >&2
  else
    echo "install.sh: there was no previous plist; $LABEL is NOT running" >&2
  fi
  exit 1
fi
mv "$MARKER.staged" "$MARKER"
echo "install.sh: installed $LABEL from $CHECKOUT"
echo "install.sh: the runner may update this checkout by itself: $SELF_UPDATE"
echo "install.sh: note - this installs the runner only; dt-daemon-liveness (digiforge) keeps it loaded"
