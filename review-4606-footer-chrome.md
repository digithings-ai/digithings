# Review — digichat footer / 500 / caret (PR #4606)

**Subject:** PR #4606, branch `task/4605-digichat-footer-chrome`, reviewed at `0fe827c4f`,
re-reviewable at `e87d6da8b`, base `module/digichat`, issue #4605.

**Reviewer:** `gentle-jade-falcon` — fresh-context read-only subagent (`general`), **no shell
tool**; static verification only (on-disk reads + GitHub API `get_diff`/`get_commit`, plus two
live Chromium checks via Playwright for `color-mix` and `CSS.supports`). The reviewer did not
write this code. The author session wrote this file.

**Verdict at `0fe827c4f`:** REQUEST CHANGES — 0 blocker / 3 major / 3 minor / 4 nit.

**Verdict after the fixes (`e87d6da8b`):** the three majors are resolved; minors/nits triaged
below (m1 recorded as an accepted follow-up; the rest fixed).

## Verified clean at `0fe827c4f`

- **A** — `.dc-attribution` carried no `position` and no `background`; only `.dc-block-caret`
  is absolute (the caret, not the credit).
- **D** — `lib/thread-skins.ts` has no `"use client"` and only a type-only
  `import type { CSSProperties } from "react"` (erased), so it stays server-safe.
  `presentation-frame.tsx:17,23` imports/re-exports from `@/lib/thread-skins`; `page.tsx:9`
  same, and `:31` keeps `const framed = isFramedPresentation(mode) && !layoutSkin;` verbatim
  (`presentation-modes.test.ts:28` pins that text).
- **E** — the caret fix declares `caret-color: var(--tenant-accent, …)` + `caret-shape: block`
  base, with `caret-color: transparent` and the overlay paint both inside
  `@supports not (caret-shape: block)`.
- **F (mount points)** — no disclaimer copy survives (`grep "can make mistakes"` only hits one
  comment), and the credit mounts inside a Thread on every skin.
- **G (scoping)** — `expo-react-native.tsx`, `product-page-assistant/index.tsx`,
  `webpage-assistant/docs-assistant.tsx`, `assistant-modal.tsx` all import `Thread` from
  `@/app/(baseline)/stock/thread.aui` and nest it in their phone frame / modal / sidebar, so the
  credit is scoped to the chat surface, not the page.
- **Hunt items** — no credit leaks onto the page; no #4552 regression (`stream.test.ts` only
  widened a cast); server-safety unaffected; no CSS specificity/cascade problem.

## Findings and resolutions

### M1 — the credit was INVISIBLE on the five clone skins (RESOLVED)

`thread-skins.ts:131` mapped `--credit-ink` to the skin's **canvas** colour
(`chatgpt {light:"#ffffff",dark:"#000000"}`, …) and `product-chrome.css:73` paints the text
with that same token → white-on-white / black-on-black, both themes, on `/baseline` and
`/embed`. Reproduced live at `0fe827c4f` on `/baseline?skin=chatgpt&theme=dark` as
`oklch(0 0 none / 0.7)` (black@70% on black).

**Fix (`e87d6da8b`):** `SKIN_CANVAS` → `SKIN_INK`, using each skin's own **text** colour
(`chatgpt {light:"#0d0d0d",dark:"#ececec"}`, `claude {light:"#1a1a18",dark:"#eee"}`,
`grok {light:"#0d0d0d",dark:"#ececec"}`, `gemini {light:"#1f1f1f",dark:"#e3e3e3"}`,
`perplexity {light:"#1f1b17",dark:"#f5f2ed"}`); `skinCreditStyle` now emits only
`{ "--credit-ink": ink[theme] }`. `--credit-canvas` (never read) is gone (also closes N3), and
the doc comment now says the fallback is `--muted-foreground`, not `--background` (closes N4).

**Verified live** across 14 skin×theme combinations: every clone skin resolves a legible ink;
`base`/`digichat` fall through to `--muted-foreground`. Example: chatgpt dark
`oklch(0.943083 … / 0.7)` from `#ececec`; chatgpt light `oklch(0.159065 … / 0.7)` from
`#0d0d0d`.

### M2 — the `attribution: false` opt-out was ignored (RESOLVED)

Every skin mount passed a bare always-true prop, so the embed's resolved `attribution` was
never consulted; a titled opted-out tenant rendered the header parenthetical **and** the skin
footer (two credits), violating the "at most one" invariant asserted by `embed-ui-flags.ts:28`
/ `embed-ui-flags.test.ts:94,101`.

**Fix (`e87d6da8b`):** `SkinChromeValue` gained `attribution: boolean` (default `true`) and a
`useAttribution()` hook; `product-shell.tsx` threads `cfg.chrome.attribution` into the
provider; `CreditFooter` reads the context, with an optional explicit prop that still wins (for
the embed gate/paywall branch, which has no provider). Every skin mount dropped its hardcoded
`attribution` (grep: none remain). `digichat.tsx`'s `DigichatFooter` was also hoisted to module
scope (closes N1).

**Verified live:** `/embed?host=digithings.ai&theme=dark` and the baseline skins render exactly
**1** credit and **0** header-brand elements (footer wins, parenthetical suppressed).
`credit-footer.test.tsx` (new, 4 tests) pins: default render, `attribution: true` context,
`attribution: false` context → no credit, and prop-overrides-context.

### M3 — the boot carve-out did not keep the credit visible (RESOLVED)

The old rule `… > :not(.dboot-overlay):not([data-slot="aui_credit"]):not(:has([data-slot="aui_credit"]))`
exempted the whole transcript column (the credit is a **descendant**, not a direct child), and
the credit had no stacking, so the opaque `z-index: 40` `.dboot-overlay` painted over it.

**Fix (`e87d6da8b`):** `.dc-attribution` is now `position: relative; z-index: 60`; the boot rule
hides only the column (`> :not(.dboot-overlay)`); the credit re-asserts its own `visibility`.

**Verified live (40 samples @ 100ms across the boot window, `/embed?host=digithings.ai&theme=dark`):**
`bootSamples: 32`, `creditHiddenDuringBoot: 0` (credit `visible`, `z-index: 60` throughout), and
`threadVisibleDuringBoot: 0` (the column stays hidden). Exactly 1 credit after settle.

### m1 — `-0.5rem` top margin is calibrated for the 16px `gap-4` footers (ACCEPTED follow-up)

The clone skins use smaller gaps (`chatgpt gap-2`, `gemini gap-1.5`, `claude`/`perplexity` none),
so an 8px negative margin under-cancels there, and the `/embed` `padding-bottom: 0.25rem`
override is scoped to `[data-skin-canvas="1"]` (digichat only). The user explicitly approved the
current embed spacing (m2553/m2558/m2653: "the distance with the bottom of the page looks
right", then "add a bit more padding, it's to tight now"), and the owner reviewed the clone-skin
spacing live. Left as-is deliberately; a per-skin gap token would be the follow-up if it is ever
revisited.

### m2 — one of the two caret comments was wrong (RESOLVED)

`product-chrome.css` said "Chromium parses caret-shape but still paints the thin OS caret",
contradicting the reference and the actual behaviour (`CSS.supports('caret-shape','block')` is
`true` and the overlay is `display: none` in Chromium). The comment now states that engines
supporting `caret-shape` keep their native block caret and only engines without it get the
painted overlay.

### m3 — stale `block-caret.tsx` doc (RESOLVED)

The doc said the embed "promotes the painted block on every engine"; it now says the promotion
happens only inside the `@supports not (caret-shape: block)` guard in `product-chrome.css`.

### N1 — `DigichatFooter` defined inside the component body (RESOLVED)

Hoisted to module scope in `skins/digichat.tsx` with a stable comment.

### N2 — collapsed line (RESOLVED)

`ThreadScrollToBottom` in `stock/thread.aui.tsx` restored to a normal line break.

### N3 / N4 (RESOLVED)

Closed by the M1 fix (`--credit-canvas` dropped; doc corrected to `--muted-foreground`).

## Re-verification commands (author session)

```bash
# boot visibility + single credit (Playwright, 40 samples)
# creditHiddenDuringBoot: 0, threadVisibleDuringBoot: 0, zDuringBoot: 60, creditsNow: 1

# M1 ink legibility (14 skin×theme combinations, Playwright computed colour + --credit-ink)
# chatgpt dark #ececec / light #0d0d0d; claude #eee / #1a1a18; grok #ececec / #0d0d0d;
# gemini #e3e3e3 / #1f1f1f; perplexity #f5f2ed / #1f1b17; base/digichat -> --muted-foreground

# the m2644 bug: the (baseline) build must emit the layered rule
curl -s 'http://127.0.0.1:3000/_next/static/chunks/%5Broot-of-the-server%5D__0ztant8._.css' \
  | grep -c dc-attribution      # 5

# no hardcoded attribution prop remains on any skin mount
rg -n 'CreditFooter attribution' apps/digichat/src   # (no matches)
```

## Verification after the fixes (all green)

```
npx tsc --noEmit (touched files)          clean
apps/digichat  npm run test               133 files / 1331 tests passed
apps/digichat  npm run lint               30 problems, 0 errors (all pre-existing warnings)
apps/digichat  npm run build              type-checks clean (Compiled successfully)
packages/ui    npm run test               63 files / 459 tests passed
repo root      check_frontend_canon.py    clean
repo root      check_doc_links.py         OK (418 markdown files)
credit-footer.test.tsx                    1 file / 4 tests passed
```
