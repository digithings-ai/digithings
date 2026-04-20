# DigiChat

Next.js **App Router** app: React chat UI + BFF for **DigiGraph** (`POST /v1/chat/completions`). See root **[DIGICHAT.md](../DIGICHAT.md)** for architecture, Compose, and ops.

## Local chat + tools (host stack)

1. Repo root: **`make stack-local`** (DigiKey **:8005**, DigiGraph **:8000**, DigiQuant **:8001**, DigiSearch **:8002**, DigiSmith **:8003**). Ensure an **LLM** is reachable from DigiGraph ([`docs/LOCAL_STACK.md`](../docs/LOCAL_STACK.md) — LiteLLM **:4000** or Ollama on loopback).
2. **`cp -n .env.example .env.local`** and fill **`DIGIKEY_BFF_TOKEN`**, **`AUTH_SECRET`**, service URLs, **`DIGICHAT_DEV_AUTH=1`**, optional **`DIGICHAT_LOCAL_AUTH_KEY`** (see DIGICHAT.md).
3. **`npm install`** then **`npm run dev`** (or **`make digichat-dev`** from repo root).
4. Open **`http://127.0.0.1:3000`**, confirm **`GET /api/health`** is `ok` for all enabled services.
5. Sign in (dev password) or rely on local-bootstrap when **`DIGICHAT_LOCAL_AUTH_KEY`** is set; chat uses DigiKey **`bff_session`** JWTs so DigiGraph can call DigiSearch/DigiQuant tools with the same auth chain.

## Scripts

| Command | Description |
|--------|-------------|
| `npm run dev` | Local dev server |
| `npm run build` / `npm start` | Production build + Node server |
| `npm run db:generate` | Drizzle SQL from `src/db/schema.ts` |
| `npm run db:migrate` | Apply migrations (CLI; CI/init containers) |
| `npm run db:seed` | Insert `default` tenant |
| `npm run db:create-key` | Issue `digi_live_…` key (args: `tenantSlug` `label`) |

## Layout

- `src/app/api/chat` — authenticated streaming chat (humans + machines).
- `src/app/api/v1/chat` — alias for programmatic clients.
- `src/app/api/health` — readiness.
- `src/auth.ts` — Auth.js OIDC + dev credentials.
- `src/db/` — Drizzle schema + client.

Docker: `docker compose --profile digichat up -d --build digichat` from repo root.

## `/embed` — iframeable preview

`/embed` is a **minimal, unauthenticated** chat surface designed to be iframed from `digithings.ai` and `digiquant.io` for in-site previews.

- **Route:** `GET /embed?accent=<digithings|digiquant|digichat>` (default `digichat`). The query param switches the `--accent` token for host-site color parity — no server-side theming.
- **Free tier:** first **3 user turns** per host origin, counted client-side in `localStorage` (keyed by `document.referrer` origin). After the limit, a paywall card offers **Bring your own key** (reveals the BYOK input in-place) or **Open DigiChat** (link to `chat.digithings.ai`).
- **BYOK:** reuses the shared `useBYOKKey` hook — the embed never duplicates key storage or test logic. A saved key unlocks unlimited turns immediately.
- **CSP:** `next.config.ts` emits `Content-Security-Policy: frame-ancestors 'self' https://digithings.ai https://digiquant.io;` and `X-Content-Type-Options: nosniff` on `/embed[/*]`. Origins outside the allowlist cannot frame the page.
- **Analytics:** `src/lib/embed-gate.ts` exports `emit(event, props)` — a no-op today, single call-site for future vendor wiring.
- **Non-goals (see #241):** no backend rate limiting, no model selector, no SSO.

Local iframe test:
```bash
npm run dev
# In another terminal, serve website/ and open its index.html; the embed
# renders at http://localhost:3000/embed?accent=digithings
```

