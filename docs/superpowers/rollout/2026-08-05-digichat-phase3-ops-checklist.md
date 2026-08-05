# DigiChat Phase 3 — digithings ops checklist

## Hostname
- Public digichat origin: `https://chat.digithings.ai`
- DNS: CNAME `chat` → digithings-owned Azure Container App (or equivalent) hostname
- digithings.ai `/chat` stays on Cloudflare Pages (shell + iframe)

## Image
- Pull same DigiChat GHCR release DataTap uses: `ghcr.io/digithings-ai/digichat:<tag>`
- If this install pulls via ACR: after each digichat release run manual `az acr import` (not automated in Phase 3)

## Runtime env (names must match tenant JSON)
- `DIGITHINGS_SUPABASE_URL`, `DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY` (or chosen names)
- `DIGICHAT_EMBED_TENANTS` includes digithings entry below
- `DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,...` at **build** for CSP
- Do **not** put tenant `token` values in Docker build-args

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

## digithings-web build
- `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://chat.digithings.ai`

## Ops remaining (cannot be done from this repo alone)
- [ ] Create/point digithings-owned ACA (or equivalent) at GHCR digichat image
- [ ] DNS CNAME `chat.digithings.ai` → that install
- [ ] Set digivault env vars + `DIGICHAT_EMBED_TENANTS` / `DIGICHAT_EMBED_HOSTS` on the install
- [ ] Manual GHCR→ACR mirror if the install pulls from ACR
- [ ] Smoke: landing quick-ask → `/chat` iframe → seeded turn; BYOK + status bar visible
