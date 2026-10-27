# digichat on Cloudflare Containers (digithings)

Host digichat Node as a **Cloudflare Container** behind a Worker on the same
hostname as Pages (`digithings.ai`). One Container serves **all** marketing
tenants (digithings, OCC, …) — different website paths, same digichat process.

Requires **Workers Paid** (Containers are not on Free).

## Path map

| Public path | Owner | Tenant |
|---|---|---|
| `digithings.ai/chat` | Worker → Container — **the digichat app**, built with basePath `/chat` (DIG-5121) | — |
| `digithings.ai/chat/occ` | Worker `occGate` → Container, served by the app's `/chat/embed` route (invite-gated at the edge) | occ |
| `digithings.ai/chat/occ?token=<key>` | same; the gate sets the session cookie and moves the key to `x-embed-token` (DIG-1210) | occ |
| `digithings.ai/embed*` | Worker → Container (ADR 0018 compatibility route) | selected by `host` |
| `digithings.ai/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`, `/api/health` | Worker → Container (ADR 0018 compatibility routes) | — |
| `digithings.ai/_dtchat*` | Worker → Container (assetPrefix) | — |
| Other paths | Pages static export | — |

`/chat` is the app itself, not a Pages shell (DIG-5121 — in `develop`, live
with the digichat deploy lane and Chris's production approval — ADR 0018
historical note 1): the Worker claims `digithings.ai/chat*`, and the
Container is **built** with `DIGICHAT_BASE_PATH=/chat` — Next bakes
`basePath` at build time — so the app answers under `/chat` and never
nests into `/chat/chat`. The Worker maps every public path onto the path
the Container serves (`src/paths.ts: containerPathFor`): `/chat*` and
`/_dtchat*` pass through, the container-local `/api/mcp/zammad*` is never
moved (and its `/chat/api/mcp/zammad*` spelling is mapped back onto it, so
the edge key gates both), and the legacy routes are moved under the base
path so they keep working.

Future chats = a new path in the app + a row in `DIGICHAT_EMBED_TENANTS`
— **not** a new Container. A new path in the app lives **under `/chat`**
(the app is served under that base path); a client call into it goes
through `p()` (`apps/digichat/src/lib/base-path.ts`) so it carries the
prefix.

`/chat/occ` is an invite-gated path on that same app (2026-10-27): the Worker
checks the invite, sets the `occ_invite` cookie, rewrites the request to
`/chat/embed?host=occ.digithings.ai`, moves the key to `x-embed-token` and
drops `?token=`, then proxies to the Container. There is no Pages shell and no
iframe in the chain, and `OCC_INVITE_KEY` exists only as a Worker secret.

```text
Browser
  → digithings.ai/chat           (Worker → one digichat Container, basePath /chat)
  → digithings.ai/chat/occ       (Worker occGate → same Container, /chat/embed)
       → DIGIGRAPH_INTERNAL_URL=https://graph.digithings.ai
       → DIGIKEY_URL=https://key.digithings.ai
```

## What is NOT in the digichat Container

digigraph, digikey, LiteLLM, digivault, digisearch run in the **sibling** Profile A
stack Container — [`../digithings-stack-cloudflare/`](../digithings-stack-cloudflare/README.md).
Set digichat secrets `DIGIGRAPH_INTERNAL_URL` / `DIGIKEY_URL` to those stable
hostnames (not Mac Compose, not `*.trycloudflare.com` quick tunnels).

Mac Compose remains **dev-only** — see
[`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

## Prerequisites

- Docker running locally (for `wrangler deploy` image build)
- Cloudflare account with **Workers Paid**
- `npx wrangler login` (digithings CF account — same zone as digithings.ai)
- Profile A stack deployed (or reachable digigraph/digikey URLs for bring-up)

## Deploy

> **The CI deploy lane for this Worker is `deploy-digichat-cloudflare-container.yml`**, re-derived
> on `develop` on 2026-10-22 (DIG-5120). It is a re-derivation, not a revert of the file
> deleted on 2026-10-01 by `f54af7052` (#4919, Human Gate): the deleted lane had no
> `production` environment gate, so a push-triggered successor would have deployed production
> on every merge. The re-derived lane deploys on a manual `workflow_dispatch` only, behind
> `environment: production`, so Chris approves every deploy; a merge to `main` validates the
> app and deploys nothing. The `production` environment allows `main` deployments only and
> `develop` is this repo's default branch, so the lane becomes deployable when a promotion
> carries it to `main`. The recipe below is the **local** path. The build half is still
> gated: the `worker-build` job in `.github/workflows/ci.yml` runs
> `wrangler deploy --dry-run --containers-rollout=none` for this app on every
> PR. See
> [docs/DEPLOYMENT.md § Cloudflare Workers and Containers](../../docs/DEPLOYMENT.md#cloudflare-workers-and-containers).

From **repo root** (Dockerfile context is monorepo root):

```bash
cd apps/digichat-cloudflare
npm install

npx wrangler secret put AUTH_SECRET
npx wrangler secret put DIGICHAT_EMBED_TENANTS
npx wrangler secret put DIGIGRAPH_INTERNAL_URL   # https://graph.digithings.ai
npx wrangler secret put DIGIKEY_URL              # https://key.digithings.ai
npx wrangler secret put DIGIKEY_BFF_TOKEN
npx wrangler secret put DIGICHAT_PLAN_PROOF_SECRET
npx wrangler secret put DIGICHAT_MONITOR_TOKENS   # optional (DIG-613); omit => free-turn gate applies to all
npx wrangler secret put DIGICHAT_DASHBOARD_SUPABASE_URL
npx wrangler secret put DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY

npx wrangler deploy
```

The zone routes are declared, not enabled by hand: `wrangler.toml` carries all twelve
`digithings.ai` patterns (`/chat*`, `/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`,
`/api/plan-proof*`, `/api/health`, `/_dtchat*`, `/_digichat/meta`, `/_digichat-admin*`,
`/api/mcp/zammad*`, `/chat/occ*`) - a deploy must not narrow that list.

### `DIGICHAT_EMBED_TENANTS` (digithings + OCC)

```json
{
  "digithings.ai": {
    "slug": "digithings",
    "aliases": ["www.digithings.ai"],
    "gateMode": "ungated",
    "showByok": true,
    "showStatusBar": true,
    "layout": "page",
    "skin": "digichat",
    "llmAccess": "free_then_byok",
    "activityDetail": "full",
    "attribution": true,
    "token": "unused-for-first-party",
    "backend": { "type": "digigraph" }
  },
  "occ.digithings.ai": {
    "slug": "occ",
    "gateMode": "ungated",
    "showByok": true,
    "showStatusBar": true,
    "layout": "page",
    "skin": "digichat",
    "activityDetail": "full",
    "title": "OCC help assistant",
    "welcome": "Ask about Online Compliance Center policies, procedures, and help articles.",
    "attribution": true,
    "token": "unused-for-first-party",
    "backend": {
      "type": "digigraph",
      "digisearchIndex": "occ_help",
      "vaultPathPrefix": "clients/online-compliance-center"
    }
  }
}
```

Tenant entries may also carry the same operator-only `mcp.servers` entries as
the deploy YAML — `{ id, url, label?, default?, token?, tokenEnv?, authHeader? }`
— e.g. the OCC Zammad server, served by this Worker's own key-gated route
(`url: https://digithings.ai/api/mcp/zammad/mcp`,
`token: <ZAMMAD_EDGE_KEY value>`, `authHeader: x-digi-mcp-key`). Use a literal
`token`: `tokenEnv` only resolves variables present in the Container's own
environment, and the Worker's `ZAMMAD_EDGE_KEY` secret is not forwarded there.
The in-container zammad-mcp authenticates to Zammad with its own environment, so
it needs `ZAMMAD_API_TOKEN` (and optionally `ZAMMAD_BASE_URL`) as Container
secrets. They are resolved server-side and stripped by the browser projections
(see `apps/digichat/ARCHITECTURE.md`).

`DIGICHAT_EMBED_HOSTS` is already set in `wrangler.toml` `[vars]` (CSP
`frame-ancestors` — no tokens). Keep it aligned with tenant host keys:

| Align | Rule |
|---|---|
| Host keys | `DIGICHAT_EMBED_TENANTS` object keys (and `aliases`) must match iframe `?host=` / `X-Embed-Host`. `X-Embed-Host` only selects the tenant — it never authorizes (see below). |
| `DIGICHAT_EMBED_HOSTS` | Comma-separated parent hostnames allowed to frame `/embed`. Must include every live parent (marketing `digithings.ai` / `www` / `occ.digithings.ai`, plus `digiquant.io` if the dashboard popup iframes this origin). Not a secret. |
| First-party token | `digithings.ai` and `www.digithings.ai` skip `X-Embed-Token` when registered **and** the request carries a first-party browser-attested origin (`Origin`/`Referer`). A spoofed `X-Embed-Host` alone does not qualify. `occ.digithings.ai` is **not** on the first-party allowlist (DIG-1210 Act B2). OCC is gated by an **invite key**, carried as `?token=<key>` on `digithings.ai/chat/occ` and forwarded as `X-Embed-Token`. That key is a **bearer capability, not authentication** — anyone holding the link can use the tenant. The JSON schema still requires a `token` field — use a non-secret placeholder for a tenant with no live customer data, and a real secret via `wrangler secret put` for one that has; do not commit one. **Mint, rotate, revoke and verify the OCC key: [`docs/ops/OCC_INVITE_KEY.md`](../../docs/ops/OCC_INVITE_KEY.md).** The `/chat/occ` shell is also gated at the edge (`OCC_INVITE_KEY` on the Worker, and the Pages function) so the chat page is not served without the key or the `occ_invite` cookie. |
| First-party skin | Unset `skin` on those hosts defaults to `digichat` (DigichatThread). Set `"skin": "digichat"` in the wrangler secret anyway so the live JSON matches the YAML examples. Third-party tenants still default to catalog `base`. |
| Legacy anonymous embed | The flag is deliberately **unset** in `wrangler.toml` `[vars]` (OFF). A stock deploy refuses unregistered hosts. To opt in, add `DIGICHAT_LEGACY_EMBED_ENABLED = "1"` to `[vars]` (the Worker forwards it; deprecated alias `DIGICHAT_EMBED_ENABLED` is also honored) — only on a deployment **without** `DIGICHAT_EMBED_TENANTS`; with tenants configured the flag is ignored and unregistered hosts get 503. |
| Other hosts | Parent snippet / `NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN` must equal that tenant’s registry `token`. Put the real JSON only via `wrangler secret put DIGICHAT_EMBED_TENANTS`. |
| Tools | `backend.type: digigraph` (and OCC `digisearchIndex` / `vaultPathPrefix`) is how digisearch + digivault reach Profile A. digichat only probes digigraph (`DIGICHAT_ENABLED_SERVICES`); it does not talk to those services directly. |

Worker **path** routes: `/chat*` (the app itself — the Container is built with
`DIGICHAT_BASE_PATH=/chat`, DIG-5121) plus the ADR 0018 compatibility window
`/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`
(1.5 Desk+ HMAC), `/api/health`, `/_dtchat*`. `/embed*` stays **indefinitely**:
the OCC shell's iframe and the marketing site both point at
`digithings.ai/embed?host=…`, so it is not a temporary bridge. The `/api/*`
routes are the old spelling of what the app now serves under `/chat/api/*`
and are reviewed once the cutover is verified live — they are removed only
after that, and never before. Pages keeps the `/chat/occ` shell; iframe
origin stays `digithings.ai`.

### digiquant.io Desk+ tenant shape (names only)

For the digiquant dashboard embed tenant in `DIGICHAT_EMBED_TENANTS`, production shape is:
`gateMode: ungated`, `llmAccess: operator`, `requiredPlanTier: desk`, `showByok: true`
(no gate block). Put real values only via `wrangler secret put` — never commit them.
`POST /api/plan-proof` mint needs the three plan-proof / dashboard Supabase names above
whitelisted into the Container `envVars` (already wired in `src/index.ts`).

## Pages

After the Worker routes are live:

```bash
NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai
```

(or rely on a build default once Containers is production). iframe CSP
`frame-src` must allow `https://digithings.ai`.

## Smoke

```bash
curl -sf https://digithings.ai/api/health
# `"version"` must match apps/digichat/package.json (baked into the image)
curl -s -o /dev/null -w '%{http_code}\n' 'https://digithings.ai/embed?host=digithings.ai'
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
# after the /chat cutover: the app itself, under the base path (200)
# Browser: https://digithings.ai/chat and /chat/occ
```

## Local Worker

```bash
npm run dev   # wrangler dev — needs Docker for Container
npm test
```

## See also

- [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md)
- [`docs/adr/0018-digichat-path-routing.md`](../../docs/adr/0018-digichat-path-routing.md)
