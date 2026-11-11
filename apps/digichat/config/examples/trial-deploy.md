# Trial chat — tenant deployment example

Two variants, one per backend. Names below are placeholders. Copy them per
tenant; do not commit a live resource id, hostname, or key.

- **V1 (Foundry agent, current):** a UI-only container on a tenant-local
  Foundry agent that carries the tenant search index and MCP tool. Deploy
  this one.
- **V2 (digigraph harness):** digichat driving the tenant dev MCP server
  through digigraph operator MCP (`X-API-Key` static auth). Parked follow-up.

This is the **trial** chat, not the website docs chat. The website chat is
untouched.

## What you need

- digichat 2.x container image (GHCR `digichat`, or `docker build -f
  apps/digichat/Dockerfile .`).
- A trial tenant resource group with a Container App Environment, e.g.
  `00000000-0000-0000-0000-000000000000` (already has a matching environment).
- The tenant MCP API key (`mcp+search` scope) for the **dev** MCP server
  (`https://example-dev-mcp.azurewebsites.net/`, in `example-dev-rg`).
- A Foundry model endpoint. The example subscription
  (`00000000-0000-0000-0000-000000000001`) may have no model access grant yet,
  so the shared dev resource group cannot host a deployment until access is
  granted. Until then, point at an existing deployment:
  - endpoint `https://example.cognitiveservices.azure.com/`
    (`example-search-rg`), deployment `gpt-5-mini`.
- A reachable digigraph + digikey pair (a shared dev stack is fine for trials).

## Container environment (V1 — Foundry agent)

| Variable | Value / source |
|---|---|
| `DIGICHAT_CONFIG_PATH` | per-trial rendered yaml (template in `config/`, copied per trial with that tenant's `projectEndpoint` + `agentName`) |
| `AUTH_SECRET`, `AUTH_URL` | per standard digichat deploy; `AUTH_TRUST_HOST=true` alongside them |
| `DIGICHAT_EMBED_TOKEN` | the tenant's embed token, as a **secret** (`secretref:`), never baked into the image |
| `AZURE_CLIENT_ID` | the **user-assigned** managed identity's client id, when the app uses one |
| `DIGICHAT_DATABASE_URL` | Postgres (persistence may be `none` in this config, but sessions still need it) |

`DIGICHAT_ENABLED_SERVICES` is **not** needed for V1. The warm-up gate reads
the deployment's backend and skips digigraph when the install does not use it.

No MCP token and no digikey/digigraph URLs on V1: the container talks to the
tenant's Foundry agent via its managed identity (`DefaultAzureCredential`),
and the agent carries the search index and MCP tool server-side.

## Backend wiring (V1)

- Foundry project and model deployment in the tenant resource group.
- The agent carries the tenant search index and the dev MCP server (MCP tool,
  custom-keys connection, tenant key).
- Reasoning summary **enabled** on the agent definition, otherwise thinking
  rows stay dropped by design.
- `guardrails` inherits the stability cap from defaults: `maxToolCallsPerTurn: 20`,
  `answerAt: 0.7`, `pauseAt: 0.9`.
- The agent's search tool needs a project connection that can **read the index
  definition**, not just query it. Use the search service's **admin** key,
  held in a secret store, never in the agent definition.

## Deploy sketch — V1

```bash
TENANT_RG="00000000-0000-0000-0000-000000000000"
CAE="<cae-name-in-tenant-rg>"
az containerapp create \
  --subscription "Example Subscription" \
  --resource-group "$TENANT_RG" \
  --environment "$CAE" \
  --name digichat-trial \
  --image example.azurecr.io/digichat:<tag> \
  --target-port 3000 --ingress external \
  --env-vars DIGICHAT_CONFIG_PATH=config/trial-foundry.yaml \
             AUTH_URL=https://<this-app-fqdn> \
             AUTH_TRUST_HOST=true
```

## Deploy sketch — V2 (parked)

```bash
TENANT_RG="<trial-tenant-rg>"
CAE="<cae-name-in-tenant-rg>"
az containerapp create \
  --subscription "Example Subscription" \
  --resource-group "$TENANT_RG" \
  --environment "$CAE" \
  --name digichat-trial \
  --image example.azurecr.io/digichat:<tag> \
  --target-port 3000 --ingress external \
  --env-vars DIGICHAT_CONFIG_PATH=config/trial-harness.yaml \
             DIGIKEY_URL=https://key.<shared-stack> \
             DIGIGRAPH_INTERNAL_URL=https://graph.<shared-stack> \
             AUTH_URL=https://<this-app-fqdn> \
  --secrets mcp-token="<tenant-mcp-key>" \
            digikey-bff-token="<bff-token>" \
            auth-secret="<auth-secret>"
```

## Verify

1. `GET /api/health` → `{"ok":true,…,"version":"<DIGICHAT_VERSION>"}`.
   `version` is `DIGICHAT_VERSION` when that env is set and non-empty, otherwise
   `apps/digichat/package.json` `version` (`resolveDigichatVersion()`).
2. A chat turn that lists connections shows the tenant tool row, completes
   while the answer streams, and expands to the connections JSON.
3. Unauthenticated `tools/list` on the MCP server shows the base set; the
   keyed container sees the search tools.

## Secret custody and rotation

Two independent credentials back this chat, both held as inline Azure Container
App secrets on `digichat-trial` (resource group
`00000000-0000-0000-0000-000000000000`, subscription `Example Subscription`):

| Container App secret | Bound env var | What it gates |
|---|---|---|
| `embed-token` | `DIGICHAT_EMBED_TOKEN` | the single-install `/api/chat` gate |
| `auth-secret` | `AUTH_SECRET` | this app's Auth.js session secret |

- **Readback** is `az containerapp secret list --show-values` for a principal
  holding `Microsoft.App/containerApps/listSecrets/action`. See
  `docs/ops/credential-ownership.md`.
- **Custody stays in the tenant Azure account.** No copy is held in this repo.
- **Rotation blast radius.** `embed-token`: without a matching
  `DIGICHAT_EMBED_TOKEN` the single-install path refuses every `/api/chat`.
  `auth-secret`: every session on the app is invalidated.
- **Handing a value to the tenant stays a human act.** The Azure write is a
  human step.
- **No recorded fingerprint** for this pair lives in the example lock. The
  sibling detector is `scripts/digichat_aca_secret_detector.py`. A private lock
  is selected with `DIGICHAT_ACA_SECRET_FINGERPRINTS`.
