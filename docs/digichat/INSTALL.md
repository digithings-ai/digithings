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
docker pull ghcr.io/digithings-ai/digichat:v0.9.3
```

| Artifact | Value |
|---|---|
| Git tag | `digichat-vX.Y.Z` |
| GHCR image | `ghcr.io/digithings-ai/digichat:vX.Y.Z` |
| Changelog | `frontend/digichat/CHANGELOG.md` |
| Current app version | `0.9.3` |

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

v1 honesty: digichat Node always pulls GHCR. digikey / digigraph / digivault still
**build from the monorepo** until those services have GHCR tags. Clone this repo to
run Profile A.

```bash
cp infra/digichat-release/.env.profile-a.example \
   infra/digichat-release/.env.profile-a
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, provider keys

docker compose -f infra/digichat-release/compose.profile-a.yml \
  --env-file infra/digichat-release/.env.profile-a up -d --build
```

Does **not** start digiquant / digisearch / digismith / heartbeat / observability.

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

## Embed CSP note

Stock GHCR bakes `frame-ancestors` from `frontend/digichat/embed-hosts.txt` at image
build time (`DIGICHAT_EMBED_HOSTS`). If your parent site hostname is **not** in that
list, you need a rebuild with your hosts (or a digithings PR adding the hostname —
non-secret). Runtime CSP is a follow-up; see the architecture sketch Follow-ups.

Still set `DIGICHAT_EMBED_TENANTS` at **runtime** with tokens — never as a build-arg.

## Smoke

```bash
docker pull ghcr.io/digithings-ai/digichat:v0.9.3
curl -sf http://127.0.0.1:3005/api/health | jq .
# Embed (clients always pass token):
# open http://127.0.0.1:3005/embed?host=client.example.com&token=…
```

Profile A: expect digigraph tool activity in the embed (not a direct OpenRouter call
from digichat). Profile B: Foundry smoke only when Azure credentials are available.

Operator post-publish checklist: [`RELEASE-SMOKE.md`](RELEASE-SMOKE.md).

## Out of scope (v1)

Corpus / crawl / OCR / vault ingest for client doc chatbots is **not** part of this
install. See Follow-ups in
[`digichat-self-hosted-release.md`](../architecture/digichat-self-hosted-release.md)
and “Later” in
[`digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md) §5.

## Related

- Overlays: [`infra/digichat-release/README.md`](../../infra/digichat-release/README.md)
- digithings operator Tunnel host: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md)
- Local ops: [`frontend/digichat/OPERATIONS.md`](../../frontend/digichat/OPERATIONS.md)
- Product model: [`digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md) §5
