# DigiChat on Cloudflare Containers (DigiThings website)

DigiThings has **no Azure**. DigiChat for digithings.ai runs as a **Cloudflare
Container** (existing DigiChat Dockerfile / GHCR image family) behind a Worker
that shares the `digithings.ai` hostname with Cloudflare Pages.

DataTap keeps its own DigiChat Azure ACA — do not reuse it for DigiThings.

## Architecture

| Path | Owner |
|---|---|
| `digithings.ai/chat` | Pages (`frontend/digithings-web`) — shell + iframe |
| `digithings.ai/embed*` | Worker → DigiChat Container |
| `digithings.ai/api/chat*`, `/api/embed*`, `/api/byok*` | Worker → DigiChat Container |
| `digithings.ai/_dtchat*` | Worker → DigiChat Container (assetPrefix; avoids Pages `/_next` clash) |
| Other paths | Pages static export |

## Prerequisites

- Docker running locally (for `wrangler deploy` image build)
- Cloudflare account with Workers Paid (Containers)
- `npx wrangler login` (DigiThings CF account — same zone as digithings.ai)
- Digivault secrets (Supabase + OpenRouter) as Worker/Container secrets

## Deploy

From **repo root** (Dockerfile context is monorepo root):

```bash
# Optional: build digichat image with embed hosts + asset prefix baked in
# DIGICHAT_EMBED_HOSTS and DIGICHAT_ASSET_PREFIX are build-args on the Dockerfile —
# pass via docker build or extend containers image_build_context later.

cd frontend/digichat-cloudflare
npm install
npx wrangler secret put AUTH_SECRET   # throwaway for layout auth(); not OIDC
npx wrangler secret put DIGITHINGS_SUPABASE_URL
npx wrangler secret put DIGITHINGS_SUPABASE_ANON_KEY
npx wrangler secret put DIGITHINGS_OPENROUTER_API_KEY
npx wrangler secret put DIGICHAT_EMBED_TENANTS   # digithings tenant JSON (see ops checklist)
npx wrangler deploy
```

Then attach **zone routes** on digithings.ai (Dashboard → Worker → Settings → Domains & Routes, or wrangler `routes`):

- `digithings.ai/embed*`
- `digithings.ai/api/chat*`
- `digithings.ai/api/embed*`
- `digithings.ai/api/byok*`
- `digithings.ai/_dtchat*`

Pages project: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`.

## Embed-only container env

Prefer **omit** `DIGICHAT_DATABASE_URL` / `DIGICHAT_AUTO_MIGRATE` (no Postgres).
Set `DIGICHAT_ENABLED_SERVICES=` empty so health does not probe digigraph.
Do not set DigiKey / Foundry / Azure credentials.

Build DigiChat image with:

- `DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai`
- `DIGICHAT_ASSET_PREFIX=/_dtchat`

## Smoke

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/embed
# Browser: landing quick-ask → /chat seeded turn
```

Merge PR #1868 CF Function delete only after `/embed` returns 200.
