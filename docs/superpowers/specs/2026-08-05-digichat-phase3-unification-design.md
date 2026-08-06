# DigiChat Phase 3 unification — design

**Date:** 2026-08-05  
**Status:** Approved (amended 2026-08-05 — Pages-native)  
**Scope:** Phase 3 of the DigiChat unification program — digithings.ai `/chat` uses shared `@digithings/digichat-ui` + digivault Pages Function on the free Cloudflare plan (no Containers, no iframe cutover).

## Amendment (2026-08-05 evening)

**Supersedes** the earlier Phase 3 lock of “iframe → DigiChat Cloudflare Containers at `/embed`.”

Reason: DigiThings Cloudflare account is on the **Workers Free** plan; Containers require **Workers Paid**. Product choice: keep marketing chat on **free Pages** by hosting `DigiChatSession` natively and restoring the digivault Pages Function, rather than pay for Containers or fork OpenNext DigiChat.

Still locked from earlier Phase 3 product intent:

- Visitor URL stays `/chat` with `DtNav` outside the chat pane
- `showByok: true`, `showStatusBar: true`, `layout: "page"`
- Landing quick-ask handoff via `chatHandoff` (same-origin `localStorage` — no postMessage)
- DigiThings has **no Azure**; DataTap ACA is client-only
- Do **not** use `chat.digithings.ai` as the marketing chat host

Deferred (optional later, Paid-only): `frontend/digichat-cloudflare/` Containers scaffold + iframe shell.
*Superseded 2026-08-06 — that scaffold was deleted unused; see ADR-0018 historical note 4.*

## Problem

Phase 1–2 unified activity + digivault inside DigiChat for embed customers (DataTap). Digithings.ai marketing chat still needs a **free**, same-site assistant grounded in digivault. The Containers/iframe approach blocked on Workers Paid. Native digichat-ui + Pages Function restores a working free path without a second DigiChat Node deploy.

## Non-goals

- DigiThings DigiChat on Azure (forbidden)
- Sharing DataTap’s ACA
- Workers Paid / Containers as a Phase 3 merge gate
- Replacing DataTap’s iframe embed path (unchanged)
- Automating GHCR→ACR

## Locked decisions (amended)

1. **Architecture: native** — `/chat` renders `@digithings/digichat-ui` `DigiChatSession` under `DtNav` (no iframe).
2. **Runtime: Cloudflare Pages Function** — `POST /api/chat` (+ `/api/byok/test`) digivault agentic NDJSON stream; secrets `OPENROUTER_API_KEY`, `CORE_SUPABASE_URL`, `CORE_SUPABASE_ANON_KEY` on the Pages project.
3. **Transport:** `useStackChat` + `chatStream` (NDJSON) → `DigiChatController`.
4. **UI flags:** `showByok: true`, `showStatusBar: true`, `layout: "page"` (hardcoded for digithings marketing — not tenant JSON).
5. **Seed:** `readAndClearHandoff()` inside the DigiChatSession wrapper (full transcript + pending).
6. **Cutover:** one PR restores Function + native UI and removes iframe/`ChatEmbedShell` / embed-origin wiring for digithings-web.
7. **Containers scaffold** remains in-tree as **deferred** documentation only — not required to merge or smoke marketing chat. *(Superseded 2026-08-06 — the scaffold was deleted; see ADR-0018 historical note 4.)*

## Architecture

```text
Browser  digithings.ai/chat
  ├─ DtNav
  └─ DigiChatSession (@digithings/digichat-ui)
       └─ useStackChat → POST /api/chat (Pages Function)
            → digivault (Supabase architecture_notes) + OpenRouter free pool / BYOK
            → NDJSON status|tool_*|reasoning|content|done
```

Landing quick-ask → `writeHandoff` → `/chat` → `readAndClearHandoff` → seed controller (+ auto-send pending).

## Components

| Area | Change |
|---|---|
| digithings-web `app/chat/page.tsx` | DtNav + native `DigiChatSession` |
| digithings-web `components/DigiChatSession.tsx` | Controller + BYOK `ProviderSettings` |
| digithings-web `functions/api/chat.ts` | Digivault Pages Function (restored) |
| digithings-web `functions/api/byok/test.ts` | BYOK probe (restored) |
| digithings-web `lib/useStackChat.ts` / `chatStream.ts` / `providerSettings.ts` | Restored |
| digithings-web CSP | `frame-src 'none'` (no iframe) |
| **Delete (digithings-web)** | `ChatEmbedShell`, `digichatEmbed*`, `digichatSeedBridge*` |
| digichat `/embed` | Unchanged (DataTap / customer embeds) |
| digichat-cloudflare | Deferred Paid option — not Phase 3 gate |

## Success criteria

- `https://digithings.ai/chat` renders native session (200)
- `POST https://digithings.ai/api/chat` streams digivault answers when Pages secrets are set
- Landing quick-ask seeds `/chat`
- BYOK settings panel works
- No Workers Paid / Containers required
- DataTap DigiChat embed path unaffected

## Out of scope / follow-ups

- Converging Pages Function digivault with digichat’s TypeScript digivault provider (shared package) — later
- Promoting digithings to Containers + iframe if/when Workers Paid is acceptable
