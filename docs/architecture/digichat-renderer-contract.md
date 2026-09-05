# digichat renderer contract

**Status:** Living architecture note (2026-09-05)
**Related:** [ADR-0028](../adr/0028-digichat-web-foundation-and-opencode-distribution.md),
[digichat modular frontend](digichat-modular-frontend.md),
[`frontend/digichat/ARCHITECTURE.md`](../../frontend/digichat/ARCHITECTURE.md),
implementation [#3626](https://github.com/digithings-ai/digithings/issues/3626)
**Verified:** 2026-09-05 against live assistant-ui, AI SDK v7, AG-UI, LangGraph,
ACP, and OpenAI docs, plus `origin/develop` `frontend/digichat`.

This note records the public **renderer** contract. It does not invent a
digithings-only event dialect. Implementation lives in a follow-up issue, not
this ADR PR.

## Decision

The canonical browser-facing contract is the **Vercel AI SDK UI message
stream**: SSE chunks of `UIMessage` / `UIMessageChunk`, advertised with
`x-vercel-ai-ui-message-stream: v1`.

That is what `@assistant-ui/react` consumes on the recommended AI SDK runtime
and on DataStream. Other OSS chat UIs that speak `useChat` consume the same
bytes. Custom product chrome (tool/search/vault activity) stays a `data-*`
part **on that stream**, not a second wire protocol.

## Layers (correcting “we already use OpenAI contracts”)

OpenAI Chat Completions is a **model** API. It is not a UI-event contract.
digithings already uses it at the orchestration hop; the BFF already translates
it into a UI stream.

| Layer | What it is | Live surface |
|-------|------------|--------------|
| Browser / any UI | Renderer contract | AI SDK UI message stream (`UIMessage[]` in, SSE `UIMessageChunk` out) |
| digichat BFF `POST /api/chat` | Auth, persistence, tenant/embed policy, adapter translation | Already emits the UI stream; default path is `createDigigraphTraceStreamResponse` |
| digigraph HTTP | OpenAI-compatible **model** API | `POST /v1/chat/completions` (`stream: true` → `chat.completion.chunk` SSE). Optional `delta.digigraph_trace` / `delta.digigraph_error` are product extensions on that model stream, not a UI protocol |
| digigraph LangGraph | Internal graph runtime | `graph.stream` / `astream` modes (`values`, `updates`, `messages`, `custom`, …). Thread APIs are opt-in (`DIGI_ENABLE_THREAD_API=1`) |
| digigraph MCP | Agent ↔ tools | FastMCP on `:8766`; unauthenticated; not a renderer |
| Foundry adapter | Client-embed backend | Translated into the same UI stream + `data-digichatActivity` |

```text
UI  --UIMessage stream-->  digichat BFF  --OpenAI Chat Completions SSE-->  digigraph
                                              (LangGraph inside the process)
```

## What `@assistant-ui/react` actually consumes (2026-09)

assistant-ui is a React UI + runtime, not a wire protocol of its own. Runtimes
wrap one of two cores (`LocalRuntime`, `ExternalStoreRuntime`) and optionally a
protocol layer.

Checked: [pick a runtime](https://www.assistant-ui.com/docs/runtimes/pick-a-runtime),
[architecture](https://www.assistant-ui.com/docs/runtimes/concepts/architecture),
[AI SDK overview](https://www.assistant-ui.com/docs/runtimes/ai-sdk/overview),
[AI SDK v7](https://www.assistant-ui.com/docs/runtimes/ai-sdk/v7),
[DataStream](https://www.assistant-ui.com/docs/runtimes/custom/data-stream),
[Assistant Transport](https://www.assistant-ui.com/docs/runtimes/custom/assistant-transport),
[LangGraph](https://www.assistant-ui.com/docs/runtimes/langgraph/quickstart),
[AG-UI](https://www.assistant-ui.com/docs/runtimes/ag-ui/overview).

| Runtime | Package | Wire | Role for digichat |
|---------|---------|------|-------------------|
| AI SDK `useChatRuntime` / `AssistantChatTransport` | `@assistant-ui/ai-sdk` (v7 current) or `@assistant-ui/react-ai-sdk@1.3.40` (v6 pin) | AI SDK UI message stream from `/api/chat` | **Selected client path.** Matches the BFF. New assistant-ui projects target v7 (`ai@^7`, `@ai-sdk/react@^4`). Some older assistant-ui pages still say v6 is current; the versioned v7 page and overview table are authoritative as of this check |
| DataStream `useDataStreamRuntime` | `@assistant-ui/react-data-stream` | Auto-detects `x-vercel-ai-ui-message-stream: v1` (AI SDK v5+) or `x-vercel-ai-data-stream: v1` (AI SDK v4 / `assistant-stream`); unknown markers fall back to UI message stream | Compatible fallback if we do not use `useChat` |
| LocalRuntime | `@assistant-ui/react` | Custom `ChatModelAdapter` (you invent the fetch) | Avoid. That *is* a private dialect |
| ExternalStoreRuntime | `@assistant-ui/react` | You own the store; no wire | Used underneath LangGraph / AG-UI adapters |
| Assistant Transport | `@assistant-ui/react` | Full **agent state** snapshots + commands, not a message stream | Skip. We stream messages, not a second state machine |
| LangGraph `useLangGraphRuntime` | `@assistant-ui/react-langgraph` | LangGraph SDK / Cloud (`unstable_createLangGraphStream`) | Skip as the public contract. It bypasses the BFF (auth, embed policy, persistence) and couples every UI to LangGraph Platform |
| AG-UI `useAgUiRuntime` | `@assistant-ui/react-ag-ui` + `@ag-ui/client` | AG-UI events over `HttpAgent` | **Later adapter only.** First-class for CopilotKit-class UIs, not what assistant-ui’s AI SDK path speaks natively |

## Ranked contracts

Preference if tied: (1) what assistant-ui speaks natively, (2) what other OSS
UIs also speak, (3) what digigraph already produces, (4) maturity.

| Option | Verdict |
|--------|---------|
| **c) AI SDK UI message stream (current BFF)** | **Pick.** Native for assistant-ui AI SDK + DataStream. Public, documented, already emitted by `POST /api/chat`. Other `useChat` UIs speak it. Custom activity is a `data-*` part on the same stream ([AI SDK stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol)) |
| e) AG-UI | Later adapter. Open agent↔UI protocol with a LangGraph integration and an assistant-ui runtime, but adopting it as canonical would rewrite the BFF away from a stream we already emit and assistant-ui already consumes. Interrupt/`resume[]` is still opt-in on the LangGraph bridge |
| a) OpenAI Chat Completions SSE | Keep as the **digigraph model** API (Open WebUI, LiteLLM-shaped callers, OpenCode `model`). Not a renderer contract: `chat.completion.chunk` deltas have no UI part model, no `data-*`, no first-class citations/tool UI lifecycle |
| b) OpenAI Responses API | Richer model events (`response.output_text.delta`, …). digigraph lists it **not built** (Phase 2). assistant-ui’s chat runtimes do not treat it as the `/api/chat` contract |
| d) LangGraph `stream` / `useStream` | Keep **inside** digigraph. Public UIs must not speak it; that would skip the BFF |
| f) ACP | **Rejected as canonical.** Editor↔coding-agent JSON-RPC (stdio today; remote still in progress). Markdown-centric, no citation/RAG part model. Optional later as an editor/workspace gateway only. Spec: https://agentclientprotocol.com/get-started/introduction |

Honest one-liner: **speak the AI SDK UI stream because that is what assistant-ui
DataStream / `useChatRuntime` consume; add an AG-UI adapter later if another UI
needs it. Do not invent a new dialect.**

## What digichat emits today (`origin/develop`)

`frontend/digichat/package.json`: `ai ^6.0.116`, `@ai-sdk/react ^3.0.118`,
`@ai-sdk/openai ^3.0.41`. No `@assistant-ui/*`.

`POST /api/chat` (also `/api/v1/chat`):

- Request: `{ messages: UIMessage[] }` plus turn/session headers
  (`X-Digi-Turn-Mode`, `X-Digichat-Session`, …).
- Default response: `createUIMessageStream` + `createUIMessageStreamResponse`
  in `src/lib/adapters/digithings/stream.ts`. That helper sets
  `x-vercel-ai-ui-message-stream: v1`. Text uses `text-start` / `text-delta` /
  `text-end`. Activity uses `type: "data-digichatActivity"`.
- Legacy path: `streamText(…).toUIMessageStreamResponse()` (AI SDK v6 instance
  method; v7 prefers stateless `toUIMessageStream` +
  `createUIMessageStreamResponse`).
- The BFF **parses** digigraph OpenAI SSE (`iterateOpenAiSse`) and **writes**
  AI SDK UI chunks. The browser never sees `delta.digigraph_trace`.

AI SDK v6 → v7 is a library bump on the **same** UI-stream family, not a
protocol replacement. Fold it into the assistant-ui migration: new assistant-ui
projects target `ai@^7` / `@ai-sdk/react@^4` / `@assistant-ui/ai-sdk`. Until
then a v6 pin (`@assistant-ui/react-ai-sdk@1.3.40`) can consume today’s BFF.

## `data-digichatActivity`

`ACTIVITY_PART_TYPE = "data-digichatActivity"` is already the AI SDK **Data
Parts** extension (`data: {"type":"data-<name>","data":…}`). The *payload*
schema (`ActivitySpan` → `DigiChatActivity`, OTel GenAI field names, embed
`activityDetail` gate) is product-specific and stays in the BFF mapper. That
is using the public protocol’s extension point, not a proprietary wire.

On assistant-ui, those parts arrive as `data-*` (DataStream `onData`, or AI SDK
`UIMessage` parts). Theme them as CLI/tool rows. Do not rename the part type
in the first migration unless a renderer forces it.

## Out of scope here

- Implementing assistant-ui or rewriting the BFF
- Making digigraph emit UI messages (it keeps Chat Completions)
- Exposing unauthenticated MCP as a UI backend
- ACP or AG-UI as the embed/`/chat` contract
