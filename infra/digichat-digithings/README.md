# Digithings DigiChat (Phase 3) — Azure install

Digithings-owned DigiChat runtime for `https://chat.digithings.ai` (iframe
target for `digithings.ai/chat`). Separate from DataTap’s ACA (`jollygrass` /
`datatap-rg`).

## Live resources (DataTap WebSite subscription)

| Resource | Name | Notes |
|---|---|---|
| Resource group | `digithings-rg` | eastus2 |
| Container Apps env | `digithings-cae` | default domain `*.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io` |
| ACR | `digithingschatregistry` | `digithingschatregistry.azurecr.io` |
| Container App | `digichat` | image `digichat:phase3-preview` (Phase 3 branch build) |

**Interim URL (until DNS):**
`https://digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io`

## Image policy

- **Prod target:** same GHCR release tags DataTap uses (`ghcr.io/digithings-ai/digichat:vX.Y.Z`), mirrored into this ACR when needed.
- **Phase 3 bootstrap:** ACR was built from `task/1866-digichat-phase3-unification` as `phase3-preview` because GHCR `v0.5.0` predates Phase 2 digivault + Phase 3 first-party/UI flags.
- After #1868 merges and a digichat release is published on `main`, switch the ACA to that tag and drop `phase3-preview`.

Rebuild preview from a clean tree (avoid `.git` IPC sockets):

```bash
./infra/digichat-digithings/build-image.sh
```

Mirror a published GHCR tag:

```bash
./infra/digichat-digithings/import-ghcr.sh v0.6.0   # example
```

## Runtime env (secret refs on the ACA)

| Env var | Source |
|---|---|
| `AUTH_SECRET` | ACA secret `auth-secret` |
| `AUTH_URL` | Public origin (`https://chat.digithings.ai` once DNS is live; interim = ACA FQDN) |
| `DIGICHAT_EMBED_ENABLED` | `1` |
| `DIGICHAT_EMBED_TENANTS` | ACA secret `embed-tenants` (JSON; tokens only for schema / customers) |
| `DIGITHINGS_SUPABASE_URL` | ACA secret (core Supabase project URL) |
| `DIGITHINGS_SUPABASE_ANON_KEY` | ACA secret (anon / publishable key) |
| `DIGITHINGS_OPENROUTER_API_KEY` | ACA secret |

Tenant fragment (values are **env name refs**, not secret values):

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
    "token": "<schema-required; unused for first-party>",
    "backend": {
      "type": "digivault",
      "supabaseUrlEnv": "DIGITHINGS_SUPABASE_URL",
      "supabaseAnonKeyEnv": "DIGITHINGS_SUPABASE_ANON_KEY",
      "openRouterKeyEnv": "DIGITHINGS_OPENROUTER_API_KEY"
    }
  }
}
```

`DIGICHAT_EMBED_HOSTS` is a **build-arg** (CSP `frame-ancestors`). Digithings hosts
are also hardcoded as first-party in `security-headers.ts` / `embed-first-party.ts`.

## DNS (human — Cloudflare)

Zone `digithings.ai` (NS: Cloudflare). Create:

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `chat` | `digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io` | DNS-only (grey) while binding ACA cert, then orange optional |

Then bind the hostname on the ACA and refresh `AUTH_URL`:

```bash
az containerapp hostname add -n digichat -g digithings-rg --hostname chat.digithings.ai
# complete TXT / certificate validation as prompted
az containerapp update -n digichat -g digithings-rg \
  --set-env-vars "AUTH_URL=https://chat.digithings.ai"
```

## Smoke

```bash
FQDN=digichat.agreeablepebble-8440dc16.eastus2.azurecontainerapps.io
# after DNS: FQDN=chat.digithings.ai

curl -sS -o /dev/null -w '%{http_code}\n' "https://$FQDN/embed"
curl -sS -H 'X-Embed-Host: https://digithings.ai' "https://$FQDN/api/embed/tenant-config"
```

Expect `/embed` **200** and tenant-config JSON with
`gateMode=ungated`, `showByok=true`, `showStatusBar=true`, `layout=page`.

## Apply / rotate secrets

```bash
./infra/digichat-digithings/apply-secrets.sh
```

Requires env: `AUTH_SECRET`, `DIGITHINGS_SUPABASE_URL`,
`DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY`, and optionally
`DIGICHAT_EMBED_TOKEN` (generated if unset).
