# ADR: Surfaces 1.0 architecture

- Status: proposed (DIG-2694). The CTO accepts or amends it in review.
- Date: 2026-10-10
- Scope: DigiChat, digiquant, DigiVoice and the dashboard, on the TUI and the web.
- Companion: [`parity-matrix.md`](parity-matrix.md). The matrix is the source of truth for scope; this ADR fixes the shape every row is built on.
- Evidence ref: `cursor/ui-surfaces-d8c5` at `35ee78cf8` (PR #4986). `clients/` and `digivoice/tui/` are on that branch, not yet on `develop`.

## Context

Code-presence audit, not run-tested:

- **Three TUIs, two OpenTUI flavours, one non-TUI.** `clients/digichat-tui`, `clients/digiquant-tui` and `clients/digichat-devkit` use `@opentui/react` 0.5.14 on Bun. `digivoice/tui` uses `@opentui/core` ^0.5.10 in plain JS. `digiquant/src/digiquant/cli/` is a Python argparse CLI. It is not a TUI and it is not a parity surface.
- **Shared render models already work.** `clients/digichat-tui/src/wordmark.tsx` imports `packages/ui/src/components/chat/digichat-wordmark.ts`, which is the same cell model the web `DigichatWordmark.tsx` draws. The digiquant TUI tearsheet renders from the shared `finance-tearsheet` model. The pattern is proven. It is just not applied everywhere.
- **The wordmark glyph table is copied four times:** `digivoice/tui/src/hero.js`, `clients/digiquant-tui/src/mark.ts`, `apps/digiquant-web/app/_chrome/QuantWordmark.tsx` and `apps/digithings-web/components/landing/PixelWordmark.tsx`, plus `digiquant-web/components/integrations/digivoice-wordmark.js`. They have the same 7x10 cells and different code.
- **There are two digiquant web desks.** `apps/digiquant-web/app/app/*` imports the TUI catalog, so its pages match by construction. `apps/digiquant-app` (catch-all `[[...path]]`) hand-copies it in `lib/pages.ts` and `lib/nav.ts`, and it drifts (DIG-2700 audit: 1 block TUI-only, 23 web-only).
- **Fonts.** Five `app/fonts.ts` files. Four load `Inter` and `Geist_Mono`. The dashboard loads only `Geist_Mono`. `packages/design/tokens.css` already remaps `--font-sans` to the mono stack on themed surfaces, so on those surfaces `Inter` is loaded and never painted.
- **Endpoints.** `DQ_API_URL ?? "http://127.0.0.1:8788"` is repeated in 8 TUI files. `DIGICHAT_DEVKIT_URL` defaults to `:3000`. The web apps each carry their own. The cloud hosts that exist today are `digithings.ai/api/chat*` and `/api/embed*` (`apps/digichat-cloudflare`), `graph.digithings.ai` and `key.digithings.ai` (`apps/digithings-stack-cloudflare`) and `dashboard-api.chris-stefan.workers.dev`. The dashboard-api `POST /mcp` (`apps/dashboard-api/src/mcp.ts`) is **local `wrangler dev` only**. Its header says that a public hostname is a human gate.
- **Motion.** On the web: `--ease` / `--ease-glide` `cubic-bezier(0.22,1,0.36,1)` with a `linear()` twin, `--duration-hover` 0.18s, `--duration-reveal` 0.6s and `--duration-copied` 1.5s, plus a reduced-motion contract test (`packages/ui/src/styles/reduced-motion.contract.test.ts`). In the TUIs: literal numbers (spinner 80 ms, caret 530 ms, wordmark tick 40 ms, DigiVoice `BUILD_MS` 1400, desk clock 100 ms, welcome type-on 16 ms/char), and **no reduced-motion switch**. The only escape is `DIGICHAT_WORDMARK_MS`, which freezes one wordmark.
- **Chat backends split (matrix C1).** The DigiChat TUI reads `DQ_API_URL` `/chat/sessions/*` on the digiquant runner. The DigiChat web uses its own BFF (`/api/chat`, `/api/v1/chat`, which re-exports the same `POST`, and `/api/conversations`).
- **Dashboard CSP is a closed list** (`apps/dashboard/lib/security-headers.mjs`, mirrored to `apps/digiquant-web/public/_headers`, guard test `security-headers.test.ts:36`). `frame-src` has no digiquant web origin. `connect-src` has no TUI host.

## Decisions

### D1. TUI foundation: OpenTUI on Bun, with shared models in `packages/ui`

- Every Surfaces 1.0 TUI is OpenTUI on Bun. DigiChat and digiquant stay on `@opentui/react`. DigiVoice stays on `@opentui/core` in JS (DIG-2701, already in review). A rewrite buys no parity. All three pin the **same OpenTUI minor**. One bump moves all three.
- Anything both a TUI and a web page draw is a **framework-free TS model** in `packages/ui` that returns cells or lines, not JSX. Web and TUI are thin painters over it. This is the `digichat-wordmark.ts` pattern, which is already shipped. New shared models: `wordmark` (one glyph table and one build/glint timeline for DIGICHAT, DIGIQUANT, DIGIVOICE and DIGITHINGS), `spinner`/`status`, and every desk block formatter that the web also renders.
- DigiVoice JS imports the compiled model, or a generated `glyphs.json`, rather than keeping its own table.
- The Python `digiquant` CLI is out of scope for parity. It stays an operator tool.

### D2. Web layer: one web surface per product, and the catalog is the contract

- Parity pairs: DigiChat TUI ↔ `apps/digichat`. digiquant TUI ↔ `apps/digiquant-app`. DigiVoice TUI ↔ none (TUI-only, with the web hero only on marketing). The dashboard is web-only, and it previews the others.
- `apps/digiquant-web` is the marketing site. Its `/app/*` desk is a preview embed of the same catalog, not a second parity target.
- **The digiquant page/block catalog has one copy.** Move `clients/digiquant-tui/src/catalog.ts` to `packages/ui` (or a `packages/digiquant-catalog`). The TUI, `digiquant-app` and `digiquant-web` all import it. `apps/digiquant-app/lib/pages.ts` and `lib/nav.ts` then derive from it. That removes the drift class instead of fixing rows one by one (DIG-2700).
- The web keeps Next.js and the existing apps. No new framework.

### D3. Chat backend: the DigiChat BFF, for both TUIs (matrix C1, Q6)

- The DigiChat TUI and the digiquant desk chat (TUI and web) talk to the **DigiChat BFF**: `/api/v1/chat` for send and stream, and `/api/conversations` for threads. BYOK (C5), MCP (C6), attachments (C4) and tenant (C10) already live behind that BFF. Wiring the TUI to the runner would mean building them twice.
- The runner `/chat/sessions/*` is no longer a client contract. It may stay as an internal endpoint until nothing calls it.
- The TUI authenticates to the BFF with the same session or bearer the BFF already accepts for `/api/v1`. A terminal-only login, if one is needed, is a device-code hop. It shares the MCP OAuth hop decision in C6.

### D4. One font config

- **The web face is Geist Mono, and no other face is loaded.** `next/font` needs literal options in each app, so a shared import cannot replace `fonts.ts`. Instead, every `app/fonts.ts` is the dashboard's 9-line file: `Geist_Mono`, `subsets: ['latin']`, `variable: '--font-mono-face'`, `display: 'swap'`. A contract test (extending `packages/ui/src/styles/font-tokens.contract.test.ts`) asserts that all of them match that one canonical file byte for byte. `Inter` goes. `--font-stack-sans` already falls back to the mono stack on themed surfaces. DIG-2695 confirms that no un-themed surface paints `--font-sans-face` before it deletes the loader.
- **TUIs cannot choose a font.** The terminal owns it. The TUI "font config" is the pixel wordmark, built from cells and so font-independent, plus a README line ("set your terminal to Geist Mono"). No TUI code depends on the glyph metrics of any font beyond the braille and half-block ranges that the wordmark already uses.

### D5. One local/cloud endpoint config

- A single module, `packages/surface-config/endpoints.ts`, has no dependencies and works on Bun, Node and Next.js server code. It exports `endpoint(service)` for `service ∈ { desk, chat, mcp, graph, stack }`.
- Resolution order: `DIGI_<SERVICE>_URL`, then the profile default for `DIGI_ENV` (`local` | `cloud`, default `local`), then an error. There is no silent fallback to a cloud host.
- The `local` profile is today's ports: desk `http://127.0.0.1:8788`, chat `http://127.0.0.1:3000` (`next dev` default, and the devkit default), mcp `http://127.0.0.1:8787/mcp` (dashboard-api `wrangler dev` default port). Note: the dashboard `frame-src` allows `:3005`, not `:3000`. DIG-2703 pins one port and makes the profile and the CSP agree. The `cloud` profile has only the hosts that exist and are approved: chat `https://digithings.ai`, graph `https://graph.digithings.ai`, desk `https://dashboard-api.chris-stefan.workers.dev`. **cloud `mcp` stays unset** until a public MCP hostname is approved. That is a human gate per `apps/dashboard-api/src/mcp.ts` and goes to DIG-2703 as an [external]/[security] card.
- `DQ_API_URL` and `DIGICHAT_DEVKIT_URL` stay as deprecated aliases for one release, and then they go. Web apps read the same names server-side. Browser code gets only what a route hands it, never a `NEXT_PUBLIC_` copy of the MCP key.
- Every `connect-src` / `frame-src` origin a profile can produce is listed **exactly** in `security-headers.mjs`, and the guard test enforces it. No wildcards. Adding an origin is a security-posture change, so it gets its own reviewed PR.

### D6. Motion tokens: one JSON, generated into CSS and read by the TUIs

- Source: `packages/design/motion.json`. It is plain JSON, so TS, JS, Python (DigiVoice CLI) and Lua (Hammerspoon banner) can all read it:

```json
{
  "ease":      { "house": [0.22, 1, 0.36, 1] },
  "duration":  { "hover": 180, "reveal": 600, "copied": 1500, "build": 1400 },
  "frame":     { "tick": 40, "spinner": 80, "caret": 530, "type": 16, "clock": 100 },
  "reduced":   { "duration": 0, "frame": null }
}
```

- Units: integer milliseconds. Easing is a cubic-bezier 4-tuple. The CSS `linear()` spring twin stays hand-written in `tokens.css` behind `@supports`, because it is a rendering of `house`, not a separate token.
- The web gets it through a small generator, or a contract test, that keeps `--duration-*` and `--ease` in `tokens.css` equal to the JSON. `prefers-reduced-motion` keeps working as it does now.
- **TUI reduced motion:** `DIGI_REDUCED_MOTION=1` (also honoured: `NO_MOTION=1`). When it is set, every animated element draws its **final frame**. The wordmark draws at full build with no glint, the type-on shows the full text, the caret is steady, and the spinner becomes a static `·` with its status text kept. `DIGICHAT_WORDMARK_MS` becomes the test-only freeze it already is in practice.
- This unblocks DIG-2702: the hero banners consume `duration.build`, `frame.tick` and `ease.house` from the JSON on both the web and the TUI.

### D7. Dashboard previews: live iframes for web surfaces, recorded frames for TUIs

- The web previews (DigiChat, digiquant-app) are iframes. Each origin is named exactly in `frame-src` (D5), and the change is approved as its own security PR.
- **TUI previews are not live sockets in 1.0.** The three TUIs are on different runtimes, and a live render needs a `connect-src` host and a server-side PTY. Instead, each TUI exports recorded frames with OpenTUI `captureCharFrame()` (already used in `clients/digiquant-tui` tests). The dashboard renders them as text in Geist Mono. This needs no CSP change, works offline and is safe for screenshots. A live TUI preview is a post-1.0 decision.

### D8. Gloomberb and LuxAlgo/Vela (matrix Q7)

- On the web: they stay behind their flags. Gloomberb is default-off since #5245. Featuring them waits on the DIG-2704 legal and vendor-terms review.
- On the TUI: **link out, no text-mode re-implementation** in 1.0. The page shows its catalog entry, a one-line status and the web URL from `endpoint("desk")`. A text-mode chart is a separate, post-1.0 decision.

## Consequences

- DIG-2695 owns D4 and D6 (the fonts contract, `motion.json` and the TUI reduced-motion switch). DIG-2703 owns D5. DIG-2700 owns the catalog move in D2. DIG-2699 owns D3. DIG-2698 owns D7 and the exact-origin CSP PR. DIG-2702 builds on the shared wordmark model (D1) and the motion tokens (D6). DIG-2704 owns D8.
- Rejected: one web terminal render for all TUIs (three runtimes, CSP cost). A shared `fonts.ts` import (`next/font` needs literal options). Keeping the runner as the DigiChat TUI backend (it duplicates BYOK, MCP and attachments). A CSS-first motion source (TUIs cannot read CSS).
- Open, not decided here: whether `apps/digiquant-web` `/app/*` is eventually removed in favour of linking to `digiquant-app` (CTO). The public MCP hostname (Chris, human gate).
