# WS4 Phase 1 — Option B inversion plan (skins + stock → packages/ui)

Status: Steps 1–3 landed as `3994d20a6` (WS1 theme ownership + WS4 scaffolding, pure
moves, interface cuts). Step 4 (below) is the remaining work. Owner direction: build
it properly (Option B), accept risky refactoring where it scales best; follow-up goal
is runtime skin/token swapping without redeploying (selection + tokens as runtime
data — NOT remote modules).

Constraints (standing): structural only, zero visual/rendering change. Every step keeps
`packages/ui` tests, `apps/digichat` tests, `npm run lint` (0 errors), `npm run build`
green, plus a visual check of `/baseline?skin=digichat` (light + dark) vs `/embed`.

## Why B (one paragraph)

A package cannot import app code (the F1 violation in reverse). The move set has ~10
outbound deps into `@/components/stock/*` and `@/lib/*`; dragging them along (Option A)
moves product concepts into the shared kit and still leaves config deploy-baked. The
recon shows every one of those deps is already context- or prop-shaped at the call
site (providers wrap `ThreadSkinView` in all 3 hosts; `stock-send-gate` is already the
exemplary injected-handlers pattern), so inversion is mechanical, not redesign. It is
also the prerequisite for the runtime-swap goal and for per-skin `React.lazy`.

## Destination map (packages/ui)

| Incoming | Destination | Export |
|---|---|---|
| 12 skins + `ThreadSkinView` dispatch | `src/components/chat/skins/` | `./chat/skins` → `skins/index.ts` |
| `stock/` primitives (thread/attachment/markdown/reasoning/tool-*/ui/*) | `src/components/chat/stock/` | `./chat/stock` |
| registry (`thread-skins.ts`) + WS3 contract | `src/components/chat/skins/` | via `./chat/skins` |
| support contexts (see verdicts) | `src/components/chat/skins/` or `stock/` | via above |

Rules: never the main barrel (pinned by `gallery-thread.source.test.ts:158-165`);
`@digithings/ui/chat/thread` subpath style. Placing everything under
`src/components/chat/` inherits the existing host `@source` scan line for free
(`chat-widgets.css:12-13`, host `globals.css:26` / `baseline.css:17`) — zero
stylesheet/`@source` changes. Anywhere else costs a contract + host-CSS update.

## Interface verdicts (per support module)

MOVABLE-AS-IS: `stock-send-gate.tsx` (already injected `handlers` — the pattern to
copy); `deploy-ui-context.tsx` (type-only lib imports; host injects value at
`product-shell.tsx:454`); `credit-footer.tsx` (conditional: co-move `cn` +
`skin-chrome`, add `"use client"` — it consumes context but declares none).

NEEDS-INTERFACE (minimal, mechanical):
- `skin-chrome.tsx` — one runtime product import: `DEFAULT_THREAD_SKIN`. Co-move pure
  `thread-skins.ts` (dependency-free) and the import resolves itself; types
  (`ThreadSkin`, `ChromeMode`, `PageContextMode`) come from shared types.
- `message-error.aui.tsx` — inject `parseError`/`formatError` fns (replaces
  `@/lib/embed-chat-error`, which is tenant/BFF-adjacent — do NOT co-move).
- `embed-chat-prefs.tsx` — inject `defaults: { language, view, thinking }` (or co-move
  the two pure lib files `languages.ts`, `view-modes.ts`); needs a shared MCP-config
  type for the type-only `SessionMcpConfig` import.
- `stock-chat-prefs-host.tsx` — the one real interface: replace product
  `DigichatClientConfig` with a plain shared config interface; inject a
  `renderPanes` slot (instead of internal `EmbedComposerMenu`); inject
  `onOpenSessions` (instead of `querySelector("[data-memory-thread-list]")`).
  `sessionKey` is already pass-through; `newThread`/`redo` already injected props.
  Note: `detectBrowserLanguageCode` reads `navigator` — needs an SSR guard in the
  package. Persistence is `useState`-only (no localStorage/server) — unchanged.

`digichat.tsx` product wiring (all convertible, none reads server state): slash
`commands/adapter/trigger/onComposerSubmit` → derived props (only ambient is the
`useAui()` singleton); pending-header writes → injectable `sessionKey`/callback;
`PAGE_CONTEXT_ATTACHMENT_NAME` → prop with same default; baseline constants →
props with same defaults (already shadowed by context). `tool-fallback.aui.tsx`:
`toolRowTitle` is pure — hoist the call to the host or take `title?` prop.

## Step order (each shippable, verified before next)

1. **Scaffolding** — create dest dirs + `./chat/skins`, `./chat/stock` exports; extend
   source-pinning tests (`gallery-thread.source.test.ts`-style blocks or sibling
   `skins.source.test.ts`); no behavior change.
2. **Pure moves** — `stock-send-gate`, `deploy-ui-context`, `credit-footer`,
   registry `thread-skins.ts` (plain module; 14 app importers re-point — incl.
   server `page.tsx:9` and `deploy-config/schema.ts:13`, both fine importing a
   package), WS3 contract. Rewire `cn` → `src/lib/utils`, kit `Button`/`Tooltip`.
3. **Interface cuts** — the four NEEDS-INTERFACE modules above; hosts provide values
   at the 3 mount points (product-shell `:455` area, baseline-client `:126/127`,
   embed-client `:1243` area). Delete the dead `welcome` prop (declared in
   `ThreadSkinViewProps`, never forwarded — remove at type + `product-shell:531`
   call site; behavior-neutral).
4. **Skin + stock move** — `git mv` the trees; mechanical import rewrites
   (`@/lib/utils` → relative, `@/app/(baseline)/stock/*` → relative,
   `@/components/stock/*` → sibling/context, `@/lib/*` → props per above).
   Update: 2 `ThreadSkinView` hosts, 3 test mocks
   (`product-shell.test:14,18`, `chat-panel.test:122`, `home-stock-client.memory:45`),
   4 path-as-text tests (`baseline-isolation:46-49`, `product-isolation:47,72`,
   `presentation-modes:37-38,54`, `host-contract:19`), contract `setBy` paths.
5. **(Optional, same branch)** per-skin `React.lazy` — recon found NO blockers (all
   `"use client"`, sync exports, no `next/*` in skins). Boundary must sit below the
   providers; `digichat.tsx:3-7` kit CSS side effects need one host loader.

## Step 4 detailed design (from final recon — execute in build mode)

`digichat.tsx` (336 lines) becomes `DigichatSkin({ composerLayout?, copy?,
hiddenAttachmentName?, slash? })` where `copy?` carries `{ welcome?, placeholder?,
suggestions? }` (fallbacks `copy?.x ?? ""` / `?? []`), `hiddenAttachmentName?`
defaults to the `"page-context.html"` literal (with source-of-truth comment pointing
at `embed-page-context-messages.ts:158`), and `slash?` carries `{ buildCommands,
extraDefs, prefixAdapter, shouldDraft, submitAction, executeDef, executeFromComposer,
armForceTool, setForceTool, setWebSearchForce }`. `enableSlash =
Boolean(slashPrefs) && Boolean(slash)`; `onComposerSubmit` guards
`if (slashPrefs && slash)`. `useAui()`, `threadTurns` (pure, moves verbatim), and the
`copyExport`/per-id command overrides stay inside. New package types:
`SkinSlashCommand { id, label?, execute?, [k: string]: unknown }` and
`SkinSlashAction` (`block | none | force{text,forceTool} | force-web{text} |
run{command,arg}`). `composerLayout={composerLayout ?? (mode === "app" ? "expanded"
: "compact")}` stays byte-identical (pinned by `product-isolation.test.ts:71-76`).
`ThreadSkinView` gains `digichat?: DigichatSkinOptions`, forwarded to the digichat
branch only; the two hosts build it from app modules (copy = `BASELINE_EMBED_*`
constants, slash/pending = real fns, hidden name = `PAGE_CONTEXT_ATTACHMENT_NAME`).

Serializers move to the kit: `transcript-markdown.ts` + `activity-view.ts` (+
`types.ts` after an import check — they import only `./activity-view`, type-only
`@digithings/ui`, and local types) relocate to `packages/ui`, with
`packages/digichat-ui` re-exporting for compat. `toolRowTitle`
(`tool-display.ts:3-6`, pure) co-moves to package `stock/`; `ToolFallback` keeps
`title={toolRowTitle(toolName)}` via a relative import — no prop needed, test
assertions byte-identical. `PAGE_CONTEXT_ATTACHMENT_NAME` stays in app; the package
uses the literal default.

Test keep/move: `digichat.test.tsx` and `skins/index.test.tsx` move with the skins
(relative mocks; drop the `product-slash-commands` mock at rewrite).
`digichat-force-web.test.tsx` and `tool-fallback.aui.test.tsx` STAY IN APP as
app-wiring integration tests (they import `@/lib/pending-chat-headers`,
`@/components/stock/embed-chat-prefs`, `@/lib/ui-stream-parts` which all stay):
only their skin/component imports re-point to the package; force-web passes
slash+pending as the new props with real app fns. `skins-isolation.test.ts` moves
with updated paths. Mock re-points (specifier-only, identical factories):
`product-shell.test:18`, `chat-panel.test:122`, `home-stock-client.memory:45` →
`@digithings/ui/chat/skins`; `product-shell.test:14` → NEW deep export
`./chat/stock/thread` (barrel would widen blast radius onto product-shell's
send-gate/deploy-ui/chrome imports). Path-as-text updates: `baseline-isolation:48`
(read package `stock/thread.aui.tsx`), `:50` (new `@digithings/ui/chat/skins`
specifier); `product-isolation:72` (read package `skins/digichat.tsx`).
`presentation-modes` needs no change. CSS: delete `baseline.css:9,11` and
`globals.css:19,20` `@source` lines (covered by the kit scan lines `:17` / `:26`).
`skins/index.tsx` dispatch stays in `skins/index.ts` (overwrite the Step-2 barrel,
add `export *` for registry + contract). Embed gate-form branch renders no skins —
no provider needed there.

## Explicitly out of scope

- Phase 2 (runtime theme source: DB-backed tenants via `GET /api/embed/tenant-config`,
  token set as CSS vars) — separate proposal; touches BFF/config.
- Module federation / remote skins (rejected: fights Next.js bundling, weakens BFF
  posture, no product gain).
- `packages/digichat-ui` re-homing; TooltipIconButton unification; caret unification;
  sharp-vs-rounded tooltip (needs product ruling); vendored
  `reference/assistant-ui-templates/` (stays as provenance).
- No Dockerfile changes needed (both already `COPY packages/ui`); verify
  `config/` examples still list valid `chrome.skin` ids.

## Evidence base

Five parallel read-only recon agents (2026-09-24), all with file:line inventories:
outbound-dep map, support-context dossiers, inbound+deploy paths, registry/prop
surfaces + lazy feasibility, package landing zone. Full outputs in session record.
