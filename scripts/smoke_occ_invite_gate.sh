#!/bin/sh
# Post-deploy smoke for the /chat/occ invite gate (DIG-1210 / DIG-3585).
#
# /chat/occ is the app's own embed route, gated once at the Worker. This checks
# BOTH halves of the gate, because only the rejection half used to be smoke
# tested and the invited half silently rotted:
#
#   uninvited  -> the site's ordinary 404, with no chat shell in the body
#   invited    -> 200, the chat itself, and no iframe (the Pages shell is gone)
#   API        -> with ONLY the cookie (Path=/chat) and the OCC page as
#                 Referer, /chat/api/embed/tenant-config answers the occ
#                 tenant and one real chat turn streams; without the cookie,
#                 or with it from a house page, tenant-config is never occ
#
# The invited half runs only when OCC_INVITE_KEY is set. The key is read from
# the environment; it is never printed, and it never appears in this file.
# The API half sends ONE real turn (one model call); set OCC_SMOKE_SKIP_TURN=1
# to check the tenant binding without it.
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
#
# The gate answers the link with a 302 to the tokenless URL and the
# `occ_invite` cookie (DIG-1437), so the check is two requests: the redirect
# itself, then the follow-up a browser makes with the cookie.
invited=$(mktemp)
jar=$(mktemp)
trap 'rm -f "$body" "$invited" "$jar"' EXIT
code=$(curl -sS -G -o "$invited" -D "$invited.headers" -w '%{http_code}' --max-time 30 \
  -c "$jar" -H 'accept: text/html' --data-urlencode "token=${OCC_INVITE_KEY}" "$URL")

if [ "$code" != "302" ]; then
  # Never echo the URL here: it carries the invite.
  echo "invited check failed: expected 302 (the key leaves the address bar), got $code" >&2
  exit 1
fi
if ! grep -qi '^set-cookie: *occ_invite=' "$invited.headers"; then
  echo "invited check failed: 302 carried no occ_invite cookie" >&2
  exit 1
fi
location=$(sed -n 's/^[Ll]ocation: *//p' "$invited.headers" | tr -d '\r' | head -1)
case "$location" in
  *token=*)
    echo "invited check failed: the redirect still carries the invite key" >&2
    exit 1
    ;;
esac

# Follow it the way the browser does: same URL, cookie instead of the query.
final=$(mktemp)
trap 'rm -f "$body" "$invited" "$invited.headers" "$jar" "$final"' EXIT
code=$(curl -sS -o "$final" -w '%{http_code}' --max-time 30 -b "$jar" \
  -H 'accept: text/html' "$URL")

if [ "$code" != "200" ]; then
  echo "invited check failed: cookie reload expected 200, got $code" >&2
  exit 1
fi
if ! grep -E -q 'dc-embed-shell' "$final"; then
  echo "invited check failed: 200 but no chat shell (dc-embed-shell) in the body" >&2
  exit 1
fi
if grep -qiE '<iframe' "$final"; then
  echo "invited check failed: response is still an iframe shell, not the app" >&2
  exit 1
fi
echo "ok $URL invited 302 -> cookie -> 200, chat served directly (no iframe)"

# --- The page's API calls (DIG-3585 G1) -------------------------------------
# The browser on /chat/occ holds the invite only as the cookie; the edge binds
# its /chat/api/* calls to OCC from the cookie AND the OCC page Referer. Each
# call below sends what that browser sends: the jar's cookie, never a token.
ORIGIN="${BASE%/}"
OCC_PAGE="${ORIGIN}/chat/occ"
CFG_URL="${ORIGIN}/chat/api/embed/tenant-config"
TURN_URL="${ORIGIN}/chat/api/chat"
cfg=$(mktemp)
turn=$(mktemp)
trap 'rm -f "$body" "$invited" "$invited.headers" "$jar" "$final" "$cfg" "$turn"' EXIT

if ! grep -q 'occ_invite' "$jar"; then
  echo "api check failed: the cookie jar lost occ_invite" >&2
  exit 1
fi
# Path=/chat, not /chat/occ: otherwise the browser never sends it to /chat/api/*.
if ! awk '$0 ~ /occ_invite/ && $3 == "/chat" { found = 1 } END { exit !found }' "$jar"; then
  echo "api check failed: occ_invite is not scoped to Path=/chat" >&2
  exit 1
fi

tenant_slug() {
  # The slug field of the client-safe tenant config, or nothing.
  sed -n 's/.*"slug"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -1
}

code=$(curl -sS -o "$cfg" -w '%{http_code}' --max-time 30 -b "$jar" \
  -H "referer: ${OCC_PAGE}" -H "origin: ${ORIGIN}" "$CFG_URL")
slug=$(tenant_slug "$cfg")
if [ "$code" != "200" ] || [ "$slug" != "occ" ]; then
  echo "api check failed: cookie-only tenant-config from the OCC page gave $code slug '${slug}', expected occ" >&2
  exit 1
fi
echo "ok tenant-config with only the cookie -> occ"

code=$(curl -sS -o "$cfg" -w '%{http_code}' --max-time 30 \
  -H "referer: ${OCC_PAGE}" -H "origin: ${ORIGIN}" "$CFG_URL")
slug=$(tenant_slug "$cfg")
if [ "$slug" = "occ" ]; then
  echo "api check failed: tenant-config WITHOUT the cookie resolved occ" >&2
  exit 1
fi
echo "ok tenant-config without the cookie -> ${slug:-none} ($code), not occ"

code=$(curl -sS -o "$cfg" -w '%{http_code}' --max-time 30 -b "$jar" \
  -H "referer: ${ORIGIN}/chat" -H "origin: ${ORIGIN}" "$CFG_URL")
slug=$(tenant_slug "$cfg")
if [ "$slug" = "occ" ]; then
  echo "api check failed: a house page with the cookie resolved occ" >&2
  exit 1
fi
echo "ok tenant-config from a house page with the cookie -> ${slug:-none} ($code), not occ"

if [ "${OCC_SMOKE_SKIP_TURN:-}" = "1" ]; then
  echo "skip the real turn: OCC_SMOKE_SKIP_TURN=1"
  exit 0
fi

msg='{"messages":[{"id":"smoke-1","role":"user","parts":[{"type":"text","text":"Reply with the single word: ok"}]}]}'

# The same turn WITHOUT the cookie is refused before any model call, so the
# 200 below can only be the occ tenant's admission (the app emits no tenant
# marker in the stream; tenant-config above is the tenant assertion).
code=$(curl -sS -o "$turn" -w '%{http_code}' --max-time 30 \
  -H "referer: ${OCC_PAGE}" -H "origin: ${ORIGIN}" \
  -H 'content-type: application/json' --data "$msg" "$TURN_URL")
if [ "$code" = "200" ]; then
  echo "api check failed: a turn from the OCC page WITHOUT the cookie was admitted" >&2
  exit 1
fi
echo "ok a turn from the OCC page without the cookie is refused ($code)"

# One real turn, the request the page itself makes. It must be admitted and
# stream an answer: an unbound call is refused (401) on the OCC page.
code=$(curl -sS -N -o "$turn" -w '%{http_code}' --max-time 120 -b "$jar" \
  -H "referer: ${OCC_PAGE}" -H "origin: ${ORIGIN}" \
  -H 'content-type: application/json' --data "$msg" "$TURN_URL")
if [ "$code" != "200" ]; then
  echo "api check failed: the cookie-only turn from the OCC page got $code" >&2
  head -c 300 "$turn" >&2 || true
  echo >&2
  exit 1
fi
if [ ! -s "$turn" ] || grep -q '"type":"error"' "$turn"; then
  echo "api check failed: the turn returned 200 but streamed no answer or an error" >&2
  head -c 300 "$turn" >&2 || true
  echo >&2
  exit 1
fi
echo "ok one real turn with only the cookie streamed an answer as the occ tenant"
