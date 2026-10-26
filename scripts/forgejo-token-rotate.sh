#!/usr/bin/env bash
# Rotate a Forgejo PAT safely.
#
#   scripts/forgejo-token-rotate.sh <username> [scope]     # mint + write the file
#   scripts/forgejo-token-rotate.sh --revoke <username> <token-name>
#
# Minting does **not** revoke anything. Update the consumers first, then revoke
# the old token by name. The sctl admin token lives in local-forge.env, not in
# the token directory, so this script refuses to rotate sctl automatically.
set -euo pipefail

ENV_FILE="${LOCAL_FORGE_ENV:-$HOME/Code/source-control/deploy/local-forge/local-forge.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "forgejo-token-rotate: env file not found: $ENV_FILE" >&2
  echo "Set LOCAL_FORGE_ENV to the Forgejo env file." >&2
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

BASE="${FORGEJO_URL:-http://localhost:3000}"
CONTAINER="${FORGEJO_CONTAINER:-local-forge-forgejo-1}"
OWNER="${FORGEJO_REPO_ORG:-digithings-ai}"
TOKEN_DIR="${FORGEJO_TOKEN_DIR:-$HOME/.config/digithings/forgejo-tokens}"

if [ -z "${FORGEJO_TOKEN:-}" ]; then
  echo "forgejo-token-rotate: FORGEJO_TOKEN is unset in $ENV_FILE" >&2
  exit 1
fi

usage() {
  echo "usage: $0 <username> [scope]" >&2
  echo "       $0 --revoke <username> <token-name>" >&2
  exit 2
}

quote() {
  python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"
}

# curl_auth <token> [curl args...]
#
# The Authorization header is fed to curl on stdin with --config -, never as an
# argv element: an argument is readable in `ps -ww` for the life of the process.
# Only the token value moves into the config; every other argument stays here.
curl_auth() {
  token="$1"
  shift
  curl --config - "$@" <<CURLRC
header = "Authorization: token ${token}"
CURLRC
}

if [ "${1:-}" = "--revoke" ]; then
  USER="${2:-}"; NAME="${3:-}"
  [ -n "$USER" ] && [ -n "$NAME" ] || usage
  CODE=$(curl_auth "$FORGEJO_TOKEN" -s -o /dev/null -w "%{http_code}" -X DELETE \
    "$BASE/api/v1/admin/users/$USER/tokens/$(quote "$NAME")")
  if [ "$CODE" = "204" ] || [ "$CODE" = "200" ]; then
    echo "revoked token '$NAME' for $USER"
    exit 0
  fi
  echo "revoke failed: HTTP $CODE for $USER/$NAME" >&2
  exit 1
fi

USER="${1:?username required}"
SCOPE="${2:-all}"

if [ "$USER" = "sctl" ]; then
  echo "refusing to rotate sctl automatically: its admin token is in" >&2
  echo "$ENV_FILE, not in $TOKEN_DIR." >&2
  echo "Rotate it deliberately, update that file, then revoke the old token by name." >&2
  exit 2
fi

NAME="rotated-$(date +%Y%m%d-%H%M%S)"

# 1. Mint. The old tokens stay valid until step 4.
NEW=$(docker exec -u git "$CONTAINER" forgejo admin user generate-access-token \
      -u "$USER" -t "$NAME" --scopes "$SCOPE" --raw)
if [ -z "$NEW" ]; then
  echo "mint returned an empty token" >&2
  exit 1
fi
echo "minted $NAME for $USER"

# 2. Verify before overwriting anything. Use a repo endpoint, not /user: a
# scoped token may not carry user-read, and a failed check must not orphan the
# new token silently.
CODE=$(curl_auth "$NEW" -s -o /dev/null -w "%{http_code}" \
  "$BASE/api/v1/repos/$OWNER/digithings")
if [ "$CODE" != "200" ]; then
  echo "new token failed verification: HTTP $CODE" >&2
  echo "The token '$NAME' exists; revoke it with:" >&2
  echo "  $0 --revoke $USER $NAME" >&2
  exit 1
fi

# 3. Write the token and its expiry. The file is the source the git helper reads.
umask 077
mkdir -p "$TOKEN_DIR"
printf '%s\n' "$NEW" > "$TOKEN_DIR/$USER.token"
EXPIRY=$(date -v+90d +%Y-%m-%d 2>/dev/null || date -d '+90 days' +%Y-%m-%d)
printf '%s\n' "$EXPIRY" > "$TOKEN_DIR/$USER.expires"
chmod 600 "$TOKEN_DIR/$USER.token" "$TOKEN_DIR/$USER.expires"
echo "wrote $TOKEN_DIR/$USER.token (expires $EXPIRY)"

# 4. Show what is still live, but do not revoke it here. Consumers must be
# updated first; revoking immediately is how sctl/chris lose their only token.
TOKENS_JSON=$(curl_auth "$FORGEJO_TOKEN" -s \
  "$BASE/api/v1/admin/users/$USER/tokens" || true)
if [ -n "$TOKENS_JSON" ]; then
  printf '%s' "$TOKENS_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); [print('  still live:', t['name']) for t in (d if isinstance(d,list) else d.get('data',[])) if t['name']!='$NAME']" \
    || echo "could not parse the token list for $USER" >&2
else
  echo "could not list old tokens for $USER (admin token may not have admin:user)" >&2
fi

echo
echo "Update every consumer of $USER's token first."
echo "Then revoke each old name:"
echo "  $0 --revoke $USER <old-name>"
