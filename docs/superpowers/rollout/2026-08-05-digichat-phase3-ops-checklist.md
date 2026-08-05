# DigiChat Phase 3 — digithings ops checklist

## Hostname
- Public digichat origin: `https://chat.digithings.ai`
- DNS: CNAME `chat` → digithings-owned Azure Container App hostname
- digithings.ai `/chat` stays on Cloudflare Pages (shell + iframe)

## Image
- Pull same DigiChat GHCR release DataTap uses: `ghcr.io/digithings-ai/digichat:<tag>`
- If this install pulls via ACR: after each digichat release run
  `./infra/digichat-digithings/import-ghcr.sh vX.Y.Z` (not automated in Phase 3)
- **Bootstrap (2026-08-05):** GHCR `v0.5.0` predates Phase 2 digivault + Phase 3 flags.
  Digithings ACR currently serves `digichat:phase3-preview` built from
  `task/1866-digichat-phase3-unification` via `./infra/digichat-digithings/build-image.sh`.
  After #1868 merges and a digichat release is cut on `main`, switch ACA to that tag.

## Runtime env (names must match tenant JSON)
- `DIGITHINGS_SUPABASE_URL`, `DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY`
- `DIGICHAT_EMBED_TENANTS` includes digithings entry below
- `DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,...` at **build** for CSP
- Do **not** put tenant `token` values in Docker build-args
- Rotate with `./infra/digichat-digithings/apply-secrets.sh` (reads env; never prints secrets)

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

## Provisioned (2026-08-05, DataTap WebSite subscription)

| Resource | Name |
|---|---|
| RG | `digithings-rg` (eastus2) |
| CAE | `digithings-cae` |
| ACR | `digithingschatregistry` |
| ACA | `digichat` |

- **Interim URL (TLS live):**
  `https://digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io`
- Smoke (verified): `/embed` → 200; `GET /api/embed/tenant-config` with
  `X-Embed-Host: https://digithings.ai` → 200
  (`gateMode=ungated`, `showByok=true`, `showStatusBar=true`, `layout=page`);
  CSP `frame-ancestors` includes digithings.ai / www.
- Digivault secrets are ACA secret refs (not embedded in tenant JSON values).
- Docs/scripts: `infra/digichat-digithings/`

## Ops remaining (human — Cloudflare DNS + hostname bind)

`chat.digithings.ai` does **not** resolve yet (no CF API token / wrangler auth for DNS on this machine).

1. In Cloudflare DNS for `digithings.ai`, add (**DNS only / grey cloud** until ACA cert binds):

   | Type | Name | Content |
   |---|---|---|
   | TXT | `asuid.chat` | `3D78E96D5F0BC83AAC23C568E61CBF1C59F7B7368FF8B9D3276C04A6533E2CA8` |
   | CNAME | `chat` | `digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io` |

2. Bind + managed cert:

   ```bash
   az containerapp hostname add -n digichat -g digithings-rg --hostname chat.digithings.ai
   az containerapp update -n digichat -g digithings-rg \
     --set-env-vars "AUTH_URL=https://chat.digithings.ai"
   ```

3. Cloudflare Pages (digithings-ai project): set production
   `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://chat.digithings.ai` (or rebuild after #1868 lands on `main`).

4. After digichat release on `main`: `./infra/digichat-digithings/import-ghcr.sh vX.Y.Z` and point ACA at that tag (retire `phase3-preview`).

5. Smoke prod: landing quick-ask → `/chat` iframe → seeded turn; BYOK + status bar visible.

## Merge gate for #1868

- **Code PR:** can merge once reviewers are happy — iframe origin defaults to
  `https://chat.digithings.ai`; until DNS step 1–2 complete, prod `/chat` iframe will fail to load.
- **Safe to merge for code:** yes, if you accept interim downtime on marketing chat
  until DNS binds (rollback = revert PR restores CF Function path).
- **Safe for zero-downtime cutover:** **no** — finish DNS + hostname + Pages env first,
  then merge (or merge and immediately complete DNS).
