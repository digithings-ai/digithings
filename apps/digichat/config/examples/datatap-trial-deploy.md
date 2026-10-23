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
  apps/digichat/Dockerfile .`).
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

## Container environment (V1 — Foundry agent)

| Variable | Value / source |
|---|---|
| `DIGICHAT_CONFIG_PATH` | per-trial rendered yaml, e.g. `config/datatap-trial-foundry.yaml` (template in `config/`, copied per trial with that tenant's `projectEndpoint` + `agentName`) |
| `AUTH_SECRET`, `AUTH_URL` | per standard digichat deploy (`docs/DEPLOYMENT.md` § digichat); `AUTH_TRUST_HOST=true` alongside them |
| `DIGICHAT_EMBED_TOKEN` | the tenant's embed token, as a **secret** (`secretref:`), never baked into the image. The single-install path enforces it on every `/api/chat` |
| `AZURE_CLIENT_ID` | the **user-assigned** managed identity's client id, when the app uses one. Without it `DefaultAzureCredential` fails with "Unable to load the proper Managed Identity" |
| `DIGICHAT_DATABASE_URL` | Postgres (persistence is `none` in this config, but sessions still need it) |

`DIGICHAT_ENABLED_SERVICES` is **not** needed for V1. The warm-up gate used to
probe digigraph unless that variable named a service, so a Foundry-only install
parked the UI on a boot screen; the gate now reads the deployment's backend and
skips digigraph when the install does not use it (#6023).

No MCP token, no digikey/digigraph URLs on V1: the container talks to the
tenant's Foundry agent via its managed identity (`DefaultAzureCredential`),
and the agent carries the search index + MCP tool server-side.

## Backend wiring (V1 — tenant Foundry agent, #3862)

- Foundry project + model deployment in the tenant RG (blocked on the
  Trials-sub Azure OpenAI grant — see prerequisites above).
- Agent carries the tenant `dg-search-index` (`azure_ai_search` tool) and the
  dev MCP server (MCP tool, custom-keys connection, tenant key).
- Reasoning summary **enabled** on the agent definition, otherwise thinking
  rows stay dropped by design.
- `guardrails` inherits the stability cap from defaults: `maxToolCallsPerTurn: 5`,
  `answerAt: 0.7`, `pauseAt: 0.9`. The per-visitor house minute is cleared.
  `tokensPerMinute.deployment` is the trial's one shared allowance.
  TODO: it stays unset until the Azure TPM for gpt-5.6-terra in westeurope
  is known. The request limiter stays on.
  `maxToolCallsPerTurn` follows the per-adapter matrix in `toolCallCapSupport`
  (`src/lib/deploy-config/schema.ts`) and the Guardrails section of
  `apps/digichat/ARCHITECTURE.md`. Foundry and the AI SDK backends
  (openai-completions, openai-responses, anthropic, google-vertex) enforce
  it and stop the tool loop. langgraph and ag-ui stop forwarding the next
  call (notice/best-effort, no `tool_choice: none` follow-up). digigraph is
  notice only. a2a is refused at config load. `backend.maxToolCalls` remains
  the Foundry alias and the shared key wins.
- The agent's search tool needs a project connection that can **read the index
  definition**, not just query it. A query key returns `403` on
  `GET /indexes/<name>`, and the tool is refused with "Access denied. Check
  your permissions or managed identity access to the search service". Use the
  search service's **admin** key, held in a secret store, never in the agent
  definition.
- An `AAD` connection authenticates as **whoever calls the agent**. A direct
  call from an operator's own session can therefore succeed while the
  container's managed identity is refused. A key connection is the same for
  every caller, which is why the trial uses one.

## MCP schema proxy (V1, DC-18)

The .NET MCP SDK publishes every `int?` tool parameter (`pageSize`,
`minSizeBytes`) as `{"type":["string","integer","null"],"default":0}`. The
server's own argument check (DCE-152) reads only the first member, so a
numeric `pageSize` on a call that fails for ANY reason is reported as
"'pageSize' must be a string, but a number was provided" — the real error is
replaced. digichat can sit between the agent and the MCP to fix this without
touching the server:

1. Set on the Container App (server-only env, not a secret — no credential in it):
   `DIGICHAT_MCP_SCHEMA_PROXY={"datatap":{"url":"https://datatap-dev-mcp.azurewebsites.net/","toolErrorsAsResults":true}}`
2. Point the agent's MCP tool `server_url` at
   `https://<this-app-fqdn>/api/mcp-proxy/datatap`. The custom-keys connection
   (`X-API-Key`) is unchanged: the proxy forwards the caller's header and adds
   nothing.

Every `tools/list` reply is normalized (`integer|null`, mismatched defaults
dropped), every `tools/call` is coerced back onto the server's original schema
(a number becomes the string the server leads with; an optional `null` is
omitted), and with `toolErrorsAsResults` an `isError` tool result reaches the
model as a normal result that names the error, so the agent can retry or
explain instead of the turn ending. Unset the env var (or point `server_url`
back) to remove it.

**Exposure.** The route adds no credentials: it forwards the caller's own auth
headers, so all authorisation is the upstream's. Publish it only behind the
same edge gate as `/api/mcp/zammad` (`x-digi-mcp-key`), and treat a loopback
target (`http://127.0.0.1:<port>`) as a development setting — it would publish
an internal, unauthenticated MCP to whoever can reach the app.

## Container environment (V2 — DigiGraph harness, parked)

| Variable | Value / source |
|---|---|
| `DIGICHAT_CONFIG_PATH` | `config/datatap-trial-test.yaml` (baked into the image) |
| `DATATAP_MCP_TOKEN` | tenant MCP key — Container App **secret**, never baked into the image |
| `DIGIKEY_URL` | `https://key.<shared-stack>` |
| `DIGIKEY_BFF_TOKEN` | same value the shared digikey was issued with (secret) |
| `DIGIGRAPH_INTERNAL_URL` | `https://graph.<shared-stack>` |
| `AUTH_SECRET`, `AUTH_URL` | per standard digichat deploy (`docs/DEPLOYMENT.md` § digichat) |
| `DIGICHAT_DATABASE_URL` | Postgres (persistence is `none` in this config, but sessions still need it) |

## Backend wiring (V2 — shared digigraph, parked)

- `DIGI_TENANT_CORPUS_MAP` must map the deployment slug to a
  `researchSystemPrompt`, otherwise the workflow takes the quant-extraction
  path and non-quant questions fail:
  `{"datatap-trial-test":{"researchSystemPrompt":"You are the DataTap trial
  assistant. … use the datatap MCP tools …"}}`.
- Model: route `DIGI_LLM_MODEL` at the sharedstack's LiteLLM proxy to the
  Foundry `gpt-5-mini` deployment (azure provider entry), or set it directly
  once the Trials-subscription Foundry account has a deployment.

## Build the image

The Dockerfile consumes `image-packages/`, which
`scripts/package_r5_image_inputs.py` produces:

```bash
python3 scripts/package_r5_image_inputs.py --npm-only   # what this image needs
docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
  -f apps/digichat/Dockerfile -t <registry>/digichat:<tag> . --push
```

Two traps: the build is `linux/amd64` (a plain `docker build` on an arm64 Mac
produces an arm64 image and the Container App rejects it with "no child with
platform linux/amd64"), and the config the image bakes must be the **rendered**
one — a template with `REPLACE-` placeholders now fails at boot with a clear
error instead of failing every chat on a DNS lookup (#6023).

## Deploy sketch — V1 (Azure CLI)

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
  --user-assigned <identity-with-foundry-access> \
  --env-vars DIGICHAT_CONFIG_PATH=config/datatap-trial-foundry.yaml \
             AUTH_URL=https://<this-app-fqdn> \
  --secrets auth-secret="<auth-secret>"
# then set AUTH_SECRET=secretref:auth-secret via
# `az containerapp update --set-env-vars` (secretref form).
```

## Deploy sketch — V2 (parked)

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

1. `GET /api/health` → `{"ok":true,…,"version":"<DIGICHAT_VERSION>"}`.
   `version` is `DIGICHAT_VERSION` when that env is set and non-empty, otherwise
   `apps/digichat/package.json` `version` (`resolveDigichatVersion()`). The image
   bakes the package version into `DIGICHAT_VERSION` and `/etc/digichat-version`;
   `version` only differs if `DIGICHAT_VERSION` is overridden at build or run time.
2. Chat "List my DataTap connections" → a `datatap__list_connections` tool
   row appears, completes while the answer streams, and expands to the
   connections JSON (args pane + Result pane).
3. Unauthenticated `tools/list` on the MCP server shows the base set; the
   keyed container sees the Search tools — scope gating intact.

## Secret custody and rotation

Two independent credentials back this chat, both held as inline Azure Container App
secrets on `digichat-datatap-trial` (resource group `1d0a8149-9387-4574-9d10-e83948e7fcd5`,
subscription `Datatap Trials`; measured 2026-10-22, `keyVaultUrl: null`):

| Container App secret | Bound env var | What it gates |
|---|---|---|
| `embed-token` | `DIGICHAT_EMBED_TOKEN` | the single-install `/api/chat` gate: `apps/digichat/src/lib/deploy-config/loader.ts:261-264` copies it into `deployment.token`, and `apps/digichat/src/lib/embed-chat-tenant.ts:118-125` (`installAuthorized`) matches it on the single-install path (`apps/digichat/src/app/api/chat/route.ts:209`; `installAuthorized` is consulted only when no embed tenants are configured — `apps/digichat/src/lib/embed-chat-tenant.ts:159`) |
| `auth-secret` | `AUTH_SECRET` | this app's Auth.js session secret |

The V1 sketch above does not set `embed-token`; the live app carries it (measured
2026-10-22).

- **Readback: yes, but only through `az containerapp secret list --show-values`.**
  Any principal holding `Microsoft.App/containerApps/listSecrets/action` reads an
  inline Container App secret in cleartext that way (`docs/ops/credential-ownership.md`).
  `az containerapp show` and `az containerapp secret show` redact, so "write-only"
  is false for this pair (measured on the sibling ACAs of the same shape —
  `docs/ops/digichat-datatap-aca.md`).
- **Custody: the client's Azure only.** No copy is held in our repo or in our local
  host secret store, and none is needed: the value can be read back with the command
  above, so a rotation does not depend on anyone supplying it out of band (the same
  conclusion the sibling ACAs reached — `docs/ops/credential-ownership.md`).
- **Rotation blast radius.** `embed-token`: without a matching `DIGICHAT_EMBED_TOKEN`
  the single-install path refuses every `/api/chat`. `auth-secret`: every session on
  the app is invalidated.
- **Handing a value to the client stays a human act** — person to person, never
  pasted into a chat, a ticket or a link. The Azure write is a human step. The
  trial lane's own rule is the one the runbook states at the top of its promotion
  steps: every command there is a write to a customer's Azure, and none of it runs
  without the approval named at the top of that step
  (`docs/ops/digichat-datatap-aca.md`); DevOps owns the trial deploy lane and this
  guide, and the client-facing handoff is Chris's act.
- **This is not the OCC invite key.** The pair is the tenant's own credential and the
  two must not be confused. The client's own `datatap-dev` MCP `X-API-Key` stays
  theirs (R18) and is not in the container: in the V1 Foundry setup the MCP tool
  sits server-side in the tenant's Foundry agent.
- **Open: no recorded fingerprint and no staleness detector for this pair.** The
  sibling ACA detector (`scripts/digichat_aca_secret_detector.py`, DIG-1344) has no
  binding for this app. Owner: Security & Risk Lead, 2026-10-22. Closing it needs a
  read of the client's Azure secrets, which the trial lane gates behind the named
  approval (`docs/ops/digichat-datatap-aca.md`), so it rides with DevOps and Chris.
- **Why this file and not `docs/ops/SECRETS_INVENTORY.md`.** The R0 client-literals
  gate (DIG-3689) checks `docs/ops/SECRETS_INVENTORY.md` — it carries a grandfathered
  count of 4 there, and the allowance may only shrink (DIG-4577); the growth check's
  failure message asks the author to remove the literal from the source instead of
  allowlisting it, while the DIG-3689 check's own message offers to grandfather a new
  path or remove the literals. The gate does not check this file, so the record can
  live here without touching that allowance. No credential value or fingerprint of
  this pair is written down here; the identifiers it names (the trial app, its
  resource group and its subscription) are the ones the sibling runbook
  `docs/ops/digichat-datatap-aca.md` already carries.
- **Open: this path's R-class is contested in the repo's own artifacts.** The
  canonical split map (`scripts/split/manifest.py`, DIG-3690) assigns **R0 (public)**
  to this guide, to `docs/ops/SECRETS_INVENTORY.md` and to
  `docs/ops/digichat-datatap-aca.md`; the older move lists
  (`scripts/repo-split/move-lists/r5.paths`) put the inventory and the ACA runbook in
  R5, and the DIG-3689 gate's prefix table treats this guide as private — while the
  gate's own docstring says the manifest supersedes that table. Raised with the R0
  owner on DIG-3689; the classification is the split owner's call, not this
  record's.

## Traps worth knowing before the demo

- The chat answers with the **generic** "The assistant is unavailable right now"
  for every upstream failure, including a refused search connection. Check the
  container log (`[foundry] stream error …`) before blaming the model.
- A partially streamed answer followed by that message is not a truncated
  answer: the turn failed after the first tokens.
- `GET /api/health` probes the whole ecosystem, so a Foundry-only install
  reports a failing check while the chat is fine. Read `service` and `version`
  in the body, not the status code.

## Promotion notes

- Replace the Website-subscription Foundry endpoint with a
  Trials-subscription deployment once the access grant lands (one-line model
  change, no rebuild).
- Per-tenant provisioning automation (new MCP connection + agent per trial)
  is DCE-143 Phase 2 scope; this guide is the manual path that automation
  must reproduce.
