# Secrets rotation runbook — digithings

For the operator rotating a live credential. This is the *procedure* companion to
[`docs/ops/SECRETS_INVENTORY.md`](docs/ops/SECRETS_INVENTORY.md) (the evidence base: names, locations,
risk ids R1–R13). No value is ever printed here; every literal below is masked `***`.

**Preconditions for every procedure.**

- Work from the Worker directory: `cd cloudflare/<worker>` — `digichat-cloudflare`, `digithings-stack-cloudflare`, `digithings-cron` (each has its own `wrangler.toml`).
- Pin wrangler: `npx --yes wrangler@4.133.0` (`cloudflare/digichat-cloudflare/package.json:16`, `cloudflare/digithings-stack-cloudflare/package.json:19`).
- Use `env -u CLOUDFLARE_API_TOKEN` for wrangler so a shell token cannot shadow `wrangler login` — auth error 10000 otherwise (`cloudflare/digithings-stack-cloudflare/wrangler.toml:167-180`).
- Worker secrets are `secret_text` and **write-only** (`wrangler secret list` returns names + type, never values). "Verify" below always means **behaviour**, never readback.
- Bump the container id whenever a rotated value must reach a running Container — see the next section. `wrangler deploy` alone does **not**.
- Log every rotation in [`## Rotation log`](#rotation-log). An unlogged rotation is an unverified rotation.

## The container boot-env trap

**A running Container is not replaced when a new Worker version deploys.** It keeps the environment it
booted with until the instance is recycled. Evidence: `cloudflare/digithings-stack-cloudflare/README.md:18-23`
("a running digichat Container keeps start-time env values until recycled"); `sleepAfter` is `15m`
(`cloudflare/digichat-cloudflare/src/index.ts:26`), `15m` for the stack sibling (`cloudflare/digithings-stack-cloudflare/src/index.ts:54`),
`15m` for the MCP container (`:167`). So a re-`put` secret looks rotated in `secret list` while the old value stays live — R5.

**The lever that works today: bump the container id.** Change `SHARED_DIGICHAT_CONTAINER_ID`
(`cloudflare/digichat-cloudflare/src/paths.ts:22`) from `shared-v7` to `shared-v8` and deploy. Incident #4289 / PR #4290
did exactly this: `shared-v6`→`shared-v7` booted a new instance with the current image + env while the old one went
inactive. The stack equivalent is `SHARED_STACK_CONTAINER_ID` (`cloudflare/digithings-stack-cloudflare/src/ports.ts:37`,
`shared-v15`); its comment names the exact case — "to pick up the rotated `DIGIKEY_ADMIN_TOKEN`, since the container
reads worker env only when the instance starts" (`ports.ts:33`). The MCP container id is `MCP_CONTAINER_ID` (`ports.ts:29`).

**Conflicting instruction to ignore.** `cloudflare/digithings-stack-cloudflare/README.md:18-23` and the rebuild-marker
comments (`Dockerfile.digichat-cloudflare:65-69`, `Dockerfile.digithings-stack-cloudflare:77-95`) say to bump the
**Dockerfile rebuild marker** to propagate env. That changes the image tag, not the instance id; it does not by itself
replace a warm instance. Prefer the `SHARED_*_CONTAINER_ID` bump, and treat the marker as an image-rebuild trigger only.

**The `envVars` whitelist is the only path into the container.** A secret `put` on the Worker but absent from the
Container's `envVars` never reaches the process — silently. The digichat whitelist is `cloudflare/digichat-cloudflare/src/index.ts:32-56`;
the stack whitelist is `cloudflare/digithings-stack-cloudflare/src/index.ts:60-112`. Known silent drops: on digichat,
`DIGICHAT_DATABASE_URL` (`wrangler.toml:58`), `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY`; on the stack, the
`[vars]` `DIGI_CONFIG_PATH`, `DIGI_PROJECT_CONFIG`, `DIGI_WORKFLOW_PROFILE`, `DIGI_ALLOWED_TOOLS`
(`wrangler.toml:213-221`) never arrive (R4).

**Trap verification commands.**

```bash
# stack: the live instance id is served by the Worker itself (src/index.ts:319).
curl -sf https://graph.digithings.ai/_stack/meta \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["containerId"])'   # → shared-v15 (or the bumped value)
# digichat has no id probe. Prove the recycle behaviourally: rotate AUTH_SECRET, then a
# pre-rotation browser session must fail and a fresh login must succeed (see §13).
sleep 900   # digichat sleepAfter == 15m; the old instance drains within this window (paths.ts:22, index.ts:26)
```

## Per-target procedures

### 1. `MCP_EDGE_KEY` + `DIGICHAT_EMBED_TENANTS`

**Blast radius** — `/_stack/mcp/{zammad,digisearch,digivault}/*` returns fail-closed 401 (`cloudflare/digithings-stack-cloudflare/src/index.ts:344-345`); the embed MCP tool calls break. `DIGICHAT_EMBED_TENANTS` drives all tenant routing, gate mode and per-tenant tokens (R10).
**Copies** — stack Worker secret `MCP_EDGE_KEY` (declared `cloudflare/digithings-stack-cloudflare/wrangler.toml:35`, consumed `src/index.ts:282`); the value **as a literal `token`** inside digichat `DIGICHAT_EMBED_TENANTS` (`cloudflare/digichat-cloudflare/src/index.ts:48`; `cloudflare/digichat/config/examples/occ-embed.yaml:56-58`). Optional `MCP_EDGE_KEYS` JSON overrides per server (`src/index.ts:283-296`).
**Pre-flight** — read the tenant JSON shape at `cloudflare/digichat-cloudflare/README.md:81-142`; locate the single `mcp.servers` entry for the OCC Zammad route.
**Steps**
1. Generate: `openssl rand -hex 32`.
2. On the stack Worker: `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put MCP_EDGE_KEY`. The Worker reads it per request, so the edge rotates instantly.
3. Replace the literal `token` in `DIGICHAT_EMBED_TENANTS`, then `printf '%s' "$JSON" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_EMBED_TENANTS` in `cloudflare/digichat-cloudflare`.
4. Bump `SHARED_DIGICHAT_CONTAINER_ID` (`paths.ts:22`) so the container reboots with the new tenant JSON.
5. `npx --yes wrangler@4.133.0 deploy` for the digichat Worker.
**Verify** — new key not 401, old/absent key 401:
`curl -s -o /dev/null -w '%{http_code}\n' -H "x-digi-mcp-key: $NEW" https://graph.digithings.ai/_stack/mcp/zammad/mcp` → any status except `401`; drop the header → `401`.
**Rollback** — re-put the previous `MCP_EDGE_KEY` **and** the previous tenant JSON together.
**Gotchas** — a one-sided rotation 401s the embed (R10). `tokenEnv` cannot resolve the key: the stack Worker secret is never forwarded into the digichat container, so the literal is required (`cloudflare/digichat-cloudflare/README.md:115-117`).

### 2. `DIGIKEY_BFF_TOKEN`

**Blast radius** — digichat BFF→digikey session exchange; chat auth. A one-sided rotation breaks chat (R6). The token is a static bearer compared with `secrets.compare_digest` (`digikey/src/digikey/server.py:233-240`).
**Copies** — digichat Worker (`cloudflare/digichat-cloudflare/wrangler.toml:54`, forwarded `src/index.ts:51`); stack Worker (`cloudflare/digithings-stack-cloudflare/wrangler.toml:136`, forwarded `src/index.ts:66`); digikey process (`digikey/src/digikey/settings.py:20`); `docker-compose.yml:560`; `infra/digichat-release/.env.profile-a.example:44`.
**Pre-flight** — both Workers must be deployable in the same window; the values **must agree**.
**Steps**
1. Generate the new value once.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGIKEY_BFF_TOKEN` in `cloudflare/digithings-stack-cloudflare`.
3. Same command in `cloudflare/digichat-cloudflare`.
4. Bump `SHARED_STACK_CONTAINER_ID` (`ports.ts:37`) and `SHARED_DIGICHAT_CONTAINER_ID` (`paths.ts:22`).
5. Deploy both Workers.
**Verify** — `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://key.digithings.ai/v1/oauth/token -H "Authorization: Bearer $NEW" -H 'Content-Type: application/json' -d '{"grant_type":"bff_session","tenant_slug":"digithings","subject":"bff-rotation-probe"}'` → `200`; with the previous value → `401`.
**Rollback** — re-put the previous value on both Workers and bump both ids again.
**Gotchas** — no dual-accept window (`server.py:233` accepts exactly one value), so move both surfaces within seconds. Rotating this is also the only way to block outstanding BFF JWTs (`digikey/ARCHITECTURE.md:354`).

### 3. Cloudflare token family — `CLOUDFLARE_API_TOKEN` / `VECTORIZE_API_TOKEN` / `D1_API_TOKEN`

**Blast radius** — Vectorize + D1 access (digivault, digisearch, the remote-index cutover); deploy workflows (`deploy-*.yml`, `docs-onboard-digithings.yml`, `sync-cheaperinference-cf-secrets.yml`); local `scripts/d1_sync.py:442`, `scripts/vectorize_sync.py:365` (R7).
**Copies** — stack Worker: canonical `CLOUDFLARE_API_TOKEN` (`cloudflare/digithings-stack-cloudflare/wrangler.toml:159`) and legacy `VECTORIZE_API_TOKEN` / `D1_API_TOKEN` (`:190-193`), forwarded at `src/index.ts:89-93`; GitHub repo secret; local `.env`.
**Pre-flight** — the wrangler self-auth trap: `CLOUDFLARE_API_TOKEN` is also wrangler's own auth variable (`wrangler.toml:167-180`). Never `set -a; . .env` before wrangler; use `env -u CLOUDFLARE_API_TOKEN` and keep `CLOUDFLARE_ACCOUNT_ID` exported.
**Steps**
1. Create the new token in the Cloudflare dashboard with the same scopes (Workers Scripts, Vectorize, D1 as used).
2. `env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 whoami` — confirm you are authenticated as the login, not the token.
3. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put CLOUDFLARE_API_TOKEN` in `cloudflare/digithings-stack-cloudflare`. Leave the legacy names in place — they are the fallback.
4. `gh secret set CLOUDFLARE_API_TOKEN` (stdin / `--body-file -`).
5. Update the gitignored local `.env`.
6. Bump `SHARED_STACK_CONTAINER_ID`, then deploy the stack.
7. Only after Verify passes, delete `VECTORIZE_API_TOKEN` / `D1_API_TOKEN` (`wrangler secret delete` or dashboard).
**Verify** — three checks, because `env -u` makes wrangler use the login, not the secret:
`CLOUDFLARE_API_TOKEN="$NEW" npx --yes wrangler@4.133.0 vectorize info digithings_docs` → non-empty `vectorCount` (the new token itself carries Vectorize scope); `env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 whoami` → the login identity (wrangler is not shadowed); then a digisearch query on `search.digithings.ai` with a digikey JWT scoped `digisearch:query` returns hits from the remote index, i.e. the container resolved the credentials on boot (`docs/ops/vectorize-cutover.md:132-207`).
**Rollback** — re-put the previous token, bump the id, redeploy. The legacy names still cover the fallback path.
**Gotchas** — one logical token, three names; legacy presence is inferred, not diffed (inventory Gaps). `CLOUDFLARE_ACCOUNT_ID` / `D1_ACCOUNT_ID` / `VECTORIZE_ACCOUNT_ID` are ids, not credentials.

### 4. `GH_DISPATCH_TOKEN`

**Blast radius** — every cron→GitHub `workflow_dispatch` / `repository_dispatch`; all scheduled pipelines stop (`cloudflare/digithings-cron/src/dispatch.ts:92,101`).
**Copies** — cron Worker (`cloudflare/digithings-cron/wrangler.toml:18` comment); GitHub repo secret (source), pushed by `deploy-digithings-cron.yml:51`.
**Pre-flight** — fine-grained PAT with Actions write on `digithings-ai/digithings` + `digithings-ai/twelve-x` (`wrangler.toml:18-19` comment).
**Steps**
1. Mint the new PAT in GitHub (dashboard action), same repos + Actions write.
2. `gh secret set GH_DISPATCH_TOKEN`.
3. Either re-run `deploy-digithings-cron.yml` (workflow_dispatch), or put directly: `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put GH_DISPATCH_TOKEN` in `cloudflare/digithings-cron`.
4. Deploy. No Container here — no id bump.
**Verify** — trigger one job and confirm a run appears:
`curl -s -X POST https://digithings-cron.<subdomain>.workers.dev/kick -H "Authorization: Bearer $CRON_KICK_SECRET" -H 'Content-Type: application/json' -d '{"cron":"17 9 * * *"}'` → `{"ok":true,...}`; then `gh run list --limit 5`. `<subdomain>` is the `*.workers.dev` URL printed by the last deploy (`workers_dev = true`, `wrangler.toml:10`); `/kick` is 404 without `CRON_KICK_SECRET` (`src/index.ts:85-86`).
**Rollback** — re-put the previous PAT and redeploy.
**Gotchas** — `DRY_RUN = "0"` (`wrangler.toml:16`); with `DRY_RUN=1` the dispatch is logged but never sent (`dispatch.ts:61`).

### 5. `DIGIKEY_ADMIN_TOKEN`

**Blast radius** — `POST /v1/admin/keys`, `/v1/admin/keys/{id}/revoke`, `/v1/admin/bff-sessions/revoke` return 503 when unset and 401 on mismatch (`digikey/src/digikey/server.py:117-121`). Key-issue / revoke only; chat is unaffected.
**Copies** — stack Worker (`cloudflare/digithings-stack-cloudflare/wrangler.toml:138`, forwarded `src/index.ts:68`); `docker-compose.yml:37`; `compose.profile-a.yml:60`.
**Pre-flight** — if compromise is suspected, also revoke keys the old token could mint.
**Steps**
1. Generate.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGIKEY_ADMIN_TOKEN` in `cloudflare/digithings-stack-cloudflare`.
3. Bump `SHARED_STACK_CONTAINER_ID` (`ports.ts:37` — its comment names this exact token as the reason).
4. Deploy.
**Verify** — `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://key.digithings.ai/v1/admin/keys -H "Authorization: Bearer $NEW" -H 'Content-Type: application/json' -d '{}'` → anything except `503` / `401` (a 4xx validation error still proves the bearer was accepted); with the old token → `401`.
**Rollback** — re-put the previous token and bump the id.
**Gotchas** — optional; the container only reads it at boot, hence the id bump (`ports.ts:33`). Empty means a startup warning, not a failure (`server.py:58-60`).

### 6. `DIGIKEY_PRIVATE_KEY_PEM`

**Blast radius** — every minted JWT + the JWKS; org-wide 401 until each consumer refetches. RS256 signing key, static `kid=digikey-1`, no overlap (R1).
**Copies** — stack Worker (`cloudflare/digithings-stack-cloudflare/wrangler.toml:137`, forwarded `src/index.ts:67`); GitHub repo secret / password manager (prod origin not visible in-repo); `infra/digichat-release/.env.profile-a.example:50` (commented).
**Pre-flight — what does not work today.** There is no JWKS overlap: the JWKS returns exactly one key (`digikey/src/digikey/jwt_issue.py:96`), `kid` is a static string, and no `DIGIKEY_PREV_KEY_PEM` exists (`digikey/ARCHITECTURE.md:305-335,572-610`). Rotating invalidates all outstanding tokens once consumers' caches expire — up to `DIGIKEY_JWKS_CACHE_SEC` = 300 s (`jwt_verify.py:45`). **Least-bad procedure:** rotate in a maintenance window and accept a hard ≤300 s 401 window, then have clients re-authenticate. Flag: keep `DIGIKEY_ALLOW_EPHEMERAL_KEY="0"` in prod — `"1"` generates a non-persistent key that rotates JWKS on every restart and breaks cross-instance verification (R2; `crypto_keys.py:65`; `cloudflare/digithings-stack-cloudflare/wrangler.toml:203`).
**Steps**
1. Generate a new RSA-2048 PKCS8 PEM (unencrypted) offline and store it in the secrets manager.
2. `printf '%s' "$PEM" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGIKEY_PRIVATE_KEY_PEM` in `cloudflare/digithings-stack-cloudflare`.
3. Bump `SHARED_STACK_CONTAINER_ID`.
4. Deploy, and announce the 401 window.
**Verify** — fingerprint the served public key (never the private one):
`curl -s https://key.digithings.ai/.well-known/jwks.json | python3 -c 'import sys,json,hashlib;k=json.load(sys.stdin)["keys"][0];print(k["kid"],hashlib.sha256(k["n"].encode()).hexdigest()[:16])'` → the fingerprint changes; `kid` stays `digikey-1`. Then a BFF token exchange → 200.
**Rollback** — re-put the previous PEM and bump the id again.
**Gotchas** — static `kid` means consumers cannot distinguish keys across rotations (R1); `DIGIKEY_KEY_ID` is a plain var (`wrangler.toml:201`), changing it is a config change. PEM accepts base64 or `\n`-escaped form (`wrangler.toml:137` comment).

### 7. `DIGIKEY_DATABASE_URL`

**Blast radius** — digikey **refuses to start** when unset: no SQLite fallback by design, because `/data` is ephemeral and a fallback would silently lose every issued key (#4080; `digikey/src/digikey/db.py:33-38`). The URL carries the Postgres password (R11).
**Copies** — stack Worker secret only (`cloudflare/digithings-stack-cloudflare/wrangler.toml:139`, forwarded `src/index.ts:72`); deliberately **not** a `[vars]` (`wrangler.toml:228-233` comment).
**Pre-flight** — confirm the new role/password on the same Postgres/Supabase instance; keys minted into a *different* store do not exist there.
**Steps**
1. Change the role password in Postgres (dashboard or `ALTER ROLE … PASSWORD`).
2. `printf '%s' "$NEW_DSN" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGIKEY_DATABASE_URL` in `cloudflare/digithings-stack-cloudflare`.
3. Bump `SHARED_STACK_CONTAINER_ID`.
4. Deploy.
5. If the store itself changed, re-issue the digiquant service key per `docs/ops/digiquant-digikey-service-key.md:77-103`.
**Verify** — `curl -sf https://key.digithings.ai/healthz` → `{"ok":true}`; then a BFF/API-key exchange → 200; and a key issued **before** the rotation still exchanges (proves the durable store, not `/data`).
**Rollback** — re-put the previous DSN and bump the id.
**Gotchas** — a DSN change without a recycle is an auth outage (trap). A bare `postgresql://` URL is accepted, routed to psycopg 3 (`wrangler.toml:140-143`).

### 8. `DIGIQUANT_VAULT_MASTER_KEY`

**Blast radius** — every sealed broker credential (AES-256-GCM envelope) becomes unreadable; `DIGIQUANT_VAULT_KEY_ID` carries one label, `v1` (R12).
**Copies** — local secret store, read from `.env` on every call (`digiquant/src/digiquant/vault/envelope.py:79-80`); no default and no fallback.
**Pre-flight — no re-seal path exists.** The module docstring is explicit: "Rotation (a second key plus a re-seal job) is out of scope for K3 — this module only makes the version legible" (`envelope.py:43-44`). There is no previous-key env and no rewrap CLI. Rotating today means re-sealing or recreating every stored connection; do not rotate until a re-seal job exists.
**Steps (only if the key is known-compromised)**
1. Back up the `broker_connections` ciphertext rows (unreadable without the old key, but required for a future re-seal).
2. Set `DIGIQUANT_VAULT_KEY_ID=v2` and the new `DIGIQUANT_VAULT_MASTER_KEY`.
3. Re-connect each broker through the OAuth/connect flow to re-seal under `v2` (human-gated broker path).
4. Delete the old ciphertext only after every row is re-sealed.
**Verify** — `pytest tests/dq/vault/test_envelope.py` proves the crypto; the only end-to-end open path for prod rows is a broker connect that unseals (`envelope.py:488`). `fingerprint()` (8 hex chars) is the only display-safe artifact (`envelope.py:55-58`) — never log plaintext.
**Rollback** — restore the previous master key + `v1` and the untouched ciphertext.
**Gotchas** — key is read per call, so a new process env takes effect immediately; there is no long-lived module copy to flush.

### 9. Supabase service-role alias pair — `SUPABASE_SERVICE_ROLE_KEY` / `CORE_SUPABASE_SERVICE_KEY`

**Blast radius** — full DB read/write for digibase, digisearch, digivault and the digiquant pipelines. The URL pair is `CORE_SUPABASE_URL` / `SUPABASE_URL`.
**Copies** — GitHub repo secret under both names (repeated in `pipeline-*.yml` and `execution-cron-check.yml`); local `.env`; consumers `digibase/src/digibase/connectors/supabase.py:112-113`. No Worker secret.
**Steps**
1. Rotate the service key in the Supabase dashboard (Project Settings → API). Confirm in-dashboard whether the legacy JWT pair rotates together or the newer API keys rotate independently before proceeding.
2. `gh secret set CORE_SUPABASE_SERVICE_KEY` and `gh secret set SUPABASE_SERVICE_ROLE_KEY` (read-new / fall-back-to-old, ADR-0022).
3. Update the gitignored local `.env`.
**Verify** — `curl -s -o /dev/null -w '%{http_code}\n' "$CORE_SUPABASE_URL/rest/v1/" -H "apikey: $NEW" -H "Authorization: Bearer $NEW"` → `200`; then a pipeline run (`pipeline-digiquant.yml`, `execution-cron-check.yml`) green.
**Rollback** — restore the previous key in both secret names.
**Gotchas** — digivault prefers `CORE_SUPABASE_ANON_KEY` (RLS) over the service key (`python.md:73`); the service key bypasses RLS. Alias equality is inferred from config, never diffed (inventory Gaps).

### 10. `LITELLM_MASTER_KEY` + `LITELLM_PROXY_API_KEY`

**Blast radius** — LiteLLM proxy auth (loopback in the stack container) and the digichat proxy bearer (`X-LiteLLM-Proxy-Key`). `DIGIKEY_LITELLM_PROXY_KEY` defaults to `LITELLM_MASTER_KEY` (`docker-compose.yml:36`).
**Copies** — stack Worker `LITELLM_PROXY_API_KEY` (`cloudflare/digithings-stack-cloudflare/wrangler.toml:149`, forwarded `src/index.ts:108`); `LITELLM_MASTER_KEY` live but undocumented (forwarded `src/index.ts:109` — R9); `docker-compose.yml:36,127`; `.env.example:43` (commented).
**Steps**
1. Generate both new values.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put LITELLM_MASTER_KEY` and the same for `LITELLM_PROXY_API_KEY` in `cloudflare/digithings-stack-cloudflare`.
3. Rotate `DIGIKEY_LITELLM_PROXY_KEY` in lockstep **only** if it is not derived from the master key.
4. Bump `SHARED_STACK_CONTAINER_ID`; deploy.
**Verify** — `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4000/v1/models -H "Authorization: Bearer $LITELLM_MASTER_KEY"` → `200` (loopback in the container; reproduce locally with `PATH="$PWD/.venv/bin:$PATH" make stack-local` then the same curl). Hosted verification is indirect: a chat completion through `graph.digithings.ai` with a digikey JWT.
**Rollback** — re-put the previous pair and bump the id.
**Gotchas** — `LITELLM_MASTER_KEY` is absent from the wrangler secret checklist (R9): enumerate live names with `secret list` before assuming. See `SECURITY.md:44` for the master-key + virtual-key model.

### 11. Provider keys — `OPENROUTER_API_KEY`, `CHEAPERINFERENCE_API_KEY`, `GROQ_API_KEY`

**Blast radius** — house LLM routing (`digillm/src/digillm/client.py:242,485`) and digigraph/LiteLLM (`cloudflare/digithings-stack-cloudflare/src/index.ts:100-104`).
**Copies (note the dead/misdirected ones)** — `OPENROUTER_API_KEY`: GitHub repo secret; stack Worker (`wrangler.toml:145`); digichat Worker **dead** (put but not in `envVars`, `cloudflare/digichat-cloudflare/src/index.ts:32-56`); local `.env`; Pages `digithings-web` **dead** (`wrangler.toml:24`; `/chat` returns 410). `CHEAPERINFERENCE_API_KEY`: GitHub repo secret; stack Worker (`wrangler.toml:146`); digichat Worker **dead**; synced by `sync-cheaperinference-cf-secrets.yml:27,56`. `GROQ_API_KEY`: GitHub repo secret; stack Worker (`wrangler.toml:145`); local `.env` (R4/R9).
**Steps**
1. Rotate upstream in the provider console.
2. `gh secret set OPENROUTER_API_KEY` (and `CHEAPERINFERENCE_API_KEY`, `GROQ_API_KEY`).
3. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put OPENROUTER_API_KEY` in `cloudflare/digithings-stack-cloudflare` (repeat per key). The CI sync workflow can do the stack put for `CHEAPERINFERENCE_API_KEY` / `OPENROUTER_API_KEY`.
4. Bump `SHARED_STACK_CONTAINER_ID`; deploy the stack.
**Verify** — a one-token completion through LiteLLM: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4000/v1/chat/completions -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' -d '{"model":"house","messages":[{"role":"user","content":"ping"}],"max_tokens":1}'` → `200`.
**Rollback** — re-put the previous key and bump the id.
**Gotchas** — setting `CHEAPERINFERENCE_API_KEY` flips the house default upstream (`entrypoint.sh:35-50`; [cheaperinference](docs/providers/cheaperinference.md)); `DIGI_HOUSE_UPSTREAM=openrouter` forces OpenRouter. The digichat copies are misdirected: rotating them changes no behaviour, but keep them hygienic. Empty optional secrets fail the wrangler-action deploy (`deploy-digichat-cloudflare-container.yml:171-172`).

### 12. `ZAMMAD_API_TOKEN`

**Blast radius** — the read-only Zammad helpdesk MCP (OCC demo) 401s (`cloudflare/digithings-stack-cloudflare/src/index.ts:111`).
**Copies** — stack Worker (`cloudflare/digithings-stack-cloudflare/wrangler.toml:150`, forwarded `src/index.ts:111`); `docker-compose.yml:459` (via `.env`); the tenant entry references the env name, not the value (`cloudflare/digichat/config/examples/occ-embed.yaml`).
**Steps**
1. Regenerate the token in Zammad.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put ZAMMAD_API_TOKEN` in `cloudflare/digithings-stack-cloudflare`.
3. Bump `SHARED_STACK_CONTAINER_ID`; deploy.
**Verify** — the edge gate first: `curl -s -o /dev/null -w '%{http_code}\n' -H "x-digi-mcp-key: $MCP_EDGE_KEY" https://graph.digithings.ai/_stack/mcp/zammad/mcp` → not `401`; then confirm a real Zammad tool call succeeds from the OCC embed (edge key and Zammad token are independent gates).
**Rollback** — re-put the previous token and bump the id.
**Gotchas** — a raw token or `Token token=` form is accepted (`docker-compose.yml:459` comment). A wrong edge key masks a token problem: the 401 is returned before the token is ever used (`src/index.ts:344`).

### 13. `AUTH_SECRET`

**Blast radius** — every Auth.js session/JWT invalid; all logins must re-authenticate. `AUTH_URL` must change in lockstep (R8).
**Copies** — digichat Worker (`cloudflare/digichat-cloudflare/wrangler.toml:50`, forwarded `src/index.ts:47`); `docker-compose.yml:550`; root `.env.example:240` (plaintext-literal, placeholder-shaped — not verified); `infra/digichat-release/.env.profile-a.example:17`.
**Steps**
1. Generate the new value once.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put AUTH_SECRET` in `cloudflare/digichat-cloudflare`.
3. Bump `SHARED_DIGICHAT_CONTAINER_ID` (`paths.ts:22`).
4. Deploy the digichat Worker.
5. Update the compose / profile env files for the non-Cloudflare instances.
**Verify** — `/api/auth/*` is not a Worker-proxied path (`paths.ts:6-19`), so there is no curl probe. Prove it in a browser: `curl -s -o /dev/null -w '%{http_code}\n' 'https://digithings.ai/embed?host=digithings.ai'` → not `5xx` (container up), then log in at `https://digithings.ai/chat` and reload a pre-rotation session — it must be logged out, which is the expected proof of the rotation.
**Rollback** — re-put the previous secret; only sessions whose tokens are still within lifetime resume.
**Gotchas** — four+ surfaces (R8): a partial rotation logs out only some instances, i.e. intermittent logouts. Stale-cookie troubleshooting: `cloudflare/digichat/OPERATIONS.md:94-96`.

### 14. `DIGICHAT_PLAN_PROOF_SECRET`

**Blast radius** — Desk+ plan proofs (`X-Embed-Plan-Proof`) fail to verify; `POST /api/plan-proof` returns 503 when the secret is unset (`cloudflare/digichat/src/app/api/plan-proof/route.ts`).
**Copies** — digichat Worker (`cloudflare/digichat-cloudflare/wrangler.toml:55`, forwarded `src/index.ts:52`); `cloudflare/digichat/.env.example:111` (commented). The verifier is digichat itself, and must hold the same value.
**Steps**
1. Generate.
2. `printf '%s' "$NEW" | env -u CLOUDFLARE_API_TOKEN npx --yes wrangler@4.133.0 secret put DIGICHAT_PLAN_PROOF_SECRET` in `cloudflare/digichat-cloudflare`.
3. Bump `SHARED_DIGICHAT_CONTAINER_ID`; deploy.
**Verify** — `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://digithings.ai/api/plan-proof -H 'X-Embed-Host: digiquant.io' -H 'X-Embed-Token: ***'` → `401`/`403` without a valid Supabase access token; a real dashboard session mints `{proof,…}` and `/api/chat` accepts `X-Embed-Plan-Proof`. A proof minted before rotation must now fail verification.
**Rollback** — re-put the previous secret and bump the id.
**Gotchas** — proofs hold the old signature until expiry; the mint endpoint is the only source, so clients must re-mint.

## Rotation cadence

| Target | Recommended interval | Trigger | Owner role |
|---|---|---|---|
| `DIGIKEY_PRIVATE_KEY_PEM` | 12 months (no overlap path — §6) | expiry plan; any suspected key exposure | digikey / security owner |
| `DIGIKEY_ADMIN_TOKEN`, `DIGIKEY_BFF_TOKEN` | 12 months | admin-token exposure; offboarding | digikey / security owner |
| `DIGIKEY_DATABASE_URL` | 12 months, with the DB role | DB incident; role audit | data platform |
| `MCP_EDGE_KEY` + tenant JSON | 12 months | edge 401 incident; tenant offboarding | Cloudflare / platform operator |
| `GH_DISPATCH_TOKEN` | 12 months | CI PAT expiry (GitHub notifies); offboarding | CI / platform operator |
| `CLOUDFLARE_API_TOKEN` / `VECTORIZE_API_TOKEN` / `D1_API_TOKEN` | 12 months | token expiry; leaked-scope audit | Cloudflare / platform operator |
| `AUTH_SECRET` | 12 months | auth incident; expected session reset | digichat owner |
| `DIGICHAT_PLAN_PROOF_SECRET` | 12 months | proof forgery suspicion | digichat owner |
| `LITELLM_MASTER_KEY` / `LITELLM_PROXY_API_KEY` | 12 months | proxy exposure | LLM platform owner |
| `OPENROUTER_API_KEY` / `CHEAPERINFERENCE_API_KEY` / `GROQ_API_KEY` | 6 months | provider breach notice; spend anomaly | LLM platform owner |
| `ZAMMAD_API_TOKEN` | 12 months | helpdesk incident; offboarding | OCC / support owner |
| Supabase service-role pair | 12 months | Supabase advisory; role audit | data platform |
| `DIGIQUANT_VAULT_MASTER_KEY` | **do not rotate** until a re-seal job exists (§8) | only on confirmed compromise | digiquant / security owner |
| Any secret | immediately | incident, public exposure, offboarding | the owning role above |

## Cannot verify from here

These docs must never claim the following — the evidence is not available in this repo:

- **Pages `digithings-web` env vars.** `wrangler secret list` does not list Pages; the live Pages env is unknown, and its documented `OPENROUTER_API_KEY` is dead (`cloudflare/digithings-web/wrangler.toml:24`). A Pages surface needs `pages secret list --project-name digithings-web`.
- **A Container's runtime env.** Only the Worker `envVars` whitelist in source is visible; nothing reports the container process env at runtime (inventory Gaps).
- **Liveness of keys committed in history.** Whether the gitleaks-allowlisted `mcp.secrets.env.example` values or `local-dev-unused-first-party` are still live cannot be proven without the values, and the "owner-confirmed dead" note is not reproducible (R3).
- **Alias equality.** The two `DIGIKEY_BFF_TOKEN` copies, `MCP_EDGE_KEY` vs the tenant literal, and legacy `VECTORIZE_*`/`D1_*` presence are inferred from config, never diffed against live state.
- **The actual GitHub secret/var set.** Only workflow *references* are mapped; whether `CORE_SUPABASE_*` exist or workflows silently fall back is unverified.

## Rotation log

| Date (UTC) | Secret | Actor | Ticket | Verification evidence |
|---|---|---|---|---|
|  |  |  |  |  |
