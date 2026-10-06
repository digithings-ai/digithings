#!/usr/bin/env bash
# The ONLY sanctioned way to run wrangler in an agent session (DIG-1653).
#
# WHY THIS WRAPPER EXISTS
#   The agent harness sets XDG_CONFIG_HOME to a temp directory. Wrangler honours
#   it, so it reads an empty config dir and answers "Not logged in" while the
#   real credential file at ~/Library/Preferences/.wrangler/config/default.toml
#   sits untouched. The first `wrangler logout` in DIG-1639 was exactly this: a
#   silent no-op that reads as success. Unsetting the variable is mandatory, and
#   mandatory means enforced in code — if the next person deletes this wrapper
#   because it looks redundant, `env -u XDG_CONFIG_HOME` must go with it.
#
#   The second variable is CLOUDFLARE_API_TOKEN. It is a Worker secret *and*
#   wrangler's own auth variable. Exported, wrangler stops using the token we
#   want and authenticates as that token instead; since it carries Vectorize +
#   D1 and not Workers, every `secret put` / `deploy` fails with auth error
#   10000 — which reads like a broken token but is the wrong identity. The
#   secret VALUE still reaches wrangler on stdin, a separate channel from the
#   environment, so unsetting the variable costs nothing.
#
# WHY AGENTS NEVER GET OAUTH
#   `wrangler login` mints a long-lived OAuth grant with a refresh token, and
#   that refresh token is what leaked into a transcript (DIG-1639). Agents
#   authenticate with CLOUDFLARE_API_TOKEN and nothing else. `wrangler login`
#   is refused here for exactly that reason; if you need it, you are in a human
#   session and you should run it yourself, not through this script.
#
# USAGE
#   scripts/wrangler-auth.sh whoami
#   printf '%s' "$VALUE" | scripts/wrangler-auth.sh secret put MCP_EDGE_KEY
#   scripts/wrangler-auth.sh secret list
#
# Pin wrangler the way the repo does: apps/digichat-cloudflare/package.json:16
# and apps/digithings-stack-cloudflare/package.json:19 both pin 4.133.0.
set -euo pipefail

WRANGLER_VERSION="${DIGI_WRANGLER_VERSION:-4.133.0}"

# Refuse the OAuth path outright, before anything else runs.
for arg in "$@"; do
  case "$arg" in
    login | logout | oauth*)
      echo "wrangler-auth: '$arg' is an OAuth operation and is not available to agents." >&2
      echo "wrangler-auth: OAuth grants are long-lived and are what leaked in DIG-1639." >&2
      echo "wrangler-auth: agents use CLOUDFLARE_API_TOKEN. See docs/ops/SECRETS_ROTATION.md." >&2
      exit 2
      ;;
  esac
done

if [ "$#" -eq 0 ]; then
  echo "usage: scripts/wrangler-auth.sh <wrangler args...>" >&2
  exit 2
fi

# wrangler uses CLOUDFLARE_ACCOUNT_ID to pick the account. Without it the
# fallback lookup needs a User->Memberships scope the Vectorize/D1 token lacks.
if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  echo "wrangler-auth: CLOUDFLARE_ACCOUNT_ID is not exported." >&2
  echo "wrangler-auth: it is an account id, not a credential, and must stay set" >&2
  echo "wrangler-auth: (it is unset here only if you cleared it — do not)." >&2
  exit 2
fi

# The two unsets that make this work. See the header before changing them.
exec env -u XDG_CONFIG_HOME -u CLOUDFLARE_API_TOKEN \
  npx --yes "wrangler@${WRANGLER_VERSION}" "$@"