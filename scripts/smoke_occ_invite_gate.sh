#!/bin/sh
# Post-deploy smoke for the /chat/occ invite gate (DIG-1210 / DIG-3585).
#
# /chat/occ is the app's own embed route, gated once at the Worker. This checks
# BOTH halves of the gate, because only the rejection half used to be smoke
# tested and the invited half silently rotted:
#
#   uninvited  -> the site's ordinary 404, with no chat shell in the body
#   invited    -> 200, the chat itself, and no iframe (the Pages shell is gone)
#
# The invited half runs only when OCC_INVITE_KEY is set. The key is read from
# the environment; it is never printed, and it never appears in this file.
#
#   scripts/smoke_occ_invite_gate.sh
#   scripts/smoke_occ_invite_gate.sh https://digithings.ai
#
# Does not deploy anything.
set -eu

BASE="${1:-https://digithings.ai}"
URL="${BASE%/}/chat/occ/"
body=$(mktemp)
trap 'rm -f "$body"' EXIT

code=$(curl -sS -o "$body" -w '%{http_code}' --max-time 20 -H 'accept: text/html' "$URL")
if [ "$code" != "404" ]; then
  echo "expected 404 from $URL, got $code" >&2
  exit 1
fi
if grep -E -q 'dc-embed-shell|OCC help assistant|digichat:ready' "$body"; then
  echo "chat shell markup leaked in the 404 body for $URL" >&2
  exit 1
fi
echo "ok $URL 404, no chat shell"

if [ -z "${OCC_INVITE_KEY:-}" ]; then
  echo "skip invited check: OCC_INVITE_KEY is not set"
  exit 0
fi

# -G moves the token into the query string; --data-urlencode keeps it out of
# the process list's plain arguments and out of this script's output.
invited=$(mktemp)
trap 'rm -f "$body" "$invited"' EXIT
code=$(curl -sS -G -o "$invited" -w '%{http_code}' --max-time 30 \
  -H 'accept: text/html' --data-urlencode "token=${OCC_INVITE_KEY}" "$URL")

if [ "$code" != "200" ]; then
  # Never echo the URL here: it carries the invite.
  echo "invited check failed: expected 200, got $code" >&2
  exit 1
fi
if ! grep -E -q 'dc-embed-shell' "$invited"; then
  echo "invited check failed: 200 but no chat shell (dc-embed-shell) in the body" >&2
  exit 1
fi
if grep -qiE '<iframe' "$invited"; then
  echo "invited check failed: response is still an iframe shell, not the app" >&2
  exit 1
fi
echo "ok $URL invited 200, chat served directly (no iframe)"
