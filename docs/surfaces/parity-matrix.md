# Surfaces 1.0 parity matrix

Source of truth for Surfaces 1.0 scope (DIG-2693). Architecture: [`adr-surfaces-1-0.md`](adr-surfaces-1-0.md).

- **Basis:** code presence on `cursor/ui-surfaces-d8c5` at `35ee78cf8` (PR #4986). Not run-tested. A row's status changes only on run evidence (a screenshot or a test) posted to its owner ticket.
- **Status words:** `yes` = drawn and wired. `stub` = drawn, not wired. `none` = absent. `n/a` = out of scope by design.
- **Data/API** and **MCP** name the endpoint each side reads. Endpoint names (`desk`, `chat`, `mcp`, `graph`) are the services in ADR D5.
- **Owner ticket** is the sibling that closes the gap. The ticket owns the ETA.

## 1. DigiChat: `clients/digichat-tui` ↔ `apps/digichat`

| # | Feature | TUI | Web | Data / API | MCP | Gap | Owner ticket |
|---|---|---|---|---|---|---|---|
| C1 | Chat backend | runner `desk` `/chat/sessions/*` | BFF `/api/chat`, `/api/v1/chat`, `/api/conversations` | ADR D3: `chat` BFF for both | — | TUI moves to the BFF | DIG-2699 |
| C2 | Send/stream, tool calls, reasoning | yes (fold, spinner, stop) | yes (assistant-ui, tool-fallback) | `chat` `/api/v1/chat` | — | parity after C1 | DIG-2699 |
| C3 | Threads/sessions | yes (list, title, history skeleton) | yes (memory-thread-list) | `chat` `/api/conversations` | — | same data after C1 | DIG-2699 |
| C4 | Attachments | stub: path collected, **dropped on send** | yes | `chat` | — | needs a send path | DIG-2699 |
| C5 | Provider/BYOK, models | stub (`/provider`, `/models`) | yes (`byok-cli-flow`) | `chat` `/api/byok/*` | — | wire to `/api/byok` | DIG-2699 |
| C6 | MCP connectors, tools | stub ("No MCP servers.") | yes (OAuth, tool-catalog bar, embed catalog) | `chat` `/api/mcp/oauth/*` | session MCP list | list first. The OAuth hop is a device/browser hop (ADR D3) and may slip | DIG-2699 |
| C7 | Settings (lang, view, thinking, effort, search) | yes (palette) | yes (session-prefs) | `chat` | — | check against the web prefs schema | DIG-2699 |
| C8 | Charts (echarts, quant strip) | none | yes | `chat` | — | "open in web" link. ASCII render may slip | DIG-2699 |
| C9 | Voice | n/a ("not available in the terminal") | 1 reference | — | — | n/a by design: DigiVoice owns voice | — |
| C10 | Tenant, embed config, auth | none | yes (`/api/embed/tenant-config`, NextAuth) | `chat` | — | dev-env builder | DIG-2696 |
| C11 | Export, `@` mentions, `/` palette | yes | yes | — | — | probably equal; check | DIG-2699 |
| C12 | Wordmark/hero, font | truecolor wordmark (shared `digichat-wordmark.ts`) | Geist Mono via `fonts.ts` | — | — | shared tokens + banner | DIG-2695, DIG-2702 |

## 2. digiquant: `clients/digiquant-tui` ↔ `apps/digiquant-app`

`apps/digiquant-web` is the marketing site. Its `/app/*` desk imports the TUI catalog and is a preview, not a parity target (ADR D2). The root fix for drift is the single catalog in ADR D2. DIG-2700's audit (document `digiquant-parity-audit`) has the per-block detail.

| # | Page / feature | TUI | Web (`digiquant-app`) | Data / API | MCP | Gap | Owner ticket |
|---|---|---|---|---|---|---|---|
| Q0 | Page/block catalog | `src/catalog.ts` | hand copy in `lib/pages.ts`, `lib/nav.ts` | — | — | one catalog, imported by all (ADR D2) | DIG-2700 |
| Q1 | Brief | yes (`brief.tsx`) | yes | `desk` | `mcp` brief tool | check that the blocks match | DIG-2700 |
| Q2 | Portfolio, holdings, attribution, ledger, theses, tearsheet | yes (#5047: as-of, staleness) | yes | `desk` | `mcp` per route | check that the blocks match | DIG-2700 |
| Q2b | Performance page | yes (`/performance`) | none | `desk` | `mcp` | add to the web | DIG-2700 |
| Q3 | Pipeline | yes | yes | `desk` | `mcp` | check that the blocks match | DIG-2700 |
| Q4 | Strategies, detail, deploy | yes; detail has `st-tearsheet`; deploy is plan/draft only | yes; **no `st-tearsheet`** (4 blocks vs 5) | `desk` | `mcp` | add tearsheet to the web; confirm deploy scope matches | DIG-2700 |
| Q5 | FX Hub (summary, ideas, watch, rates, settings) + twelve-x group lock | yes (`access` in rail + command) | yes (locked by access) | `desk` | `mcp` | check the lock behaves the same | DIG-2700 |
| Q6 | Chat (`/tools/chat`) | page + rail threads | "wip" (`ch-*` ×4) | `chat` BFF (ADR D3) | — | both on the DigiChat BFF | DIG-2699 + DIG-2700 |
| Q7 | Terminal (Gloomberb), Charts (Vela/LuxAlgo, `mk-*` ×9) | none ("browser pages") | "soon"; Gloomberb default-off (#5245) | vendor | — | TUI links out (ADR D8). Web featuring gated on legal | DIG-2704 |
| Q8 | Settings, paper trading (`se-*` ×4) | `/fx/settings` only | `/settings`, `/settings/paper` | `desk` | — | add a TUI settings page | DIG-2700 |
| Q9 | Integrations band, MCP band (`McpCli`), live portfolio island | none | yes | `desk`, `mcp` | `mcp` | MCP endpoint → DIG-2703; integrations → DIG-2704 | DIG-2703, DIG-2704 |
| Q10 | Command search | yes (`command.ts`) | yes (`desk-command-search`) | — | — | probably equal | DIG-2700 |
| Q11 | Nav model | groups Desk/Portfolio/Strategies/FX Hub | tool groups with `wip`/`soon` + `lock` | — | — | derive both from the one catalog (Q0) | DIG-2700 |
| Q12 | Chrome (`sh-*` ×6) | own header + `mark.ts` | yes | — | — | shared chrome model | DIG-2700, DIG-2695 |
| Q13 | Mark/hero, font | `mark.ts` (copy of the web glyphs) | `QuantWordmark`, `fonts.ts` | — | — | shared wordmark model (ADR D1) | DIG-2702, DIG-2695 |

## 3. DigiVoice: `digivoice/tui` (TUI-only)

`@opentui/core` in plain JS (ADR D1). DigiVoice has no web app. Its web presence is the marketing hero (`apps/digiquant-web/components/integrations/digivoice-hero.tsx`). Foundation work is DIG-2701 (in review).

| # | Feature | TUI | Web | Data / API | MCP | Gap | Owner ticket |
|---|---|---|---|---|---|---|---|
| V1 | Home / menu (`/digivoice`) | yes | n/a | local Python CLI (`digivoice`) | — | — | DIG-2701 |
| V2 | History, copy, delete (`/history/*`) | yes | n/a | local history store | — | — | DIG-2701 |
| V3 | Settings (`/settings`), replace rules | yes | n/a | local config | — | — | DIG-2701 |
| V4 | System: doctor, logs, update, reload, restart, reset | yes | n/a | local CLI | — | — | DIG-2701 |
| V5 | Hero wordmark | yes (`hero.js`, `BUILD_MS` 1400, own glyph table) | marketing hero (`digivoice-wordmark.js`, another copy) | — | — | one wordmark model + `motion.json` (ADR D1, D6) | DIG-2702 |
| V6 | Reduced motion | none | `prefers-reduced-motion` on the marketing hero | — | — | `DIGI_REDUCED_MOTION` (ADR D6) | DIG-2695 |
| V7 | Endpoint config | `DIGIVOICE_TUI_START` only; local-only | n/a | — | — | none needed in 1.0 (no remote service) | — |

## 4. Dashboard: `apps/dashboard` (web-only)

The dashboard has no TUI. Its parity question is real data (DIG-2697) and previews of the other surfaces (DIG-2698).

| # | Page / feature | TUI | Web | Data / API | MCP | Gap | Owner ticket |
|---|---|---|---|---|---|---|---|
| D1 | Brief (`/`), portfolio + attribution, ledger, performance, period, theses, tickers | n/a (the digiquant TUI covers the desk) | yes | Supabase + `desk` (`dashboard-api`) | `mcp` (`dashboard-api` `POST /mcp`, local only) | real data, no mocks | DIG-2697 |
| D2 | Pipeline, strategy, research (+ `/research/vela-spike`), library | n/a | yes | Supabase + `desk` | `mcp` | real data; Vela spike follows ADR D8 | DIG-2697, DIG-2704 |
| D3 | System, observability, architecture, house | n/a | yes | Supabase, Langfuse | — | real data | DIG-2697 |
| D4 | twelve-x FX hub (`/twelve-x`) | n/a | yes (access-gated) | `desk` | `mcp` | real data; same lock as Q5 | DIG-2697 |
| D5 | Settings, broker callback | n/a | yes | Supabase | — | real data | DIG-2697 |
| D6 | Auth (login, signup, callback, invite) | n/a | yes | Supabase auth | — | — | DIG-2697 |
| D7 | DigiChat popup | n/a | yes (`digichat-popup.ts`; `frame-src` allows `digichat.digithings.ai`, `:3005`) | `chat` | — | align the local port with the profile (ADR D5) | DIG-2703 |
| D8 | Live preview: DigiChat, digiquant-app | n/a | none | iframe | — | exact-origin `frame-src` PR, its own security review (ADR D7) | DIG-2698 |
| D9 | Live preview: TUIs | n/a | none | recorded `captureCharFrame()` frames | — | no live socket in 1.0 (ADR D7) | DIG-2698 |
| D10 | Mark, Gloomberb mark, font | n/a | `dashboard-mark.tsx`, `gloomberb-mark.tsx`; Geist Mono only (canonical `fonts.ts`) | — | — | shared wordmark model; the dashboard's `fonts.ts` is the canonical file (ADR D4) | DIG-2695, DIG-2702 |

## 5. Cross-cutting rows

| # | Item | TUI | Web | Config / endpoint | Gap | Owner ticket |
|---|---|---|---|---|---|---|
| X1 | Hero banners (DIGICHAT, DIGIQUANT, DIGIVOICE, DIGITHINGS) | 3 painters, 2 glyph tables (`hero.js`, `mark.ts`) + shared `digichat-wordmark.ts` | 5 painters (`DigichatWordmark`, `QuantWordmark`, `PixelWordmark`, `FooterWordmark`, `digivoice-wordmark.js`) | `motion.json` `duration.build`, `frame.tick`, `ease.house` | one wordmark model, one timeline, reduced-motion final frame | DIG-2702 |
| X2 | Font | terminal-owned; README says Geist Mono | 5 `fonts.ts`, 4 load unused `Inter` | canonical `apps/dashboard/app/fonts.ts` + contract test | drop `Inter`; byte-identical `fonts.ts` | DIG-2695 |
| X3 | Motion tokens | literals; no reduced-motion | `tokens.css` vars + reduced-motion contract | `packages/design/motion.json` | generate/verify CSS; `DIGI_REDUCED_MOTION` in TUIs | DIG-2695 |
| X4 | Local/cloud endpoint config | `DQ_API_URL` ×8, `DIGICHAT_DEVKIT_URL` | per-app env | `packages/surface-config/endpoints.ts`, `DIGI_ENV`, `DIGI_<SERVICE>_URL` | build the module; alias old names for one release | DIG-2703 |
| X5 | Cloudflare API hosts | — | — | `digithings.ai/api/chat*`, `/api/embed*` (digichat worker); `graph.`, `key.digithings.ai` (stack); `dashboard-api.chris-stefan.workers.dev` | list them exactly in the `cloud` profile and the CSP | DIG-2703 |
| X6 | Cloudflare MCP endpoint | — | — | `dashboard-api` `POST /mcp` (`x-digi-mcp-key`, fail-closed); `/_stack/mcp` precedent | **no public host**: human gate, [external]/[security] card | DIG-2703 |
| X7 | Gloomberb | link out (ADR D8) | flagged, default-off (#5245) | vendor | legal/vendor terms | DIG-2704 |
| X8 | LuxAlgo / Vela | link out (ADR D8) | `vela-pane.tsx`, `/research/vela-spike`, "soon" | vendor | legal/vendor terms | DIG-2704 |
| X9 | CSP | — | closed list (`security-headers.mjs`, mirrored to `digiquant-web/_headers`) | exact origins only, guard test `security-headers.test.ts:36` | every new origin is its own reviewed PR | DIG-2698, DIG-2703 |
