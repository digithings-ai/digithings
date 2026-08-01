# DigiChat activity protocol — design

**Date:** 2026-08-01
**Status:** Approved
**Scope:** Phase 1 of the DigiChat unification program. Entirely within `frontend/digichat`.

## Problem

DigiChat renders in two places that look different, and the difference is not styling.

`digithings-web` serves `/chat` as a native React page whose backend is a 983-line
Cloudflare Pages Function running its own agentic loop over digivault (RAG) on the
OpenRouter free pool. It streams NDJSON events — `status`, `tool_call`, `tool_result`
(with vault hits), `reasoning` — producing a layered "thinking chain".

`datatap-web` reaches DigiChat through the `/embed` iframe served by the `digichat`
container, whose backend is an Azure AI Foundry agent. Every provider in that
container (`foundry`, `external-relay`, `digigraph`) emits exactly one data-part
shape: `data-digigraphTrace` with `{label, status}`. `uiMessageToDigiChat` can
therefore only synthesize `kind: "trace"` activities.

The shared UI package `@digithings/digichat-ui` already renders five activity kinds
(`status | tool_call | tool_result | reasoning | trace`). The embed path starves it
of four. Same component, different input.

The data needed for the rich chain is already arriving from Foundry and being
stringified away — search queries land in `item.queries`, and citations arrive as
`url_citation{url, title}` or `{filename}` annotations, both collapsed into a single
`"Sources: a, b"` label line.

## Non-goals

- Porting the digivault/OpenRouter loop into the container (Phase 2).
- Moving `digithings.ai/chat` to an iframe (Phase 3).
- Any change to `@digithings/digichat-ui`, `datatap-web`, or `digithings-web`.
- Standing up an OTLP collector or exporting spans (deferred; see "OpenTelemetry").

## Program context

Three phases, each with its own spec, plan, and implementation cycle. End state: one
runtime (the `digichat` container), one UI package, one provider architecture.

| Phase | Scope | Ships |
|---|---|---|
| 1 (this spec) | Activity contract: `gen_ai`-named span events + projector; all providers widened | digichat release — DataTap chain gets rich immediately |
| 2 | Port digivault RAG + OpenRouter pool into the container as a `digivault` provider | parity-tested against the live Cloudflare Function |
| 3 | `digithings.ai/chat` → iframe; postMessage seed; config flags; retire the Cloudflare Function and `useStackChat` | one runtime |

Phase 1 is independently shippable and cleanly revertable because it touches no
other repo and no shared package.

### Decisions carried into later phases

Recorded here so phases 2 and 3 inherit them rather than relitigating:

- **Shared backend means one codebase with pluggable providers**, not one assistant.
  Which model or knowledge base a tenant talks to stays configuration.
- **`digithings.ai/chat` becomes an iframe embed.** The container is the single
  runtime; the Cloudflare Function and `useStackChat` are retired in Phase 3. A
  shared controller abstraction is deliberately *not* built — `useStackChat` is
  being deleted, so it would be scaffolding for a consumer we are removing.
- **The landing quick-ask handoff survives via parent postMessage.** Cross-origin
  iframes do not share `localStorage`, so `/chat` reads its own storage and posts a
  `seed` message into the iframe, reusing the channel the trial gate established.
- **These become tenant config in Phase 3:** `showByok` (today derived as
  `!ungated`), `showStatusBar` (today hardcoded `false`), `layout: "page"`, and
  mermaid rendering.

## OpenTelemetry

The vocabulary follows OpenTelemetry GenAI semantic conventions rather than
inventing bespoke names. Two planes, only one of which OTLP suits:

**Observability plane** (backend → collector). OTel is already the declared standard:
`digigraph`, `digivault`, `digismith`, `digiquant`, and `digisearch` all call
`setup_otel_fastapi` from `digibase.otel`. `ai@6.0.168` ships `gen_ai.*` attributes
behind `experimental_telemetry`. `digichat` is the one hop emitting nothing.

**Presentation plane** (backend → browser). OTLP is a poor fit here:

1. **Timing.** Spans record on *end*; the chain's value is in-progress signal. OTLP
   export has no span-start event.
2. **Transport.** OTLP is collector-bound batches; the embed streams over a single
   HTTP response via the AI SDK data-part channel.
3. **Disclosure.** Spans carry model IDs, upstream endpoints, service names, and
   prompt content. The DataTap embed is public and anonymous, so an allowlist
   projection is required regardless — at which point the allowlist *is* the
   protocol.
4. **Volume.** Dozens of spans per turn against roughly five rendered rows.

**Resolution: one vocabulary, two sinks.** Adopt GenAI semantic-convention naming
now and build the projector seam. Leave the exporter a no-op behind the standard
env var — the pattern `digibase` already uses. No `OTEL_EXPORTER_OTLP_ENDPOINT` is
configured anywhere in the repo today, and `ARCHITECTURE.md:293` records that OTel
"complements LangSmith; it does not replace it", so Phase 1 must not depend on an
observability backend that has not been chosen. Wiring a real exporter later is
configuration plus a tracer provider, against a vocabulary that already matches.

## Architecture

### The vocabulary

New module `src/lib/chat-activity.ts`:

```ts
export type ActivitySpan = {
  /** gen_ai.operation.name */
  operation: "execute_tool" | "retrieve" | "chat";
  /** gen_ai.tool.name */
  toolName?: string;
  query?: string;
  status: "started" | "completed" | "failed";
  /** Presentation-safe; never raw upstream text. */
  label: string;
  documents?: { title: string; path: string }[];
  reasoningDelta?: string;
};
```

Two fields are declared but unemitted by any Phase 1 provider, and that is
deliberate rather than an oversight. `reasoningDelta` exists because Phase 2's
digivault loop already streams reasoning deltas and will emit it unchanged; Foundry
does not expose reasoning at all. `status: "failed"` exists for the error path
described below. An implementer should build the projector to handle both and should
not expect a Phase 1 provider fixture to exercise them.

Providers stop writing `data-digigraphTrace` and write **`data-digichatActivity`**
carrying an `ActivitySpan`. A pure function `toDigiChatActivity(spans):
DigiChatActivity[]` projects onto the shared UI union, so `uiMessageToDigiChat`
sheds its trace-synthesis guesswork and becomes a mapper.

### The allowlist is the projector

`ActivitySpan` has no field for an endpoint, model ID, raw prompt, or upstream error
detail. Anything a provider wants to surface must pass through a declared field, so
the public embed cannot leak internals by accident — and the same events later feed
an OTLP exporter without a second sanitization pass.

### Detail level is tenant config

`EmbedTenantConfig` gains `activityDetail: "off" | "labels" | "full"`:

- `off` — no activity parts emitted at all.
- `labels` — labels only; no `documents`. **Default** when unspecified.
- `full` — the complete chain including retrieved documents.

The gate is applied **server-side in the projector**, so `off` and `labels` tenants
never receive documents over the wire. This is not CSS hiding.

## Provider mappings

### Foundry

| Foundry event | Today | `ActivitySpan` | UI row |
|---|---|---|---|
| `response.file_search_call.in_progress` | `trace "Searching…"` | `execute_tool`, `toolName: "file_search"`, `started` | `tool_call` |
| `output_item.done` / `file_search_call` (carries `item.queries`) | `trace "Searched for: …"` | `execute_tool`, `toolName: "file_search"`, `query: queries[0]`, `completed` | merged into the result row |
| `output_item.done` / `message` annotations (`url_citation{url,title}` or `{filename}`) | `trace "Sources: a, b"` | `retrieve`, `completed`, `documents: [{title, path}]` | `tool_result` with a titled hit list |

Foundry emits the search and the citations as two separate events, so this produces
two spans. The projector merges them into one `tool_result` row: the `execute_tool`
span supplies `name` and `query`, the `retrieve` span supplies `hits` and `count`.
When only one of the two arrives, the row still renders with whichever half is
present — a search with no citations becomes a "no hits" row, and citations with no
preceding search step render with an empty query.

Same bytes off the wire, structured instead of flattened. Both citation shapes must
keep working — `url_citation` comes from the `azure_ai_search` tool and `filename`
from Foundry's native `file_search` (see commit `91caa0e0`).

### external-relay

Upstream sends only `{label, status}` → `{operation: "chat", label, status}` →
`trace`. Faithful; cannot be enriched without relay-side changes. Not a regression.

### digigraph

Passes `delta.digigraph_trace` through opaquely, so it maps to `trace` initially.
The projector is the seam where richer digigraph fields land later, and where Phase
2's `digivault` provider plugs in — its agentic loop already produces exactly these
five kinds over NDJSON.

## Adjacent fix folded into this phase

`src/lib/stream-digigraph-trace.ts:100` streams up to 1500 characters of raw
upstream error body to the browser as assistant text. On a public anonymous embed
that can disclose internals. It is the same allowlist principle this phase
establishes, so it is fixed here: a generic user-facing message plus a server-side
log carrying the detail.

## Client changes

`uiMessageToDigiChat` reads `data-digichatActivity` and delegates to
`toDigiChatActivity`. It keeps accepting `data-digigraphTrace` for one release —
client and server ship in the same image, so this covers only iframe pages cached in
a visitor's tab across a deploy.

Today's by-label `Map` collapse moves into the projector and re-keys on
`(toolName, query)`. Two different searches currently merge if their labels happen
to match; keyed this way they stay distinct.

## Error handling

- A malformed or unrecognized `ActivitySpan` is dropped, not rendered. The turn's
  text stream is unaffected.
- A provider that emits no spans renders no activity block, exactly as today.
- Projection never throws into the stream: `toDigiChatActivity` is total over its
  input type and returns `[]` rather than propagating.
- `status: "failed"` renders as a completed row with the failure label; upstream
  error detail is logged server-side and never projected.

## Testing

- `mapFoundryEvent` fixtures → `ActivitySpan`, covering **both** citation shapes.
- `toDigiChatActivity`: ordering, dedupe by `(toolName, query)`, `started` →
  `completed` collapse, empty input yields no rows.
- **Allowlist guard:** feed a span carrying endpoint / model / prompt keys and
  assert nothing beyond declared fields survives projection. This is the regression
  test for the disclosure boundary.
- `activityDetail`: `off` emits no activity parts; `labels` emits no documents.
- Compatibility: a legacy `data-digigraphTrace` message still renders.
- Existing `src/app/api/chat/route.test.ts` stays untouched — evidence nothing
  outside the activity channel changed.

## Rollout

digichat release → GHCR → the manual ACR mirror → dev revision → verify → prod.
DataTap dev tenant set to `full`; unspecified tenants default to `labels`.

The GHCR → ACR mirror remains a manual `az acr import` after every digichat release.
Automating it is tracked separately and is not in this phase.
