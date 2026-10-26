#!/bin/sh
# Install, inspect or remove the digiquant host-runner launchd clocks (DIG-2915).
#
#   scripts/digiquant-host-runner/install.sh --list          # the clocks this repo would install
#   scripts/digiquant-host-runner/install.sh --dry-run       # print the rendered plists, change nothing
#   scripts/digiquant-host-runner/install.sh --status        # installed? loaded? stale against this repo?
#   scripts/digiquant-host-runner/install.sh --install       # write the plists, do NOT load them
#   scripts/digiquant-host-runner/install.sh --install --load  # write and load them
#   scripts/digiquant-host-runner/install.sh --unload        # unload them (plists stay on disk)
#
# Loading a launchd job is Chris's call: the Host & Runtime seat writes the plists and
# never loads, unloads or edits one on its own, so --load is explicit and required.
#
# The checkout given here is the code every clock runs. Pass a dedicated clone on
# develop, not a working tree: the clocks run every day, long after this session, and
# a deleted feature branch would leave them with nothing. --allow-worktree and
# --allow-branch are for a deliberate, temporary exception.
#
# Secrets live in an env file outside the repository (default
# ~/.config/digithings/digiquant-host-runner.env, mode 600). An install refuses a
# missing or group/world-readable file, because a job that starts without its
# credentials writes half a result and exits zero.
#
# launchd does not re-read a plist that changes on disk. A loaded job keeps the
# definition it was bootstrapped with, so a re-install only takes effect after a
# bootout and a bootstrap. --status reports that case as "stale".
set -eu
: "${HOME:?install.sh: HOME is empty; refusing to install outside a user tree}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCHEDULE="$HERE/schedule.py"
RENDERER=${DT_PYTHON:-/usr/bin/python3}
CHECKOUT=""
ENV_FILE=${DIGIQUANT_HOST_RUNNER_ENV:-$HOME/.config/digithings/digiquant-host-runner.env}
DRY=0
INSTALL=0
LOAD=0
UNLOAD=0
STATUS=0
LIST=0
ALLOW_WT=0
ALLOW_BRANCH=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --install) INSTALL=1 ;;
    --load) LOAD=1 ;;
    --unload) UNLOAD=1 ;;
    --status) STATUS=1 ;;
    --list) LIST=1 ;;
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
AGENTS="$HOME/Library/LaunchAgents"
LABEL_PREFIX=com.digithings.digiquant.

labels() { "$RENDERER" "$SCHEDULE" --list | cut -f1; }

is_loaded() {
  launchctl print "gui/$(id -u)/$1" > /dev/null 2>&1
}

if [ "$LIST" = 1 ]; then
  "$RENDERER" "$SCHEDULE" --list
  exit 0
fi

if ! command -v plutil > /dev/null 2>&1; then
  echo "install.sh: plutil is missing; this is not a macOS host" >&2
  exit 1
fi

STAGE=$(mktemp -d "${TMPDIR:-/tmp}/digiquant-plists.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM
if ! "$RENDERER" "$SCHEDULE" --render-to "$STAGE" --checkout "$CHECKOUT" --env-file "$ENV_FILE" > /dev/null; then
  echo "install.sh: could not render the plists" >&2
  exit 1
fi
for plist in "$STAGE"/*.plist; do
  if ! plutil -lint "$plist" > /dev/null; then
    echo "install.sh: rendered plist does not lint: $plist" >&2
    exit 1
  fi
done

if [ "$STATUS" = 1 ]; then
  printf '%-46s %-12s %-8s %s\n' LABEL INSTALLED LOADED STATE
  for label in $(labels); do
    dest="$AGENTS/$label.plist"
    installed=no
    state="-"
    if [ -f "$dest" ]; then
      installed=yes
      if cmp -s "$dest" "$STAGE/$label.plist"; then
        state=current
      else
        state=stale
      fi
    fi
    if is_loaded "$label"; then loaded=yes; else loaded=no; fi
    printf '%-46s %-12s %-8s %s\n' "$label" "$installed" "$loaded" "$state"
  done
  if [ -f "$ENV_FILE" ]; then
    mode=$(stat -f '%Lp' "$ENV_FILE")
    echo "env file: $ENV_FILE (mode $mode)"
  else
    echo "env file: $ENV_FILE (missing)"
  fi
  exit 0
fi

if [ "$DRY" = 1 ]; then
  for label in $(labels); do
    printf '### %s\n' "$label"
    cat "$STAGE/$label.plist"
  done
  exit 0
fi

if [ "$UNLOAD" = 1 ]; then
  if [ "$INSTALL" = 1 ]; then
    echo "install.sh: --unload and --install are different actions; pick one" >&2
    exit 2
  fi
  failed=0
  for label in $(labels); do
    if is_loaded "$label"; then
      if launchctl bootout "gui/$(id -u)/$label"; then
        echo "install.sh: unloaded $label"
      else
        echo "install.sh: bootout of $label failed; it may still be loaded" >&2
        failed=1
      fi
    fi
  done
  exit "$failed"
fi

if [ "$INSTALL" != 1 ]; then
  echo "install.sh: nothing changed. Pass --install to write the plists (--load to also load them)." >&2
  exit 2
fi

# --- from here on the install is real ----------------------------------------

if [ -f "$CHECKOUT/.git" ] && [ "$ALLOW_WT" != 1 ]; then
  echo "install.sh: $CHECKOUT is a linked worktree (.git is a file)." >&2
  echo "install.sh: point the clocks at a dedicated clone on develop, or pass --allow-worktree." >&2
  exit 1
fi
if ! git -C "$CHECKOUT" rev-parse --verify -q HEAD > /dev/null 2>&1; then
  echo "install.sh: $CHECKOUT is not a git checkout" >&2
  exit 1
fi
BRANCH=$(git -C "$CHECKOUT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
if [ "$BRANCH" != "develop" ] && [ "$ALLOW_BRANCH" != 1 ]; then
  echo "install.sh: $CHECKOUT is on '$BRANCH', not develop; nothing was changed" >&2
  echo "install.sh: point the clocks at a dedicated clone on develop, or pass --allow-branch." >&2
  exit 1
fi
if [ ! -f "$CHECKOUT/scripts/digiquant-host-runner/run_job.py" ]; then
  echo "install.sh: no run_job.py under $CHECKOUT; nothing was changed" >&2
  exit 1
fi
if [ ! -f "$ENV_FILE" ]; then
  echo "install.sh: no env file at $ENV_FILE; nothing was changed" >&2
  echo "install.sh: every clock would start without its credentials. Create it mode 600" >&2
  echo "install.sh: (see docs/ops/digiquant-host-runner.md), then install again." >&2
  exit 1
fi
if ! "$RENDERER" -c 'import os,sys; sys.exit(0 if not os.stat(sys.argv[1]).st_mode & 0o077 else 1)' "$ENV_FILE"; then
  echo "install.sh: $ENV_FILE is readable by group or others; chmod 600 it first" >&2
  exit 1
fi
if [ ! -x /opt/homebrew/bin/uv ]; then
  echo "install.sh: no /opt/homebrew/bin/uv; the plists call it, nothing was changed" >&2
  exit 1
fi

mkdir -p "$AGENTS" "$HOME/.config/digithings/logs/digiquant-host-runner"
STAMP=$(date +%Y%m%d-%H%M%S)
for label in $(labels); do
  dest="$AGENTS/$label.plist"
  if [ -f "$dest" ]; then
    cp "$dest" "$dest.bak.$STAMP"
    echo "install.sh: previous $label saved as $dest.bak.$STAMP"
  fi
  cp "$STAGE/$label.plist" "$dest"
  echo "install.sh: wrote $dest"
done

if [ "$LOAD" != 1 ]; then
  echo "install.sh: the plists are on disk and NOT loaded. Loading a launchd job is Chris's call:"
  echo "install.sh:   $0 --install --load $CHECKOUT"
  exit 0
fi

# Load one clock at a time. A bootout that fails means the old definition may still be
# running, and bootstrapping on top of that leaves two jobs or none: stop there.
for label in $(labels); do
  dest="$AGENTS/$label.plist"
  if is_loaded "$label"; then
    if ! launchctl bootout "gui/$(id -u)/$label"; then
      echo "install.sh: bootout of $label failed; nothing further was loaded" >&2
      echo "install.sh: check it with: launchctl print gui/$(id -u)/$label" >&2
      exit 1
    fi
  fi
  if ! launchctl bootstrap "gui/$(id -u)" "$dest"; then
    echo "install.sh: bootstrap failed for $label; restoring the previous definition" >&2
    if [ -f "$dest.bak.$STAMP" ]; then
      cp "$dest.bak.$STAMP" "$dest"
      launchctl bootstrap "gui/$(id -u)" "$dest" \
        || echo "install.sh: restore failed too - $label is NOT running" >&2
    else
      echo "install.sh: there was no previous $label; it is NOT running" >&2
    fi
    exit 1
  fi
  echo "install.sh: loaded $label"
done
echo "install.sh: installed and loaded $(labels | wc -l | tr -d ' ') clocks from $CHECKOUT"
echo "install.sh: check them with: $0 --status"
