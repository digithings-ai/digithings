# digichat Phase 2 unification — design

**Date:** 2026-08-05
**Status:** Approved (brainstorm complete; awaiting user review of this written spec)
**Scope:** Phase 2 of the digichat unification program — digivault provider port (2a) + digigraph rich mapping / dual-emit retirement (2b), shipped as **one PR**.

## Problem

Phase 1 shipped a shared `ActivitySpan` vocabulary and made Foundry emit rich `tool_result` rows on the public embed. Two gaps remain before Phase 3 can point `digithings.ai/chat` at the digichat container:

1. **digivault lives only in Cloudflare.** `frontend/digithings-web/functions/api/chat.ts` (~983 lines) runs the digivault RAG + OpenRouter free-pool agentic loop and streams NDJSON. The digichat container has no equivalent provider, so digithings cannot cut over to one runtime.
2. **Authenticated digichat still dual-emits.** `stream-digigraph-trace.ts` writes gated `data-digichatActivity` plus ungated legacy `data-digigraphTrace` on the auth path because `chat-panel.tsx` still renders `RagSourcesTrace` / `ResearchBriefTrace` off the legacy part. The flat Phase 1 `chat` span cannot carry evidence tier, year, snippet, or a research brief.

Until both land, Phase 3 would either regress digithings chat or re-split auth vs embed UI again.

## Non-goals

- Retiring the Cloudflare Function, `useStackChat`, `chatStream`, or the native digithings-web `/chat` page (Phase 3).
- Iframe cutover, postMessage seed, `showByok` / `showStatusBar` / `layout: "page"` / mermaid tenant flags (Phase 3 — decisions already locked in the Phase 1 spec).
- Fixing the terracotta accent bug (separate branch/PR; out of scope here).
- Standing up an OTLP collector or exporting spans (unchanged from Phase 1).
- Rebuilding a shared client “controller” abstraction for digithings-web (Phase 1 locked: `useStackChat` dies in Phase 3; do not scaffold it).

## Program context

Inherited from Phase 1 (`docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`). Do not relitigate:

| Phase | Scope | Ships |
|---|---|---|
| 1 (done) | Activity contract + Foundry enrichment | digichat release — DataTap chain gets rich |
| 2 (this spec) | digivault provider in container + digigraph rich mapping; dual-emit deleted | one digichat PR; CF Function still live |
| 3 | `digithings.ai/chat` → iframe; retire CF Function + `useStackChat` | one runtime |

Also inherited:

- Shared backend means **pluggable providers**, not one assistant.
- Presentation allowlist is `ActivitySpan` / `sanitizeActivitySpan` — undeclared keys never copy.
- `activityDetail: "off" | "labels" | "full"` is gated **server-side** before write.
- `reasoningDelta` and documents must not share one span — emit two (projector constraint already documented in `chat-activity.ts`).

## Locked decisions

Recorded from the Phase 2 brainstorm (2026-08-05):

1. Extend `ActivityDocument` / digichat-ui `VaultHitSummary` with optional `tier?`, `year?`, `snippet?` (length-capped in sanitize).
2. `@digithings/digichat-ui` **is** in Phase 2 scope (richer hits + brief rendering) so embed and auth share one renderer.
3. New allowlisted `brief?: { themes: { label; summary }[]; questions?: string[] }` on `ActivitySpan` for digigraph `graph_update` / research brief.
4. digivault secrets: **per-tenant env var NAME refs** on `EmbedBackendConfig` — not raw secrets in tenant JSON; not a single hardwired global digithings key pair; shared UI never sees keys.
5. Full BYOK parity with the CF Function (OpenRouter / OpenAI / Anthropic / Gemini + free pool + `quota_exhausted`).
6. **One PR** for full Phase 2 (2a + 2b together).
7. Parity via **recorded fixture replay** (CF NDJSON + vault RPC → golden `ActivitySpan` / text), not live A/B as the gate.
8. Port an IP rate limit at **60 req / 60 s / IP** parity; store is Node/Azure-appropriate (not Workers KV). The implementation plan chooses the concrete store (in-memory vs Redis/Azure) for the deploy topology.

## Architecture

```text
Browser (embed or auth chat-panel)
  → POST /api/chat (AI SDK UI message stream)
  → route.ts dispatches by EmbedBackendConfig / auth path
       ├─ digivault  → digivault-stream.ts  (ported agentic loop)
       ├─ foundry    → foundry-stream.ts    (unchanged protocol)
       ├─ external-relay → …
       └─ digigraph  → stream-digigraph-trace.ts (typed mapper; no legacy part)
  → data-digichatActivity only (sanitized + activityDetail)
  → digichat-ui ChatActivities (rich hits + brief)
```

### Provider config

Extend `EmbedBackendConfig` in `frontend/digichat/src/lib/embed-tenants.ts`:

```ts
| {
    type: "digivault";
    /** process.env key names — values are never stored in DIGICHAT_EMBED_TENANTS JSON */
    supabaseUrlEnv: string;
    supabaseAnonKeyEnv: string;
    openRouterKeyEnv: string;
  }
```

Validation rules:

- Each `*Env` field is a non-empty string matching a conservative env-name pattern (implementation plan picks the exact regex; must reject values that look like URLs or API keys).
- At request time the handler resolves `process.env[name]`; missing or empty → fail closed with a safe 5xx and a server-side log. Never return the env name’s value or the missing key’s contents to the browser.
- Tenant JSON must not accept raw Supabase URLs/keys or OpenRouter keys as sibling fields for this backend type.

### Stream contract

- digivault loop runs in **Node route handlers** (same peer pattern as Foundry).
- Browser receives the **AI SDK UI message stream**, not NDJSON. Mapping from CF NDJSON event kinds to spans is internal to the provider.
- Every provider emits **only** `data-digichatActivity`. Delete dual-emit, the `data-digigraphTrace` writer, `emitLegacyTracePart`, and chat-panel’s `DigigraphTraceBlock` / `RagSourcesTrace` / `ResearchBriefTrace` / `isDigigraphTracePart`.
- Cloudflare Function stays until Phase 3.

### Accent bug

Out of scope. Ships from `cursor/accent-bug-fix` (or successor) as a separate PR.

## Data model

### ActivityDocument / VaultHitSummary

```ts
ActivityDocument = {
  title: string;
  path: string;
  tier?: string;    // evidence_tier / peer_reviewed mapping
  year?: number;    // publication_year
  snippet?: string; // capped in sanitizeActivitySpan
};
```

`VaultHitSummary` in `@digithings/digichat-ui` mirrors the same optional fields. Cap constants stay in digichat (`MAX_DOC_FIELD_CHARS` / a dedicated snippet cap); the implementation plan sets the numeric snippet budget (must be ≤ existing document field caps unless a new named constant is introduced and tested).

### ActivitySpan

```ts
ActivitySpan = {
  operation: "execute_tool" | "retrieve" | "chat";
  toolName?: string;
  query?: string;
  status: "started" | "completed" | "failed";
  label: string;
  documents?: ActivityDocument[];
  documentsWithheld?: boolean; // Phase 1 — set only by applyActivityDetail
  reasoningDelta?: string;     // digivault; never mixed with documents/brief on one span
  brief?: {
    themes: { label: string; summary: string }[];
    questions?: string[];
  };
};
```

`sanitizeActivitySpan` allowlists the new fields. Undeclared keys (including `source_id`, scores, model ids, vault body text) are never copied.

### digigraph mappings

| Upstream | Span |
|---|---|
| `rag_sources` | `retrieve` + `documents`: map `source_id` / `doc_id` → `path`; metadata title / DOI fallback → `title`; `evidence_tier` / peer_reviewed → `tier`; `publication_year` → `year`; `snippet` → capped `snippet` |
| `graph_update` | `chat` (or dedicated label) spanning `brief` from `research_brief` themes + `profiling_questions` → `questions` |
| other trace types | opaque `chat` / `trace` as Phase 1 (`label` + status) |

### activityDetail

| Level | Behavior |
|---|---|
| `off` | No activity parts |
| `labels` | Labels / tool steps only; strip **`documents` and `brief`**; set `documentsWithheld` when documents were present (Phase 1 semantics). Brief-only spans at `labels` become label/status rows without themes/questions — implementation plan decides the exact projector row shape for “brief withheld” vs omit |
| `full` | Documents + brief allowed after sanitize |

### Vault body

Supabase / digivault RPC `VaultHit.body_markdown` is **server-side only** — injected into the model tool context (CF already truncates with `MAX_NOTE_CHARS`). Activity parts never carry body markdown.

### digichat-ui

- Extend `VaultHitSummary` with optional `tier?`, `year?`, `snippet?`.
- Add a brief/themes activity kind (or dedicated block rendered from a new `DigiChatActivity` variant) so auth and embed share one path.
- Projector (`toDigiChatActivity`) maps `brief` spans onto that UI kind; exact kind name is an implementation-plan detail but must live in digichat-ui, not only in chat-panel.

## Components

| Component | Change |
|---|---|
| `frontend/digichat/src/lib/digivault-stream.ts` | **New.** Peer to `foundry-stream.ts`. Port agentic loop from `functions/api/chat.ts`: ≤3 tool rounds, `search_digivault` → Supabase `search_architecture_notes`, OpenRouter free pool + full BYOK, emit AI SDK UI stream (text + activity spans). |
| `frontend/digichat/src/lib/chat-activity.ts` | Extend document + brief allowlist; `applyActivityDetail` strips documents **and** brief at `labels`/`off`. |
| `frontend/digichat/src/lib/stream-digigraph-trace.ts` | Typed mapper for `rag_sources` / `graph_update`; delete legacy part writer and `emitLegacyTracePart`. |
| `frontend/digichat/src/lib/embed-tenants.ts` | Parse/validate `digivault` backend variant (env-name fields). |
| `frontend/digichat/src/app/api/chat/route.ts` | Branch `backend.type === "digivault"`; stop passing `emitLegacyTracePart`. |
| `frontend/digichat/src/components/chat-panel.tsx` | Consume `data-digichatActivity` via `toDigiChatActivity` + digichat-ui; delete DigigraphTraceBlock / RagSourcesTrace / ResearchBriefTrace. |
| `frontend/digichat-ui` | Richer hits + brief activity rendering. |
| Rate limit helper | New small module or extension of existing digichat limiters — **60/min/IP** on digivault path. Implementation plan decides store (in-memory first if single-replica; Redis/Azure if multi-replica). |

### digivault event → span mapping

| CF NDJSON kind | ActivitySpan / stream |
|---|---|
| `status` | `operation: "chat"` (or status row via label) |
| `tool_call` | `execute_tool` started (+ completed when appropriate) |
| `tool_result` | `retrieve` + `documents` (`{ title, path }` from CF hits; optional fields unused unless present) |
| `reasoning` | `reasoningDelta` alone |
| `content` | AI SDK text deltas |
| `quota_exhausted` | User-safe status/error path; no upstream body |
| `error` | Generic browser message + server log |
| `done` | Stream end |

### BYOK

Parity with CF Function:

- Providers: OpenRouter, OpenAI, Anthropic, Gemini via existing digichat `X-BYOK-*` headers (same semantics as CF `x-byok-*`).
- Free-pool rotation + `quota_exhausted` when the pool returns no usable content.
- Validation failures → HTTP 400 with safe messages (no key material echoed).

## Error handling

Inherit Phase 1 disclosure rules; apply them to digivault:

- Upstream / SDK / network exceptions → generic browser message + server-side log (same pattern already applied to Foundry, digigraph, relay).
- Malformed or unrecognized `ActivitySpan` → dropped; text stream unaffected.
- Vault tool failure → user-safe tool-result text + `status: "failed"` where appropriate (do not invent empty-hit success).
- Free-pool quota → `quota_exhausted` UX parity without leaking upstream bodies.
- BYOK validation → 400, safe body.
- Rate limit exceeded → 429, clear non-leaky body (“rate limit exceeded — slow down a moment” or digichat-equivalent wording).
- Missing digivault env resolution → fail closed (5xx), log server-side; do not fall back to another tenant’s env names.

## Testing

- **digigraph mapper fixtures:** `rag_sources`, `graph_update`, generic types → expected spans; assert **no** `data-digigraphTrace` on auth or embed paths.
- **Allowlist guards:** feed spans with undeclared keys / oversized snippet / brief; assert only declared capped fields survive.
- **activityDetail:** `off` emits nothing; `labels` emits neither documents nor brief; `full` emits both after sanitize; `documentsWithheld` honesty preserved.
- **digivault unit tests:** env-name resolve (success + fail-closed), tool-round loop, reasoning-only span rule, BYOK routing, rate-limit 429, document projection never includes `body_markdown`.
- **Parity (gate):** recorded CF NDJSON + vault RPC fixtures replayed through the digivault adapter → golden `ActivitySpan` sequences and assistant text equivalence. Behavior parity, not byte-identical AI SDK vs NDJSON streams.
- **digichat-ui:** richer hit fields + brief render smoke/unit coverage.
- **Regression:** existing Foundry / relay / chat-activity suites stay green with thin `{ title, path }` documents still valid.
- **chat-panel / route:** no legacy part type strings on the wire after migration.

## Rollout

1. Land this design; write implementation plan via writing-plans; implement in **one PR**.
2. digichat release → manual GHCR→ACR mirror (unchanged ops) → staging tenant configured with `backend: { type: "digivault", supabaseUrlEnv, supabaseAnonKeyEnv, openRouterKeyEnv }` + fixture/live smoke.
3. Verify authenticated digigraph chat shows rich sources + brief via `data-digichatActivity` only.
4. Cloudflare Function remains live until Phase 3 iframe cutover.
5. Accent fix ships separately; do not block Phase 2 on it.

## Success criteria

- Auth digichat shows RAG sources (tier/year/snippet where present) and research brief via **`data-digichatActivity` only** — zero `data-digigraphTrace` emission or consumption.
- A digivault-configured embed/auth tenant serves a digithings-equivalent activity chain with **fixture parity** against recorded CF NDJSON + vault RPC.
- Anonymous embeds cannot receive undeclared fields; `labels` / `off` never put documents or brief on the wire.
- Secrets never appear in digichat-ui, client bundles, or tenant JSON **values** (only env **names** in registry JSON).
- IP rate limit enforces 60/min/IP on the digivault path with a Node/Azure-appropriate store.
- No Workers-only APIs (KV bindings, etc.) copied into the Node port without an explicit substitute.

## Spec self-review

1. **Placeholders:** Rate-limit store, snippet numeric budget, brief-withheld projector row shape, and digichat-ui brief kind name are deferred with the phrase “implementation plan decides …” — not open product questions.
2. **Consistency:** One PR; env-name secrets; digichat-ui in scope; CF retained; accent out of scope; allowlist + activityDetail apply to documents and brief.
3. **Scope:** Phase 2 only (2a+2b); Phase 3 cutover explicitly excluded.
4. **Ambiguities resolved:** NDJSON is not the browser protocol; parity is fixture/behavior not bytes; dual-emit is deleted not soft-deprecated; global hardwired digithings keys are rejected in favor of per-tenant env refs.
)
