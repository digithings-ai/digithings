#!/usr/bin/env bash
# R5 deploy half of the OCC invite-key rollout (DIG-3697).
#
# The R6 write half is scripts/occ_invite_key_write.sh. This half only
# prints the container-id bump a later deploy would make. It does not
# edit paths.ts, does not commit, and does not call wrangler.
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
[ -n "$current" ] || { echo "could not read SHARED_DIGICHAT_CONTAINER_ID from $PATHS_TS" >&2; exit 1; }
next_n=$(( ${current##*v} + 1 ))
next_id="shared-v${next_n}"
after="$(cksum "$PATHS_TS")"
[ "$before" = "$after" ] || { echo "paths.ts changed during a dry-run; refusing." >&2; exit 1; }

echo "dry-run: would bump ${current} -> ${next_id}, then deploy the digichat Worker. Nothing was changed."
