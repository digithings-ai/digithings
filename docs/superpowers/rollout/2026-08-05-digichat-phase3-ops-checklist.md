# DigiChat Phase 3 — digithings ops checklist

## Hostname / hosting (locked)

- **Visitor chat:** `digithings.ai/chat` — Pages shell (`DtNav` + iframe).
- **DigiChat surface:** `digithings.ai/embed` — Cloudflare route → DigiThings-owned DigiChat Node.
- **Embed origin env:** `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai` (same-origin; `frame-src 'self'`).
- **Leave `DIGICHAT_BASE_PATH` unset** (DigiChat at root behind the path route).
- Do **not** use `chat.digithings.ai` as the marketing embed origin.

## Hard constraint — Azure ownership

**DigiThings DigiChat MUST NOT run in any DataTap Azure subscription.**

- Forbidden: **DataTap WebSite** `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0` (and any other DataTap sub).
- DataTap is a **client**. DigiThings may only touch DataTap Azure for DataTap’s own website DigiChat ACA.
- **2026-08-05 misdeploy (torn down):** `digithings-rg` (CAE / ACR / digichat ACA) was created on DataTap WebSite by mistake and deleted. Do **not** recreate DigiThings stack there.

## DigiThings-owned DigiChat Node

1. Provision ACA (+ ACR if needed) in a **DigiThings** Azure subscription only (`az account show` must not be DataTap*).
2. Image: `ghcr.io/digithings-ai/digichat:<tag>` (post–Phase 2 digivault + Phase 3 flags; release after #1868 or build from this branch).
3. Env: digivault name refs + tenant registry below; `DIGICHAT_EMBED_HOSTS` at **build** includes digithings.ai / www.
4. Cloudflare: route `digithings.ai/embed*` (and DigiChat `/api` / `/_next` paths the embed needs) → that ACA origin.
5. Pages: set `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`.

## Runtime env (names must match tenant JSON)

- `DIGITHINGS_SUPABASE_URL`, `DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY`
- `DIGICHAT_EMBED_TENANTS` includes digithings entry below
- `DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,...` at **build** for CSP
- Do **not** put vault/OpenRouter secret **values** in tenant JSON

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
# Browser: landing quick-ask → /chat seeded turn; BYOK + status bar
```

## Merge gate for #1868

- Do **not** merge the CF Function delete cutover until `https://digithings.ai/embed` returns 200 from DigiThings-owned DigiChat.
- Code/docs origin retarget (`chat.` → same-origin `/embed`) can land on the PR branch anytime.
