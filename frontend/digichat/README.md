# digichat

Next.js **App Router** app: React chat UI + BFF for **digigraph** (`POST /v1/chat/completions`). See root **[DIGICHAT.md](../DIGICHAT.md)** for architecture, Compose, and ops.

## Local chat + tools (host stack)

1. Repo root: **`make stack-local`** (digikey **:8005**, digigraph **:8000**, digiquant **:8001**, digisearch **:8002**, digismith **:8003**). Ensure an **LLM** is reachable from digigraph ([`docs/LOCAL_STACK.md`](../docs/LOCAL_STACK.md) — LiteLLM **:4000** or Ollama on loopback).
2. **`cp -n .env.example .env.local`** and fill **`DIGIKEY_BFF_TOKEN`**, **`AUTH_SECRET`**, service URLs, **`DIGICHAT_DEV_AUTH=1`**, optional **`DIGICHAT_LOCAL_AUTH_KEY`** (see DIGICHAT.md).
3. **`npm install`** then **`npm run dev`** (or **`make digichat-dev`** from repo root).
4. Open **`http://127.0.0.1:3000`**, confirm **`GET /api/health`** is `ok` for all enabled services.
5. Sign in (dev password) or rely on local-bootstrap when **`DIGICHAT_LOCAL_AUTH_KEY`** is set; chat uses digikey **`bff_session`** JWTs so digigraph can call digisearch/digiquant tools with the same auth chain.

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

`/embed` is a **minimal, unauthenticated** chat surface iframed from marketing parents.

### Popup widget (`/widget.js`) — #3421

Bottom-right **dot** or **bar** launcher that opens a floating panel iframes `/embed?layout=embed` (same tenant registry / RAG corpus as full-page).

```html
<script
  src="https://digithings.ai/widget.js"
  data-host="digithings.ai"
  data-mode="dot"
  data-page-context="1"
  async
></script>
```

| Attribute | Purpose |
|-----------|---------|
| `data-host` | Embed tenant registry key (`?host=`) |
| `data-mode` | `dot` (default) or `bar` |
| `data-origin` | digichat origin when the script is not served from digichat |
| `data-token` | Optional tenant embed token |
| `data-theme` / `data-accent` | Optional UI pins |
| `data-page-context` | `1` — after `digichat:ready`, post visible `document.body.innerText` (+ best-effort screenshot) as `digichat:page-context` |

Page context uses only content already visible on the host page (no behind-auth scrape). The embed prepends it to the next user turn once.

### Production marketing path (#266 / CHR-68)

Live digithings.ai chat is **`frontend/digithings-web`** (`app/chat/page.tsx` + `ChatEmbedShell`) → same-origin iframe:

`https://digithings.ai/embed?host=digithings.ai`

Parent `frame-src` and iframe origin both come from `embedOriginForChat()` (default `https://digithings.ai`). Child `/embed` CSP `frame-ancestors` is set at request time by `src/proxy.ts` (matcher `/embed` only) — first-party `'self' https://digithings.ai https://www.digithings.ai https://digiquant.io` plus runtime `DIGICHAT_EMBED_HOSTS` / tenants. Other digichat routes keep `frame-ancestors 'none'` + `X-Frame-Options: DENY`.

Prod tenant (`host=digithings.ai`): `gateMode: ungated`, `llmAccess: free_then_byok`, `showByok: true`. Do **not** assert a 3-turn gate on that path. `turn_limited` remains for other tenants (unit tests lock it).

The deleted `frontend/website/` landing (`#try` iframe) is **not** the marketing surface — do not restore it.

### Embed behavior

- **Route:** `GET /embed?host=<registry-host>&layout=page|embed&theme=…` (plus optional UI query params). Tenant theme/accent come from `DIGICHAT_EMBED_TENANTS`, not a legacy `?accent=` switch alone.
- **Gates:** per-tenant `gateMode` — `ungated` (marketing), `turn_limited` (client-side free-turn quota then BYOK), or `trial_form`.
- **BYOK:** shared `useBYOKKey` hook. `llmAccess: free_then_byok` serves free replies until quota/errors open in-chat BYOK.
- **CSP:** `next.config.ts` bakes fail-closed `frame-ancestors 'none'` on `/embed`; `src/proxy.ts` overwrites with the allowlist at request time. Never emit `*`.
- **Errors:** failed `/api/chat` responses surface in the embed UI with Retry (`formatEmbedChatError`).
- **Analytics:** `src/lib/embed-gate.ts` exports `emit(event, props)` — no-op today.
- **Non-goals:** #260 tokens, #202 SSO, #201 model selector.

**Production embed gate:** `POST /api/chat` returns **503** for embed requests (`X-Embed-Host`) on **unregistered** hosts unless `DIGICHAT_LEGACY_EMBED_ENABLED=1` (or deprecated `DIGICHAT_EMBED_ENABLED=1`) or `X-Embed-Token` matches `DIGICHAT_EMBED_TOKEN`. Registered tenants in `DIGICHAT_EMBED_TENANTS` use their own token, or first-party bypass for `digithings.ai` / `www.digithings.ai` (and `localhost` / `127.0.0.1` in development when registered). Legacy generic embed does **not** default on when tenants are configured.

### Local dogfood against digithings-web

```bash
# Terminal 1 — digichat (embed child)
cd frontend/digichat && npm run dev   # http://127.0.0.1:3000

# Terminal 2 — marketing parent (frontend/digithings-web, not frontend/website)
cd frontend/digithings-web
NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=http://127.0.0.1:3000 npm run dev
# open http://127.0.0.1:<web-port>/chat — ChatEmbedShell iframes /embed?host=digithings.ai
```

Ensure digichat `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_ALLOW_LOCAL_EMBED_PARENTS` admit the parent origin so `/embed` `frame-ancestors` matches. Direct child check: `http://127.0.0.1:3000/embed?host=digithings.ai`.

