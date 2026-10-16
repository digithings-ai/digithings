# Design: dev Cloudflare containers for clean dev → prod — #3854

**Status:** proposal, docs-only. No service, secret, route, or DNS change is made
by this document. Everything in §7 marked *human-only* is gated.

## 1. Problem

Live full-stack testing of the digiquant dashboard popup + digichat currently has
nowhere to run except the production Cloudflare containers. #3851 knowingly
manipulated prod containers because no users existed; the next promotion needs a
dev target so verification never touches prod. Acceptance (#3854):

- `dashboard` popup + `digichat` run end-to-end against dev containers with
  **zero prod traffic**.
- The promotion checklist references dev-container verification explicitly.

There is no promotion checklist file in the repo today (searched `docs/`), so §8
proposes the checklist line rather than editing a non-existent file.

## 2. Current production surface (what has to be duplicated)

Two Workers, three containers, all `sleepAfter = "15m"` after #4328 / #4334 (the
prod warm window is no longer 2h/24h — see `docs/ops/SECRETS_ROTATION.md` § *The
container boot-env trap*):

| Worker (`wrangler.toml` `name`) | Container class | `max_instances` | `instance_type` | Sleep | Ingress |
|---|---|---|---|---|---|
| `digithings-digichat` | `DigiChatContainer` | 5 | default | 15m | `digithings.ai` routes (`/embed`, `/api/*`, `/_dtchat*`) |
| `digithings-stack` | `DigiStackContainer` | 5 | `standard-2` | 15m | `graph.` / `key.` / `search.digithings.ai` custom domains |
| `digithings-stack` | `DigiQuantMcpContainer` | 1 | `standard-2` | 15m | `mcp.digithings.ai` route (commented out, not enabled) |

Sources: `apps/digichat-cloudflare/wrangler.toml`,
`apps/digithings-stack-cloudflare/wrangler.toml`,
`apps/digichat-cloudflare/src/index.ts:26`,
`apps/digithings-stack-cloudflare/src/index.ts:54,166`.

Deploy paths differ and matter for isolation:

- `deploy-digichat-cloudflare-container.yml` — auto-deploys on push to `main`
  (path-filtered) **and** `workflow_dispatch`; **no** `environment:` gate; reads
  repo secrets `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`.
- `deploy-digithings-stack-cloudflare.yml` — `workflow_dispatch` only, `deploy`
  job under `environment: production`.

A dev track must not be reachable by the existing `push: main` trigger.

## 3. Isolation options (decision needed)

### Option A — `env.dev` blocks in the existing `wrangler.toml` (recommended)

Add `[env.dev]` with its own `name`, `vars`, `[[env.dev.containers]]`,
`[[env.dev.durable_objects.bindings]]`, and `[[env.dev.migrations]]`; no
custom-domain `[[routes]]`; `workers_dev = true`. Deploy with
`wrangler deploy --env dev`; secrets with `wrangler secret put NAME --env dev`;
run `wrangler dev --env dev` locally.

- One file, `[vars]` shared, dev/prod diff is visible in review.
- Workers/Durable Objects/Containers each get an isolated namespace and secret
  set under the env.
- **Risk:** a forgotten `--env dev` deploys prod. Mitigate with a `make` target
  that always passes `--env dev` plus a CI test asserting the dev `name` differs
  from prod (`wrangler deploy --env dev --dry-run --outdir` is not needed for
  the assert). `wrangler.toml` currently has no `[env]` blocks at all, so this
  is additive.
- **Constraint:** a dev `env` still needs a distinct Durable Object id (see §4);
  DO migrations are declared per env.

### Option B — `-dev` suffixed services

Keep `digithings-stack` / `digithings-digichat` untouched; add top-level
`digithings-stack-dev` / `digithings-digichat-dev` (separate `wrangler.dev.toml`
or a second config file). Strongest blast-radius isolation: the prod deploy
command cannot reach a dev service and vice versa.

- Cost: two configs to keep in sync (vars, routes, container sizes drift).
- Wrangler resolves `image` / `image_build_context` relative to the config file's
  directory, so a sibling config under the same directory keeps the monorepo-root
  build context correct.

**Recommendation:** Option A for a single source of truth, Option B if the DO /
container behaviour under `env` proves awkward. This is a question for the owner
(see §9).

## 4. Container identity and dev isolation

Container ids are pinned constants today — dev must not share a Durable Object
with prod:

- `SHARED_DIGICHAT_CONTAINER_ID = "shared-v7"` — `apps/digichat-cloudflare/src/paths.ts:22`
- `SHARED_STACK_CONTAINER_ID = "shared-v15"` — `apps/digithings-stack-cloudflare/src/ports.ts:37`
- `MCP_CONTAINER_ID = "mcp-v1"` — `apps/digithings-stack-cloudflare/src/ports.ts:29`

A dev env needs distinct ids (e.g. `shared-v7-dev`) derived from the Worker
name/env, so a dev boot can never attach to a prod instance. The ids are also the
lever that forces a new Firecracker instance when rotated env must reach a warm
container (same doc, § *The container boot-env trap*), so making them
env-derived is a prerequisite, not a nicety.

`ports.ts:56` already routes any `*.workers.dev` / `localhost` / `127.0.0.1` host
to digigraph, so a dev stack on its `workers.dev` URL works without a new DNS
record.

## 5. Dev secret set (values never in the repo)

Every secret below must be dev-specific. Reusing a prod value is the failure mode
this design exists to prevent.

**`digithings-stack-dev`**

| Secret | Why it must differ |
|---|---|
| `DIGIKEY_PRIVATE_KEY_PEM` | Dev RS256 keypair. Sharing prod's signing key would let a dev JWT verify in prod. |
| `DIGIKEY_DATABASE_URL` | Dev Postgres/Supabase. Holds API keys + the JWT revocation blocklist; pointing at prod mutates prod auth state. digikey refuses to start without it (#4080). |
| `DIGIKEY_ADMIN_TOKEN` | Dev admin bearer. |
| `DIGIKEY_BFF_TOKEN` | Dev value, **must equal** the dev digichat Worker's copy (one-sided rotation breaks chat). |
| `MCP_EDGE_KEY` | Dev edge key for `/_stack/mcp/*`. |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | Token scoped to dev Worker/R2/D1/Vectorize only; keep `env -u CLOUDFLARE_API_TOKEN` for wrangler (see `docs/ops/SECRETS_ROTATION.md` § Preconditions). |
| `R2_ACCOUNT_ID` / `R2_BUCKET` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Dev bucket (`digithings-archive-dev`), never `digithings-archive`. A dev write to prod R2 is a prod-traffic violation even if no user sees it. |
| provider keys (`GROQ_API_KEY`, `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY`, `FRED_API_KEY`, `ZAMMAD_API_TOKEN`) | Prefer dev-scoped keys to isolate spend; if shared, set spend guardrails explicitly. |

Vars that are not secrets but drive dev behaviour: `DIGIKEY_ALLOW_EPHEMERAL_KEY`,
`DIGIKEY_ISSUER`/`DIGIKEY_AUDIENCE`, `DIGIKEY_ALLOW_DEV_GLOBAL`,
`DIGIQUANT_MARKET_DATA_BACKEND`, `DIGI_LLM_MODE`, `DIGIVAULT_ROOT`, `CHROMA_PATH`.

**`digithings-digichat-dev`**

| Secret | Why it must differ |
|---|---|
| `AUTH_SECRET` | Dev sessions; sharing it makes a dev session valid in prod (and vice versa). |
| `DIGICHAT_EMBED_TENANTS` | Dev tenant JSON: dev parent origins (`localhost` / `127.0.0.1`) and dev backends. The prod JSON's per-tenant `token` and `mcp.servers` entries are prod values. |
| `DIGIGRAPH_INTERNAL_URL` | Dev stack URL (e.g. `https://digithings-stack-dev.<subdomain>.workers.dev`), never `https://graph.digithings.ai`. |
| `DIGIKEY_URL` | Dev stack key URL. |
| `DIGIKEY_BFF_TOKEN` | Same dev value as the dev stack. |
| `DIGICHAT_PLAN_PROOF_SECRET` | Dev plan-proof signing; prod proofs must not verify in dev. |
| `DIGICHAT_DASHBOARD_SUPABASE_URL` / `_ANON_KEY` | Dev Supabase. If unset, plan-proof/dashboard features stay off (that is acceptable for a chat-only dev loop). |
| `DIGICHAT_DATABASE_URL` | Optional. The Cloudflare deployment is DB-less by default; a dev Postgres is optional. |

Non-secret vars that must include the dev parent origin: `DIGICHAT_EMBED_HOSTS`
(prod value is `digithings.ai,…,digiquant.io`). Do **not** add prod hosts to the
dev value.

## 6. `sleepAfter` parity

Prod is **15m on all three containers** (#4328 shortened the stack from 2h;
#4334 shortened the MCP from 24h; digichat was already 15m). Dev should match
15m for behaviour parity — cold starts are now graceful (`Connecting…` status +
abort-aware upstream retry, #4323/#4325), so 15m is safe for both. If dev cost
matters more than cold-start parity, a shorter dev window (e.g. `5m`) is
acceptable **only if** the dev loop tolerates the cold start; keep the value
explicit and commented so it does not silently drift from prod. Do not shorten
prod as part of the dev work.

## 7. The documented dev loop

The issue text names `frontend/dashboard` and `frontend/digichat`; those paths no
longer exist on `develop`. The frontends live under `cloudflare/`:

```bash
# repo root, once
npm install

# local dashboard (static-export Next app), http://127.0.0.1:3001/dashboard/
npm --workspace apps/dashboard run dev

# local digichat (Next), default port 3000; 3002 avoids a clash
npm --workspace apps/digichat run dev -- -p 3002
# or explicitly:
#   cd apps/digichat && npx next dev --hostname 127.0.0.1 -p 3002
```

Local `.env.local` points at the **dev** containers, not prod:

- `apps/digichat/.env.local` — `DIGIGRAPH_INTERNAL_URL`, `DIGIKEY_URL`,
  `DIGIKEY_BFF_TOKEN` at the dev stack; `AUTH_URL` at the local digichat origin.
- `apps/dashboard/.env.local` — `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` at the
  local digichat origin and `NEXT_PUBLIC_DIGICHAT_EMBED_HOST` for the dev parent.
  `apps/dashboard/README.md` documents the loopback dogfood pattern
  (digichat `:3005`, dashboard `:4014`); the current `dev` script serves `:3001`.
  `NEXT_PUBLIC_MARKET_DATA_URL` should point at the dev stack's
  `/v1/market/*`, not `graph.digithings.ai`.

End-to-end gate for the acceptance criterion:

1. `curl -sf <dev-stack>/healthz` and `<dev-key>/healthz` on the dev URLs.
2. Open the dashboard dev URL, confirm the digichat popup frames the local
   digichat, send a chat turn that reaches the dev digigraph.
3. Confirm **zero prod traffic**: the dev Workers' request counts are the only
   ones that move; `graph.digithings.ai` / `key.digithings.ai` stay flat; the dev
   R2 bucket is the only one written.

## 8. Promotion checklist hook

No promotion checklist file exists. Propose adding to `docs/DEPLOYMENT.md` (or a
new `docs/ops/` checklist) a line requiring, before any `develop → main` promote:

> - [ ] Dev-container verification recorded: dashboard popup + digichat ran
>   end-to-end against `*-dev` containers; dev Workers served the traffic and
>   prod containers saw none (link the run/log evidence). — #3854

## 9. Cost, instance, and open questions

- **Base fee:** Workers Paid is per account ($5/mo). Same Cloudflare account →
  no extra base fee; a separate dev account → +$5/mo. This is an owner
  decision.
- **Usage:** billing is only while an instance runs; 15m `sleepAfter` scales dev
  to zero between test sessions. Dev is bursty, so usage is far below prod's
  always-on cost (the #3851 invoice showed ~one always-on `standard-2` as the
  dominant line).
- **Instance type:** keep `standard-2` for the dev stack/MCP for parity, or try
  `standard-1` if dev-only memory headroom is proven — do **not** drop to
  `lite`/`basic` (multi-process Profile A does not fit). digichat uses the
  wrangler default.
- **Open questions for the owner:**
  1. Same Cloudflare account (extra Worker names, no base fee) or a separate dev
     account/project (+$5/mo, stronger isolation)?
  2. `env.dev` blocks (Option A) or `-dev` suffixed services (Option B)?
  3. Dev uses its own R2 bucket, or read-only against prod R2? (This proposal
     assumes a separate dev bucket.)
  4. Shared provider keys with spend guardrails, or dev-scoped keys?

## 10. Automation boundary

**An agent may later do (no external change):**

- Author the `[env.dev]` blocks / `-dev` config, env-derived container ids, and
  the `make` target that always passes `--env dev`.
- Add a CI test asserting the dev Worker `name`, container id, routes, and R2
  bucket differ from prod.
- Update `cloudflare/*/README.md` and this plan with the chosen dev loop.
- Add the promotion-checklist line from §8 and dev `.env.local.example` entries
  (names only, no values).

**Human-only (blocked on owner; AGENTS.md human gate):**

- Create new Workers/containers, custom domains, or any DNS record.
- Set any secret (`wrangler secret put`, `gh secret set`) — needs account login.
- Create the dev Postgres/Supabase, the dev R2 bucket, and the dev digikey
  keypair / admin / BFF tokens.
- Approve the new external service dependency / network exposure and run the
  first deploy.

## See also

- `apps/digichat-cloudflare/README.md`, `apps/digithings-stack-cloudflare/README.md`
- `apps/dashboard/README.md`, `apps/digichat/README.md`
- `docs/ops/SECRETS_ROTATION.md` (container boot-env trap, wrangler auth trap)
- `docs/DEPLOYMENT.md`
