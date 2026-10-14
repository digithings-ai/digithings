# Foundry-agent trial POC spec (DCE-142/143 V1)

Per-trial DigiChat for DataTap trials: a UI-only container in each trial
tenant talking to a tenant-local Foundry agent that grounds on the tenant's
own search index and acts through the shared DataTap MCP server. The
DigiGraph-harness config already in repo is V2 and stays untouched.

Issues: #3861 (digichat adapter + trial yaml, this spec's build item),
#3862 (azure tenant setup), #3863 (per-trial container pipeline).

## Principle

One trial = one tenant = one container app + one baked yaml + one agent,
everything inside the trial tenant as it would live on the client's real
tenant. Only the MCP *server binary* is shared; tenancy travels in the
tenant's API key. Trial data belongs "to the client" (simulated) and never
leaves the tenant except as keyed MCP HTTPS calls.

## Decisions (locked)

- Reasoning **on**: the agent runs with reasoning summary enabled so the
  thinking chain renders. The adapter drops empty reasoning rows by design.
- Display parity: Foundry-driven MCP/search activity renders exactly like
  native rows (args + JSON result, mid-stream completion) via the standard
  `tool-{name}` message parts — no new package capability, no per-tool UI.
- `mcp_approval_request`: **auto-approve** server-side. First-party agent on
  tenant-owned data with the tenant's key; surfacing approvals needs UI that
  does not exist.
- Per-trial config: **baked yaml per trial** (endpoint + agent baked,
  `DATATAP_MCP_TOKEN` as Container App secret), one container app per trial.

## Azure half (#3862, later)

Tenant `1d0a8149-9387-4574-9d10-e83948e7fcd5` (verified): Cosmos DB, Storage,
empty CAE `cae-1d0a8149`, AI Search `dg-search-…` (free, running) with
`dg-search-index` = 12,761 email docs. Steps: Trials-sub Azure OpenAI grant
(hard prerequisite) → Foundry project + model in tenant RG → attach
`dg-search-index` as `azure_ai_search` tool → attach dev MCP as MCP tool
(custom-keys, `X-API-Key`; confirm MCP tool shape in `@azure/ai-projects`) →
reasoning summary on → record agent id + project endpoint.

## DigiChat half (#3861, now)

`adapters/foundry/stream.ts` maps only `azure_ai_search_call`/`_output`,
text-bearing `reasoning`, `file_search_call`, `message`. MCP items
(`mcp_call`, `mcp_call_output`) hit `default: null` and vanish. Work:
map `mcp_call` to a started `execute_tool` span (name + parsed args as
`toolInput`) and `mcp_call_output` to a completed span with output as
`toolResult`, reusing the `toolResult` sanitizer, labels-gate pass-through,
and `ToolFallback` JSON rendering. Cover `.added` too if MCP streams
partial args (verify live). Tests mirror the search-mapping tests in
`stream.test.ts`. Ship the UI-only trial yaml shape (foundry backend) as the
per-trial template. Container authenticates via `DefaultAzureCredential`,
so it needs a managed identity on the tenant's Foundry project.

## Pipeline half (#3863, later)

Per trial: render baked yaml, deploy UI-only container into the tenant CAE
with `DIGICHAT_CONFIG_PATH`, secret `DATATAP_MCP_TOKEN`, managed identity.

## Promotion notes

Replace nothing on the website chat (search-only, no MCP — untouched).
Trials-sub model grant unblocks tenant-local deployments; until then V1
cannot leave planning on the Azure side.
