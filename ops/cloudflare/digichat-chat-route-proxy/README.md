# digichat `/chat` route proxy (Cloudflare Worker)

This worker path-routes `https://digithings.ai/chat*` to a separately hosted
DigiChat origin while keeping the public URL at `digithings.ai/chat`.

## Why this exists

`frontend/digichat` is a stateful Next.js server app (Auth.js + DB + streaming),
so it cannot run directly on the static Cloudflare Pages site that serves
`digithings.ai`. ADR-0018 already decided the public path should be `/chat`; this
worker is the concrete route layer for that decision.

## Prerequisites

1. A running DigiChat origin (container host), for example:
   `https://chat-origin.example.com`
2. DigiChat configured for path serving:
   - `DIGICHAT_BASE_PATH=/chat`
   - `NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat`
   - `AUTH_URL=https://digithings.ai/chat`
3. Wrangler authenticated to the digithings Cloudflare account.

## Deploy

From this directory:

```bash
npx wrangler secret put DIGICHAT_ORIGIN
npx wrangler deploy --env prod
```

Use the worker secret value for `DIGICHAT_ORIGIN`, e.g.
`https://chat-origin.example.com`.

## Verify

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat/embed
```

Expected: `200` or `307` for `/chat` (redirect to `/chat/login` is valid),
and `200` for `/chat/embed` once DigiChat is up.
