# digichat UI ownership — tracked plan

Tracked companion to the untracked preparation note
`docs/architecture/digichat-ui-simplification.md` (never commit that file; its
content is folded in below). Status: WS6 landed; WS1–WS5 queued on branch
`task/4605-digichat-footer-chrome`, one PR into `module/digichat` at the end.

## Verdict

The layering is already right; the ownership is leaky. `packages/*` = shared UI
+ design system; `apps/digichat` = product + BFF. The boundary is crossed in both
directions. Fix = move ownership down (theme, skins, primitives → package) and
collapse duplicated surfaces — **not** "move UI into one folder".

## Ownership map

| Concern | Lives today | Should live |
|---|---|---|
| Design tokens (`--bg/--ink/--term-*`, `[data-theme]`) | `packages/design/tokens.css` | unchanged |
| Tailwind v4 `@theme inline` bridge | `packages/ui/src/styles/web-theme.css` | unchanged |
| digichat skin palette (`.digichat-thread` dark/light + portal mirrors) | `packages/ui/src/styles/chat-aui.css` | merge into one theme file |
| digichat theme grammar (caret, radii, composer, markdown, tooltips) | `apps/reference/app/(chatbot)/chatbot/chatbot.css`, re-exported by a 4-line package shim | move into `packages/ui/src/styles/` |
| First-party Thread + DotMatrix + caret + boot loader | `packages/ui/src/components/chat/` | unchanged |
| 12 skins + registry + dispatch | `apps/digichat/src/components/assistant-ui/skins/`, `apps/digichat/src/lib/thread-skins.ts` | move into the package |
| Shared primitives for the catalog skins | `apps/digichat/src/app/(baseline)/stock/` | move out of a route folder |
| Product shell, chrome bar, deploy UI context | `apps/digichat/src/components/stock/` | unchanged (app chrome) |
| BFF, auth, config, deployment | `apps/digichat/src/app/api/`, `src/lib/` | unchanged |

## Findings

- **F1** — `packages/ui/src/styles/chatbot.css` is 4 lines reaching into the
  `apps/reference` tree, pinned by `chatbot-css.share.test.ts`. Move the sheet into
  the package (e.g. `chat-digichat.css`); `apps/reference` imports it; delete the shim.
- **F2** — Three palettes / three bridges for one product (`packages/design/tokens.css`,
  `chat-aui.css`, `chatbot.css`), plus two app entry sheets re-declaring their own
  `@theme inline` instead of importing the shared bridge. Direct cause of the white
  composer / black light-mode / missing Geist Mono bugs. Direction: one digichat theme
  entry point in the package; app globals import the shared bridge.
- **F3** — Primitive duplication: `tooltip.tsx` ×4 real (+4 vendored), incl. a 34-line
  gallery adapter whose only job is hiding the arrow; `tooltip-icon-button.tsx` ×3;
  carets ×3. Direction: `hideArrow` prop on the kit tooltip, delete the adapter; one
  `TooltipIconButton`; one caret. Constraint (owner): no visual changes — the sharp
  (kit) vs rounded (stock) tooltip split stays; dedup via shared component + per-site
  styling, not by collapsing the look.
- **F4** — `apps/digichat/src/app/(baseline)/stock/` is an app route folder serving as
  the shared library for 10+ skins. Move under the skin system / package.
- **F5** — Skins + registry are app-owned while the Thread is package-owned
  (`@digithings/ui/chat/thread`); no other app can reuse a skin. Move registry + skins
  into the package (or new `packages/chat-skins`).
- **F6** (strongest structural signal) — "What a skin needs to render correctly" is
  implicit: `/baseline` needed four accommodations, each a bug
  (`data-thread-skin="digichat"` marker; `@source` into `packages/ui`; `--font-geist-mono`;
  `useStockChatPrefs` host). Direction: self-describing skin descriptor carrying its own
  provider and stylesheet list, so a host mounts `<Skin />` and cannot get it subtly wrong.
- **F7** — Two overlapping UI packages (`packages/ui`, `packages/digichat-ui`);
  `tokens-shadcn-bridge.css` is exported but imported nowhere. State the split explicitly;
  delete dead exports.
- **F8** — `apps/digichat/reference/assistant-ui-templates/` interleaves vendored upstream
  sources with live skins. Owner: the vendored sources **stay** as themes-library
  provenance for future command-palette theme switching — no deletion.
- **F9** — Docs sprawl/drift. Landed as WS6 (index + version single-source + auth-claim fix).
- **F10** — `/baseline` isolation is a good instinct; keep it, improve encapsulation.

## Workstreams (independent, each shippable)

Order: **WS6 → WS2 → WS1 → WS3 → WS4 → WS5**.

- **WS6** (landed) — docs index + version single-source + auth-claim fix.
- **WS1** — theme ownership: move grammar into package, collapse the two app bridges,
  delete the shim. Medium risk, highest structural value; needs `/embed` vs `/baseline`
  visual diff. Also settles the deferred baseline-vs-embed footer spacing delta (24px vs
  4px), which is an F2 symptom.
- **WS2** — primitive dedup (`hideArrow`, one `TooltipIconButton`, one caret). Low,
  mechanical, no visual changes per owner scope ruling.
- **WS3** — skin encapsulation via descriptor (medium, kills the F6 class).
- **WS4** — move registry + skins + stock primitives into the package (medium-high,
  largest diff; full move per owner reusability ruling). Also settles the base thread
  footer (`stock/thread.aui.tsx`), the F4 "route folder as shared library" surface.
- **WS5** — package-boundary cleanup: `digichat-ui` vs `ui` split, dead exports, archive
  location. Low-medium, mostly deletions (minus the F8 vendored sources, which stay).

Each step must keep `packages/ui` tests, `apps/digichat` tests, `npm run lint`
(0 errors) and `npm run build` green, plus a visual check of `/baseline?skin=digichat`
(light + dark) against `/embed`.

## Deletion targets

The `chatbot.css` shim (once the sheet moves); the gallery tooltip adapter; duplicate
`TooltipIconButton` / `tooltip.tsx` copies; two of three carets; the dead
`tokens-shadcn-bridge.css`; the duplicate `@theme inline` bridges; any
`(baseline)/stock/` file identical to a package equivalent.

## Non-goals (push back if proposed)

Do **not** merge `packages/ui` into `apps/digichat` (shared by digithings-web,
dashboard, reference, digiquant-web); do **not** touch the BFF/secret boundary
(`requireDigiChatAuth`, client projection types, `isAllowedServiceUrl`, `fetchGuarded`,
fail-closed config loader, browser-visible-env discipline); do **not** remove the
`/baseline` isolation; do **not** unify all apps' CSS (sharing the token layer is enough).

## Owner decisions (recorded 2026-09-24)

1. Part A commit `1ad29faff` folds into this branch — no separate PR; one PR into
   `module/digichat` at the end (branch name may be renamed at PR time).
2. Scope = structural cleanliness only; all 12 skins' visuals stay as-is.
3. Approved: chatbot sheet moves into `packages/ui`; `apps/reference` imports it; shim deleted.
4. Skin system reusable by other apps → full WS4.
5. Vendored `reference/assistant-ui-templates/` stays as provenance — no deletion.

## Known follow-ups (not WS6)

- `docs/digichat/ONBOARDING.html` still calls `module/digichat` a stale branch not to
  revive — reconcile with the planned PR into `module/digichat` before landing.
- `docs/DEPLOYMENT.md:38` (`v0.9.3` retention note) left as factual retention — verify
  context on next touch.
- `docs/openapi/digichat.json` version `0.9.3` is the API spec version — out of scope,
  change only with an API revision.
