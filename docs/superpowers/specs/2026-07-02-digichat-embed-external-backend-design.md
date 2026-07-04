# DigiChat embed: pluggable external backends (design)

- **Date:** 2026-07-02
- **Status:** Draft — awaiting review
- **Related:** Epic #1248 (DigiChat-as-gateway), ADR-0018 (path routing), PR #1280 (per-IP embed rate limiting), PR #1171 (streaming + agentic activity UI), datatap-web PR #5 (the first external consumer)
- **Human gate:** This design adds a new external network dependency (DigiChat BFF → a non-DigiThings relay endpoint). Per CLAUDE.md, the implementing PR always requires human review regardless of score.

## Problem

DigiChat is meant to be the single source of truth for all chat frontends in the DigiThings ecosystem — but today its `/embed` surface is hardwired to one backend (DigiGraph) and one access model (3 free turns, then a BYOK paywall). The first real external consumer, DataTapStream's marketing site, needs the opposite on both axes: its chat is powered by an Azure AI Foundry agent behind DataTapStream's own relay, paid centrally by DataTapStream, with no turn limit and no key prompt — ever. DataTapStream currently ships its own bespoke `ChatPanel` React code to get this, which is exactly the duplication DigiChat exists to eliminate.

## Goal

Make `/embed`'s backend and access policy **per-tenant configuration** rather than hardcoded, so that:

1. `digithings.ai` / `digiquant.io` embeds keep today's exact behavior (DigiGraph, turn-limited, BYOK unlock) with zero migration.
2. DataTapStream embeds the same `/embed` page in an iframe and gets: its own Azure Foundry agent (via its existing relay), no gate, its own accent color, and a "powered by digichat — a digithings product." attribution line.
3. Any future external site follows the same path by adding one config entry — no new code.

## Non-goals

- **No datatap-web changes in this spec.** Migrating DataTapStream's site (replace `ChatPanel` with the iframe, retire its custom chat components, keep its relay + knowledge-sync pipeline) is a follow-up in the datatap-web repo.
- **No direct Azure Foundry integration.** DigiChat talks to DataTapStream's already-built, tested Azure Function relay over a simple SSE contract; it learns nothing about Foundry's SDK, auth, or `agent_reference` protocol. (Decided: the relay owns that complexity and already works.)
- **No backend pluggability for the authenticated app.** Signed-in DigiChat users stay on DigiGraph. External backends are an embed-tenant concept only.
- **No BYOK on external-relay tenants.** `X-BYOK-*` headers are ignored on that path (the relay accepts no keys).
- **No database-backed tenant admin.** Config is an env-var JSON registry for v1 (see Alternatives).
- **No per-tenant suggestion chips, model selectors, or other embed feature flags.** One new axis (backend) and one new policy (gate mode); everything else stays shared.

## Current state (what this builds on)

**DigiChat side** (`frontend/digichat`):

- `/embed` (`src/app/embed/page.tsx`): iframe-ready unauthenticated chat. Client-side free-turn gate (`src/lib/embed-gate.ts`, `EMBED_FREE_TURN_LIMIT = 3`, localStorage per host origin) with a BYOK paywall card. Accent is a closed enum (`digithings | digiquant | digichat`) via `?accent=` query param. Messages render as plain-text bubbles — no markdown, no trace parts.
- `POST /api/chat` (`src/app/api/chat/route.ts`): resolves embed requests via `resolveEmbedChatTenant()` (`src/lib/embed-chat-tenant.ts`) to the fixed identity `{tenantSlug: "embed", ownerUserSub: "embed:anonymous"}`, then unconditionally builds a DigiGraph client. Rate limiting: shared BFF bucket (30/min) plus per-IP embed limiter (10/min, PR #1280).
- Trace streaming (`src/lib/stream-digigraph-trace.ts`): re-emits DigiGraph SSE as AI SDK UI message stream parts; activity events travel as `data-digigraphTrace` parts carrying `DigigraphTracePayload {v?, type, service?, payload?, ...}`. Only the main app's `chat-panel.tsx` renders them today.
- CSP (`src/lib/security-headers.ts`): `EMBED_FRAME_ANCESTORS = ['self', https://digithings.ai, https://digiquant.io]`, applied to `/embed` routes by `next.config.ts`.
- Host detection: the embed page resolves the embedding page's origin client-side (`resolveEmbedHost()`, from `document.referrer`) and sends it as `X-Embed-Host` on every chat request.

**DataTapStream side** (datatap-web repo, already live and verified end-to-end):

- Azure Function relay at `https://datatap-digichat-relay.azurewebsites.net/api/digichat`. Anonymous POST, JSON body `{conversationId: string | null, message: string}`. Foundry conversation state lives server-side in Azure; the relay creates a conversation when `conversationId` is null and reports its id back.
- Response is SSE, one frame per event: `event: <type>\ndata: <json>\n\n`, with five event types:

| event | data payload | meaning |
|---|---|---|
| `conversation` | `{type, conversationId}` | new conversation created; client must echo the id on subsequent turns |
| `text-delta` | `{type, delta}` | assistant text token(s) |
| `trace` | `{type, label, status: "in_progress" \| "completed"}` | activity step (file-search queries, cited sources) |
| `done` | `{type}` | response complete |
| `error` | `{type, message}` | terminal error |

- Client disconnect aborts the upstream Foundry call (verified). No Turnstile, no rate limiting on the relay itself — abuse protection is expected from the caller's side (see Rate limiting below).

## Design

### 1. Embed tenant registry (env JSON)

One new env var, `DIGICHAT_EMBED_TENANTS`, holding a JSON object keyed by **hostname** (no scheme):

```json
{
  "datatapstream.com": {
    "slug": "datatapstream",
    "aliases": ["www.datatapstream.com", "dev.datatapstream.com", "dev.datatap.stream"],
    "backend": {
      "type": "external-relay",
      "url": "https://datatap-digichat-relay.azurewebsites.net/api/digichat"
    },
    "gateMode": "ungated",
    "theme": "light",
    "accent": { "color": "#b5562b", "foreground": "#fff7f2" },
    "attribution": true
  }
}
```

New module `src/lib/embed-tenants.ts`:

- `EmbedTenantConfig` type: `slug` (string), `aliases` (string[], optional), `backend` (`{type: "digigraph"}` | `{type: "external-relay", url: string}`), `gateMode` (`"turn_limited"` | `"ungated"`), `theme` (`"dark"` | `"light"`, default `"dark"` — the embed page hardcodes its dark wrapper today; light-themed host pages like DataTapStream's need the light token set), `accent` (`{color, foreground}` hex pair, optional), `attribution` (boolean, default false).
- `loadEmbedTenants()`: parses the env var once at module load. Validation is fail-fast with a descriptive error: malformed JSON, a non-https relay URL, an invalid hex color, or a duplicate host/alias all throw. An unset/empty env var yields an empty registry — every current deployment keeps working with zero config.
- `resolveEmbedTenantByHost(hostOrOrigin)`: normalizes an origin or hostname (strips scheme/port, lowercases) and looks it up across keys and aliases. Returns the config or `null`.
- The registry is the **single source** for both request-time resolution and CSP frame-ancestors (below).

**Known caveat, stated up front:** `next.config.ts` `headers()` is evaluated at build time, so `DIGICHAT_EMBED_TENANTS` must be present **at build** (Docker build arg) for the CSP to include external hosts, and at runtime for routing. A missing build-time var fails visibly (iframe blocked by CSP), not silently; a startup log line lists the loaded tenants and derived frame-ancestors to make misconfiguration diagnosable.

### 2. Host → tenant resolution in `/api/chat`

`resolveEmbedChatTenant()` in `src/lib/embed-chat-tenant.ts` extends to consult the registry:

- Read `X-Embed-Host` (fallback: referer), normalize, look up the registry.
- **Known tenant:** return `{tenantSlug: config.slug, ownerUserSub: "embed:anonymous", embedConfig: config}`. Presence in the registry *is* the embed allowance — `isEmbedAllowed()`'s env-token check is skipped for registered hosts.
- **Unknown host (or no registry):** exactly today's behavior — `{tenantSlug: "embed", ownerUserSub: "embed:anonymous"}` gated by `DIGICHAT_EMBED_ENABLED`/`X-Embed-Token`, DigiGraph backend, turn-limited client gate. `digithings.ai`/`digiquant.io` need no registry entries; they ride this legacy default unchanged.

The route then branches once, immediately after tenant resolution and rate-limit checks:

```
embedConfig?.backend.type === "external-relay"
  → createExternalRelayStreamResponse(...)      // new, section 3
  : existing DigiGraph path                     // byte-for-byte untouched
```

Spoofing analysis: `X-Embed-Host` is attacker-settable from curl, but it only *selects among preconfigured* tenants — the relay URL always comes from config, never from the request, so DigiChat cannot be used as an open proxy (no SSRF surface). A spoofer selecting the DataTapStream tenant reaches an endpoint that is already public, minus nothing — and still passes through DigiChat's per-IP limiter. The client-side turn gate was never a security boundary (documented as UX-only in #241).

### 3. External relay stream adapter

New `src/lib/external-relay-stream.ts`, a sibling of `createDigigraphTraceStreamResponse` with the same output type (an AI SDK UI message stream response via `createUIMessageStream`):

`createExternalRelayStreamResponse({ relayUrl, messages, conversationId, responseHeaders, signal })`

- **Request mapping:** the relay takes a single message per turn (Foundry holds history server-side), while `useChat` posts the full `UIMessage[]`. The adapter extracts the **last user message's** text parts and POSTs `{conversationId, message}` to `relayUrl`, forwarding `signal` so a client disconnect aborts the relay's upstream Foundry call (the relay handles this correctly today).
- **SSE parsing:** the relay's frames are `event:`-typed (unlike DigiGraph's OpenAI-style `data:`-only frames), so the adapter includes its own small typed-event parser (exported for unit tests) rather than reusing `iterateOpenAiSse`.
- **Translation table:**

| relay event | UI message stream output |
|---|---|
| `conversation` | `data-externalConversation` part, `data: {conversationId}` — the client persists and echoes it (below) |
| `text-delta` | `text-delta` (one `text-start` before the first delta, `text-end` at stream close — mirroring the DigiGraph trace path) |
| `trace` | `data-digigraphTrace` part with payload `{v: 1, type: "external_activity", service: "external", payload: {label, status}}` — same part vocabulary as DigiGraph traces, so one renderer serves both |
| `done` | close the text block; stream finish |
| `error` | AI SDK error part → surfaces through `useChat`'s existing `error` state and the embed's existing retry card |

- **Conversation continuity:** the client stores the conversation id in `sessionStorage` (`digichat_embed_conversation:<host>`, matching the existing `digichat_embed_turns:` prefix style) and sends it back as `X-External-Conversation` on subsequent turns. Session-scoped persistence matches what DataTapStream's current panel does.
- **Upstream failure:** non-200 or empty-body relay responses produce a readable in-stream error (same pattern as the DigiGraph path's "Upstream error: ..." handling).
- `X-BYOK-*` headers are ignored on this path.

### 4. Tenant config endpoint for the client

The embed page needs `gateMode`, `accent`, and `attribution` before the first message. New route `GET /api/embed/tenant-config` (`src/app/api/embed/tenant-config/route.ts`):

- Resolves the tenant the same way as `/api/chat` (via `X-Embed-Host` sent by the page).
- Returns `{slug, gateMode, theme, accent, attribution}` — **never** the backend config; the relay URL stays server-side.
- Unknown host → `{slug: "embed", gateMode: "turn_limited", theme: "dark", accent: null, attribution: false}` (legacy defaults).
- `Cache-Control: no-store`.

### 5. Embed page changes (`src/app/embed/page.tsx`)

- Fetch tenant config on mount (one GET; until it resolves, render the legacy defaults — a flash of the gated default is acceptable, a flash of an ungated default is not, so default-closed).
- **Gate bypass:** when `gateMode === "ungated"`, the turn counter, `useEmbedGate` lock, and `PaywallCard` never engage; the header shows no `n/3 free` badge.
- **Accent:** when config provides `accent`, apply it as `--accent`/`--accent-foreground` CSS vars (overriding the enum-based classes). The `?accent=` query param and its three first-party values keep working for digithings/digiquant embeds. This refines the earlier "add a 4th enum accent" idea: external brand colors live in config, not in DigiThings source.
- **Theme:** the wrapper's hardcoded `dark` class becomes conditional on the tenant's `theme` — `"dark"` (default, today's behavior) keeps it, `"light"` drops it so the standard light token set applies. DataTapStream's host page is light-themed; a dark iframe would reintroduce exactly the boxed-widget look its site just moved away from.
- **Markdown:** assistant bubbles render through `react-markdown` + `remark-gfm` (both already dependencies) instead of plain text. User bubbles stay plain.
- **Activity/trace box:** render `data-digigraphTrace` parts in a collapsed-by-default activity box under the assistant message — reusing the main app's activity component from `chat-panel.tsx` if it extracts cleanly, otherwise a minimal list styled like it (`… label` in progress, `✓ label` completed). This benefits digithings' own embeds too — they gain the trace UI the main app already has.
- **Attribution:** when `attribution: true`, a footer line — exactly `powered by digichat — a digithings product.` with "digithings" linking to `https://digithings.ai` — all lowercase (repo convention per PR #1158; the header's current "DigiChat" label is normalized to "digichat" in passing, same convention).
- **Conversation echo:** the chat transport's `prepareSendMessagesRequest` adds `X-External-Conversation` from sessionStorage when present, and a small effect stores the id when a `data-externalConversation` part arrives.

### 6. CSP / frame-ancestors

`EMBED_FRAME_ANCESTORS` in `src/lib/security-headers.ts` becomes `embedFrameAncestors()`: the static first-party list plus `https://<host>` for every registry host and alias. `security-headers.test.ts` updates accordingly (first-party origins always present; registry hosts appended; no wildcards). The build-time env caveat from section 1 applies.

### 7. Rate limiting and abuse

- The per-IP embed limiter (10/min, PR #1280) applies to **all** embed tenants including external-relay ones — unchanged, deliberately. Worth noting: DataTapStream removed its Turnstile gate earlier today, leaving its relay with no abuse protection; routing its traffic through DigiChat's BFF **restores a real per-IP limit** in front of its Foundry spend.
- The shared BFF bucket key already includes the tenant slug (`chat:<slug>:embed:anonymous`), so each external tenant gets its own 30/min bucket instead of sharing the `embed` pool — a free improvement from resolving real slugs.

## Sequencing dependency (important)

`frontend/digichat` is **not deployed anywhere today** — Epic #1248 Phase 3 (container hosting + Cloudflare Route cutover to `digithings.ai/chat`) is still open and human-gated. DataTapStream cannot embed a page that isn't served. Until Phase 3 lands (or an interim deployment of the digichat container exists), datatap-web keeps its current custom `ChatPanel`; the migration follow-up in that repo is blocked on a live embed URL. This spec's work is still fully buildable and testable now (local + CI), and makes the embed ready the moment Phase 3 ships.

## Testing

- **Unit (vitest, existing setup):**
  - `embed-tenants.ts`: parse/validate (bad JSON, http URL, bad hex, duplicate alias → throw; empty env → empty registry), host normalization, alias resolution, unknown-host null.
  - `embed-chat-tenant.ts`: registered host → slug + config with token check skipped; unknown host → exact legacy behavior (regression-pins today's semantics).
  - `external-relay-stream.ts`: fake relay SSE → expected UI stream parts for all five event types; last-user-message extraction; abort propagation; non-200 upstream → readable error.
  - `tenant-config` route: known/unknown host responses; backend URL never present in the payload.
  - `security-headers.test.ts`: extended for registry-derived ancestors.
  - Rate limiting: regression test that the per-IP limiter fires on an external-relay tenant.
- **Existing suites stay green** (`route.test.ts`, `embed-ip-rate-limit.test.ts`).
- **Manual E2E:** run digichat locally with `DIGICHAT_EMBED_TENANTS` pointing at the live DataTapStream relay; a local test page iframes `/embed`; verify streamed answer, trace box content (file-search queries + cited sources), conversation continuity across turns, no paywall at turn 4, accent + attribution rendering.
- Repo gates: `make score` (all dimensions), human review (network exposure), `frontend/digichat/ARCHITECTURE.md` updated (new sections: embed tenant registry, external relay adapter, revised embed security analysis).

## Process

Per repo rules: file a new GitHub issue (this is explicitly outside Epic #1248's scope, which excludes non-gateway backends), branch `task/<N>-digichat-embed-external-backend` off `module/digichat` (after checking the module branch isn't stale vs develop), PR into `module/digichat`. This spec document rides the task branch.

## Alternatives considered

- **Store tenant config in the existing `tenants` Drizzle table** (the shape initially floated). Rejected for v1: the embed path is deliberately DB-free today (anonymous public traffic never touches Postgres), CSP frame-ancestors must be derivable at build time where the DB isn't reachable, and the existing embed knobs (`DIGICHAT_EMBED_ENABLED`, `DIGICHAT_EMBED_TOKEN`, `EMBED_FREE_TURN_LIMIT`) are already env-based. The env registry delivers the same generalized abstraction with one storage mechanism instead of two. Revisit when an admin UI or double-digit tenant count exists — the `EmbedTenantConfig` type is the stable interface either way.
- **DigiChat speaks to Azure Foundry directly** (native Foundry provider inside digichat). Rejected: duplicates the Foundry client, auth, and `agent_reference` protocol work already built, deployed, and live-debugged in datatap-web's relay; DigiChat stays agent-platform-agnostic behind one small SSE contract.
- **Extract only the chat UI into a shared package** and let each site bring its own backend glue. Rejected by decision: it leaves every consumer maintaining transport/state code, which is the duplication this work exists to remove.
- **Special-case DataTapStream in the route** (carve-out now, generalize later). Rejected by decision in favor of the full per-tenant abstraction.
