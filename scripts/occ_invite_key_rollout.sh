#!/usr/bin/env bash
#
# OCC invite key — one-command rollout, mint path excluded (DIG-1381, Act B1).
#
# This is `docs/ops/OCC_INVITE_KEY.md` § Rollout steps 2-5 as a single reviewed
# command. It exists because two accepted confirmation cards produced two
# unexecuted rollouts: the gap was friction, not intent. Nothing about the
# procedure changed — it is the same steps in the same order.
#
#   WHAT IT WRITES TO PRODUCTION
#     1. digichat Worker secret DIGICHAT_EMBED_TENANTS  (exactly two fields on
#        the OCC entry: `token`, and `backend.digisearchIndex`)
#     2. a local git commit bumping SHARED_DIGICHAT_CONTAINER_ID  (NOT pushed)
#     3. a production deploy of the digithings-digichat Worker
#
#   THE SECOND FIELD IS A CORPUS NARROWING, NOT A SIDE EFFECT (DIG-2779)
#     The same put also rewrites occ.digithings.ai.backend.digisearchIndex to
#     the help corpus only. The live tenant reads "occ_help,occ_tickets"; the
#     tickets corpus is the customer-PII one, so a token-only rotation would
#     rotate the credential and leave the retrieval grant exactly as wide as it
#     was. Counsel's condition for this rollout is that the two land together,
#     so the allowed-diff guard is exactly {token, backend.digisearchIndex} and
#     BOTH are required to change — not merely "at most these".
#
#   WHAT IT DOES NOT DO
#     - It does not mint the key. There is nowhere safe for this script to put a
#       new credential, and printing one is forbidden. Mint with
#       `openssl rand -hex 32`, hand it to the secrets manager, and keep it there.
#     - It does not push the container-id commit. `git push` is printed for you.
#     - It does not touch `mcp.servers`. That literal is the stack Worker's
#       MCP_EDGE_KEY — a different credential. A one-sided change there breaks
#       the OCC tool calls (R10).
#
#   WHY THE CONTAINER-ID BUMP IS NOT OPTIONAL
#     A warm Container keeps the env it booted with (sleepAfter = "3m",
#     apps/digichat-cloudflare/src/index.ts:26). `secret put` + `deploy` without
#     the bump looks rotated in `secret list` while the old value stays live —
#     R5, see docs/ops/SECRETS_ROTATION.md § The container boot-env trap.
#     This script makes the bump and the deploy inseparable.
#
#   SECRETS
#     Both inputs are read with the terminal echo disabled, are held only in
#     process memory, and are never written to a file, `ps` output, a shell
#     history or a log. The script never echoes either one. `set -x` is never
#     enabled. Output is the fingerprint (length + first 8 hex of SHA-256),
#     which is non-reversible and is what SECRETS_ROTATION.md § Records asks for.
#
#   LIMITS
#     No dependency, no new Worker binding, no header, no D1/KV/R2, no Durable
#     Object, no subrequest. It runs `wrangler secret put` and `wrangler deploy`
#     once each, then curls digithings.ai five times. Wall clock ~3 minutes,
#     almost all of it the `sleep` that covers the drain window.
#
#   ROLLBACK (this is also the Act B2 rollback — see the runbook)
#     Re-run with the previous tenant JSON and the previous key. Bump
#     SHARED_DIGICHAT_CONTAINER_ID again (shared-v11 -> shared-v12) and redeploy.
#     Before Act B2 lands this is a no-op in practice: nothing about the running
#     service depends on the key yet.
#
# Usage, from the repo root:
#   bash scripts/occ_invite_key_rollout.sh
#
#   Non-interactive (CI). Two env vars supply the secrets and one opts in to
#   token auth, because the default deliberately refuses a shell token:
#     OCC_ROLLOUT_AUTH=api-token \
#     OCC_EMBED_TENANTS_CURRENT=<current registry JSON from the secrets manager> \
#     OCC_INVITE_KEY=<new key> \
#     bash scripts/occ_invite_key_rollout.sh
#   The confirmation prompt is still read from stdin, so feed it ROLLOUT:
#     printf 'ROLLOUT\n' | bash scripts/occ_invite_key_rollout.sh
#   .github/workflows/occ-invite-key-rollout.yml is the one-click wrapper.
#
set -euo pipefail

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
say "3/7 confirm — this writes a production secret and deploys a Worker"
cat >&2 <<EOF
About to do, in order:
  1. wrangler secret put $SECRET_NAME   (digichat Worker, production)
  2. commit the SHARED_DIGICHAT_CONTAINER_ID bump locally (not pushed)
  3. wrangler deploy                    (digithings-digichat Worker, production)
  4. sleep $DRAIN_SECONDS
  5. scripts/verify_occ_invite_key.sh   (prints PASS/FAIL only)

Nothing user-facing changes: occ.digithings.ai is still on the first-party allowlist,
so this cannot lock OCC out. Act B2 is a separate deploy and must not be combined
with this one.
EOF
printf 'Type ROLLOUT to continue: ' >&2
CONFIRM=""
IFS= read -r CONFIRM || true
[ "$CONFIRM" = "ROLLOUT" ] || fail "confirmation not given. Nothing was written."

# ------------------------------------------------------------------- secret put --
say "4/7 put the secret"
printf '%s' "$NEW_JSON" | wrangler secret put "$SECRET_NAME" >&2 \
  || fail "the secret put failed. The deploy has NOT run, so nothing is live."

# --------------------------------------------------------------- container id bump --
say "5/7 bump SHARED_DIGICHAT_CONTAINER_ID so a warm instance is recycled"
CURRENT_ID="$(sed -n 's/^export const SHARED_DIGICHAT_CONTAINER_ID = "\(shared-v[0-9]\+\)";.*/\1/p' "$PATHS_TS")"
[ -n "$CURRENT_ID" ] || fail "could not read SHARED_DIGICHAT_CONTAINER_ID from $PATHS_TS. Nothing was deployed."
CURRENT_N="${CURRENT_ID##*v}"
NEXT_ID="shared-v$((CURRENT_N + 1))"
printf '%s -> %s\n' "$CURRENT_ID" "$NEXT_ID" >&2
[ "$CURRENT_ID" != "$NEXT_ID" ] || fail "refusing to deploy without a container-id change; the old instance would keep the old key."

cp "$PATHS_TS" "$PATHS_TS.occ-rollout.bak"
sed -i.bak "s/^export const SHARED_DIGICHAT_CONTAINER_ID = \"$CURRENT_ID\";/export const SHARED_DIGICHAT_CONTAINER_ID = \"$NEXT_ID\";/" "$PATHS_TS"
rm -f "$PATHS_TS.bak"
grep -q "SHARED_DIGICHAT_CONTAINER_ID = \"$NEXT_ID\"" "$PATHS_TS" \
  || { cp "$PATHS_TS.occ-rollout.bak" "$PATHS_TS"; fail "the bump did not apply; $PATHS_TS was restored. Nothing was deployed."; }
rm -f "$PATHS_TS.occ-rollout.bak"

git -C "$REPO_ROOT" add "$PATHS_TS"
if ! git -C "$REPO_ROOT" commit -q -m "chore(digichat): recycle the container so the OCC invite key takes effect (DIG-1381 Act B1)" \
       -m "shared-v${CURRENT_N} -> shared-v${CURRENT_N}x. A warm Container keeps its boot env, so the secret put alone leaves the old token live (R5). Recorded because the container id is the only evidence that the new value was booted."; then
  printf 'note: could not commit the container-id bump; the file on disk is still bumped. Commit it by hand.\n' >&2
fi

# ---------------------------------------------------------------------- deploy --
say "6/7 deploy the digichat Worker"
wrangler deploy --outdir "$(mktemp -d)" >/dev/null 2>&1 || wrangler deploy >&2 \
  || fail "the deploy failed. The secret is stored but the container still has the old boot env; fix the deploy before verifying."

printf 'recording the Worker version id for the rotation log:\n' >&2
wrangler versions list 2>/dev/null | tail -n 5 >&2 || true

# --------------------------------------------------------------------- verify --
say "7/7 wait $DRAIN_SECONDS s for the old instance to drain, then verify"
sleep "$DRAIN_SECONDS"

say "verification"
set +e
OCC_INVITE_KEY="$NEW_KEY" EXPECT_B2=0 bash "$REPO_ROOT/scripts/verify_occ_invite_key.sh"
VERIFY_RC=$?
set -e

# --------------------------------------------------------------------- summary --
say "result"
cat >&2 <<EOF
container id     $CURRENT_ID -> $NEXT_ID
key fingerprint   length $KEY_LEN, sha256 $KEY_FP…
verification     scripts/verify_occ_invite_key.sh exit $VERIFY_RC

Check 2 is the one that matters: "right key, no origin" must resolve slug=occ.
Checks 3 and 4 are EXPECTED to read slug=occ right now, because occ.digithings.ai
is still on the first-party allowlist. They are not a fault. They are the checks
that must flip to embed at Act B2.

If exit was 1 and check 2 said embed, the new key did NOT reach the running
registry — the recycle did not take effect. Do not start Act B2.

Push the container-id commit (it is the only record of the recycle):
  git -C $REPO_ROOT push

Append to docs/ops/SECRETS_ROTATION.md § Rotation log:
  OCC invite key, DIGICHAT_EMBED_TENANTS, $NEXT_ID, fingerprint length $KEY_LEN
  sha256 $KEY_FP, verification exit $VERIFY_RC

Still to do by hand, once: open https://digithings.ai/chat/occ?token=<key> as an
OCC staff user and send one message. That is the only end-to-end proof, and no
script can do it.
EOF

exit "$VERIFY_RC"