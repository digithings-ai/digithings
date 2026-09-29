# digichat UI & package simplification — review notes

**Status:** preparation only. No code changed. This is the evidence base for a
plan to be written next; every finding below was observed directly in this
checkout, with paths.

**Question being answered:** the UI is spread across `design/`, `styles/`,
`docs/` and several `ui` paths and is hard to follow. Can it be simplified,
deslopped and productionalised so it scales — without losing features?

## Verdict

The **layering is already right**; the **ownership is leaky**.

`packages/*` = shared UI + design system, `apps/digichat` = product + BFF is
exactly the "UI in one place, deployment in another" shape that was expected.
The problem is that the boundary is crossed in both directions:

- a **package re-exports a file that lives in an app**
  (`packages/ui/src/styles/chatbot.css` → `../../../../apps/reference/.../chatbot.css`);
- an **app route folder is the shared component library for all skins**
  (`apps/digichat/src/app/(baseline)/stock/` is imported by 10+ skins);
- **skins and their registry live in the app** while the Thread they mount
  lives in the package;
- **three palettes and three bridges** describe the same product.

So the fix is not "move the UI into one folder". It is **move ownership down**
(theme, skins, primitives → package) and **collapse duplicated surfaces**.

---

## Current ownership map

| Concern | Lives today | Should live |
|---|---|---|
| Design tokens (`--bg/--ink/--term-*`, `[data-theme]`) | `packages/design/tokens.css` | unchanged |
| Tailwind v4 `@theme inline` bridge | `packages/ui/src/styles/web-theme.css` | unchanged |
| digichat skin palette (`.digichat-thread` dark/light + portal mirrors) | `packages/ui/src/styles/chat-aui.css` | merge into one theme file |
| digichat theme **grammar** (caret, radii, composer, markdown, tooltips) | `apps/reference/app/(chatbot)/chatbot/chatbot.css`, re-exported by a 4-line package shim | **move into `packages/ui/src/styles/`** |
| First-party Thread + DotMatrix + caret + boot loader | `packages/ui/src/components/chat/` | unchanged |
| 12 skins + registry + dispatch | `apps/digichat/src/components/assistant-ui/skins/`, `apps/digichat/src/lib/thread-skins.ts` | **move into the package** |
| Shared primitives for the catalog skins | `apps/digichat/src/app/(baseline)/stock/` | **move out of a route folder** |
| Product shell, chrome bar, deploy UI context | `apps/digichat/src/components/stock/` | unchanged (app chrome) |
| BFF, auth, config, deployment | `apps/digichat/src/app/api/`, `src/lib/` | unchanged |

---

## Findings

### F1 — A package reaches into an app for its stylesheet (most clearly wrong)

`packages/ui/src/styles/chatbot.css` is four lines:

```css
@import "../../../../apps/reference/app/(chatbot)/chatbot/chatbot.css";
```

The canonical first-party theme sheet physically lives in `apps/reference` and
`packages/ui` imports it by relative path. A published package cannot depend on
an app's file tree; the file only works because the monorepo checkout has that
layout, and it is pinned by
`packages/ui/src/components/chat/chatbot-css.share.test.ts`.

**Direction:** move the sheet into `packages/ui/src/styles/` as the real file
(e.g. `chat-digichat.css`) and have `apps/reference` import *it*. Delete the shim.

### F2 — Three palettes, three bridges, one product

The digichat look is described in at least three places that can (and did)
disagree:

1. `packages/design/tokens.css` — `[data-theme="dark"|"light"]` semantic palette.
2. `packages/ui/src/styles/chat-aui.css` — `.digichat-thread` palette + the
   `html:has([data-thread-skin="digichat"])` portal mirrors.
3. `apps/reference/.../chatbot.css` — the `:is(.aui-theme-stage, [data-thread-skin="digichat"])`
   grammar, which re-declares `--accent/--on-accent/--radius/--composer-radius`.

On top of that, **two app entry sheets each re-declare their own `@theme inline`
bridge** instead of importing the shared one: `apps/digichat/src/app/(digichat)/globals.css`
and `apps/digichat/src/app/(baseline)/baseline.css` (both bypass
`web-theme.css` and `tokens.css`).

This is the direct cause of several bugs already fixed this session (the white
composer, the black light-mode, the missing Geist Mono).

**Direction:** one digichat theme entry point in the package that owns palette +
grammar; app globals import the shared bridge rather than forking it.

### F3 — Primitive duplication (tooltip, tooltip button, caret)

Confirmed by file listing:

- `tooltip.tsx` × 4 real: `packages/ui/src/ui/tooltip.tsx`,
  `packages/ui/src/components/chat/gallery-thread/ui/tooltip.tsx` (a 34-line
  adapter whose only job is to hide the arrow),
  `apps/digichat/src/app/(baseline)/stock/ui/tooltip.tsx`,
  `apps/digichat/src/components/ui/tooltip.tsx` (+ 4 vendored copies under
  `apps/digichat/reference/assistant-ui-templates/`).
- `tooltip-icon-button.tsx` × 3 real: `packages/ui/src/components/chat/gallery-thread/`,
  `apps/digichat/src/app/(baseline)/stock/`,
  `apps/digichat/src/components/assistant-ui/skins/`.
- Carets × 3: `.dt-cur` (`packages/digichat-ui/src/styles/cursor.css`),
  `.chat-cursor` (`packages/ui/src/styles/chat-core.css`), and the painted
  `aui_block-caret` (`block-caret.tsx` + `chatbot.css` + `product-chrome.css`).

The gallery tooltip adapter is fragile by construction: it suppresses the arrow
with a Tailwind arbitrary variant (`[&>[aria-hidden]]:hidden`) that is only
emitted if Tailwind happens to scan the package — which is exactly the bug that
produced the hover "diamonds" this session.

**Direction:** give the kit tooltip a `hideArrow` prop and delete the adapter
(the adapter's own docstring says it should collapse to a bare re-export);
consolidate on one `TooltipIconButton` and one caret primitive.

### F4 — An app **route folder** is the shared library for all skins

`apps/digichat/src/app/(baseline)/stock/` is imported by the clone skins
(`chatgpt`, `claude`, `grok`, `gemini`, `perplexity`, `react-ink`,
`expo-react-native`), by `skins/base/thread.tsx` and its `elements/` + `ui/`,
and by `product-page-assistant` / `webpage-assistant`. It is a vendored
assistant-ui primitive layer sitting inside the `/baseline` route group.

**Direction:** move it under the skin system (or the package). A route group
should not be a dependency of ten components.

### F5 — The skin system is app-owned but the Thread is package-owned

`packages/ui` exports `@digithings/ui/chat/thread`, but the registry
(`lib/thread-skins.ts`), the dispatch (`skins/index.tsx`) and all 12 skin
components live in `apps/digichat`. No other app can reuse a skin.

**Direction:** move registry + skins into the package (or a new
`packages/chat-skins`), leaving only app-specific chrome in the app.

### F6 — "What a skin needs to render correctly" is implicit, not encapsulated

To render the first-party skin correctly, `/baseline` needed **four** separate
accommodations, each of which was a bug this session:

| Requirement | Why it is easy to miss |
|---|---|
| `data-thread-skin="digichat"` scope marker | without it, none of the theme grammar applies |
| `@source` into `packages/ui` from the host's CSS | without it Tailwind drops kit-only utilities (the diamonds) |
| `--font-geist-mono` variable | without it the font declaration is invalid and the skin inherits the page sans |
| the embed prefs host (`useStockChatPrefs`) | without it the `/` palette and `@`-mention are disabled |

Every one of these is invisible at the call site. This is the strongest
structural signal in the review.

**Direction:** make a skin self-describing — a descriptor that carries its own
provider (marker + font + prefs) and its own stylesheet list, so a host mounts
`<Skin />` and cannot get it subtly wrong.

### F7 — Two overlapping UI packages, one dead export

`packages/ui` and `packages/digichat-ui` both ship chat CSS, components and
styles; `packages/digichat-ui/src/styles/tokens-shadcn-bridge.css` is exported
from `package.json` and imported **nowhere** (only mentioned in
`apps/digichat/ARCHITECTURE.md`).

**Direction:** state the split explicitly (shared UI kit vs digichat-specific
branding/transcript helpers) and delete dead exports.

### F8 — Vendored archives inside the app

`apps/digichat/reference/assistant-ui-templates/` holds upstream skin sources
(not imported by Next.js) alongside the live skins, and the `/baseline` `stock/`
tree duplicates primitives that also exist in `packages/ui`. Useful as
provenance, but it reads as more UI surface than there is.

**Direction:** keep provenance in one clearly-named archive location, referenced
from `SOURCE.md`, not interleaved with live code.

### F9 — Docs sprawl and drift

digichat is described across `docs/digichat/` (7 files),
`docs/architecture/` (5), `apps/digichat/{AGENTS,ARCHITECTURE,README,OPERATIONS,CONTROLS,CHANGELOG}.md`,
ADRs 0018/0027/0028/0029, `docs/vision/digichat.md` + `docs/vision/api/*`,
`docs/superpowers/{specs,plans}/*`, and now `SKIN-GALLERY.md` + `ONBOARDING.html`.

Concrete inaccuracies found: `AGENTS.md` claims only `GET /api/health` is
public, but `deploy/chrome`, `embed/tenant-config`, `mcp/oauth/callback` and
`plan-proof` are also unauthenticated; and the current version is stated as
`1.0.0` (`INSTALL.md`, `RELEASE-SMOKE.md`), `v0.9.3`
(`docs/vision/api/guide-digichat-install.md`) and `v2.3.1` (website copy) while
the real version is `2.3.2`.

**Direction:** a docs index with one entry point, a single source for the
version, and fix the auth claim. Cheap and high-trust-value.

### F10 — `/baseline` isolation and the kit are not cleanly separated

The isolated `(baseline)` layout is a *good* instinct (it keeps the catalog
honest by not inheriting the product shell). But because the shared kit and the
product theme are not encapsulated, the isolation forced F6's four fixes. The
isolation should stay; the encapsulation should improve.

---

## Proposed workstreams (independent, each shippable on its own)

| # | Workstream | Risk | Notes |
|---|---|---|---|
| WS1 | Theme ownership: move the grammar sheet into the package; collapse the two app bridges onto the shared one; delete the shim | **medium** (production CSS) | Highest structural value. Needs the `/embed` vs `/baseline` visual diff we already built. |
| WS2 | Primitive dedup: `hideArrow` on the kit tooltip, one `TooltipIconButton`, one caret | low | Mechanical, high clarity, removes the fragile Tailwind-variant dependency. |
| WS3 | Skin encapsulation: skin descriptor carrying provider + styles | medium | Kills the whole class of "skin renders wrong on a new host" bugs (F6). |
| WS4 | Move registry + skins + stock primitives into the package | medium-high | Unlocks reuse; largest diff. |
| WS5 | Package boundary cleanup: digichat-ui vs ui, dead exports, archive location | low-medium | Mostly deletions. |
| WS6 | Docs index + version single-source + fix the auth claim | low | Do first: it makes the rest reviewable. |

Suggested order: **WS6 → WS2 → WS1 → WS3 → WS4 → WS5.** Each step must keep
`packages/ui` (62 files / 447 tests), `apps/digichat` (126 files / 1250 tests),
`npm run lint` (0 errors) and `npm run build` green, plus a visual check of
`/baseline?skin=digichat` (light + dark) against `/embed`.

## Explicit deletion targets (deslop)

- `packages/ui/src/styles/chatbot.css` (the shim) once the sheet moves.
- `packages/ui/src/components/chat/gallery-thread/ui/tooltip.tsx` (the adapter).
- One of the two `TooltipIconButton`s and the duplicate `tooltip.tsx` copies.
- Two of the three caret implementations.
- `packages/digichat-ui/src/styles/tokens-shadcn-bridge.css` (dead).
- The duplicate `@theme inline` bridges in the two app globals.
- Any `(baseline)/stock/` file that becomes identical to a package equivalent.

## Non-goals / where I would push back

- **Do not merge `packages/ui` into `apps/digichat`.** It is shared by
  `digithings-web`, `dashboard`, `reference` and `digiquant-web`; moving it into
  the product would be a much worse outcome than today.
- **Do not touch the BFF / secret boundary.** `requireDigiChatAuth`, the client
  projection types, `isAllowedServiceUrl`, `fetchGuarded`, the fail-closed
  config loader and the browser-visible-env discipline are the strongest part of
  the codebase.
- **Do not remove the `/baseline` isolation.** It is the thing that surfaced
  every bug in F6.
- **Do not unify all apps' CSS.** The marketing site and dashboard should not be
  coupled to the chat theme; sharing the token layer is enough.

## Open questions for the next turn

1. Is the goal **structural cleanliness** (ownership/boundaries) or also a
   **visual consolidation** (fewer, larger files)? They pull in different
   directions.
2. Is `apps/reference` allowed to import from `packages/ui` for its chatbot
   sheet (i.e. is the reference app willing to consume the canonical theme), or
   must it stay standalone?
3. Are the vendored `apps/digichat/reference/assistant-ui-templates/` sources
   still needed as provenance, or can they be dropped?
4. Should the skin system be reusable by other apps (favours WS4), or is it
   fine for it to stay digichat-only (then WS4 shrinks to relocating `stock/`)?
