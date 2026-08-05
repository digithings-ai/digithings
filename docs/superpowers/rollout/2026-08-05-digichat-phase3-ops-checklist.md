# DigiChat Phase 3 — digithings ops checklist

## Hostname / hosting direction (updated)

- Visitor-facing chat remains `digithings.ai/chat` (Pages shell + embed config).
- **Product direction (owner):** DigiChat should be hosted as a **path on the DigiThings website**, then `/chat` embeds that path with config — **not** a separate DigiThings DigiChat ACA under DataTap Azure, and **pause** standing up `chat.digithings.ai` ACA until DigiThings-owned hosting is decided.
- digithings.ai `/chat` stays on Cloudflare Pages (shell + iframe / path embed).

## Hard constraint — Azure ownership

**DigiThings DigiChat MUST NOT run in any DataTap Azure subscription.**

- Forbidden: **DataTap WebSite** `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0` (and any other DataTap sub).
- DataTap is a **client**. DigiThings may only touch DataTap Azure for DataTap’s own website DigiChat ACA.
- **2026-08-05 misdeploy (torn down):** `digithings-rg` containing `digithings-cae`, `digithingschatregistry`, `digichat` ACA, and Log Analytics workspace was created on DataTap WebSite by mistake. That entire resource group was deleted. Do **not** recreate DigiThings stack there.
- Do **not** create replacement DigiThings DigiChat Azure resources until DigiThings-owned subscription / website-path hosting is available.

## Image (when DigiThings-owned runtime exists)

- Same DigiChat GHCR release family DataTap uses: `ghcr.io/digithings-ai/digichat:<tag>`
- GHCR `v0.5.0` predates Phase 2 digivault + Phase 3 flags — need a newer digichat release after #1868 (or equivalent) for digivault embed.
- ACR mirror helpers under `infra/digichat-digithings/` are DigiThings-sub only; they must refuse DataTap accounts.

## Runtime env (names must match tenant JSON)

- `DIGITHINGS_SUPABASE_URL`, `DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY`
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

- Embed origin env (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`) must point at the **DigiThings-owned** DigiChat origin once hosting is decided (website path or DigiThings Azure — **not** DataTap ACA). Pause assuming `https://chat.digithings.ai` until that decision lands.

## Ops remaining

1. DigiThings-owned hosting decision: website path vs DigiThings Azure (not DataTap).
2. Provision DigiChat only on DigiThings-owned infra; set digivault env + tenant registry.
3. Wire digithings-web `/chat` embed origin to that DigiThings origin.
4. Smoke: landing quick-ask → `/chat` seeded turn; BYOK + status bar.

## Merge gate for #1868

- Do **not** merge for zero-downtime until DigiThings-owned DigiChat origin exists for the iframe/path embed.
- ACA-on-DataTap was a mistake and has been removed — it is not a merge blocker beyond correcting docs.
