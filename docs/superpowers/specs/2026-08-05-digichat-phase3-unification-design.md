# DigiChat Phase 3 unification — design

**Date:** 2026-08-05
**Status:** Approved
**Scope:** Phase 3 of the DigiChat unification program — `digithings.ai/chat` iframe cutover onto digichat `/embed`, digithings-owned digichat runtime, postMessage handoff seed, and retirement of the Cloudflare Function + `useStackChat` + `chatStream`, shipped as **one PR**.

## Problem

Phase 1 shipped the shared `ActivitySpan` vocabulary. Phase 2 ported digivault into the digichat container and retired digigraph dual-emit, so auth and embed share one activity chain. Digithings.ai still runs a second chat stack:

1. **Native `/chat`** in `digithings-web` talks to `frontend/digithings-web/functions/api/chat.ts` (Cloudflare Pages Function) via `useStackChat` / `chatStream`.
2. **Cross-tab quick-ask handoff** (`chatHandoff.ts`) writes localStorage that only the same-origin native page can read — an iframe on another origin cannot see it.
3. Embed UI flags that Phase 1 locked for Phase 3 (`showByok`, `showStatusBar`, `layout: "page"`, mermaid) are still derived or hardcoded on the embed path (`showByok = !ungated`, `showStatusBar = false`, `layout` always embed-ish).

Until digithings points at digichat and deletes the CF path, “one runtime” is still two runtimes for the marketing site.

## Non-goals

- **ACR automation** — GHCR→ACR mirror stays manual (existing ops risk; call out in rollout checklist). Automating `az acr import` after `publish-digichat-image` is a separate follow-up, not Phase 3.
- **Sharing DataTap’s Azure Container App** — digithings gets its **own** digichat install from the same DigiChat GitHub/GHCR release DataTap uses. Not co-hosting on DataTap’s ACA unless a later ops decision explicitly says so (out of scope here).
- **DataTap gate / trial_form changes** — leave DataTap tenant `gateMode`, turn limits, and `datatap:gated` / `datatap:unlocked` alone.
- **Accent bug** — already fixed on develop (`720f96c8` / #1854); do not relitigate.
- **Relitigating Phase 1 / Phase 2** — activity allowlist, digivault env-name secrets, dual-emit deletion, fixture parity, and pluggable providers stay as shipped.
- Building a shared digithings-web “controller” abstraction — Phase 1 locked: `useStackChat` dies here; do not scaffold a replacement shared hook for a consumer we are removing.
- Standing up an OTLP collector or exporting spans (unchanged since Phase 1).

## Program context

Inherited from Phase 1 (`docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md`) and Phase 2 (`docs/superpowers/specs/2026-08-05-digichat-phase2-unification-design.md`). Do not relitigate:

| Phase | Scope | Ships |
|---|---|---|
| 1 (done) | Activity contract + Foundry enrichment | digichat release — DataTap chain gets rich |
| 2 (done, ~`8f56e178`) | Digivault provider + digigraph rich mapping; dual-emit deleted | digichat PR; CF Function still live |
| 3 (this spec) | `digithings.ai/chat` → iframe; retire CF Function + `useStackChat` + `chatStream` | **one runtime** for digithings visitors |

Also inherited:

- Shared backend means **pluggable providers**, not one assistant — digithings tenant uses `backend: { type: "digivault", … }` with per-tenant env-name refs from Phase 2.
- Presentation allowlist is `ActivitySpan` / `sanitizeActivitySpan`.
- `activityDetail` is gated **server-side** before write.
- Landing quick-ask handoff survives via **parent postMessage** (keep even for same-origin iframe — required protocol; DataTap stays cross-origin).

## Locked decisions

Recorded from the Phase 3 brainstorm (2026-08-05). Status: **Approved**.

1. **Architecture: iframe** — digithings.ai keeps URL `/chat` and `DtNav`; the chat pane is digichat `/embed` in a full-height iframe. Hard redirect away from digithings.ai and dual-path forever are rejected.
2. **Runtime: DigiChat on Cloudflare Containers** — DigiThings CF account; path `https://digithings.ai/embed` (+ APIs / `/_dtchat` assets). **Not** Azure (DigiThings has none). **Not** DataTap’s ACA. **Not** `chat.digithings.ai`. Leave `DIGICHAT_BASE_PATH` unset; use `DIGICHAT_ASSET_PREFIX=/_dtchat`.

3. **Cutover: ONE PR** — iframe shell + delete Cloudflare Function, `useStackChat`, and `chatStream` together. No sequenced “iframe first, delete later” and no long-lived feature-flag dual path in this phase.
4. **gateMode: `ungated`**; **`showByok: true`** — independent flags. Do **not** derive `showByok = !ungated` (today’s embed/page.tsx bug relative to this design).
5. **activityDetail: `full`** — rich chain including documents/brief for digithings marketing chat.
6. **layout: `page`**; **`showStatusBar: true`**; mermaid via existing `@digithings/digichat-ui` (confirm embed path renders it; no new mermaid package work).
7. **postMessage:** digichat-generic `digichat:ready` → `digichat:seed` (not DataTap-specific message names).
8. **Seed:** full transcript + pending (parity with `ChatHandoff`: `messages` + `pending`).
9. **Auth: first-party host allowlist** — `digithings.ai` (and `www.digithings.ai` if needed) may embed **without** an embed token when `host` matches the allowlist. Customer embeds (e.g. DataTap) **still require** a tenant token.
10. **Parent chrome:** `DtNav` (and digithings page chrome) stay **outside** the iframe; digichat `layout="page"` fills the content area.
11. **BYOK UX:** digichat embed’s existing BYOK / settings panel with `showByok: true` + `layout: "page"` — no digithings-specific parent settings chrome in Phase 3.

## Architecture

```text
Browser  digithings.ai/chat
  ├─ DtNav + page chrome (parent)
  └─ iframe src = {DIGICHAT_ORIGIN}/embed?host=https://digithings.ai
       │         (no token for first-party allowlisted host)
       │
       ├─ digichat emits postMessage { type: "digichat:ready" } → parent (origin-checked)
       └─ parent posts { type: "digichat:seed", messages, pending, ts }
            → embed validates origin + payload → seeds controller (+ auto-send pending)

Chat turns:
  iframe → POST digichat /api/chat
       → digivault backend (Phase 2) + activityDetail: full
       → data-digichatActivity + text (AI SDK UI stream)
```

### Digithings-web shell

- Replace native `DigiChatSession` / `useStackChat` wiring on `app/chat/page.tsx` with a thin shell: site chrome + iframe.
- Keep `chatHandoff.ts` write API for the landing quick-ask; the `/chat` parent reads-and-clears and posts seed into the iframe (never expects the iframe to read digithings.ai `localStorage`).
- CSP / `_headers`: allow digichat origin in `frame-src`. Digichat CSP `frame-ancestors` must already (or as part of this PR) allow digithings.ai / www.

### Digichat embed / tenant

- Register a digithings tenant keyed by hostname (`digithings.ai`, alias `www.digithings.ai` if used), with:

```ts
{
  slug: "digithings", // exact slug is implementation-plan detail if already reserved
  gateMode: "ungated",
  showByok: true,       // NEW explicit tenant/UI field — not derived from gateMode
  showStatusBar: true,  // NEW — stop hardcoding false on embed
  layout: "page",       // NEW tenant (or URL) flag — page chrome inside iframe content
  activityDetail: "full",
  backend: {
    type: "digivault",
    supabaseUrlEnv: "...",      // env NAME refs only (Phase 2)
    supabaseAnonKeyEnv: "...",
    openRouterKeyEnv: "...",
  },
  // token: still required in registry schema for customer tenants;
  // first-party allowlisted hosts skip token presentation at request time
}
```

- Exact field placement (`EmbedTenantConfig` vs URL query params) for `showByok` / `showStatusBar` / `layout` is an **implementation-plan** detail; product rule is fixed: values come from config, never `showByok = !ungated`.
- First-party allowlist is a small, explicit set of hostnames (prod: `digithings.ai`, `www.digithings.ai` if needed). Preview `*.pages.dev` hosts are **not** on the default allowlist; add only if the implementation plan requires preview embeds, and document each host.

### Runtime / deploy

- Digithings digichat is a separate install (ACA or equivalent) pulling the DigiChat image from GHCR (same release tags DataTap uses).
- Hostname decision (`chat.digithings.ai` CNAME vs ACA default hostname) deferred to the **implementation plan** and ops checklist.
- Manual GHCR→ACR mirror remains an ops risk if the digithings install also pulls from ACR; call it out in rollout — do not pretend Phase 3 automates it.

## Components

| Area | Change |
|---|---|
| digithings-web `app/chat/page.tsx` | Shell: DtNav + full-height iframe; drop native DigiChatSession / stack-chat wiring |
| digithings-web `lib/chatHandoff.ts` | Keep write + readAndClear APIs; parent posts seed (iframe never reads this storage) |
| digithings-web CSP / `_headers` | `frame-src` allowlist for digichat origin |
| digichat `embed/page.tsx` | Emit `digichat:ready`; accept `digichat:seed`; honor `showByok` / `showStatusBar` / `layout` from tenant/config (not `!ungated`) |
| digichat `embed-tenants.ts` (+ related auth) | First-party host set skips token; digithings tenant + digivault `*Env`; UI flag fields |
| digichat seed helper (new small module) | Validate origin + payload caps; apply `messages` + auto-send `pending` |
| digichat-ui | No new package surface required for Phase 3 beyond confirming mermaid + page layout + BYOK/status bar already work when flags are true |
| **Delete** | `frontend/digithings-web/functions/api/chat.ts`, `lib/useStackChat.ts`, `lib/chatStream.ts`, and dead native wiring that only those serve |

## Handoff flow

1. Landing quick-ask escalates → `writeHandoff(messages, pending)` on digithings.ai origin (unchanged writer).
2. Browser opens `/chat` (same origin) → parent mounts iframe to digichat `/embed?host=https://digithings.ai`.
3. Parent calls `readAndClearHandoff()` once (same expiry / shape rules as today: `messages`, `pending`, `ts`, max age).
4. Embed loads → posts `{ type: "digichat:ready" }` to `parent` with target origin digithings.ai (implementation plan picks exact payload shape; type string is locked).
5. Parent, origin-checking `event.origin` against the configured digichat origin, posts:

   `{ type: "digichat:seed", messages, pending, ts }`

6. Embed validates origin (must be digithings.ai / www allowlist), validates payload (roles/content strings, size caps — caps are **implementation-plan** numbers), seeds the chat controller with full transcript, and auto-sends `pending` when non-empty.
7. Timeout waiting for ready, or malformed/stale handoff → **fresh empty chat** (no silent hang). Origin mismatch → **ignore** message.

DataTap’s `datatap:gated` / `datatap:unlocked` channel is unrelated and unchanged; Phase 3 adds a parallel digichat-generic seed channel.

## Error handling

- **Origin mismatch** on ready/seed → ignore; do not apply seed.
- **Malformed or over-cap seed** → drop seed; parent/embed fall back to fresh chat (no partial poison of the controller).
- **Ready timeout** → parent shows a recoverable error or empty chat CTA (implementation plan picks copy); **no silent blank iframe** without affordance.
- **Iframe load failure** (network / 5xx document) → parent error UI.
- **Digivault env unresolved** → existing Phase 2 fail-closed safe 503 (`chat_not_configured`); no raw env names or secrets to the browser.
- **First-party bypass** only for allowlisted hosts; any other embed host still requires a valid tenant token (fail closed).
- Upstream / stream errors inherit Phase 1–2 disclosure rules (generic browser message + server log).

## Testing

- **Unit — digichat:** ready/seed message validators; first-party auth (allowlisted host without token succeeds; non-allowlisted without token fails; customer token path unchanged); `showByok` / `showStatusBar` / `layout` independent of `gateMode === "ungated"`.
- **Unit — digithings-web:** handoff read/clear still works; shell builds iframe URL with `host` and **without** token for first-party; seed postMessage only after ready and only to configured digichat origin.
- **CSP:** digithings `frame-src` includes digichat origin; digichat `frame-ancestors` includes digithings.ai (and www if used).
- **Manual / smoke:** landing quick-ask → `/chat` seeded turn; BYOK panel visible under ungated; mermaid render; mobile layout under DtNav; activity chain at `full` (documents/brief); confirm CF `/api/chat` is gone (404 / no function).
- **Regression:** DataTap embed still requires token + existing gate behavior; no digithings first-party bypass for datatap hosts.

## Rollout

Ops may lag the code PR; the **code cutover is still one PR** (shell + deletes together).

1. Stand up digithings-owned digichat from DigiChat GHCR release; set digivault env vars; register digithings tenant + first-party allowlist. (**Hostname** deferred to implementation plan.)
2. Land digithings-web shell + digichat seed / first-party / UI-flag changes in **one PR**; delete CF Function, `useStackChat`, `chatStream`.
3. Smoke prod (or staging equivalent): handoff, BYOK, activity full, DtNav chrome.
4. **Rollback:** revert that PR (restores digithings-web native path + prior digichat if needed). There is no soft dual-path left in-tree after merge.
5. Preview `*.pages.dev` hosts: default **prod hosts only** on the first-party allowlist; extend only if the implementation plan explicitly needs preview embeds.
6. **Ops risk (non-goal to fix here):** if digithings digichat pulls via ACR, manual GHCR→ACR mirror remains required after each digichat release — checklist item, not Phase 3 scope.

## Success criteria

- Digithings visitors use **one chat runtime** (digichat container digivault provider) for `/chat`.
- Landing quick-ask handoff works **cross-origin** via `digichat:ready` → `digichat:seed` with full transcript + pending.
- Cloudflare Function, `useStackChat`, and `chatStream` are **deleted** (no dead imports / unused native chat page path).
- digithings.ai embeds **without** a customer-style embed token; DataTap and other customers still require tokens.
- `showByok: true` with `gateMode: "ungated"` (flags independent); `layout: "page"`; `showStatusBar: true`; `activityDetail: "full"`.
- DtNav remains parent chrome outside the iframe.
- Mermaid works on the embed path via existing digichat-ui.

## Spec self-review

1. **Placeholders / deferred (explicit):** digichat public hostname (`chat.digithings.ai` vs ACA URL); numeric seed payload caps; exact `showByok`/`showStatusBar`/`layout` config surface (tenant JSON vs URL); ready/timeout UI copy; whether `www` is required; preview `*.pages.dev` allowlisting (default: prod-only). No vague product TBDs — each is implementation-plan work.
2. **Consistency:** One PR cutover; digithings-owned install from same GHCR release; not DataTap ACA; first-party no token; `showByok` independent of ungated; seed = full transcript + pending; ACR automation called out as non-goal/ops risk.
3. **Scope:** Phase 3 only — does not reopen Phase 1/2 contracts, DataTap gates, or accent work.
4. **Ambiguities resolved:** iframe (not hard redirect); digichat-generic postMessage names; parent DtNav; BYOK inside embed; delete CF path in the same PR as the shell.
