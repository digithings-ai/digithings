# DataTap MCP trial chat — tenant deployment guide

Two variants, one per backend:

- **V1 (Foundry agent, current):** `config/datatap-trial-foundry.yaml` — UI-only
  container on a tenant-local Foundry agent carrying the tenant search index +
  MCP tool (#3861). Deploy this one.
- **V2 (DigiGraph harness):** `config/datatap-trial-test.yaml` — digichat
  driving the DataTap dev MCP server through digigraph operator MCP
  (`X-API-Key` static auth, #3841). Parked follow-up.

This is the **trial** chat, not the website docs chat. The website chat
(`digichat` on `dg-agentic-datatap`, search-only, no MCP) is untouched.

## What you need

- digichat 2.x container image (GHCR `digichat`, or `docker build -f
  cloudflare/digichat/Dockerfile .`).
- A trial tenant resource group with a Container App Environment, e.g.
  `1d0a8149-9387-4574-9d10-e83948e7fcd5` (already has `cae-1d0a8149-…`).
- The tenant's DataTap MCP API key (`mcp+search` scope) for the **dev** MCP
  server (`https://datatap-dev-mcp.azurewebsites.net/`, in `datatap-dev-rg`).
- A Foundry model endpoint. The Trials subscription (`0071922f…`) still has
  no Azure OpenAI access grant, so `dg-agentic-digichat-dev`
  (`digichat-dev-rg`) cannot host a deployment yet — request access via
  `aka.ms/oai/access` first. Until then, point at the existing Website
  subscription deployment:
  - endpoint `https://dg-agentic-datatap.cognitiveservices.azure.com/`
    (`datatap-search-rg`, eastus), deployment `gpt-5-mini`.
- A reachable digigraph + digikey pair (shared dev stack is fine for trials).

## Container environment

| Variable | Value / source |
|---|---|
| `DIGICHAT_CONFIG_PATH` | `config/datatap-trial-test.yaml` (baked into the image) |
| `DATATAP_MCP_TOKEN` | tenant MCP key — Container App **secret**, never baked into the image |
| `DIGIKEY_URL` | `https://key.<shared-stack>` |
| `DIGIKEY_BFF_TOKEN` | same value the shared digikey was issued with (secret) |
| `DIGIGRAPH_INTERNAL_URL` | `https://graph.<shared-stack>` |
| `AUTH_SECRET`, `AUTH_URL` | per standard digichat deploy (`docs/DEPLOYMENT.md` § digichat) |
| `DIGICHAT_DATABASE_URL` | Postgres (persistence is `none` in this config, but sessions still need it) |

## Backend wiring (shared digigraph)

- `DIGI_TENANT_CORPUS_MAP` must map the deployment slug to a
  `researchSystemPrompt`, otherwise the workflow takes the quant-extraction
  path and non-quant questions fail:
  `{"datatap-trial-test":{"researchSystemPrompt":"You are the DataTap trial
  assistant. … use the datatap MCP tools …"}}`.
- Model: route `DIGI_LLM_MODEL` at the sharedstack's LiteLLM proxy to the
  Foundry `gpt-5-mini` deployment (azure provider entry), or set it directly
  once the Trials-subscription Foundry account has a deployment.

## Deploy sketch (Azure CLI)

```bash
TENANT_RG="<trial-tenant-rg>"
CAE="<cae-name-in-tenant-rg>"
az containerapp create \
  --subscription "Datatap Trials" \
  --resource-group "$TENANT_RG" \
  --environment "$CAE" \
  --name digichat-datatap-trial \
  --image <registry>/digichat:<tag> \
  --target-port 3000 --ingress external \
  --env-vars DIGICHAT_CONFIG_PATH=config/datatap-trial-test.yaml \
             DIGIKEY_URL=https://key.<shared-stack> \
             DIGIGRAPH_INTERNAL_URL=https://graph.<shared-stack> \
             AUTH_URL=https://<this-app-fqdn> \
  --secrets datatap-mcp-token="<tenant-mcp-key>" \
            digikey-bff-token="<bff-token>" \
            auth-secret="<auth-secret>"
# then set DATATAP_MCP_TOKEN=secretref:datatap-mcp-token etc. via
# `az containerapp update --set-env-vars` (secretref form).
```

## Verify

1. `GET /api/health` → `{"ok":true,…,"version":"2.0.0"}`.
2. Chat "List my DataTap connections" → a `datatap__list_connections` tool
   row appears, completes while the answer streams, and expands to the
   connections JSON (args pane + Result pane).
3. Unauthenticated `tools/list` on the MCP server shows the base set; the
   keyed container sees the Search tools — scope gating intact.

## Promotion notes

- Replace the Website-subscription Foundry endpoint with a
  Trials-subscription deployment once the access grant lands (one-line model
  change, no rebuild).
- Per-tenant provisioning automation (new MCP connection + agent per trial)
  is DCE-143 Phase 2 scope; this guide is the manual path that automation
  must reproduce.
