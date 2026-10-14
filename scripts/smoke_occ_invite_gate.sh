#!/bin/sh
# Post-deploy smoke for the /chat/occ invite gate (DIG-3585).
# Uninvited requests must 404 before any chat shell. Run after a digithings.ai
# deploy. Does not deploy anything.
#
#   scripts/smoke_occ_invite_gate.sh
#   scripts/smoke_occ_invite_gate.sh https://digithings.ai
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
if grep -E -q 'ChatPageShell|OCC help assistant|dc-chat-main|digichat:ready' "$body"; then
  echo "chat shell markup leaked in the 404 body for $URL" >&2
  exit 1
fi
echo "ok $URL 404, no chat shell"
