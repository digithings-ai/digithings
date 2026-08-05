# DigiChat Phase 3 — digithings ops checklist

## Hostname / hosting (locked)

- **Visitor chat:** `digithings.ai/chat` — Pages shell (`DtNav` + iframe).
- **DigiChat surface:** `digithings.ai/embed` — **Cloudflare Containers** + Worker routes (DigiThings CF account).
- **Embed origin:** `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai` (same-origin; `frame-src 'self'`).
- DigiChat build: `DIGICHAT_ASSET_PREFIX=/_dtchat` (avoids Pages `/_next` collision); leave `DIGICHAT_BASE_PATH` unset.
- DigiThings has **no Azure**. Do **not** use DataTap’s DigiChat ACA for DigiThings. Do **not** use `chat.digithings.ai` as marketing embed origin.

## Hard constraint — Azure

**DigiThings DigiChat MUST NOT run in any Azure subscription** (DigiThings is not on Azure).

- DataTap’s DigiChat ACA is **client-only** (DataTap website). Leave it alone.
- **2026-08-05 misdeploy:** DigiThings resources on DataTap WebSite were torn down. Do not recreate.

## DigiThings DigiChat = Cloudflare Containers

Scaffold: [`frontend/digichat-cloudflare/`](../../../frontend/digichat-cloudflare/README.md)

1. `npx wrangler login` on DigiThings Cloudflare account (zone digithings.ai).
2. Put secrets: `AUTH_SECRET` (stub), `DIGITHINGS_SUPABASE_*`, `DIGITHINGS_OPENROUTER_API_KEY`, `DIGICHAT_EMBED_TENANTS`.
3. From `frontend/digichat-cloudflare`: `npx wrangler deploy` (builds [`Dockerfile.digichat-cloudflare`](../../../Dockerfile.digichat-cloudflare)).
4. Attach zone routes: `/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`, `/_dtchat*`.
5. Pages env: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`.

### Embed-only runtime

- Omit `DIGICHAT_DATABASE_URL` / `DIGICHAT_AUTO_MIGRATE` (no Postgres).
- `DIGICHAT_ENABLED_SERVICES=` empty; no DigiKey/Foundry/Azure env.
- Prefer `DIGICHAT_EMBED_ENABLED=1` plus digithings tenant + first-party hosts.

## Tenant JSON fragment
```json
{
  "digithings.ai": {
    "slug": "digithings",
    "aliases": ["www.digithings.ai"],
    "gateMode": "ungated",
    "showByok": true,
    "showStatusBar": true,
    "layout": "page",
    "activityDetail": "full",
    "attribution": false,
    "token": "<schema-required; unused for first-party requests>",
    "backend": {
      "type": "digivault",
      "supabaseUrlEnv": "DIGITHINGS_SUPABASE_URL",
      "supabaseAnonKeyEnv": "DIGITHINGS_SUPABASE_ANON_KEY",
      "openRouterKeyEnv": "DIGITHINGS_OPENROUTER_API_KEY"
    }
  }
}
```

## Smoke

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/embed
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
```

## Merge gate for #1868

Do **not** merge the CF Function delete until `https://digithings.ai/embed` returns 200 from the DigiThings Cloudflare Container.
