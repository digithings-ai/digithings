#!/usr/bin/env bash
# OCC invite key rollout, split (DIG-3697).
#
#   R6 write-secret: scripts/occ_invite_key_write.sh
#   R5 deploy:       scripts/occ_invite_key_deploy.sh
#
# Both halves are disarmed. This entry runs the write half so the offline
# auth guard still enters here, and it does not deploy. A disarmed write
# half does not exit 0, so the deploy half is not reached.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bash "$here/occ_invite_key_write.sh"
echo "DISARMED: R5 deploy is not run from this entry. Nothing was deployed." >&2
exit 2
