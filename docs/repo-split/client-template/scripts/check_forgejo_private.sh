#!/usr/bin/env bash
# Refuse unless this repo's Forgejo `origin` is a PRIVATE repo. Fails closed: any error
# (no origin, origin not on an allowed Forgejo host, no keychain token, API error,
# unreadable or missing flag) refuses. The token is read from the macOS keychain and is
# passed to curl on stdin, so it never appears in argv, logs or output.
#
# Env (all optional, none secret):
#   FORGEJO_HOSTS             space-separated host[:port] list origin may point at
#                             (default: "192.168.1.35:3000 localhost:3000")
#   FORGEJO_KEYCHAIN_SERVICE  keychain item holding the agent's Forgejo token
#                             (default: digiforge-grokbot)
set -euo pipefail
refuse() { echo "refused: $*" >&2; exit 1; }

hosts="${FORGEJO_HOSTS:-192.168.1.35:3000 localhost:3000}"
service="${FORGEJO_KEYCHAIN_SERVICE:-digiforge-grokbot}"

url="$(git remote get-url origin 2>/dev/null)" || refuse "no git remote 'origin'"
# http(s)://[user[:pass]@]host[:port]/owner/repo[.git][/]
re='^(https?)://([^@/]+@)?([^/]+)/([^/]+)/([^/]+)$'
url="${url%/}"
[[ "$url" =~ $re ]] || refuse "origin is not an http(s) Forgejo URL"
scheme="${BASH_REMATCH[1]}"; host="${BASH_REMATCH[3]}"
owner="${BASH_REMATCH[4]}"; name="${BASH_REMATCH[5]%.git}"
ok=0; for h in $hosts; do [ "$h" = "$host" ] && ok=1; done
[ "$ok" = 1 ] || refuse "origin host $host is not an allowed Forgejo host (FORGEJO_HOSTS)"

command -v security >/dev/null 2>&1 || refuse "no macOS keychain ('security') to read the Forgejo token"
token="$(security find-generic-password -s "$service" -w 2>/dev/null)" || refuse "keychain item $service not readable"
[ -n "$token" ] || refuse "keychain item $service is empty"

body="$(printf 'header = "Authorization: token %s"\n' "$token" \
  | curl -fsS --max-time 15 -K - "$scheme://$host/api/v1/repos/$owner/$name" 2>/dev/null)" \
  || { unset token; refuse "could not read $owner/$name from the Forgejo API"; }
unset token

flag="$(printf '%s' "$body" | python3 -c '
import json, sys
try:
    r = json.load(sys.stdin)
except Exception:
    print("unreadable"); sys.exit(0)
p = r.get("private") if isinstance(r, dict) else None
print("true" if p is True else "false" if p is False else "unreadable")
')"
case "$flag" in
  true) echo "ok: Forgejo repo $owner/$name is private" ;;
  false) refuse "Forgejo repo $owner/$name is NOT private" ;;
  *) refuse "Forgejo repo $owner/$name: private flag missing or unreadable" ;;
esac
