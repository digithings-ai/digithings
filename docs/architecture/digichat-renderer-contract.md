# digichat product contract (renderer + BFF)

**Status:** Living architecture note (2026-09-05)
**Related:** [ADR-0028](../adr/0028-digichat-web-foundation-and-opencode-distribution.md),
[digichat modular frontend](digichat-modular-frontend.md),
[`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md),
implementation [#3626](https://github.com/digithings-ai/digithings/issues/3626)
(**digichat 2.0** — do not merge to `develop` until the 2.0 cut)

digichat-the-**product** is the containerized **BFF** plus an optional default UI.
The UI and the HTTP contract do **not** change when the backend changes.
`DIGICHAT_EMBED_TENANTS[].backend.type` selects `digigraph` or `foundry`.

**AG-UI** is out of scope. Do not add `@ag-ui/*`. Callers never talk to LangGraph
Cloud, digigraph MCP, or Foundry’s native event stream.

## Modes of consumption

| Mode | What we ship | What they run |
|------|----------------|---------------|
| **Default UI** | CLI-themed assistant-ui at `/embed` and first-party `/chat` | iframe (marketing, dashboard popup, `widget.js`) or open the app |
| **Own UI** | Nothing visual | Their renderer against **their** digichat origin `POST /api/chat` |
| **Plugin** | Same HTTP, no iframe | Their existing chat calls the BFF as a backend / agent hop |

“Compatible” means the **stream + headers**, not importing `CliThread`.

## Canonical wire

The browser-facing contract is the **Vercel AI SDK UI message stream**:
`UIMessage[]` in, SSE `UIMessageChunk` out, advertised with
`x-vercel-ai-ui-message-stream: v1`.

```text
UI / plugin  --UIMessage stream-->  digichat BFF  --adapter-->  digigraph | Foundry
```

| Layer | Live surface |
|-------|--------------|
| Browser / any UI | AI SDK UI message stream |
| digichat BFF `POST /api/chat` | Auth, persistence, tenant/embed policy, adapter translation |
| digigraph | OpenAI-compatible `POST /v1/chat/completions` (LangGraph inside) |
| Foundry | Azure AI Foundry agent events (`adapters/foundry/stream.ts`) |

### Auth

- Auth.js cookie (first-party)
- Embed: `X-Embed-Host` + `X-Embed-Token` (customer hosts always need token)
- Machine: `Authorization: Bearer digi_live_…`

### Product headers

`X-Digi-Force-Tool`, `X-Digi-Turn-Mode`, `X-BYOK-*`, `X-Digi-Enable-Web-Search`,
`X-Digi-Language`, embed host/token/trial, `X-External-Conversation` (Foundry
continuity — echoed from `data-conversation`).

### Published part mapping (honest)

Chunk **types** are AI SDK-shaped. **Payloads** carry digichat product data —
a stock `useChat` client can stream text; search/vault **look** needs tool/source
UIs or a local mapping.

| Information | 2.0 part |
|-------------|----------|
| Tool / retrieve progress | `tool-*` (`tool-input-*`, `tool-output-available`) |
| Citations | `source-url` / `source-document` (snippets/body may live on tool output JSON) |
| Reasoning | `reasoning-*` |
| Opaque progress / research brief | unbranded `data-status` `{ status, label, brief? }` |
| Foundry conversation id | `data-conversation` |
| Embed `activityDetail` gate | still applied in the BFF before write |

1.4 branded `data-digichatActivity` is **not written**. Old threads are still
**read** for hydrate / export fallback.

## Default UI (assistant-ui)

`@assistant-ui/react` + `@assistant-ui/ai-sdk` + AI SDK v7. Session chrome is
`CliThread`: MessagePrimitive.Parts for text / reasoning / tools / sources /
`data-status`. Product slots only: CSS (`.dc-*`), slash + force-tool, pending
headers, BYOK/paywall, chart fence, copy/export serializers.

Package version stays **1.4.0** until the owner cuts 2.0.

## Backends

- **Profile A** — digichat + digigraph stack (digithings.ai dogfood).
- **Profile B** — digichat (+ db) only → Azure AI Foundry
  (`DefaultAzureCredential`; no Foundry key in env). Same `/embed` or headless
  BFF. digithings itself has **no Azure**.

Both adapters call `writeStandardActivity`. UI never selects a backend.

## Out of scope

- Merging 2.0 into `develop` before the cut
- AG-UI / ACP as the embed contract
- Making digigraph or Foundry emit UI messages natively
- A third backend type in this milestone
- LangGraph Cloud in the browser
