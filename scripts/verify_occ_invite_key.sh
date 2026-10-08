#!/bin/sh
# Verify the OCC invite key (DIG-1381, Act B1) against a deployed digichat surface.
#
# The key is read from the OCC_INVITE_KEY environment variable and is never printed, never
# written to a file, and never placed in a command line: the headers are handed to curl through
# `curl --config -` on stdin, so the value does not appear in `ps` output or shell history.
#
# What it proves, and what it cannot: see docs/ops/OCC_INVITE_KEY.md. Short version — it reads
# the `slug` in the body of GET /api/embed/tenant-config, because that route always answers HTTP
# 200 and encodes the authorization decision in the body. A script that only checks status codes
# reports a false PASS here.
#
# Usage:
#   read -rs OCC_INVITE_KEY && export OCC_INVITE_KEY   # never put it in the command line
#   bash scripts/verify_occ_invite_key.sh
#
# Environment:
#   OCC_INVITE_KEY  required. The live OCC tenant token.
#   PROBE_BASE      optional. Default https://digithings.ai (production).
#   OCC_EMBED_HOST  optional. Default https://occ.digithings.ai.
#   EXPECT_B2       optional. 0 (default) = Act B1 state, allowlist still contains OCC.
#                   1 = Act B2 state, OCC is off the allowlist and the key is the only proof.
#
# Exit status: 0 if every check matched its expected slug, 1 otherwise.

set -eu

PROBE_BASE="${PROBE_BASE:-https://digithings.ai}"
OCC_EMBED_HOST="${OCC_EMBED_HOST:-https://occ.digithings.ai}"
EXPECT_B2="${EXPECT_B2:-0}"
FIRST_PARTY_ORIGIN="${FIRST_PARTY_ORIGIN:-https://digithings.ai}"
PROBE_URL="$PROBE_BASE/api/embed/tenant-config"
TIMEOUT="${TIMEOUT:-20}"

GRANTED_SLUG="occ"
REFUSED_SLUG="embed"

if [ "${EXPECT_B2}" != "0" ] && [ "${EXPECT_B2}" != "1" ]; then
  echo "FATAL: EXPECT_B2 must be 0 or 1, got '$EXPECT_B2'" >&2
  exit 2
fi

if [ -z "${OCC_INVITE_KEY:-}" ]; then
  echo "FATAL: OCC_INVITE_KEY is not set. Load it with 'read -rs OCC_INVITE_KEY && export OCC_INVITE_KEY'." >&2
  echo "       Never pass it as a command-line argument; it would land in history and in ps." >&2
  exit 2
fi

# Reject the values the docs use as placeholders. Shipping one of these as the OCC token would
# make the check pass for anyone who has read the README.
case "$OCC_INVITE_KEY" in
  unused-for-first-party|local-dev-unused-first-party|changeme|placeholder|"")
    echo "FATAL: OCC_INVITE_KEY looks like a documentation placeholder, not a minted key." >&2
    exit 2
    ;;
esac

if [ "${#OCC_INVITE_KEY}" -lt 16 ]; then
  echo "FATAL: OCC_INVITE_KEY is ${#OCC_INVITE_KEY} characters; a minted key is 64 hex characters." >&2
  exit 2
fi

# Wrong key for the negative checks. Derived from the real one so it is guaranteed to differ
# without consulting a PRNG: suffixing cannot collide with the real value.
WRONG_KEY="${OCC_INVITE_KEY}-not-the-key"

have_jq=1
command -v jq >/dev/null 2>&1 || have_jq=0

slug_of() {
  if [ "$have_jq" -eq 1 ]; then
    printf '%s' "$1" | jq -r '.slug // "<no slug>"'
  else
    printf '%s' "$1" | sed -n 's/.*"slug" *: *"\([^"]*\)".*/\1/p' | head -n 1
  fi
}

# probe <token-mode> <origin-mode>; echoes the response body on stdout.
# token-mode:  match | mismatch | none      origin-mode:  first-party | none
probe() {
  _token_mode="$1"
  _origin_mode="$2"
  _token=""
  case "$_token_mode" in
    match) _token="$OCC_INVITE_KEY" ;;
    mismatch) _token="$WRONG_KEY" ;;
  esac
  {
    printf 'url = "%s"\n' "$PROBE_URL"
    printf 'header = "X-Embed-Host: %s"\n' "$OCC_EMBED_HOST"
    if [ -n "$_token" ]; then
      printf 'header = "X-Embed-Token: %s"\n' "$_token"
    fi
    if [ "$_origin_mode" = "first-party" ]; then
      printf 'header = "Origin: %s"\n' "$FIRST_PARTY_ORIGIN"
    fi
    printf 'silent\n'
    printf 'show-error\n'
    printf 'max-time = %s\n' "$TIMEOUT"
  } | curl -q --config - 2>&1 || true
}

failures=0
checks=0

check() {
  _label="$1"
  _token_mode="$2"
  _origin_mode="$3"
  _expected="$4"
  _explain="$5"

  checks=$((checks + 1))
  _body="$(probe "$_token_mode" "$_origin_mode")"
  _slug="$(slug_of "$_body")"

  if [ "$_slug" = "$_expected" ]; then
    printf 'PASS  %-52s slug=%s\n' "$_label" "$_slug"
  else
    failures=$((failures + 1))
    printf 'FAIL  %-52s slug=%s (expected %s)\n' "$_label" "$_slug" "$_expected"
    printf '      %s\n' "$_explain"
    printf '      body: %.200s\n' "$_body"
  fi
}

echo "OCC invite key verification"
echo "  target     : $PROBE_URL"
echo "  embed host : $OCC_EMBED_HOST"
echo "  act state  : $([ "$EXPECT_B2" = "1" ] && echo 'B2 (key is the only proof)' || echo 'B1 (occ.digithings.ai still on the first-party allowlist)')"
echo "  tooling    : $([ "$have_jq" -eq 1 ] && echo 'jq present' || echo 'jq absent, using sed')"
echo

if [ "$EXPECT_B2" = "0" ]; then
  echo "NOTE: pre-B2 a first-party Origin is authorized by the allowlist, not by the key."
  echo "      Checks 3 and 4 therefore EXPECT slug=occ (no denial). That is correct for Act B1;"
  echo "      they are expected to read slug=embed once occ.digithings.ai leaves FIRST_PARTY_EMBED_HOSTS."
  echo "      Re-run with EXPECT_B2=1 after Act B2 lands."
  echo
fi

# 1. The header alone must never authorize.
check "X-Embed-Host alone, no token, no origin" none none "$REFUSED_SLUG" \
  "A host header without a browser-attested first-party origin must never resolve a tenant."

# 2. The key must work on its own, with no origin help. This is the check that proves the new
#    value actually reached the live registry (i.e. the put + container recycle both landed).
check "correct key, no origin" match none "$GRANTED_SLUG" \
  "The key did not authorize. Either the secret put did not land, or the container was not recycled (SHARED_DIGICHAT_CONTAINER_ID bump)."

# 3 + 4. The two checks whose expected value flips at Act B2.
if [ "$EXPECT_B2" = "1" ]; then
  _denied="$REFUSED_SLUG"
else
  _denied="$GRANTED_SLUG"
fi

check "wrong key, first-party origin" mismatch first-party "$_denied" \
  "Pre-B2 this resolves occ because occ.digithings.ai is still first-party. If Act B2 has landed, this is a real denial gap."
check "no key, first-party origin" none first-party "$_denied" \
  "Pre-B2 this resolves occ because occ.digithings.ai is still first-party. Post-B2 it must be embed."

# 5. The real end-state: staff user, correct key, first-party origin.
check "correct key, first-party origin (staff path)" match first-party "$GRANTED_SLUG" \
  "This is the combination a real digithings.ai/chat/occ?token=... session produces. Note this check CANNOT tell a correct key from a wrong one pre-B2: the allowlist authorizes the origin either way. Check 2 is the only discriminating one until Act B2 lands."

# 6. No token material may come back out.
checks=$((checks + 1))
body="$(probe match first-party)"
case "$body" in
  *"$OCC_INVITE_KEY"*)
    failures=$((failures + 1))
    echo "FAIL  $(printf '%-52s' 'response body carries no key material')"
    echo "      The tenant-config response contained the key. Do not paste this body anywhere."
    ;;
  *)
    # No argv leak: shell pattern match, not grep with the key as an argument.
    if printf '%s' "$body" | grep -qi '"token"'; then
      failures=$((failures + 1))
      echo "FAIL  $(printf '%-52s' 'response body carries no key material')"
      echo "      The tenant-config response serialised a token field. toEmbedClientConfig should copy declared fields only."
    else
      echo "PASS  $(printf '%-52s' 'response body carries no key material')"
    fi
    ;;
esac

echo
if [ "$failures" -eq 0 ]; then
  echo "All $checks checks passed."
  echo "Still outstanding, and not scriptable: open https://digithings.ai/chat/occ?token=\$OCC_INVITE_KEY"
  echo "in a browser and complete one real chat message as an OCC staff user. That is the only"
  echo "proof that Pages -> readInviteToken -> X-Embed-Token -> digichat -> Container -> model"
  echo "works end to end. Record the result in docs/ops/SECRETS_ROTATION.md 'Rotation log'."
  exit 0
fi

echo "$failures of $checks checks FAILED."
exit 1