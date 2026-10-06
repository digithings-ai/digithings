#!/usr/bin/env bash
# Install (or remove) the az guard so it sits on PATH ahead of the real `az`.
#
#   scripts/az-guard/install.sh                    # install into ~/.local/bin
#   scripts/az-guard/install.sh --bindir DIR      # install somewhere else
#   scripts/az-guard/install.sh --check            # verify an existing install, write nothing
#   scripts/az-guard/install.sh --uninstall        # rollback: remove the symlink
#
# It installs a symlink, not a copy, so `git pull` updates the guard with no second step.
# The guard reads its register relative to its own resolved path, so the symlink does not
# change where the register is found.
#
# Rollback is one command: `scripts/az-guard/install.sh --uninstall`. It removes only the
# symlink this script created and never touches a real `az`.

set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
shim="$here/az"
bindir="${HOME}/.local/bin"
mode="install"

while [ $# -gt 0 ]; do
  case "$1" in
    --bindir) bindir="${2:?--bindir needs a directory}"; shift 2 ;;
    --check) mode="check"; shift ;;
    --uninstall) mode="uninstall"; shift ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
  printf '  register: %s\n' "$(cd -- "$here/../.." && pwd)/config/datatap_azure_access_register.json"
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
    probe=$(az account show --subscription fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0 2>&1) && probe_rc=0 || probe_rc=$?
    if [ "$probe_rc" -eq 78 ] && printf '%s' "$probe" | grep -q 'az guard: REFUSED'; then
      echo "  PASS    : the production subscription id is refused (exit 78, nothing executed)"
    else
      echo "  FAIL    : the probe exited $probe_rc instead of the documented refusal." >&2
      printf '%s\n' "$probe" >&2
      status=1
    fi
    exit "$status"
    ;;
esac

mkdir -p "$bindir"
ln -sfn "$shim" "$link"
chmod +x "$shim"
echo "installed $link -> $shim"
describe
echo
echo "verify with: scripts/az-guard/install.sh --check"
echo "roll back with: scripts/az-guard/install.sh --uninstall"
