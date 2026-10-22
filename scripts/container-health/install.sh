#!/bin/sh
# Install or repoint the container-health launchd job at a checkout of this repository.
#
#   scripts/container-health/install.sh --dry-run          # print the plist, change nothing
#   scripts/container-health/install.sh --status           # is the job installed and loaded?
#   scripts/container-health/install.sh --install          # write the plist, do NOT load it
#   scripts/container-health/install.sh --install --load   # write the plist and load it
#   scripts/container-health/install.sh --unload           # unload the job
#
# The checkout given here becomes the location of the probe script. Pass a dedicated
# clone on develop, not a working tree: the job runs every day, long after this
# session is over, and it must find the same script it was installed with.
# A checkout that is not on develop is refused, because a job that runs from a
# feature branch checks code nobody merged. --allow-branch overrides that.
#
# Loading a launchd job is Chris's call (the Host & Runtime seat never loads, unloads
# or edits one on its own), so the installer writes the plist and leaves the load to
# an explicit --load. The install is staged: the plist is rendered and linted before
# it is put in place, the previous one is kept, and a failed load puts it back.
#
# launchd does not re-read a plist that changes on disk. A job that is already
# loaded keeps the definition it was bootstrapped with, so a re-install only takes
# effect after the job is booted out and loaded again.
set -eu
: "${HOME:?install.sh: HOME is empty; refusing to install outside a user tree}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LABEL=com.digithings.container-health
CHECKOUT=""
DRY=0
INSTALL=0
LOAD=0
UNLOAD=0
STATUS=0
ALLOW_WT=0
ALLOW_BRANCH=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --install) INSTALL=1 ;;
    --load) LOAD=1 ;;
    --unload) UNLOAD=1 ;;
    --status) STATUS=1 ;;
    --allow-worktree) ALLOW_WT=1 ;;
    --allow-branch) ALLOW_BRANCH=1 ;;
    -*) echo "install.sh: unknown option: $arg" >&2; exit 2 ;;
    *) CHECKOUT="$arg" ;;
  esac
done
if [ -z "$CHECKOUT" ]; then
  CHECKOUT=$(CDPATH= cd -- "$HERE/../.." && pwd)
fi
CHECKOUT=$(CDPATH= cd -- "$CHECKOUT" && pwd)
SCRIPT="$CHECKOUT/scripts/container-health/container_health.py"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
SERVICE="gui/$(id -u)/$LABEL"
# The helper the job uses to file a ticket. A job without it runs every day and
# never files anything, and nothing says so, so the install refuses it.
CREATE_HELPER=${DT_CREATE_ISSUE:-$HOME/paperclip-workspace/kit/bin/dt-create-issue}

is_loaded() {
  launchctl print "$SERVICE" > /dev/null 2>&1
}

if [ "$STATUS" = 1 ]; then
  echo "plist:   $DEST"
  if [ -f "$DEST" ]; then
    echo "state:   installed"
  else
    echo "state:   not installed"
  fi
  if is_loaded; then
    echo "loaded:  yes"
    launchctl print "$SERVICE" 2>/dev/null | sed -n 's/^[[:space:]]*state = /state:  /p' | head -n 1
  else
    echo "loaded:  no"
  fi
  exit 0
fi

if [ "$UNLOAD" = 1 ]; then
  if is_loaded; then
    # Boot out by service target, not by path: a path based bootout only
    # removes a service that was bootstrapped from that exact file, and a job
    # that is still running with its plist deleted is the worst outcome.
    if launchctl bootout "$SERVICE"; then
      echo "install.sh: unloaded $LABEL"
    else
      echo "install.sh: bootout of $LABEL failed; the job may still be loaded" >&2
    fi
    if is_loaded; then
      echo "install.sh: $LABEL is still loaded. Check it with:" >&2
      echo "install.sh:   launchctl print $SERVICE" >&2
    fi
  else
    echo "install.sh: $LABEL is not loaded"
  fi
  if [ -f "$DEST" ]; then
    echo "install.sh: the plist is still on disk ($DEST); remove it by hand"
  fi
  exit 0
fi

if [ ! -f "$SCRIPT" ]; then
  echo "install.sh: no probe script at $SCRIPT" >&2
  exit 1
fi
if [ ! -x "$CREATE_HELPER" ] && [ ! -f "$CREATE_HELPER" ]; then
  # The job files its ticket through this helper. Without it the check keeps
  # running and keeps failing to file, every day, in silence.
  if [ "$INSTALL" = 1 ]; then
    echo "install.sh: no create helper at $CREATE_HELPER" >&2
    echo "install.sh: the job would run and never file a ticket; nothing was changed" >&2
    exit 1
  fi
  echo "install.sh: warning: no create helper at $CREATE_HELPER; an install would refuse" >&2
fi
if [ -f "$CHECKOUT/.git" ] && [ "$ALLOW_WT" != 1 ]; then
  echo "install.sh: $CHECKOUT is a linked worktree (.git is a file)." >&2
  echo "install.sh: point the job at a dedicated clone on develop, or pass --allow-worktree." >&2
  exit 1
fi
if ! git -C "$CHECKOUT" rev-parse --verify -q HEAD > /dev/null 2>&1; then
  echo "install.sh: $CHECKOUT is not a git checkout" >&2
  exit 1
fi
BRANCH=$(git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
if [ "$BRANCH" != "develop" ]; then
  # The job runs every day, long after this session. A checkout on a feature
  # branch would have the job check code nobody merged, and a branch that is
  # deleted later leaves the job with nothing to run. A warning was not enough
  # to stop that, so an install refuses and a dry run only says so.
  if [ "$INSTALL" = 1 ] && [ "$ALLOW_BRANCH" != 1 ]; then
    echo "install.sh: $CHECKOUT is on '$BRANCH', not develop; nothing was changed" >&2
    echo "install.sh: point the job at a dedicated clone on develop, or pass --allow-branch." >&2
    exit 1
  fi
  echo "install.sh: warning: $CHECKOUT is on '$BRANCH', not develop" >&2
fi

# Paths go through sed; escape the three characters that would change the pattern.
esc() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
# The result also goes into XML, where & and < are not allowed as they are.
xml_esc() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
OUT=$(sed -e "s|__CHECKOUT__|$(esc "$(xml_esc "$CHECKOUT")")|g" -e "s|__HOME__|$(esc "$(xml_esc "$HOME")")|g" "$HERE/$LABEL.plist.template")
if [ "$DRY" = 1 ]; then
  printf '%s\n' "$OUT"
  exit 0
fi
if [ "$INSTALL" != 1 ]; then
  echo "install.sh: nothing changed. Pass --install to write the plist (--load to also load it)." >&2
  exit 2
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.config/digithings/logs/container-health"
BACKUP="$DEST.bak.$(date +%Y%m%d-%H%M%S)"
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
echo "install.sh: wrote $DEST"
if [ "$LOAD" != 1 ]; then
  if is_loaded; then
    echo "install.sh: $LABEL is loaded, and launchd keeps the definition it was loaded with."
    echo "install.sh: re-load it to pick up this plist (Chris's call):"
    echo "install.sh:   scripts/container-health/install.sh --install --load"
  else
    echo "install.sh: the job is NOT loaded. Loading a launchd job is Chris's call:"
    echo "install.sh:   scripts/container-health/install.sh --install --load"
  fi
  exit 0
fi
if is_loaded; then
  # A bootout that fails means the old job may still be running with the old
  # definition. Bootstrapping on top of that leaves two jobs or none, so this
  # is an error and not a warning.
  if ! launchctl bootout "$SERVICE"; then
    echo "install.sh: bootout of $LABEL failed; the old job may still be loaded" >&2
    echo "install.sh: the new plist was not loaded. Check it with:" >&2
    echo "install.sh:   launchctl print $SERVICE" >&2
    exit 1
  fi
fi
if ! launchctl bootstrap "gui/$(id -u)" "$DEST"; then
  echo "install.sh: bootstrap failed; restoring the previous job" >&2
  if [ -f "$BACKUP" ]; then
    cp "$BACKUP" "$DEST"
    launchctl bootstrap "gui/$(id -u)" "$DEST" \
      || echo "install.sh: restore failed too - $LABEL is NOT running" >&2
  else
    echo "install.sh: there was no previous plist; $LABEL is NOT running" >&2
  fi
  exit 1
fi
echo "install.sh: installed and loaded $LABEL from $CHECKOUT"
echo "install.sh: the job runs every day at 07:40 local; check it with:"
echo "install.sh:   scripts/container-health/install.sh --status"
