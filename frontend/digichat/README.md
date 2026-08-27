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

`/embed` is a **minimal, unauthenticated** chat surface iframed from marketing hosts (`digithings.ai`, `digiquant.io`, and registered customer parents).

**Production path (2026):** the old static `frontend/website/` `#try` iframe is gone. digithings.ai loads digichat via `frontend/digithings-web` at `/chat` → same-origin iframe `https://digithings.ai/embed?host=digithings.ai` (Workers/Containers). Smoke: `curl -sI 'https://digithings.ai/embed?host=digithings.ai'` should be **200** with `content-security-policy: frame-ancestors …`.

- **Route:** `GET /embed?host=<tenant-host>&accent=<digithings|digiquant|digichat>` (accent default `digichat`). `host` selects the tenant registry entry; `accent` only switches CSS `--accent` presets.
- **Free tier (`gateMode: turn_limited`):** first **3 user turns** per embed host, counted client-side in `localStorage` (`digichat_embed_turns:` + host). After the limit, the gate holds the next prompt and shows the paywall / BYOK affordance when `showByok` is enabled. digithings.ai dogfood uses `gateMode: ungated` + `llmAccess: free_then_byok` (operator free quota → in-chat BYOK); the **3-turn client counter** still applies to turn-limited tenants and is covered by unit tests in `embed-gate.test.ts` / `embed-turn-quota.test.ts`.
- **BYOK:** shared `useBYOKKey` hook — a saved key unlocks the client gate immediately; free-quota / rate-limit errors open the in-chat settings panel for `free_then_byok`.
- **CSP:** `next.config.ts` bakes fail-closed `frame-ancestors 'none'` on `/embed`. `src/proxy.ts` overwrites CSP at request time with `embedFrameAncestorsCsp()` — first-party allowlist (`'self'`, `https://digithings.ai`, `https://www.digithings.ai`, `https://digiquant.io`) plus registry / `DIGICHAT_EMBED_HOSTS` parents. Non-`/embed` routes keep `frame-ancestors 'none'` + `X-Frame-Options: DENY`. Never emits `frame-ancestors *`.
- **Errors:** failed `/api/chat` responses surface in the embed UI with Retry (`formatEmbedChatError`).
- **Analytics:** `src/lib/embed-gate.ts` exports `emit(event, props)` — no-op today.

**Production embed gate:** `POST /api/chat` returns **503** for embed requests (`X-Embed-Host`) on **unregistered** hosts unless `DIGICHAT_LEGACY_EMBED_ENABLED=1` (or deprecated `DIGICHAT_EMBED_ENABLED=1`) or `X-Embed-Token` matches `DIGICHAT_EMBED_TOKEN`. Registered tenants in `DIGICHAT_EMBED_TENANTS` use their own token, or first-party bypass for `digithings.ai` / `www.digithings.ai` (and `localhost` / `127.0.0.1` in development when registered). Legacy generic embed does **not** default on when tenants are configured.

### Local two-server recipe (CHR-68 / #266)

`frontend/website/` no longer exists — use the fixture parent under `fixtures/embed-parent/`:

```bash
# Terminal 1 — digichat (from repo root). Pick ONE admit path:
# A) loopback tenant (recommended for turn-limited + BYOK):
export DIGICHAT_EMBED_TENANTS='{"127.0.0.1":{"slug":"local","gateMode":"turn_limited","showByok":true,"layout":"embed","llmAccess":"free_then_byok","token":"dev","backend":{"type":"digigraph"}}}'
# B) or legacy generic admit for unregistered hosts:
# export DIGICHAT_LEGACY_EMBED_ENABLED=1
npm run dev --workspace digichat
# → http://127.0.0.1:3000/embed?host=127.0.0.1&accent=digithings

# Terminal 2 — static parent (frame-ancestors allow http://127.0.0.1:* in non-production)
cd frontend/digichat/fixtures/embed-parent
python3 -m http.server 8765
# → open http://127.0.0.1:8765/  (section #try iframes digichat)
```

Watch the browser console for CSP / blocked-frame errors. Chat replies need a reachable digigraph stack (`make stack-local` + `.env.local` / BYOK key) — the iframe itself must render without that.

