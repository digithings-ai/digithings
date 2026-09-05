# OpenCode as digichat CLI/TUI foundation — adoption plan

> **Superseded:** [ADR-0028](../adr/0028-digichat-web-foundation-and-opencode-distribution.md)
> rejects OpenCode as digichat's UI/frontend foundation. This file is retained
> as historical research and must not be used as an implementation plan.

**Status:** superseded
**Date:** 2026-09-04  
**Issue:** [#3568](https://github.com/digithings-ai/digithings/issues/3568)  
**Related ADR:** [ADR-0027](../adr/0027-opencode-digichat-cli-foundation.md), superseded by [ADR-0028](../adr/0028-digichat-web-foundation-and-opencode-distribution.md)
**Naming:** Digi product names are always lowercase in prose (`digichat`, `digisearch`, `digivault`, `digigraph`, `digithings`).

This document is the agent-facing plan for adopting **OpenCode** as the CLI/TUI foundation for digichat. It is intentionally **docs-only**: do not replace digichat UI or ship a digichat CLI binary from this plan alone.

---

## 1. Problem

digichat’s product surface is a **Next.js BFF + shared web UI** (`@digithings/digichat-ui` `DigiChatSession`). The UX is terminal-*styled* in the browser (slash palette, help as transcript notes, force-tool headers for digisearch / digivault), but digithings does **not** yet ship a first-class coding-agent-style CLI/TUI.

Rebuilding CLI dogfood from scratch (overlays above the prompt, dismissible help, arrow-key command palette, streaming tool rows, settings dialogs) duplicates years of OpenCode UX investment. Product intent:

- digichat today is primarily **RAG / knowledge**, not a code editor.
- Prefer **adapting OpenCode** for CLI look & interaction over rebuilding digichat UX.
- Keep OpenCode’s **editing / agent** capabilities as a **feature path**, not delete them.
- Must plug into digisearch, digivault, digigraph / OpenFoundry, and existing digichat BFF/auth where relevant.

---

## 2. Goals / non-goals

### Goals

1. Inventory the correct OpenCode project (license, stack, extension surfaces).
2. Rank integration options for digithings agents to implement later.
3. Define how digisearch / digivault / digigraph / Foundry and digichat auth plug in.
4. Recommend a **first spike** (1–3 days) that de-risks the path without replacing web digichat.

### Non-goals (this plan / #3568)

- Shipping a replacement digichat UI or deleting `DigiChatSession`.
- digikey crypto / JWT changes (human gate).
- Live-trading paths.
- Promoting anything to `main`.
- Committing a full OpenCode fork into the digithings monorepo as a submodule in this cycle (document the path only).

---

## 3. OpenCode inventory

### Correct project (do not confuse)

| Project | Notes |
|---------|--------|
| **[anomalyco/opencode](https://github.com/anomalyco/opencode)** | **Canonical.** Active; ~200k★; homepage [opencode.ai](https://opencode.ai). Formerly SST / anomalyco. |
| `opencode-ai/opencode` | Older Go TUI; Charm-related acquisition narrative; **not** the target. |
| `sst/opencode` | Historical rename / redirect path; use `anomalyco/opencode`. |

Local inspection (2026-09-04): shallow clone under `/tmp/opencode-inspect` (MIT allows this). Do not commit that tree into digithings.

### License / stack

| Item | Value |
|------|--------|
| License | **MIT** (`LICENSE`, Copyright 2025 opencode) |
| Language | **TypeScript** |
| Runtime / package manager | **Bun** (`packageManager: bun@1.3.x`, turbo monorepo) |
| Primary TUI toolkit | **OpenTUI** — `@opentui/core`, `@opentui/solid`, `@opentui/keymap` (Solid.js in the terminal; **not** Bubble Tea / Ink) |
| Published npm name | `opencode-ai` (global CLI); scoped packages `@opencode-ai/*` |
| Version sampled | `1.18.27` (workspace packages) |
| Default git branch | `dev` |

### Key packages (monorepo `packages/`)

| Package | Role |
|---------|------|
| `packages/opencode` | CLI entry (`bin/opencode`), yargs commands, session/server orchestration, providers, MCP, LSP, permissions |
| `packages/tui` | `@opencode-ai/tui` — TUI app: command palette, help dialog, prompt, themes, plugin slots |
| `packages/server` | Local HTTP API the TUI/desktop/SDK attach to |
| `packages/core` | Shared session/runtime primitives |
| `packages/plugin` | `@opencode-ai/plugin` — plugin hooks + custom tools + TUI slot types |
| `packages/sdk` / `sdk-next` / `client` | Typed clients for the server (`createOpencode`, `createOpencodeClient`) |
| `packages/ui` / `session-ui` | Shared UI pieces (also used beyond pure TUI) |
| `packages/app` / `desktop` / `web` | Desktop / web surfaces (OpenCode is multi-surface, not TUI-only) |
| `packages/llm` | Model provider routing |

### Architecture sketch (OpenCode)

```text
opencode CLI (yargs)
  ├─ tui / attach / serve / mcp / run / …
  └─ starts or attaches to local server (:4096 default)

TUI (@opencode-ai/tui + OpenTUI/Solid)
  ├─ overlays: DialogHelp, CommandPaletteDialog, theme/model/session selectors
  ├─ prompt + streaming message/tool parts
  └─ plugin slots (host can inject TUI chrome)

Server (HttpApi)
  ├─ sessions, prompts, permissions, files, events (SSE)
  ├─ MCP catalog (local + remote + OAuth)
  └─ provider auth (/connect, auth.set)

Plugins (.opencode/plugins or npm)
  ├─ hooks: tool.execute.*, session.*, message.*, tui.*, …
  └─ custom tools via `tool({ … })`
```

**UX surfaces digithings wants to reuse (not rebuild):**

- Slash / command UX and **command palette** (`command-palette.tsx` → `DialogSelect`, arrow nav, suggested commands).
- Dismissible **help** overlay (`dialog-help.tsx` — esc/enter, mouse “ok”).
- Prompt-adjacent overlays (models, themes, sessions) driven by keymap + dialog stack.
- Streaming transcript with tool-call chrome (session message parts).
- Toast / spinner affordances; hover-like mouse targets where the terminal supports them (`onMouseUp` on help dismiss).

**Extension surfaces useful for digithings:**

1. **MCP** — configure digigraph / digisearch / digivault MCP servers in `opencode.json` (`type: local|remote`, headers, OAuth). Native digithings fit: MCP-first stack.
2. **Plugins** — custom tools that call digichat BFF or digigraph; hooks for force-tool-like behavior; TUI slots for digichat branding.
3. **SDK** — headless `session.prompt` / `event.subscribe` for tests and non-TUI clients.
4. **Agents** — built-in `build` vs `plan` (Tab); digichat “knowledge” mode can map to a read-only / tool-restricted agent that enables MCP search tools and disables (or gates) file-edit tools.
5. **Embedded OpenCode** — in-process client + server (from OpenCode `CONTEXT.md`); relevant if digithings later embeds the runtime inside a digichat sidecar.

### Auth / providers (OpenCode)

- BYOK-style provider keys via `/connect` and `auth.set`.
- OpenCode Zen curated models; many AI SDK providers.
- MCP OAuth stored under OpenCode’s local data dir — **orthogonal** to digikey; do not conflate.

---

## 4. Current digichat contrast

### What digichat is today

| Layer | Location | Notes |
|-------|----------|--------|
| BFF | `frontend/digichat` | Next.js 16; browser never holds digigraph JWT |
| Shared UI | `frontend/digichat-ui` | `DigiChatSession`, activity rows, slash parser |
| Slash | `slash-commands.ts` | `/search`→`digisearch`, `/docs`→`digivault_search_notes`, `/help`, `/new`, `/lang` |
| Force tools | BFF `X-Digi-Force-Tool` | Send-only; embed + app shell |
| Backends | digigraph \| Foundry | Adapters only; digivault/digisearch are **digigraph tools**, not digichat HTTP backends |
| Auth | Auth.js + digichat session | Machine keys hashed; `requireDigiChatAuth()` |

See: [`frontend/digichat/AGENTS.md`](../../frontend/digichat/AGENTS.md), [`docs/architecture/digichat-modular-frontend.md`](digichat-modular-frontend.md).

### Duplicated effort vs OpenCode already solves

| digichat / digichat-ui today | OpenCode already has |
|-----------------------------|----------------------|
| Lightweight slash list under composer | Full command palette + keymap + categories |
| `/help` as transcript note | Modal help dialog + palette discovery |
| Terminal-styled CSS chrome | Native TUI dialogs, themes, keybinds |
| Activity → tool row mapping | Session message parts + permissions UX |
| BYOK settings panel (web) | `/connect`, provider/model selectors |
| (missing) real CLI entry | `opencode` binary, `serve` / `attach`, SDK |

### What digichat must keep (do not throw away)

- Web embed + Pages `/chat` product path and BFF security model.
- Activity protocol / adapter translation (digigraph + Foundry).
- Tenant config (`DIGICHAT_EMBED_TENANTS`), trial/paywall embed gates.
- Force-tool slash semantics for digisearch / digivault (product vocabulary).
- Self-hosted release model (clients run **their** digichat — not a shared SaaS chat).

---

## 5. Integration options (ranked)

### Option A — Fork + rebrand CLI

Clone `anomalyco/opencode`, rebrand as e.g. `digichat` CLI, wire digithings defaults (MCP, agents, theme).

| Pros | Cons |
|------|------|
| Full control of UX and defaults | Permanent fork tax; upstream velocity is very high |
| Can strip or gate code-edit tools for RAG-first | Large maintenance surface (Bun monorepo, OpenTUI, desktop/web too) |
| MIT allows rebrand (note OpenCode’s “not affiliated” naming ask if keeping “opencode” in name) | Risk of diverging auth/provider stacks from digikey/BFF |

**Fit:** only if digithings commits to owning a long-lived fork team. **Not** first move.

### Option B — Embed OpenCode UI / TUI packages

Depend on `@opencode-ai/tui` (and/or SDK) from digithings packages; host a thin digichat shell that supplies digigraph MCP + branding slots.

| Pros | Cons |
|------|------|
| Reuses palette/help/overlays without full fork | Packages may be private/workspace-coupled; publish/semver stability unclear |
| Plugin slots designed for host chrome | Version coupling to OpenTUI + Bun |
| Keeps digithings repo smaller than a fork | Still need a digichat-specific “brain” (digigraph vs OpenCode’s own agent loop) |

**Fit:** medium-term if published packages stabilize; spike should verify **what is actually importable from npm** vs monorepo-only.

### Option C — Port patterns only

Rebuild digichat CLI (or improve web overlays) by copying interaction patterns (palette, help, keymap) without depending on OpenCode code.

| Pros | Cons |
|------|------|
| No upstream dependency | Rebuilds exactly the UX debt product wants to avoid |
| Full control inside React/Next | Weakest reuse of OpenCode |

**Fit:** fallback if B/D prove legally or technically blocked. **Not** preferred.

### Option D — Hybrid: keep web digichat + add OpenCode-based CLI (recommended)

- **Keep** digichat Node BFF + digichat-ui for embeds and `/chat`.
- **Add** an OpenCode-powered CLI path (config + plugins + MCP, optionally a thin wrapper binary) aimed at operators and power users.
- Default CLI agent profile: **knowledge / RAG** (digisearch + digivault MCP via digigraph); file-edit / shell tools available under a **code** profile (future feature path).
- Auth: CLI uses digichat machine API key or digikey-issued scoped key **through** digichat/digigraph HTTP — never invent a parallel crypto path in digikey without human gate.

| Pros | Cons |
|------|------|
| Matches product reality (web RAG first, CLI dogfood second) | Two surfaces to keep slash/command vocabulary aligned |
| Maximum reuse of OpenCode TUI without replacing embeds | Need clear “source of truth” for sessions (digichat DB vs OpenCode local sessions) |
| MCP-native plug-in for digithings tools | Upstream OpenCode breaking changes |
| Editing capabilities retained as optional agent/tools | Branding / naming clarity (`digichat` CLI vs `opencode` dependency) |

**Recommendation:** **Option D**, with a **spike toward B-shaped packaging** (prefer npm/SDK/plugins over a hard fork). Escalate to A only if upstream packaging or licensing/branding blocks rebranded distribution.

---

## 6. How digithings services plug in

```text
digichat CLI (OpenCode TUI + digithings plugin/config)
        │
        ├─ MCP: digigraph tools (preferred) ──► digisearch, digivault_hub, …
        ├─ optional: HTTP to digichat BFF (/api/chat) for parity with web
        └─ optional: Foundry path only for client Azure installs (same adapter story)

Web digichat (unchanged)
        └─ BFF ──► digigraph | Foundry
```

| Capability | Integration |
|------------|-------------|
| digisearch | MCP tool or digigraph tool force; map `/search` slash to OpenCode command or prompt prefix |
| digivault | Same via `digivault_search_notes` / vault MCP |
| digigraph / OpenFoundry | Primary orchestration brain; prefer tool calls through digigraph, not re-implementing graphs in OpenCode |
| Foundry | Client embeds stay on digichat web adapter; CLI spike can defer Foundry unless a client pilot needs it |
| digichat BFF auth | Machine key / session equivalent for CLI; SSRF and credential rules still apply if calling BFF |
| digikey | **No crypto changes.** Reuse existing token exchange / API keys. Human gate if anything in `digikey/` is required |
| BYOK | Align with digichat BYOK story: user provider keys for LLM; digithings tools still auth via stack credentials |

**Session model (open question for spike):**

1. **OpenCode-local sessions** + digigraph tools (fastest spike), or  
2. **digichat conversation IDs** as source of truth (better web/CLI parity, more BFF work).

Spike should pick (1) and document the gap to (2).

---

## 7. Phased implementation plan

### Phase 0 — Decide (this doc / #3568)

- Accept Option D as working recommendation.
- Record ADR-0027 as **proposed** until a spike validates packaging.

### Phase 1 — Spike (1–3 days) — *do next*

See §10. Outcome: spike report comment on #3568 + go/no-go for Phase 2.

### Phase 2 — digichat knowledge CLI MVP

- Ship `digichat` (or `digi chat`) wrapper: OpenCode + checked-in `opencode.json` / plugin for digithings MCP.
- Slash parity: `/search`, `/docs`, `/help`, `/new` (map to OpenCode commands or plugin tools).
- RAG-first agent: edit tools off or permission-gated.
- Docs: install from digichat INSTALL / self-host guides.
- **No** replacement of web UI.

### Phase 3 — BFF / session parity

- Optional: CLI turns create digichat conversations; shared history with embed/`/chat`.
- Align activity vocabulary for tool rows where useful.

### Phase 4 — Code-editing feature path

- Enable OpenCode build agent / file tools for repos that opt in.
- Keep knowledge profile default for digithings.ai-style deployments.

### Phase 5 — Optional deeper embed (B)

- If npm packages are stable: embed `@opencode-ai/tui` in a digithings-owned binary with slots for branding.
- Only then consider a soft-fork (A) for defaults that cannot be expressed via config/plugins.

---

## 8. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Upstream velocity / breakages** — OpenCode moves extremely fast; private workspace packages may not match npm | High | Pin versions; spike proves install from public npm; avoid deep forks early |
| **Dual brain** — OpenCode agent loop vs digigraph supervisor | High | Prefer digigraph (or digichat BFF→digigraph) as tool/LLM authority; treat OpenCode as UI + thin runner in knowledge mode |
| **Auth mismatch** — OpenCode provider auth vs digichat/digikey | Med | Do not touch digikey; document CLI key acquisition via existing digichat machine keys / digikey issue-key |
| **Session split** — local OpenCode DB vs digichat Postgres | Med | Phase 1 accept split; Phase 3 design sync |
| **Scope creep into replacing web digichat** | Med | Explicit non-goal; embeds stay on digichat-ui |
| **Naming / affiliation** — OpenCode README asks clarifying non-affiliation if name contains “opencode” | Low | Prefer `digichat` CLI brand; document dependency |
| **Bun / OpenTUI toolchain** unfamiliar in digithings CI | Med | Isolate CLI package; optional CI job; don’t block digichat Node tests |

---

## 9. Effort estimate (rough)

| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 0 (docs) | 0.5–1 d | This deliverable |
| Phase 1 spike | **1–3 d** | See §10 |
| Phase 2 MVP CLI | 1–2 w | Plugin + config + docs + slash parity |
| Phase 3 session parity | 2–4 w | BFF + auth + conversation mapping |
| Phase 4 code profile | 1–2 w | Mostly config/permissions + docs |
| Phase 5 deep embed / fork | 1–3 mo | Only if MVP proves product pull |

---

## 10. Recommended first spike (1–3 days)

**Goal:** Prove OpenCode can talk to digithings knowledge tools with OpenCode’s TUI (palette/help intact), without forking and without changing digichat web.

**Slice:**

1. Install public `opencode-ai` (pin version) on a developer machine; confirm TUI help + command palette work.
2. Point MCP config at a **local digigraph** (or digisearch MCP if exposed) with a digikey/dev token — read-only search tools only.
3. Add a tiny **plugin** (local `.opencode/plugins` or npm placeholder) that registers `/search`-like custom command or tool wrapper matching digichat semantics.
4. Run 5 manual prompts: free chat, forced search, vault docs query, `/help`, permission denial on file write (knowledge profile).
5. Write a spike report on #3568: what was npm-installable, what required monorepo source, auth approach, and go/no-go for Phase 2.

**Exit criteria:**

- [ ] TUI overlays work out of the box (help + palette).
- [ ] At least one digithings search tool callable from OpenCode.
- [ ] Documented auth path that does **not** change digikey.
- [ ] Explicit recommendation: proceed D→2, pivot to C, or escalate to A.

**Out of spike scope:** digichat BFF conversation sync, Foundry, desktop app, publishing a digithings binary.

---

## 11. Open questions for humans

1. Is the CLI brand `digichat` / `digi` acceptable while depending on OpenCode upstream?
2. Should CLI default LLM traffic go **digigraph → digillm** (stack path) or OpenCode’s native providers with digithings MCP only for tools?
3. Priority of web/CLI shared transcripts (Phase 3) vs shipping knowledge CLI faster (Phase 2 only)?

---

## 12. Links

- OpenCode repo: https://github.com/anomalyco/opencode  
- OpenCode docs: https://opencode.ai/docs/ (plugins, MCP, SDK)  
- digichat modular frontend: [digichat-modular-frontend.md](digichat-modular-frontend.md)  
- digichat-ui slash: `frontend/digichat-ui/src/slash-commands.ts`  
- Issue: https://github.com/digithings-ai/digithings/issues/3568  
