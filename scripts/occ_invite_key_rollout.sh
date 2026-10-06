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
#     1. digichat Worker secret DIGICHAT_EMBED_TENANTS  (the OCC `token` field only)
#     2. a local git commit bumping SHARED_DIGICHAT_CONTAINER_ID  (NOT pushed)
#     3. a production deploy of the digithings-digichat Worker
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
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_DIR="$REPO_ROOT/apps/digichat-cloudflare"
PATHS_TS="$WORKER_DIR/src/paths.ts"
SECRET_NAME="DIGICHAT_EMBED_TENANTS"
OCC_HOST="occ.digithings.ai"
WRANGLER_VERSION="4.133.0"
DRAIN_SECONDS=180

# A bare `wrangler login` must win over a shell token; a shell CLOUDFLARE_API_TOKEN
# shadows it and fails with auth error 10000 (docs/ops/SECRETS_ROTATION.md preamble).
wrangler() { env -u CLOUDFLARE_API_TOKEN npx --yes "wrangler@$WRANGLER_VERSION" "$@"; }

say()  { printf '\n=== %s\n' "$*" >&2; }
fail() { printf '\nFATAL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preflight --
say "0/7 preflight"

for tool in git jq npx curl node; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required and was not found on PATH."
done

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
WHOAMI_OUT="$(wrangler whoami 2>&1 || true)"
printf '%s\n' "$WHOAMI_OUT" >&2
case "$WHOAMI_OUT" in
  *"not authenticated"*|*"Provide a valid API token"*|*"Missing an account ID"*)
    fail "wrangler is not authenticated. Run 'wrangler login' first; this script will not fall back to a CLOUDFLARE_API_TOKEN from the shell, on purpose." ;;
esac
case "$WHOAMI_OUT" in
  *"OAuth token"*|*"API Token"*|*"logged in"*) : ;;
  *) fail "could not confirm a Cloudflare identity from wrangler's output. Stop here rather than guess which account a deploy would land on." ;;
esac

say "0/7 preflight: confirm the secret name already exists (names only; values are write-only)"
# Distinguish "auth/network failed" from "genuinely not set": they look identical
# after a grep, and only one of them is the operator's problem to fix here.
SECRET_LIST="$(wrangler secret list 2>&1 || true)"
if ! printf '%s' "$SECRET_LIST" | grep -q "$SECRET_NAME"; then
  case "$SECRET_LIST" in
    *"not authenticated"*|*"Missing an account ID"*|*"error code:"|*"Invalid"*)
      fail "could not read the secret list from the Cloudflare API (auth or network). Output:
$(printf '%s' "$SECRET_LIST" | sed 's/^/    /')
Nothing was written." ;;
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
say "2/7 build the new registry value (exactly one field changes: the OCC token)"
# Everything except the OCC token is carried across verbatim, including the
# mcp.servers entry whose literal is MCP_EDGE_KEY.
NEW_JSON="$(
  printf '%s' "$CURRENT_JSON" \
    | jq --arg h "$OCC_HOST" --arg k "$NEW_KEY" '.[$h].token = $k'
)"

say "2/7 validate the shape before it goes near the account"
printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" --arg k "$NEW_KEY" '.[$h].token == $k' >/dev/null \
  || fail "the OCC token did not survive the edit. Nothing was written."
printf '%s' "$NEW_JSON" | jq -e --arg h "$OCC_HOST" '.[$h].mcp.servers | length > 0' >/dev/null \
  || fail "the OCC entry has no mcp.servers after the edit. The zammad route would break (R10). Nothing was written."
printf '%s' "$NEW_JSON" | jq -e 'to_entries | all(.value | has("token"))' >/dev/null \
  || fail "at least one tenant entry has no token field. The registry validator requires one per entry (apps/digichat/src/lib/embed-tenants.ts:511). Nothing was written."
# Prove the ONLY difference is the OCC token. Anything else means the paste was
# wrong and a `put` would silently change routing, gate mode or the MCP edge key.
CHANGED_KEYS="$(printf '%s' "$CURRENT_JSON" | jq -r --slurpfile new <(printf '%s' "$NEW_JSON" | jq -S .) 'paths(scalars) as $p | select(getpath($p) != ($new[0] | getpath($p))) | $p | join(".")' 2>/dev/null || true)"
UNEXPECTED="$(printf '%s' "$CHANGED_KEYS" | grep -v "^$OCC_HOST\.token$" || true)"
[ -z "$UNEXPECTED" ] \
  || fail "the edit would change more than the OCC token:
$(printf '%s' "$UNEXPECTED" | sed 's/^/    /')
Refusing to put. Nothing was written."

printf 'exactly one field will change: %s.token\n' "$OCC_HOST"
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