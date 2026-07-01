#!/usr/bin/env bash
# Block curl/wget/http calls to non-allowlisted hosts. Best-effort: parses the
# first URL-looking token from the command. Not a firewall — a guardrail against
# accidental data exfiltration or third-party service calls.
source "$(dirname "$0")/_lib.sh"

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

case "$cmd" in
  *curl*|*wget*|*httpie*|*http\ *) ;;
  *) exit 0 ;;
esac

# Allowed hosts. Edit this list to match your project's legitimate external services.
# Loopback and private network ranges are always allowed (see below).
allowed_hosts=(
  {{ALLOWED_HOSTS_BASH}}
)

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
  # Private network ranges always allowed.
  if [[ "$host" =~ ^10\. ]] || [[ "$host" =~ ^192\.168\. ]] || [[ "$host" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]]; then
    allowed=1
  fi
  if [ "$allowed" = 0 ]; then
    deny "network call to '$host' is not in the allowlist. \
If this host is legitimate, add it to scripts/claude-hooks/network-host-guard.sh."
  fi
done <<< "$urls"

exit 0
