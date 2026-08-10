# digichat self-hosted install

Client / operator guide: pull a pinned digichat image, choose a backend profile, set
env, smoke. Digi module names are always lowercase in prose.

## Product model

digithings ships **self-hosted AI infra**. Clients install digichat **releases from
GitHub** and run them in **their** cloud or on-prem. There is **no** live shared
digichat SaaS for clients.

`digithings.ai/chat` is digithings’ **own** install of the same product (Pages shell
+ iframe → digichat Node via Tunnel → digigraph). It is not a multi-tenant host for
other companies.

Same pattern as DataTap: client-hosted digichat Node + **their** backend (Foundry
**or** digigraph stack).

**Hard rule:** scale by shipping a clean release + adapters + configurable
digigraph/digivault modules. Custom work is env, secrets, and ingest — not a second
chat app.

## Install unit

Primary install unit: a **pinned GHCR image** — not npm (`private: true`), not
`:latest` in production.

```bash
docker pull ghcr.io/digithings-ai/digichat:v1.0.0
```

| Artifact | Value |
|---|---|
| Git tag | `digichat-vX.Y.Z` |
| GHCR image | `ghcr.io/digithings-ai/digichat:vX.Y.Z` |
| Changelog | `frontend/digichat/CHANGELOG.md` |
| Current app version | `1.0.0` |

**Existing clients (DataTap and others) stay on `v0.9.3`.** That GHCR tag remains
published and is not deleted — only new installs / digithings’ own cut should move
to `v1.0.0` until those clients choose to upgrade.

Compose overlays and env templates live under
[`infra/digichat-release/`](../../infra/digichat-release/).

## Choose a profile

| Profile | Backend | Minimum services |
|---|---|---|
| **A** | digigraph → digillm → LiteLLM (+ digivault tools) | digichat + db + digikey + digigraph + LiteLLM + digivault |
| **B** | Azure AI Foundry (`DefaultAzureCredential`) | digichat + db only |

Adapters only: `digigraph` \| `foundry`. digigraph owns digillm→LiteLLM and digivault.

### Profile A — digigraph stack

```text
Browser → digichat → digigraph → digillm/LiteLLM
                           └─ digivault_hub → digivault
```

Pull **all** Profile A services from GHCR (digichat + digikey + digigraph + digivault).
LiteLLM uses the public berriai image. Pin stack and digichat tags separately:

| Variable | Example | Services |
|---|---|---|
| `DIGICHAT_VERSION` | `1.0.0` | digichat → `…/digichat:v1.0.0` |
| `DIGI_IMAGE_TAG` | `sha-<12>` or `v0.1.0` | digikey, digigraph, digivault |

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, DIGI_IMAGE_TAG, provider keys

make digichat-profile-a-up
# or:
docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a up -d
```

Does **not** start digiquant / digisearch / digismith / heartbeat / observability.

**Local / digithings website parity:** one supervisord image (same as Cloudflare
Containers) instead of N GHCR services — `make digichat-profile-a-bundle-up`
([`compose.profile-a-bundle.yml`](../../infra/digichat-release/compose.profile-a-bundle.yml)).
Clients who want per-service pins keep multi-image Profile A above.

Config for LiteLLM / digigraph is vendored under
[`infra/digichat-release/config/`](../../infra/digichat-release/config/) (no monorepo
`config/` clone required). Stack GHCR packages appear after
`publish-service-images.yml` runs on `main` (promote #2023, then first publish).

Full monorepo stack (all Python services) alternative:
[`docs/templates/self-host/README.md`](../templates/self-host/README.md)
(`make up-ghcr` + `--profile digivault --profile digichat`).

digithings’ own Tunnel operator path (not the client default):
[`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

### Profile B — Foundry (client Azure only)

digithings has **no Azure**. This path is for client environments (DataTap-like).

```text
Browser → digichat → Foundry (managed identity on the host)
```

```bash
cp infra/digichat-release/.env.profile-b.example \
   infra/digichat-release/.env.profile-b
# edit AUTH_SECRET, AUTH_URL, DIGICHAT_EMBED_TENANTS (foundry backend)

docker compose -f infra/digichat-release/compose.profile-b.yml \
  --env-file infra/digichat-release/.env.profile-b up -d
```

Host must supply Azure identity for Foundry calls. Do **not** put a Foundry API key
in digichat env.

## Env checklist

Full schema: [`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md).
Product sketch: [`digichat-self-hosted-release.md`](../architecture/digichat-self-hosted-release.md) §3.

### Always (both profiles)

| Variable | Purpose |
|---|---|
| `AUTH_SECRET` / `AUTH_URL` / `AUTH_TRUST_HOST` | Auth.js |
| `DIGICHAT_DATABASE_URL` | Postgres (Compose wires digichat-db) |
| `DIGICHAT_AUTO_MIGRATE=1` | Apply Drizzle migrations on start |
| `DIGICHAT_EMBED_ENABLED` | Enable `/embed` as needed |
| `DIGICHAT_REQUIRE_ROOT_AUTH` | Default **unset/`0`** (Option A): `/` redirects to `/embed` — no Auth.js login wall. Set `1` only if the client wants a root session gate. Dogfood digithings.ai stays OFF. |
| `DIGICHAT_EMBED_HOSTS` | **Runtime** comma-separated parent hostnames for CSP `frame-ancestors` (no secrets). Optional if hosts are already `DIGICHAT_EMBED_TENANTS` keys. |
| `DIGICHAT_EMBED_TENANTS` | **Runtime** JSON registry (hostname → branding, gate, token, `backend`). **Never** a Docker build-arg — tokens leak in layers. |

Illustrative registry (Profile A):

```json
{
  "client.example.com": {
    "slug": "client",
    "gateMode": "token",
    "activityDetail": "full",
    "layout": "page",
    "token": "<required-secret>",
    "backend": { "type": "digigraph" }
  }
}
```

Foundry tenant: `"backend": { "type": "foundry", "projectEndpoint": "https://…", "agentName": "…" }`.

Customer embeds always need a matching `token`. First-party digithings hosts
(`digithings.ai` / `www.digithings.ai`) may skip token when registered.

### Profile A only

| Variable | Purpose |
|---|---|
| `DIGICHAT_VERSION` | digichat GHCR tag (`v${DIGICHAT_VERSION}`) |
| `DIGI_IMAGE_TAG` | digikey / digigraph / digivault GHCR tag (`sha-…` or `v0.1.0`) |
| `DIGIGRAPH_INTERNAL_URL` | digigraph base |
| `DIGIKEY_URL` + `DIGIKEY_BFF_TOKEN` | Preferred upstream auth |
| On digigraph: `DIGIVAULT_URL`, LiteLLM / digillm provider keys | Vault tool + LLM path |

### Profile B only

| Surface | Purpose |
|---|---|
| Tenant `backend.type: foundry` + endpoint / agent | In `DIGICHAT_EMBED_TENANTS` |
| Host Azure identity | Foundry via `DefaultAzureCredential` |

### Parent site (marketing / product shell)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` | Iframe origin (e.g. Tunnel hostname) |
| Embed URL | `/embed?host=<parent-host>&token=…` |

## Custom embed parent hosts (CSP)

Stock GHCR digichat sets `/embed` `frame-ancestors` at **runtime** from:

1. `DIGICHAT_EMBED_HOSTS` — comma-separated parent hostnames (no secrets), and/or
2. Host keys (and aliases) in `DIGICHAT_EMBED_TENANTS` when `DIGICHAT_EMBED_HOSTS` is unset.

Example (Compose / ACA env):

```bash
DIGICHAT_EMBED_HOSTS=client.example.com,www.client.example.com
# still required for tokens / backend — never a build-arg:
DIGICHAT_EMBED_TENANTS={"client.example.com":{...}}
```

Security: digichat never emits `frame-ancestors *`. If neither source yields hosts,
only first-party digithings origins (plus `'self'`) remain allowlisted.

Optional seed list of known hosts: `frontend/digichat/embed-hosts.txt` (not baked into the image).

## Smoke

```bash
docker pull ghcr.io/digithings-ai/digichat:v1.0.0
curl -sf http://127.0.0.1:3005/api/health | jq .
# Embed (clients always pass token):
# open http://127.0.0.1:3005/embed?host=client.example.com&token=…
```

Profile A: expect digigraph tool activity in the embed (not a direct OpenRouter call
from digichat). Profile B: Foundry smoke only when Azure credentials are available.

Operator post-publish checklist: [`RELEASE-SMOKE.md`](RELEASE-SMOKE.md).

## Populate client docs

Client documentation chatbots use an **offline ops pipeline** (not this install
unit and not a digichat fork): `scripts/docs_onboard/` crawls a docs site and
writes digivault notes and/or a digisearch index for Profile A grounding.

- Runbook: [`CLIENT-DOCS-ONBOARD.md`](CLIENT-DOCS-ONBOARD.md)
- Ops index: [`docs/ops/CLIENT_PIPELINES.md`](../ops/CLIENT_PIPELINES.md)

OCR stays in digisearch. Pick 1 (runtime CSP) and Pick 2 (GHCR Profile A) are
orthogonal — see
[`digichat-self-host-picks-fit.md`](../architecture/digichat-self-host-picks-fit.md).

## Related

- Overlays: [`infra/digichat-release/README.md`](../../infra/digichat-release/README.md)
- digithings operator Tunnel host: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md)
- Local ops: [`frontend/digichat/OPERATIONS.md`](../../frontend/digichat/OPERATIONS.md)
- Product model: [`digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md) §5
- Docs onboard: [`CLIENT-DOCS-ONBOARD.md`](CLIENT-DOCS-ONBOARD.md)
