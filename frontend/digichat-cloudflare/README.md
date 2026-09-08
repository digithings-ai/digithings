# digichat on Cloudflare Containers (digithings)

Host digichat Node as a **Cloudflare Container** behind a Worker on the same
hostname as Pages (`digithings.ai`). One Container serves **all** marketing
tenants (digithings, OCC, …) — different website paths, same digichat process.

Requires **Workers Paid** (Containers are not on Free).

## Path map

| Public path | Owner | Tenant |
|---|---|---|
| `digithings.ai/chat` | Pages shell → iframe `/embed?host=digithings.ai` | digithings |
| `digithings.ai/chat/occ` | Pages shell → iframe `/embed?host=occ.digithings.ai` | occ |
| `digithings.ai/embed*` | Worker → Container | selected by `host` |
| `digithings.ai/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`, `/api/health` | Worker → Container | — |
| `digithings.ai/_dtchat*` | Worker → Container (assetPrefix) | — |
| Other paths | Pages static export | — |

Future chats = new Pages route under `/chat/<slug>` + a row in
`DIGICHAT_EMBED_TENANTS` — **not** a new Container.

```text
Browser
  → digithings.ai/chat[/occ]     (Pages)
       → iframe digithings.ai/embed?host=…   (Worker → one DigiChat Container)
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

From **repo root** (Dockerfile context is monorepo root):

```bash
cd frontend/digichat-cloudflare
npm install

npx wrangler secret put AUTH_SECRET
npx wrangler secret put DIGICHAT_EMBED_TENANTS
npx wrangler secret put DIGIGRAPH_INTERNAL_URL   # https://graph.digithings.ai
npx wrangler secret put DIGIKEY_URL              # https://key.digithings.ai
npx wrangler secret put DIGIKEY_BFF_TOKEN
npx wrangler secret put DIGICHAT_PLAN_PROOF_SECRET
npx wrangler secret put DIGICHAT_DASHBOARD_SUPABASE_URL
npx wrangler secret put DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY

npx wrangler deploy
```

Then enable zone routes (uncomment in `wrangler.toml` or Dashboard → Worker →
Domains & Routes) for `/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`,
`/api/health`, `/_dtchat*`.

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
    "llmAccess": "free_then_byok",
    "activityDetail": "full",
    "attribution": false,
    "token": "unused-for-first-party",
    "backend": { "type": "digigraph" }
  },
  "occ.digithings.ai": {
    "slug": "occ",
    "gateMode": "ungated",
    "showByok": true,
    "showStatusBar": true,
    "layout": "page",
    "activityDetail": "full",
    "title": "OCC help assistant",
    "welcome": "Ask about Online Compliance Center policies, procedures, and help articles.",
    "attribution": false,
    "token": "unused-for-first-party",
    "backend": {
      "type": "digigraph",
      "digisearchIndex": "occ_help",
      "vaultPathPrefix": "clients/online-compliance-center"
    }
  }
}
```

`DIGICHAT_EMBED_HOSTS` is already set in `wrangler.toml` `[vars]` (CSP
`frame-ancestors` — no tokens). Keep it aligned with tenant host keys:

| Align | Rule |
|---|---|
| Host keys | `DIGICHAT_EMBED_TENANTS` object keys (and `aliases`) must match iframe `?host=` / `X-Embed-Host`. |
| `DIGICHAT_EMBED_HOSTS` | Comma-separated parent hostnames allowed to frame `/embed`. Must include every live parent (marketing `digithings.ai` / `www` / `occ.digithings.ai`, plus `digiquant.io` if the dashboard popup iframes this origin). Not a secret. |
| First-party token | `digithings.ai`, `www.digithings.ai`, and `occ.digithings.ai` skip `X-Embed-Token` when registered. The JSON schema still requires a `token` field — use a non-secret placeholder; do not invent or commit a real secret. |
| Other hosts | Parent snippet / `NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN` must equal that tenant’s registry `token`. Put the real JSON only via `wrangler secret put DIGICHAT_EMBED_TENANTS`. |
| Tools | `backend.type: digigraph` (and OCC `digisearchIndex` / `vaultPathPrefix`) is how digisearch + digivault reach Profile A. digichat only probes digigraph (`DIGICHAT_ENABLED_SERVICES`); it does not talk to those services directly. |

Worker **path** routes stay unchanged: `/embed*`, `/api/chat*`, `/api/embed*`,
`/api/byok*`, `/api/plan-proof*` (1.5 Desk+ HMAC), `/api/health`, `/_dtchat*`.
Pages still owns `/chat` and `/chat/occ` shells; iframe origin stays `digithings.ai`.

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
# `"version"` must match frontend/digichat/package.json (baked into the image)
curl -s -o /dev/null -w '%{http_code}\n' 'https://digithings.ai/embed?host=digithings.ai'
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
- OCC: [`docs/projects/online-compliance-center/README.md`](../../docs/projects/online-compliance-center/README.md)
