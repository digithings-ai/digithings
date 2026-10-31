#!/usr/bin/env bash
# Install (or remove) the az guard so it sits on PATH ahead of the real `az`.
#
#   scripts/az-guard/install.sh                         # install into ~/.local/bin
#   scripts/az-guard/install.sh --bindir DIR            # install somewhere else
#   scripts/az-guard/install.sh --register PATH         # private register for this run
#   scripts/az-guard/install.sh --check                 # verify an existing install, write nothing
#   scripts/az-guard/install.sh --uninstall             # rollback: remove the symlink
#
# Default register: config/azure_access_register.example.json next to this repo.
# It authorises nothing. AZ_GUARD_REGISTER or --register selects a private register
# supplied outside the repo. The guard reads AZ_GUARD_REGISTER when az runs, so export
# it in the shell that invokes az. This script exports it for the --check probe and
# prints the path it resolved.
#
# It installs a symlink, not a copy, so `git pull` updates the guard with no second step.
# Rollback is one command: `scripts/az-guard/install.sh --uninstall`. It removes only the
# symlink this script created and never touches a real `az`.

set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
shim="$here/az"
bindir="${HOME}/.local/bin"
repo_root=$(cd -- "$here/../.." && pwd)
register="${AZ_GUARD_REGISTER:-$repo_root/config/azure_access_register.example.json}"
mode="install"

while [ $# -gt 0 ]; do
  case "$1" in
    --bindir) bindir="${2:?--bindir needs a directory}"; shift 2 ;;
    --check) mode="check"; shift ;;
    --uninstall) mode="uninstall"; shift ;;
    --register) register="${2:?--register needs a path}"; shift 2 ;;
    -h|--help) sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ ! -x "$shim" ]; then
  echo "install.sh: $shim is missing or not executable — run: chmod +x '$shim'" >&2
  exit 1
fi

link="$bindir/az"

describe() {
  printf 'az guard\n'
  printf '  shim    : %s\n' "$shim"
  printf '  link    : %s\n' "$link"
  printf '  register: %s\n' "$register"
  printf '  log     : %s\n' "${AZ_GUARD_LOG:-$HOME/.digithings/az-guard-refusals.log}"
  printf '  guard   : %s\n' "$(command -v az || echo 'not on PATH')"
}

case "$mode" in
  uninstall)
    if [ -L "$link" ] && [ "$(cd -- "$(dirname -- "$link")" && readlink "$link")" = "$shim" ]; then
      rm -f "$link"
      echo "removed $link (rollback complete)"
    elif [ -e "$link" ]; then
      echo "install.sh: $link exists and is not this guard's symlink — left alone." >&2
      exit 1
    else
      echo "nothing to remove at $link"
    fi
    exit 0
    ;;
  check)
    describe
    resolved=$(command -v az || true)
    if [ "$resolved" != "$link" ]; then
      echo "  FAIL    : 'az' resolves to '${resolved:-nothing}', not the guard at $link." >&2
      echo "            Put $bindir ahead of the real az on PATH (or move the real az)." >&2
      # Stop here: the probe below would call whatever `az` won, which is exactly the
      # thing that just failed to check. A check that runs the thing it is checking
      # because the check failed first is worse than no check.
      exit 1
    fi
    status=0
    # A refusal probe, not a call: the guard refuses before exec, so this makes no
    # network call and touches no tenant. Exit 78 is the documented refusal code.
    # Nil UUID: not a real subscription, and not on the example register. A private
    # register must not authorise this placeholder or the probe stops proving refusal.
    probe=$(AZ_GUARD_REGISTER="$register" az account show --subscription 00000000-0000-0000-0000-000000000000 2>&1) && probe_rc=0 || probe_rc=$?
    if [ "$probe_rc" -eq 78 ] && printf '%s' "$probe" | grep -q 'az guard: REFUSED'; then
      echo "  PASS    : an unauthorised example subscription id is refused (exit 78, nothing executed)"
    else
      echo "  FAIL    : the probe exited $probe_rc instead of the documented refusal." >&2
      printf '%s\n' "$probe" >&2
      status=1
    fi
    exit "$status"
    ;;
esac

mkdir -p "$bindir"

# Never clobber something that is not already this guard. Replacing a real `az` binary
# here looks like hardening, but the documented rollback then deletes the replacement and
# takes the real CLI with it -- and `--uninstall` refuses to restore what it never backed
# up. Refuse loudly and let the operator choose a bindir of their own.
if [ -e "$link" ] || [ -L "$link" ]; then
  if [ -d "$link" ]; then
    echo "install.sh: $link is a directory, not a place for the guard." >&2
    echo "install.sh: refusing to install; pick another --bindir." >&2
    exit 1
  fi
  if [ ! -L "$link" ] || [ "$(cd "$(dirname "$link")" && readlink "$link")" != "$shim" ]; then
    echo "install.sh: $link already exists and is not this guard's symlink -- left alone." >&2
    echo "install.sh: refusing to replace it. Point the guard at its own bindir instead:" >&2
    echo "install.sh:   install.sh --bindir <dir>   (and put <dir> ahead of the real az on PATH)" >&2
    exit 1
  fi
fi

ln -sfn "$shim" "$link"
chmod +x "$shim"
echo "installed $link -> $shim"
describe
echo
echo "verify with: scripts/az-guard/install.sh --check"
echo "roll back with: scripts/az-guard/install.sh --uninstall"
