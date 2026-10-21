# OCC invite key — mint, rotate, revoke, verify

Runbook for the OCC tenant's bearer key in the digichat Worker secret
`DIGICHAT_EMBED_TENANTS` (DIG-1381, Act B1 of board approval `e4c1d067`).
Companion to [SECRETS_ROTATION.md](SECRETS_ROTATION.md); this file is the OCC-specific
part of §1, and it also holds the **Act B2 rollback**.

**No value ever appears in this file, in a ticket, in a comment, or in a log.** Every literal
below is a placeholder or a command that reads the key from your shell.

**No PII masking: the invite link is the only gate (Chris, 9 Oct, reaffirmed 16 Oct).**
Ticket and Zammad text is stored and shown as written. Do not add a masker.

## Status — 2026-10-21

- **Act B2 has landed.** `occ.digithings.ai` is no longer in `FIRST_PARTY_EMBED_HOSTS`
  (`apps/digichat/src/lib/embed-first-party.ts:4-8`). The invite key is now the **only** accepted
  proof for the OCC tenant. Every section below that describes the pre-B2 state is history, not
  current behaviour.
- **Custody is restored** (DIG-4810): the sanctioned Keychain copy `digithings.occ-invite-key`
  (account `DIG-1474`) exists again, and the value in it was proved against production with
  `EXPECT_B2=1 bash scripts/verify_occ_invite_key.sh` → 7/7 PASS. **No rotation was performed**:
  the value that is live is the value that was installed on 2026-10-11. See [Custody](#custody).
- **The live value is 48 hex characters, not 64.** The `openssl rand -hex 32` recipe in this file
  produces 64. Measure the fingerprint; do not assume the recipe.
- **Run the verification with `EXPECT_B2=1`.** The script's default expectations are the pre-B2
  ones, so checks 3 and 4 report `FAIL` against a correctly gated deployment.

## What the key is

A **bearer capability, not authentication** — the same model as a Stripe publishable key in an
iframe `src`. It says "this embed was provisioned by us", not "this caller is staff". It is not
issued per user, has no expiry of its own, and cannot be attributed to a person.

- **Lives in three copies, and two of them are gates:**
  1. the `token` field of the `occ.digithings.ai` entry inside the digichat Worker secret
     `DIGICHAT_EMBED_TENANTS` (`apps/digichat-cloudflare/src/index.ts:144`) — the registry copy the
     Container reads;
  2. the digichat Worker secret `OCC_INVITE_KEY` (`apps/digichat-cloudflare/src/index.ts:125`,
     documented in `apps/digichat-cloudflare/wrangler.toml:125` as "Worker-only /chat/occ gate;
     never forwarded to the container"), which the route gate compares at
     `apps/digichat-cloudflare/src/index.ts:174`;
  3. the Cloudflare Pages secret `OCC_INVITE_KEY` on project `digithings-ai`, which the `/chat/occ`
     shell gate compares (`apps/digithings-web/functions/chat/occ/[[path]].ts:25`).

  The registry field is **required** by the registry validator
  (`apps/digichat/src/lib/embed-tenants.ts:570`), so it cannot simply be omitted. **All three
  copies must hold the same value**: a one-sided change opens the shell and refuses the tenant, or
  the tenant admits the caller and the shell answers 404.
- **Entered by the browser as** `?token=<key>` on `https://digithings.ai/chat/occ`, read once
  in a mount effect (`apps/digithings-web/lib/inviteToken.ts`, only because
  `app/chat/occ/page.tsx` sets `acceptsInviteToken`), and forwarded to digichat as the
  `X-Embed-Token` request header.
- **Compared with** `tokenMatches` in `apps/digichat/src/lib/embed-chat-tenant.ts:87`.
- **Not authentication** means: it must be treated as revocable-but-shareable. Anyone holding it
  reaches the OCC tenant. There is no second factor, no per-user identity and no audit trail of
  who presented it.

## Custody

The key needs **one sanctioned copy that a person can read** and **one record that says where it
is**. The record is the inventory row `OCC_INVITE_KEY` in `docs/ops/SECRETS_INVENTORY.md` (with
risk `R19`) and the paragraph in `docs/repo-split/secrets-access-inventory.md`.

| copy | where | who can read it |
|---|---|---|
| **sanctioned custody copy** | macOS Keychain, service `digithings.occ-invite-key`, account `DIG-1474` | Security, on Chris's Mac |
| local host secret store | `~/.config/digithings/secrets/consolidated.env` and `~/.config/digithings/secrets/digichat-embed-tenants.deploy.json` (mode 600) | the seat that composes the registry, on Chris's Mac |
| production copies | Worker secret `OCC_INVITE_KEY`, Pages secret `OCC_INVITE_KEY`, the OCC `token` in `DIGICHAT_EMBED_TENANTS` | write-only; nobody can read them back |

**The end state is Bitwarden Secrets Manager** — one project, one item named `OCC_INVITE_KEY`.
That is blocked on a project grant for the `keymaster` machine account (DIG-95): the plan cap of
3 projects is exhausted, and granting is an owner action in Bitwarden. Until that grant exists,
the Keychain is the sanctioned copy.

**Custody is not revocation.** The production copies cannot be read back from any surface, so a
local copy can be destroyed (DIG-3524, 2026-10-18) while the credential stays live. When the
custody copy is gone, the only way to get the value back is to rotate.

Restore a custody copy without printing the value:

```bash
# the value stays inside the shell; it never reaches the terminal
OCC_INVITE_KEY="$(python3 - <<'PY'
import pathlib
p = pathlib.Path.home() / ".config/digithings/secrets/consolidated.env"
for line in p.read_text().splitlines():
    if line.startswith("OCC_INVITE_KEY="):
        print(line.split("=", 1)[1].strip())
PY
)"
security add-generic-password -U -s digithings.occ-invite-key -a DIG-1474 \
  -w "$OCC_INVITE_KEY" -l "digithings occ-invite-key"
unset OCC_INVITE_KEY
```

Then prove that the copy is the live value and not a guess: run the verification with the key in
the environment. Check 2 (right key, no origin) is the discriminating probe; a wrong value reads
`embed` there.

## Why the key changes nothing on its own — read this before scheduling the deploy

> **Pre-B2 history. Act B2 has landed** (see [Status](#status--2026-10-21)): `occ.digithings.ai`
> is no longer in `FIRST_PARTY_EMBED_HOSTS`
> (`apps/digichat/src/lib/embed-first-party.ts:4-8`). The key is now the only way in. The
> measurements below were taken on 2026-10-06 and no longer hold: today an OCC request with no
> key and a first-party `Origin` is **refused** (`slug=embed`). Keep this section for the
> rollback it describes, not for the current state.

The authorisation rule is (`apps/digichat/src/lib/embed-chat-tenant.ts:101-108`):

```ts
function hostTenantAuthorized(tenant, token, host, originHost): boolean {
  if (tokenMatches(tenant.token, token)) return true;
  return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
}
```

Before Act B2, `occ.digithings.ai` was **in `FIRST_PARTY_EMBED_HOSTS`**
(`apps/digichat/src/lib/embed-first-party.ts:4-8`; the entry carried the `TODO(DIG-1210)` comment
that said deleting it is "deliberately a separate deploy from the key rollout"). While that entry
existed, the second line authorized OCC **with the right key, the wrong key, or no key**.

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
   `TODO(DIG-1210)` comment are the same instruction. Act B2 has since landed — see
   [Status](#status--2026-10-21).
3. **The token is a bearer capability in the URL.** See [Known limits](#known-limits).

## Rollout — Act B1 (Chris-only: this touches a production Worker secret and deploys)

> **The one-command entry is disarmed (2026-10-21).** `scripts/occ_invite_key_rollout.sh` runs
> `scripts/occ_invite_key_write.sh` and then stops with
> `DISARMED: R5 deploy is not run from this entry. Nothing was deployed.` and exit code 2. The
> write script does not run `wrangler secret put` and does not write KV (the KV read path is
> DIG-3699). **There is no working one-command rollout today** — run the steps below by hand, and
> read `scripts/occ_invite_key_rollout.sh` before you do.

The container boot-env trap applies: `DIGICHAT_EMBED_TENANTS` reaches the digichat Container
process env (`apps/digichat-cloudflare/src/index.ts:69`, merged from the KV registry at
`:94-114`), but a warm instance keeps its boot env until it is recycled, and `sleepAfter` alone
does not evict a Container under steady traffic. `secret put` **plus** `deploy` is **not** enough
on its own.

**The container id now follows the deploying commit** (`apps/digichat-cloudflare/src/paths.ts:110`):
it is `shared-<deploying short sha>`, injected at deploy time by `scripts/deploy.mjs` as
`--var DIGICHAT_CONTAINER_REV:<sha12>`, and it must **not** be hand-bumped
(`apps/digichat-cloudflare/src/paths.ts:37-40`). A deploy that carries no rev falls back to the
legacy literal `shared-v10` (`apps/digichat-cloudflare/src/paths.ts:40`), and then the recycle
does not happen. Read the live id from the Worker's own meta route
(`curl -s https://digithings.ai/_digichat/meta | jq -r .containerId`). See
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
   from the secrets manager and change exactly two fields on the `occ.digithings.ai` entry:

   | field | to | why |
   |---|---|---|
   | `token` | the new invite key | the rotation itself |
   | `backend.digisearchIndex` | `occ_help` | the retrieval-corpus narrowing (below) |

   Do not touch the `mcp.servers` entry for the `zammad` route — its literal `token` is
   the stack Worker's `MCP_EDGE_KEY` and it is a **different** credential; a one-sided change
   there breaks the OCC tool calls (R10).

   ```bash
   # $JSON is the full registry with the OCC token replaced AND the corpus narrowed.
   # Verify the shape before it goes anywhere near the account:
   printf '%s' "$JSON" | jq -e '.["occ.digithings.ai"].token == env.OCC_INVITE_KEY' >/dev/null
   printf '%s' "$JSON" | jq -e '.["occ.digithings.ai"].mcp.servers | length > 0' >/dev/null
   printf '%s' "$JSON" | jq -e '.["occ.digithings.ai"].backend.digisearchIndex == "occ_help"' >/dev/null
   # And the negative, because a plausible-looking index is the failure that matters:
   ! printf '%s' "$JSON" | jq -e \
       '.["occ.digithings.ai"].backend.digisearchIndex | test("(^|,)occ_tickets(,|$)")'
   ```

### Why the corpus moves in the same put (DIG-2779)

The live OCC tenant reads `digisearchIndex: "occ_help,occ_tickets"`. `occ_tickets` is the corpus
built by `scripts/index_occ_tickets.py` from customer ticket text
([ADR 0031](../adr/0031-occ-tickets-corpus-retrieval.md)). Counsel's condition for this
rollout is that the embed reaches the **help corpus only**, so a token rotation that leaves
`occ_tickets` reachable rotates the credential and leaves the retrieval grant exactly as wide as
it was. The two fields therefore ship together, and `scripts/occ_invite_key_rollout.sh` step 2
refuses a put that is not exactly those two fields, or that moves only one of them.

The index is a **fixed literal in the script, not an operator-supplied value**. Do not parameterise
it from the environment: an operator who could widen the corpus through the guard is the exact
failure this gate exists to stop.

**The live corpus cannot be read back over HTTP, by design.** The tenant registry is a write-only
Worker secret, and `toEmbedClientConfig` copies declared fields only — it has no
`backend.digisearchIndex` branch
([embed-client-config.ts](../../apps/digichat/src/lib/embed-client-config.ts)). So the rollout
script is the only place the narrowing can be proved, and it proves it before the put. What
`scripts/verify_occ_invite_key.sh` check 7 asserts is the observable consequence: that the corpus
is **not** discoverable from the client projection, i.e. the browser is not given a corpus oracle.

3. **Put the value in every copy that holds it** — the registry's legacy copy and the two gate
   secrets. From `apps/digichat-cloudflare`:

   ```bash
   # a) the legacy registry copy (the OCC `token` literal)
   printf '%s' "$JSON" \
     | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_EMBED_TENANTS
   # b) the Worker gate secret
   printf '%s' "$OCC_INVITE_KEY" \
     | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put OCC_INVITE_KEY
   ```

   ```bash
   # c) the Pages gate secret (project digithings-ai)
   cd apps/digithings-web
   printf '%s' "$OCC_INVITE_KEY" | npx wrangler pages secret put OCC_INVITE_KEY --project-name digithings-ai
   ```

   The **KV copy carries no value to change**: the OCC entry in `embed-tenants` holds the
   credential *reference* `tokenEnv: "OCC_INVITE_KEY"`, which the Worker resolves from the Worker
   secret (`apps/digichat-cloudflare/src/tenants-kv.ts`). A KV host whose references resolve wins
   over the legacy copy, so the KV document is what decides the OCC tenant. Keep the legacy literal
   identical to the Worker secret anyway: it is the fallback, and a stale literal is one way to
   resurrect an old key.

   When the change is a registry change, use the sanctioned tool instead of hand-writing the JSON:
   `python3 scripts/digichat_tenant_registry.py apply --live-from <host-store-file> --overlay
   <overlay-file>` writes both copies and recycles the container as one change. It prints a plan
   and asks for a typed confirmation before it writes. `scripts/occ_invite_key_rollout.sh` is
   disarmed — see the banner above.

4. **Recycle the container.** `sleepAfter` alone does not evict a Container under steady traffic,
   so the value only reaches the process when the instance changes. The id is derived from the
   deploying commit (`apps/digichat-cloudflare/src/paths.ts:110`) and injected at deploy time by
   `apps/digichat-cloudflare/scripts/deploy.mjs` as `--var DIGICHAT_CONTAINER_REV:<sha12>`; do
   **not** hand-bump a literal id (the legacy fallback is `shared-v10`,
   `apps/digichat-cloudflare/src/paths.ts:40`). A deploy that carries the rev **is** the recycle,
   and that wrapper fails closed when the commit cannot be resolved. The registry tool does the
   same thing through the container reset endpoint
   (`https://digithings.ai/_digichat-admin/container/reset`) as part of the write.

   ```bash
   # from apps/digichat-cloudflare
   npm run deploy
   ```

5. **Verify**, after the recycle has taken effect (the old instance answers with the old value
   until it is gone; `scripts/verify_occ_invite_key.sh` names a missing recycle as one of the two
   causes of a check-2 failure):

   ```bash
   EXPECT_B2=1 bash scripts/verify_occ_invite_key.sh
   ```

Rollback of Act B1 itself: re-put the **previous** tenant JSON and deploy — the container id
follows the deploying commit, so the deploy is the recycle; there is no id to bump by hand and
no fixed drain to wait for. Nothing about the running service depends on the key before Act B2,
so this is a no-op in practice; the interesting rollback is the one below.

## Verification

`scripts/verify_occ_invite_key.sh` reads the key from `OCC_INVITE_KEY` in the environment and
prints one line per check — `PASS`/`FAIL` plus the resolved tenant slug. It never echoes the key,
never writes it to a file, and passes the header to `curl` through `--config -` on **stdin** so
the key never appears in `ps` output or shell history.

It probes `GET https://digithings.ai/api/embed/tenant-config`, which is the cheapest PII-free,
model-free proof available: that route always answers **HTTP 200** and encodes the decision in the
body's `slug` — `occ` when the tenant was authorized, `embed` when it was not
(`apps/digichat/src/app/api/embed/tenant-config/route.ts:15`, `DEFAULT_EMBED_TENANT_CONFIG` at
`apps/digichat/src/lib/embed-client-config.ts:114`). Reading `slug` rather than the status code is
the whole trick; a script that only checks for 503-style codes will report a false PASS.

**Run it with `EXPECT_B2=1`.** Act B2 has landed (see [Status](#status--2026-10-21)), so the
script's default expectations — the pre-B2 ones — make checks 3 and 4 report `FAIL` against a
correctly gated deployment.

`slug=embed` does not say *why* the request was refused: the OCC tenant may be missing from the
merged registry, or the presented token may not have matched. Only check 2 separates the two, and
only with the right key.

The script's checks:

| # | check | expected now (Act B2 landed) | expected before Act B2 (history) |
|---|---|---|---|
| 1 | `X-Embed-Host` alone, no origin | `embed` (refused) | `embed` (refused) |
| 2 | right key, no origin | **`occ`** — proves the key reached the live registry | `occ` |
| 3 | wrong key, first-party origin | **`embed`** — refused | `occ` — OCC was still on the allowlist |
| 4 | no key, first-party origin | **`embed`** — refused | `occ` — same reason |
| 5 | right key, first-party origin | `occ` | `occ` |
| 6 | tenant-config body echoes no token material | pass | pass |
| 7 | tenant-config body names no retrieval corpus | pass | pass |

Check 7 is not a check on the key. It asserts that the response carries neither a
`digisearchIndex` field nor the name `occ_tickets`, i.e. that the retrieval corpus is not
discoverable from the client projection. It is the observable half of the narrowing; the
pre-put half lives in `scripts/occ_invite_key_rollout.sh` step 2, because the registry is a
write-only secret and no HTTP surface can report the live corpus.

Check 2 is the only one that can tell a **correct** key from a **wrong** one, because it is the
only one that withholds the first-party origin — and without that origin the allowlist cannot
authorize anything. Checks 3 and 4 read `embed` today, and that is the evidence that the allowlist
entry is gone: before Act B2 they were expected to read `occ` (no denial). The executable version
of this table is `apps/digichat/src/lib/embed-occ-invite-key.test.ts`.

One check the script cannot do: that a **staff user** gets a working chat session at
`https://digithings.ai/chat/occ?token=<key>` — a real message round-trip. That is a browser step
and it is the only proof that the whole chain (Pages route → `readInviteToken` → `X-Embed-Token`
→ digichat → Container → model) works end to end. Do it by hand, once, and record the outcome in
[Rotation log](SECRETS_ROTATION.md#rotation-log).

**A person does this step, not an agent.** The key rides in the URL, so an agent driving the
browser would write it into a tool call and into the run transcript, and the OCC turn exercises the
ticket tool, whose answer carries client ticket text. The key is in the Keychain; the person
loads it in their own browser and never pastes it into a chat.

## Revocation — this is the Act B2 rollback

**There is no deny-list and no per-recipient revoke.** The key is a single shared value held in
three copies (see [Custody](#custody)), so *revoking is rotating*: mint a new value, put it in
every copy, recycle the container. The procedure is Act B1 steps 1-5 above, with the two gate
secrets included:

```bash
read -rs OCC_INVITE_KEY && printf '\n'   # the NEW value
# …build $JSON with the new OCC token, jq-check it, then:
printf '%s' "$JSON" \
  | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_EMBED_TENANTS
printf '%s' "$OCC_INVITE_KEY" \
  | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put OCC_INVITE_KEY
# and the Pages gate secret
(cd apps/digithings-web && printf '%s' "$OCC_INVITE_KEY" \
  | npx wrangler pages secret put OCC_INVITE_KEY --project-name digithings-ai)
# the recycle is the deploy: the container id follows the deploying commit (paths.ts:110)
(cd apps/digichat-cloudflare && npm run deploy)
EXPECT_B2=1 bash scripts/verify_occ_invite_key.sh
```

Time to revoke, and what it does to OCC:

- **The old key stops working when the warm instance is gone, not at the `put`.** Until the
  instance is recycled the previous value is still live — this is R5, and it is why the recycle
  step is not optional. The recycle is the deploy (the id follows the deploying commit).
- **Act B2 has landed, so revocation locks OCC out completely.** The key is the only accepted
  proof, so rotating it invalidates every outstanding invite link at once. Hand the new link out
  with a fresh rotate-on-hand-off decision; there is no overlap window and no dual-accept.
- **Before Act B2 landed, revocation changed nothing for a first-party browser origin** — that
  caller was authorized by the allowlist, not by the key. Do not report a revocation as an
  access-control action while the allowlist entry is still in place.

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
  whether the new value went live. The container id is now `shared-<deploying short sha>`; read it
  from `curl -s https://digithings.ai/_digichat/meta | jq -r .containerId`.
- Owner: Platform (Cloudflare operator) for the value, Security for custody.
- Inventory: `docs/ops/SECRETS_INVENTORY.md` — row `OCC_INVITE_KEY`, and risk `R19` (the custody
  gap of 2026-10-18 → 2026-10-21). `R10` covers `DIGICHAT_EMBED_TENANTS`.
## Cloudflare-side rotation (decision 2026-10-10)

The invite key is rotated on Cloudflare only. Do **not** store the current
`DIGICHAT_EMBED_TENANTS` value (it contains the live `MCP_EDGE_KEY`) or the new
invite key as GitHub secrets. `.github/workflows/occ-invite-key-rollout.yml`
runs the offline guards only and has no production write path.

Run it as a staged-deploy step, after the release merge to main is approved, from a
terminal logged in with `wrangler login`. Values come from the local
secrets manager and are never echoed. **The entry script is disarmed** (see the banner
above), so the example below shows the inputs it expects, not a working command:

```sh
OCC_ROLLOUT_AUTH=login \
OCC_EMBED_TENANTS_CURRENT="$(< ~/.config/digithings/secrets/digichat-embed-tenants.deploy.json)" \
OCC_INVITE_KEY="$(security find-generic-password -s digithings.occ-invite-key -w)" \
  bash scripts/occ_invite_key_rollout.sh    # type ROLLOUT when prompted
```

The custody copy is read from the Keychain service `digithings.occ-invite-key`
(account `DIG-1474`) — the one sanctioned name. The registry copy comes from the local
host secret store, which is where `scripts/digichat_tenant_registry.py` composes it
from.

Mint the key once with `openssl rand -hex 32` straight into the keychain
(`security add-generic-password -U -s digithings.occ-invite-key -a DIG-1474 -w "$(openssl rand -hex 32)"`).
The rotation **changes production behaviour** (it puts the key in the live OCC tenant
and redeploys the digichat Worker), so it is never a background secret update.

A rotation is Act B1, but **Act B2 has since landed** (see [Status](#status--2026-10-21)):
the gate is already on, and `occ.digithings.ai` is not in `FIRST_PARTY_EMBED_HOSTS` any more
(`apps/digichat/src/lib/embed-first-party.ts:4-8`). A rotation today therefore **revokes
every outstanding invite link at once** — see [Revocation](#revocation--this-is-the-act-b2-rollback) —
and it must replace the value in **all three copies** (Worker secret, Pages secret, registry
`token`) or the chain breaks in one direction or the other.
