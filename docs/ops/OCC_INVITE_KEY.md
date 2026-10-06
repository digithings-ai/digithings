# OCC invite key — mint, rotate, revoke, verify

Runbook for the OCC tenant's bearer key in the digichat Worker secret
`DIGICHAT_EMBED_TENANTS` (DIG-1381, Act B1 of board approval `e4c1d067`).
Companion to [SECRETS_ROTATION.md](SECRETS_ROTATION.md); this file is the OCC-specific
part of §1, and it also holds the **Act B2 rollback**.

**No value ever appears in this file, in a ticket, in a comment, or in a log.** Every literal
below is a placeholder or a command that reads the key from your shell.

## What the key is

A **bearer capability, not authentication** — the same model as a Stripe publishable key in an
iframe `src`. It says "this embed was provisioned by us", not "this caller is staff". It is not
issued per user, has no expiry of its own, and cannot be attributed to a person.

- **Lives in exactly one place:** the `token` field of the `occ.digithings.ai` entry inside the
  digichat Worker secret `DIGICHAT_EMBED_TENANTS`
  (`apps/digichat-cloudflare/src/index.ts:48`). The field is **required** by the registry
  validator (`apps/digichat/src/lib/embed-tenants.ts:511`), so it cannot simply be omitted.
- **Entered by the browser as** `?token=<key>` on `https://digithings.ai/chat/occ`, read once
  in a mount effect (`apps/digithings-web/lib/inviteToken.ts`, only because
  `app/chat/occ/page.tsx` sets `acceptsInviteToken`), and forwarded to digichat as the
  `X-Embed-Token` request header.
- **Compared with** `tokenMatches` in `apps/digichat/src/lib/embed-chat-tenant.ts:84`.
- **Not authentication** means: it must be treated as revocable-but-shareable. Anyone holding it
  reaches the OCC tenant. There is no second factor, no per-user identity and no audit trail of
  who presented it.

## Why the key changes nothing on its own — read this before scheduling the deploy

The authorisation rule is (`apps/digichat/src/lib/embed-chat-tenant.ts:101-107`):

```ts
function hostTenantAuthorized(tenant, token, host, originHost): boolean {
  if (tokenMatches(tenant.token, token)) return true;
  return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
}
```

`occ.digithings.ai` is **still in `FIRST_PARTY_EMBED_HOSTS`**
(`apps/digichat/src/lib/embed-first-party.ts:4-19`, carrying the `TODO(DIG-1210)` comment that
says deleting the entry is "deliberately a separate deploy from the key rollout"). So while that
entry exists, the second line authorizes OCC **with the right key, the wrong key, or no key**.

Measured in production on 2026-10-06, against `GET /api/embed/tenant-config` (see
[Verification](#verification)):

| request | body `slug` | meaning |
|---|---|---|
| `X-Embed-Host: occ.digithings.ai`, no token, `Origin: https://digithings.ai` | `occ` | **admitted with no credential at all** |
| same + wrong token | `occ` | admitted; the token is ignored on this path |
| `X-Embed-Host: occ.digithings.ai`, wrong token, no `Origin`/`Referer` | `embed` | refused |
| `X-Embed-Host: occ.digithings.ai`, no token, no `Origin`/`Referer` | `embed` | refused |

Consequences:

1. **Rolling out the key (Act B1) is additive only.** It cannot break OCC and it does not close
   OCC. It exists so that Act B2 can close OCC without a gap.
2. **Act B2 (delete the `occ.digithings.ai` allowlist entry) is what closes it.** After B2 the
   `tokenMatches` line is the only way in, and then "no key" and "wrong key" are both refused.
   Do not deploy B1 and B2 together and do not ship B2 first — the CTO's ordering note and the
   `TODO(DIG-1210)` comment are the same instruction.
3. **The token is a bearer capability in the URL.** See [Known limits](#known-limits).

## Rollout — Act B1 (Chris-only: this touches a production Worker secret and deploys)

> **One command, if you prefer:** `bash scripts/occ_invite_key_rollout.sh` runs steps 2-5
> below in order and prints the verification at the end. It prompts for the current registry
> value and the new key with terminal echo off, refuses to put anything unless the edit changes
> *exactly one field* (`occ.digithings.ai.token`), computes the next container id from the file
> instead of hard-coding one, makes the bump and the deploy inseparable, and prints the
> fingerprint plus the rotation-log line. It does **not** mint the key and does **not** push the
> container-id commit. Read it before running it: `scripts/occ_invite_key_rollout.sh`.
> The steps below remain the reference for what it does and for the rollback.

The container boot-env trap applies: `DIGICHAT_EMBED_TENANTS` reaches the digichat Container
process env (`apps/digichat-cloudflare/src/index.ts:32-56`), but a warm instance keeps its boot
env until it is recycled. `secret put` **plus** `deploy` is **not** enough on its own — the
`SHARED_DIGICHAT_CONTAINER_ID` bump is what forces the recycle. See
[SECRETS_ROTATION.md § The container boot-env trap](SECRETS_ROTATION.md#the-container-boot-env-trap).

Steps 2-4 write to production. Steps 1 and 5 are safe to rehearse.

1. **Load the key into your shell without echoing or persisting it:**

   ```bash
   # bash: read -rs OCC_INVITE_KEY    zsh: read -s OCC_INVITE_KEY
   read -rs OCC_INVITE_KEY && printf '\n'
   ```

   Mint it with `openssl rand -hex 32`, hand it to the security owner through the secrets path,
   and store it there. Never in a ticket, a comment, a document, a commit or a shell that writes
   history.
2. **Build the new tenant JSON.** Take the **current** production `DIGICHAT_EMBED_TENANTS` value
   from the secrets manager and change exactly one field: the `occ.digithings.ai` entry's
   `token`. Do not touch the `mcp.servers` entry for the `zammad` route — its literal `token` is
   the stack Worker's `MCP_EDGE_KEY` and it is a **different** credential; a one-sided change
   there breaks the OCC tool calls (R10).

   ```bash
   # $JSON is the full registry with only the OCC token replaced. Verify the shape
   # before it goes anywhere near the account:
   printf '%s' "$JSON" | jq -e '.["occ.digithings.ai"].token == env.OCC_INVITE_KEY' >/dev/null
   printf '%s' "$JSON" | jq -e '.["occ.digithings.ai"].mcp.servers | length > 0' >/dev/null
   ```

3. **Put the secret** (from `apps/digichat-cloudflare`):

   ```bash
   printf '%s' "$JSON" \
     | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_EMBED_TENANTS
   ```

4. **Bump the container id and deploy.** `SHARED_DIGICHAT_CONTAINER_ID`
   (`apps/digichat-cloudflare/src/paths.ts:23`) `shared-v9` → `shared-v10`. Commit that bump —
   it is the only record of why the instance was recycled. Then, from
   `apps/digichat-cloudflare`:

   ```bash
   npx --yes wrangler@4.133.0 deploy
   ```

5. **Verify**, after waiting out the drain window (`sleepAfter = "3m"`,
   `apps/digichat-cloudflare/src/index.ts:26`):

   ```bash
   sleep 180
   bash scripts/verify_occ_invite_key.sh
   ```

Rollback of Act B1 itself: re-put the **previous** tenant JSON, bump to `shared-v11`, deploy,
wait 180 s. Nothing about the running service depends on the key before Act B2, so this is a
no-op in practice; the interesting rollback is the one below.

## Verification

`scripts/verify_occ_invite_key.sh` reads the key from `OCC_INVITE_KEY` in the environment and
prints one line per check — `PASS`/`FAIL` plus the resolved tenant slug. It never echoes the key,
never writes it to a file, and passes the header to `curl` through `--config -` on **stdin** so
the key never appears in `ps` output or shell history.

It probes `GET https://digithings.ai/api/embed/tenant-config`, which is the cheapest PII-free,
model-free proof available: that route always answers **HTTP 200** and encodes the decision in the
body's `slug` — `occ` when the tenant was authorized, `embed` when it was not
(`apps/digichat/src/app/api/embed/tenant-config/route.ts:13-19`, `DEFAULT_EMBED_TENANT_CONFIG`
at `apps/digichat/src/lib/embed-client-config.ts:100-121`). Reading `slug` rather than the status
code is the whole trick; a script that only checks for 503-style codes will report a false PASS.

The script's checks:

| # | check | expected now | expected after Act B2 |
|---|---|---|---|
| 1 | `X-Embed-Host` alone, no origin | `embed` (refused) | `embed` (refused) |
| 2 | right key, no origin | **`occ`** — proves the key reached the live registry | `occ` |
| 3 | wrong key, first-party origin | **`occ`** — expected: OCC is still on the allowlist | **`embed`** |
| 4 | no key, first-party origin | **`occ`** — expected, same reason | **`embed`** |
| 5 | right key, first-party origin | `occ` | `occ` |
| 6 | tenant-config body echoes no token material | pass | pass |

Check 2 is the only one that can tell a **correct** key from a **wrong** one before Act B2, because
it is the only one that withholds the first-party origin — and without that origin the allowlist
cannot authorize anything. Checks 3 and 4 are expected to read `occ` (i.e. no denial) immediately
after Act B1; a runbook that claims they must fail today is wrong. Checks 3 and 4 are the ones that
flip to `embed` at Act B2. The executable version of this table is
`apps/digichat/src/lib/embed-occ-invite-key.test.ts`.

One check the script cannot do: that a **staff user** gets a working chat session at
`https://digithings.ai/chat/occ?token=<key>` — a real message round-trip. That is a browser step
and it is the only proof that the whole chain (Pages route → `readInviteToken` → `X-Embed-Token`
→ digichat → Container → model) works end to end. Do it by hand, once, and record the outcome in
[Rotation log](SECRETS_ROTATION.md#rotation-log).

## Revocation — this is the Act B2 rollback

**There is no deny-list and no per-recipient revoke.** The key is a single shared value in a
single Worker secret, so *revoking is rotating*: mint a new value, put it, recycle the container.
The command is identical to Act B1 steps 1-5 above, and it is the same procedure:

```bash
cd apps/digichat-cloudflare
read -rs OCC_INVITE_KEY && printf '\n'   # the NEW value
# …build $JSON with the new OCC token, jq-check it, then:
printf '%s' "$JSON" \
  | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_EMBED_TENANTS
# SHARED_DIGICHAT_CONTAINER_ID shared-v10 → shared-v11 (paths.ts:23), commit, then:
npx --yes wrangler@4.133.0 deploy
sleep 180
bash scripts/verify_occ_invite_key.sh
```

Time to revoke, and what it does to OCC:

- **The old key stops working after the 180 s drain, not at the `put`.** Until the warm instance
  is recycled the previous value is still live — this is R5 and it is why the id bump is not
  optional.
- **After Act B2 lands, revocation locks OCC out completely.** The key is then the only accepted
  proof, so rotating it invalidates every outstanding invite link at once. Hand the new link out
  with a fresh rotate-on-hand-off decision; there is no overlap window and no dual-accept.
- **Before Act B2 lands, revocation changes nothing for a first-party browser origin** — that
  caller is authorized by the allowlist, not by the key. Do not report a revocation as an
  access-control action until Act B2 is deployed.

If the key is believed **leaked** (ticket, commit, screenshot, proxy log), do not wait for a
window: run the rotation immediately and ask Security to treat the old value as burned. Then
tell the CTO, because until Act B2 the leaked key was not the thing standing between the caller
and live customer PII anyway.

## Known limits

- **The key travels in a URL query string** and `apps/digithings-web` never strips it — there is
  no `history.replaceState` anywhere in that app. It therefore stays in browser history and in the
  Cloudflare zone's request log for that page load. `Referrer-Policy: no-referrer` on
  `/chat/occ*` (`apps/digithings-web/public/_headers:27-29`, live since DIG-1210) stops it being
  carried onward to anything else, and `/chat/occ*` is served by Cloudflare Pages, which has no
  `[observability]` block, so it is not in Workers log metadata. Fixing the history leak is a
  separate change — it alters user-facing behaviour, which is outside Act B1's scope.
- **No analytics surface exists to leak into.** `apps/digithings-web` contains no beacon, tag or
  analytics client of any kind, and the only `console` output on the embed-tenant path prints
  **host names**, never tokens (`apps/digichat/src/lib/embed-tenants.ts:791`).
- **The OCC tenant reaches live Zammad**, whose formatting helper returns unmasked customer
  names, emails and `[internal]` notes. There is no `scripts/zammad_mcp/privacy.py` on `main` and
  none of `ZAMMAD_MCP_CUSTOMER_DISCLOSURE`, `ZAMMAD_DEMO_UNMASKED_PII`,
  `ZAMMAD_MCP_UNMASK_APPROVER` exist there. So this key is currently the only thing intended to
  stand in front of that data once Act B2 lands — which is why B2 must not land before B1.
- The registry `token` is compared, not hashed, and is a required field; a placeholder such as
  `unused-for-first-party` is a real key to anyone who reads the README. Do not ship a
  placeholder on a tenant that carries live customer data.

## Records

- Rotation log (append every mint, rotation and revocation):
  [SECRETS_ROTATION.md § Rotation log](SECRETS_ROTATION.md#rotation-log). An unlogged rotation is
  an unverified rotation.
- **Record a fingerprint, never the key.** The log line for this secret is the length plus the
  first 8 hex of the SHA-256 — non-reversible, and enough to prove which value was installed:

  ```bash
  printf '%s' "$OCC_INVITE_KEY" | wc -c          # 65 with the trailing newline
  printf '%s' "$OCC_INVITE_KEY" | shasum -a 256 | cut -c1-8
  ```

  This is the same technique already used for the twelve-x publishable key in that log; the
  rationale is in [SECRETS_ROTATION.md](SECRETS_ROTATION.md#rotating-a-next_public_-supabase-client-key-pages-build-time-inlining).
- Also log the **Worker version id** and the **container id** after the deploy
  (`npx --yes wrangler@4.133.0 versions list`), because the container id is what actually decided
  whether the new value went live.
- Owner: Platform (Cloudflare operator) for the value, Security for custody.
- Inventory: `docs/ops/SECRETS_INVENTORY.md` (R10 covers `DIGICHAT_EMBED_TENANTS`).