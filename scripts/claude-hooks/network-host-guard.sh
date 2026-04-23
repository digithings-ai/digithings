#!/usr/bin/env bash
# Block curl/wget/http calls to non-allowlisted hosts. Best-effort: parses the
# first URL-looking token from the command. Not a firewall — a guardrail against
# accidental data exfiltration or third-party service calls.
source "$(dirname "$0")/_lib.sh"

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

# Only inspect commands that are likely to make network calls.
case "$cmd" in
  *curl*|*wget*|*httpie*|*http\ *) ;;
  *) exit 0 ;;
esac

# Allowed host suffixes. Loopback and private ranges always allowed.
allowed_hosts=(
  "github.com"
  "api.github.com"
  "raw.githubusercontent.com"
  "objects.githubusercontent.com"
  "codeload.github.com"
  "pypi.org"
  "files.pythonhosted.org"
  "docker.io"
  "registry-1.docker.io"
  "ghcr.io"
  "anthropic.com"
  "api.anthropic.com"
  "openai.com"
  "api.openai.com"
  "huggingface.co"
  "cursor.com"
  "cursor.sh"
  "claude.ai"
  "mcp.supabase.com"
  "localhost"
  "127.0.0.1"
  "0.0.0.0"
)

# Extract http(s) URLs from the command.
urls="$(printf '%s' "$cmd" | grep -oE 'https?://[A-Za-z0-9._:-]+' || true)"
[ -z "$urls" ] && exit 0

while IFS= read -r url; do
  [ -z "$url" ] && continue
  host="$(printf '%s' "$url" | sed -E 's|https?://||; s|/.*||; s|:.*||')"
  allowed=0
  for h in "${allowed_hosts[@]}"; do
    if [ "$host" = "$h" ] || [[ "$host" == *".$h" ]]; then
      allowed=1; break
    fi
  done
  # Private network ranges (10.x, 172.16-31.x, 192.168.x) always allowed.
  if [[ "$host" =~ ^10\. ]] || [[ "$host" =~ ^192\.168\. ]] || [[ "$host" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]]; then
    allowed=1
  fi
  if [ "$allowed" = 0 ]; then
    deny "network call to '$host' is not in the allowlist. \
If this host is legitimate, add it to scripts/claude-hooks/network-host-guard.sh."
  fi
done <<< "$urls"

exit 0
