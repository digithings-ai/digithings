#!/usr/bin/env bash
# R5 deploy half of the OCC invite-key rollout (DIG-3697).
#
# The R6 write half is scripts/occ_invite_key_write.sh. This half prints what
# the deploy step would do: bump the hand-pinned literal while one exists, or
# explain that the derived id (DIG-3814) needs no bump. It does not edit
# paths.ts, does not commit, and does not call wrangler.
#
# --live is refused. Nothing in the environment arms this script.
set -euo pipefail

for arg in "$@"; do
  case "$arg" in
    --live)
      echo "DISARMED: R5 OCC deploy is refused until Chris approves. Nothing was deployed." >&2
      exit 2
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PATHS_TS="$REPO_ROOT/apps/digichat-cloudflare/src/paths.ts"
[ -f "$PATHS_TS" ] || { echo "missing $PATHS_TS" >&2; exit 1; }

before="$(cksum "$PATHS_TS")"
current="$(sed -n 's/^export const SHARED_DIGICHAT_CONTAINER_ID = "\(shared-v[0-9][0-9]*\)";.*/\1/p' "$PATHS_TS")"
after="$(cksum "$PATHS_TS")"
[ "$before" = "$after" ] || { echo "paths.ts changed during a dry-run; refusing." >&2; exit 1; }

if [ -n "$current" ]; then
  next_n=$(( ${current##*v} + 1 ))
  next_id="shared-v${next_n}"
  echo "dry-run: would bump ${current} -> ${next_id}, then deploy the digichat Worker. Nothing was changed."
else
  # DIG-3814 removed the hand-pinned literal: the digichat Container id now
  # derives from the deploying commit via DIGICHAT_CONTAINER_REV, so there is
  # no bump to make. The recycle is the deploy itself.
  echo "dry-run: no hand-pinned SHARED_DIGICHAT_CONTAINER_ID to bump (since DIG-3814 the id derives from the deploying commit). A deploy from a checkout that carries DIGICHAT_CONTAINER_REV IS the recycle. Nothing was changed."
fi
