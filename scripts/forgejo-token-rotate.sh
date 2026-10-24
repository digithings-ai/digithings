#!/usr/bin/env bash
# Rotate one Forgejo PAT. Usage: forgejo-token-rotate.sh <username> [scope]
# scope defaults to "all" for humans, callers pass "write" etc. for agents.
set -euo pipefail
USER="${1:?username required}"
SCOPE="${2:-all}"
BASE="http://localhost:3000"
ENV_FILE="/Users/chrisstefan/Code/source-control/deploy/local-forge/local-forge.env"
set -a; . "$ENV_FILE"; set +a
TOKEN_DIR="$HOME/.config/digithings/forgejo-tokens"
NAME="rotated-$(date +%Y%m%d-%H%M%S)"

# 1. mint
NEW=$(docker exec -u git local-forge-forgejo-1 forgejo admin user generate-access-token \
      -u "$USER" -t "$NAME" --scopes "$SCOPE" --raw)
echo "minted $NAME for $USER"

# 2. verify before overwriting anything
CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $NEW" "$BASE/api/v1/user")
[ "$CODE" = "200" ] || { echo "new token failed verification: HTTP $CODE"; exit 1; }

# 3. write token + expiry sidecar
umask 077
printf '%s\n' "$NEW" > "$TOKEN_DIR/$USER.token"
EXPIRY=$(date -v+90d +%Y-%m-%d 2>/dev/null || date -d '+90 days' +%Y-%m-%d)
printf '%s\n' "$EXPIRY" > "$TOKEN_DIR/$USER.expires"
chmod 600 "$TOKEN_DIR/$USER.token" "$TOKEN_DIR/$USER.expires"
echo "wrote $TOKEN_DIR/$USER.token (expires $EXPIRY)"

# 4. revoke old tokens for this user (keep the one we just minted)
curl -s -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/admin/users/$USER/tokens" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); [print(t['name']) for t in (d if isinstance(d,list) else d.get('data',[])) if t['name']!='$NAME']" \
  | while read -r old; do
      echo "revoking old token: $old"
      curl -s -X DELETE -H "Authorization: token $FORGEJO_TOKEN" "$BASE/api/v1/admin/users/$USER/tokens/$old" -o /dev/null -w "  HTTP %{http_code}\n"
    done

echo "rotation complete for $USER; update consumers (env files, CI secrets, agent configs) now."
