#!/usr/bin/env bash
#
# OCC invite key — R6 write-secret half (DIG-3697).
#
# Split out of scripts/occ_invite_key_rollout.sh. This file keeps the
# preflight and the allowed-diff guard (only occ.digithings.ai token and
# backend.digisearchIndex may change). It does not deploy. Deploy is
# scripts/occ_invite_key_deploy.sh (R5).
#
# Disarmed: after the guard it stops. It does not run `wrangler secret put`
# and it does not write KV. Tenant config is still a Worker secret today;
# the KV read path is DIG-3699, not this file.
#
# The one-command entrypoint scripts/occ_invite_key_rollout.sh calls this
# file so the offline auth guard still has one entry.
#
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DIR="$REPO_ROOT/apps/digichat-cloudflare"
PATHS_TS="$WORKER_DIR/src/paths.ts"
SECRET_NAME="DIGICHAT_EMBED_TENANTS"
OCC_HOST="occ.digithings.ai"
WRANGLER_VERSION="4.133.0"
DRAIN_SECONDS=180

# The one retrieval corpus Counsel allows the OCC embed to reach (DIG-2779).
#
# Deliberately NOT `${OCC_HELP_INDEX:-occ_help}`. The value is a security
# decision, so the environment must not be able to move it: an operator who
# exports OCC_HELP_INDEX=occ_help,occ_tickets would otherwise widen the grant
# through the very guard that is supposed to stop it. The live OCC tenant reads
# "occ_help,occ_tickets" — occ_tickets is the customer-PII corpus built by
# scripts/index_occ_tickets.py (docs/adr/0031) — and the narrowing this run
# ships is "occ_help,occ_tickets" -> "occ_help".
#
# The field is backend.digisearchIndex, not a top-level key: embed-tenants.ts:43
# declares it inside the digigraph backend type and validateEntry (embed-tenants.ts:309-325)
# reads it from there. The allowed-diff paths below are written to match.
OCC_HELP_INDEX="occ_help"
OCC_FORBIDDEN_INDEX="occ_tickets"

# Two load-bearing deviations from a plain `npx wrangler` call.
#
#   1. Every call runs inside $WORKER_DIR. The digichat Worker is configured by
#      apps/digichat-cloudflare/wrangler.toml and there is no wrangler.toml at the
#      repo root, so from the root `wrangler secret put` and `wrangler deploy`
#      resolve no Worker at all — the put would not land on digithings-digichat.
#      One wrapper covers all four call sites (secret list, secret put, deploy,
#      versions list).
#
#   2. CLOUDFLARE_API_TOKEN is dropped so a bare `wrangler login` wins over a
#      shell token; a shell token shadows it and fails with auth error 10000
#      (docs/ops/SECRETS_ROTATION.md preamble). CI has no interactive terminal,
#      so a caller that has deliberately provisioned a token opts in with
#      OCC_ROLLOUT_AUTH=api-token. The default is unchanged: login only.
if [ "${OCC_ROLLOUT_AUTH:-login}" = "api-token" ]; then
  wrangler() { (cd -- "$WORKER_DIR" && npx --yes "wrangler@$WRANGLER_VERSION" "$@"); }
else
  wrangler() { (cd -- "$WORKER_DIR" && env -u CLOUDFLARE_API_TOKEN npx --yes "wrangler@$WRANGLER_VERSION" "$@"); }
fi

say()  { printf '\n=== %s\n' "$*" >&2; }
fail() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight --
say "0/7 preflight"

for tool in git jq npx curl node; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required and was not found on PATH."
done

# Refuse an auth mode this script does not implement instead of silently falling
# back to `login`. In CI `login` cannot succeed (no terminal, no browser) and the
# failure surfaces later as a confusing whoami error.
case "${OCC_ROLLOUT_AUTH:-login}" in
  login) ;;
  api-token)
    [ -n "${CLOUDFLARE_API_TOKEN:-}" ] \
      || fail "OCC_ROLLOUT_AUTH=api-token but CLOUDFLARE_API_TOKEN is empty. Nothing was written. Unset OCC_ROLLOUT_AUTH to authenticate with an interactive 'wrangler login' instead."
    [ -n "${CLOUDFLARE_ACCOUNT_ID:-}" ] \
      || fail "OCC_ROLLOUT_AUTH=api-token but CLOUDFLARE_ACCOUNT_ID is empty, so wrangler cannot tell which account a deploy would land on. Nothing was written."
    ;;
  *) fail "OCC_ROLLOUT_AUTH must be 'login' (the default) or 'api-token'; got '${OCC_ROLLOUT_AUTH}'. Nothing was written." ;;
esac

[ -d "$WORKER_DIR" ] || fail "expected the digichat Worker at $WORKER_DIR"
[ -f "$PATHS_TS" ]    || fail "expected $PATHS_TS"
[ -x "$REPO_ROOT/scripts/verify_occ_invite_key.sh" ] || chmod +x "$REPO_ROOT/scripts/verify_occ_invite_key.sh"

git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || fail "run this from inside the digithings repo, not a copy of it."

# The script refuses to invent a key, so it also refuses to accept a doc
# placeholder as one. Same guards as scripts/verify_occ_invite_key.sh.
is_placeholder_key() {
  case "$1" in
    ""|changeme|placeholder|unused-for-first-party|local-dev-unused-first-party) return 0 ;;
  esac
  case "$1" in
    *unused-for-first-party*|*placeholder*|*changeme*|*example*|*dummy*) return 0 ;;
  esac
  return 1
}

read_secret() { # $1 = prompt label. Reads one line with the terminal echo off.
  local label="$1" value=""
  if [ -t 0 ]; then
    printf '\n%s (input is hidden; nothing is echoed back)\n' "$label" >&2
    stty -echo 2>/dev/null || true
    IFS= read -r value || true
    stty echo 2>/dev/null || true
    printf '\n' >&2
  else
    printf '%s: reading from stdin\n' "$label" >&2
    IFS= read -r value || true
  fi
  printf '%s' "$value"
}

say "0/7 preflight: confirm Cloudflare auth"
# `wrangler whoami` exits 0 even when it reports "You are not authenticated", so the
# exit code is not a usable signal here — match the output instead. Getting this
# wrong produces a misleading "the secret is not set" failure ten lines later.
#
# Order is load-bearing, so do not merge these two cases into one. On an expired
# token wrangler prints "Not logged in. Your auth token has expired..." — and the
# substring "logged in" occurs inside "Not logged in". A positive-only check
# therefore confirms an identity that does not exist, and the operator is then told
# the registry secret is missing when the real problem is only an expired token.
# That is the direction that matters: acting on it overwrites the live OCC registry.
# Asserted by scripts/check_occ_rollout_auth_guard.py.
WHOAMI_OUT="$(wrangler whoami 2>&1 || true)"
printf '%s\n' "$WHOAMI_OUT" >&2
case "$WHOAMI_OUT" in
  *"not authenticated"*|*"Not logged in"*|*"auth token has expired"*|\
  *"Provide a valid API token"*|*"Missing an account ID"*)
    fail "wrangler is not authenticated (expired token, or not logged in). Run 'wrangler login' in an interactive terminal first, or set OCC_ROLLOUT_AUTH=api-token with CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID for a non-interactive caller. By default this script will not fall back to a CLOUDFLARE_API_TOKEN from the shell, on purpose. Nothing was written." ;;
esac
case "$WHOAMI_OUT" in
  *"OAuth token"*|*"API Token"*|*"logged in"*) : ;;
  *) fail "could not confirm a Cloudflare identity from wrangler's output. Stop here rather than guess which account a deploy would land on." ;;
esac

say "0/7 preflight: confirm the secret name already exists (names only; values are write-only)"
# Distinguish "auth/network failed" from "genuinely not set": they look identical
# after a grep, and only one of them is the operator's problem to fix here. The
# auth patterns must mirror the `whoami` guard above — when they drift apart, an
# unreadable list silently becomes a false "the secret is not set" verdict.
SECRET_LIST="$(wrangler secret list 2>&1 || true)"
if ! printf '%s' "$SECRET_LIST" | grep -q "$SECRET_NAME"; then
  case "$SECRET_LIST" in
    *"not authenticated"*|*"Not logged in"*|*"auth token has expired"*|\
    *"Missing an account ID"*|*"error code:"*|*"Invalid"*)
      fail "could not read the secret list from the Cloudflare API (auth or network). Output:
$(printf '%s' "$SECRET_LIST" | sed 's/^/    /')
Nothing was written. Fix the auth or the connectivity, then re-run. This is NOT evidence that the secret is missing." ;;
    *)
      fail "$SECRET_NAME is not set on this Worker. Stop and read the runbook: Act B1 changes a field inside the existing registry, it does not create the secret. Nothing was written." ;;
  esac
fi

# -------------------------------------------------------------------- inputs --
say "1/7 read the current production registry value (contains the MCP_EDGE_KEY literal)"
say "1/7 read the new OCC invite key"
# Both prompts are read with echo off and held in memory only.
CURRENT_JSON=""
if [ -n "${OCC_EMBED_TENANTS_CURRENT:-}" ]; then
  CURRENT_JSON="$OCC_EMBED_TENANTS_CURRENT"
  printf 'using OCC_EMBED_TENANTS_CURRENT from the environment\n' >&2
else
  CURRENT_JSON="$(read_secret 'Paste the CURRENT DIGICHAT_EMBED_TENANTS value from the secrets manager')"
fi

NEW_KEY=""
if [ -n "${OCC_INVITE_KEY:-}" ]; then
  NEW_KEY="$OCC_INVITE_KEY"
  printf 'using OCC_INVITE_KEY from the environment\n' >&2
else
  NEW_KEY="$(read_secret 'Paste the NEW OCC invite key')"
fi
unset CURRENT_JSON_RAW 2>/dev/null || true

[ -n "$NEW_KEY" ] || fail "the new OCC invite key was empty. Nothing was written."
is_placeholder_key "$NEW_KEY" \
  && fail "the value supplied looks like a documentation placeholder, not a key. Mint one with 'openssl rand -hex 32'. Nothing was written."
[ "${#NEW_KEY}" -ge 16 ] || fail "the new key is only ${#NEW_KEY} characters. Expected a 64-hex value from 'openssl rand -hex 32'. Nothing was written."

printf '%s' "$CURRENT_JSON" | jq -e . >/dev/null 2>&1 \
  || fail "the current registry value did not parse as JSON. Paste the raw value from the secrets manager. Nothing was written."
printf '%s' "$CURRENT_JSON" | jq -e --arg h "$OCC_HOST" 'has($h)' >/dev/null 2>&1 \
  || fail "the registry has no \"$OCC_HOST\" entry, so this is not the OCC registry you think it is. Nothing was written."

# ------------------------------------------------------------- build the JSON --
say "2/7 build the new registry value (exactly two fields change: the OCC token, and the OCC retrieval corpus)"
# Everything except those two is carried across verbatim, including the
# mcp.servers entry whose literal is MCP_EDGE_KEY.
NEW_JSON="$(
  printf '%s' "$CURRENT_JSON" \
    | jq --arg h "$OCC_HOST" --arg k "$NEW_KEY" --arg i "$OCC_HELP_INDEX" \
          '.[$h].token = $k | .[$h].backend.digisearchIndex = $i'
)"

say "2/7 validate the shape before it goes near the account"
printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" --arg k "$NEW_KEY" '.[$h].token == $k' >/dev/null \
  || fail "the OCC token did not survive the edit. Nothing was written."
printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" '.[$h].mcp.servers | length > 0' >/dev/null \
  || fail "the OCC entry has no mcp.servers after the edit. The zammad route would break (R10). Nothing was written."
printf '%s' "$NEW_JSON" | jq -e 'to_entries | all(.value | has("token"))' >/dev/null \
  || fail "at least one tenant entry has no token field. The registry validator requires one per entry (apps/digichat/src/lib/embed-tenants.ts:511). Nothing was written."
# The corpus gate, proved with jq rather than trusted from the paste: the whole
# point of the second allowed field is that the grant gets NARROWER, so a value
# that is merely plausible is exactly the failure Counsel's condition prevents.
#
# The named-corpus check comes FIRST so a regression is refused with the reason
# a human needs ("the tickets corpus is still reachable") instead of a shape
# mismatch. Scoped to the OCC entry: another tenant may legitimately use it.
if printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" --arg i "$OCC_FORBIDDEN_INDEX" \
     '.[$h].backend.digisearchIndex | test("(^|,)" + $i + "(,|$)")' >/dev/null 2>&1; then
  fail "\"$OCC_FORBIDDEN_INDEX\" is still reachable by the OCC tenant. That corpus carries customer ticket text (docs/adr/0031). Nothing was written."
fi
printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" --arg i "$OCC_HELP_INDEX" '.[$h].backend.digisearchIndex == $i' >/dev/null \
  || fail "the OCC retrieval corpus is not exactly \"$OCC_HELP_INDEX\" after the edit. Nothing was written."
# Prove the ONLY differences are those two. Anything else means the paste was
# wrong and a `put` would silently change routing, gate mode or the MCP edge key.
#
# The path set is the UNION of both documents. Walking only the current file's
# paths would make an ADDED key invisible: `paths(scalars)` is evaluated against
# the CURRENT registry, so a backend.digisearchIndex appearing where none existed
# would contribute nothing to CHANGED_KEYS, and the "both required" assert below
# would then be unreachable rather than satisfied.
CHANGED_KEYS="$(printf '%s' "$CURRENT_JSON" | jq -r --slurpfile new <(printf '%s' "$NEW_JSON" | jq -S .) '
  . as $cur
  | (($cur | [paths(scalars)]) + ($new[0] | [paths(scalars)]) | unique_by(.)) as $all
  | $all[] as $p
  | select(($cur | getpath($p)) != ($new[0] | getpath($p)))
  | $p | join(".")' 2>/dev/null || true)"
TOKEN_PATH="$OCC_HOST.token"
INDEX_PATH="$OCC_HOST.backend.digisearchIndex"
UNEXPECTED="$(printf '%s\n' "$CHANGED_KEYS" | grep -v -e "^${TOKEN_PATH}\$" -e "^${INDEX_PATH}\$" || true)"
[ -z "$UNEXPECTED" ] \
  || fail "the edit would change more than the OCC token and the OCC retrieval corpus:
$(printf '%s' "$UNEXPECTED" | sed 's/^/    /')
Refusing to put. Nothing was written."
# "At most these two" is not the requirement. Counsel's condition is that the put
# NARROWS the corpus, so both must actually move: a run that rotates the key and
# leaves occ_tickets reachable must not report a compliant rollout.
grep -qx "$TOKEN_PATH" <<<"$CHANGED_KEYS" \
  || fail "$TOKEN_PATH did not change. This rollout rotates the key, so the pasted registry already held the new one. Nothing was written."
grep -qx "$INDEX_PATH" <<<"$CHANGED_KEYS" \
  || fail "$INDEX_PATH did not change. The live OCC tenant reads \"occ_help,occ_tickets\", so the narrowing this run exists to apply should have moved it to \"$OCC_HELP_INDEX\". Nothing was written."

printf 'exactly two fields will change: %s and %s -> %s\n' "$TOKEN_PATH" "$INDEX_PATH" "$OCC_HELP_INDEX"
printf 'tenant hosts in the new value: %s\n' "$(printf '%s' "$NEW_JSON" | jq -r 'keys | join(", ")')"

# ------------------------------------------------------------------ fingerprint --
KEY_LEN="${#NEW_KEY}"
KEY_FP="$(printf '%s' "$NEW_KEY" | shasum -a 256 | cut -c1-8)"
printf 'new key fingerprint (length %s, sha256 %s…) — record this, never the key\n' "$KEY_LEN" "$KEY_FP" >&2

# --------------------------------------------------------------------- confirm --
say "3/7 confirm — this half is disarmed and writes nothing"
cat >&2 <<EOF
This is the R6 write-secret half. It does not write a Worker secret,
does not write KV, and does not deploy the digichat Worker.

Type ROLLOUT to reach the disarm stop. Nothing is written either way.
EOF
printf 'Type ROLLOUT to continue: ' >&2
CONFIRM=""
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "ROLLOUT" ] || fail "confirmation not given. Nothing was written."

say "4/7 write-secret is disarmed"
fail "DISARMED: R6 write-secret/KV does not run until Chris approves. Nothing was written."
