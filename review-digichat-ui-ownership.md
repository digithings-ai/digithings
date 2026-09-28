# In-session review: digichat empty-state credit pin + UI ownership unification

- PR: #4636 (base `module/digichat`, head `task/4605-digichat-footer-chrome`)
- Reviewed HEAD: `1ef394cbc` (8 commits: `1ad29faff` Part A, `ef9e93074` WS6,
  `5e2f87d57` WS2, `3994d20a6` WS1 + WS4 steps 1–3, `061f2941a` WS4 step 4,
  `d19ad84f5` WS5, `db0a7476e` review fix, `1ef394cbc` WS4 step 5)
- Method: 5 foreground read-only reviewer subagents (one scope each + one
  generalist). Two background rounds failed first (general agents returned
  empty; background explore agents timed out) — the foreground round that
  produced these findings ran to completion with full signal.
- Preceded by: full suites green (`packages/ui` 76/557, `apps/digichat`
  126/1306, `packages/digichat-ui` 5/35), `npm run lint` 0 errors
  (27 pre-existing warnings), `npm run build` green (17/17 pages), HTTP smoke
  200s on `/`, `/baseline?skin=digichat`, `/embed` with `data-thread-skin`
  markers present. Test-kit diff vs pre-refactor: zero deletions, 2 files
  added, 11 moved, rest re-pointed.

## Findings

### 1. Option-B inversion integrity — NO BLOCKERS
No package→app imports in the moved trees (only `@/lib/utils` `cn`, which
resolves via the package's own `@/` alias to a byte-identical file). No
product-state reads in moved files; all product data enters via props/context
(`digichat` options object, `SkinRuntimeProvider` error parsers, prefs config
+ deps). Both hosts (`product-shell`, `baseline-client`) forward the digichat
prop; embed flows via `ProductStockShell`.

### 2. Package boundaries — NO BLOCKERS
Export-map additions only (`./chat/skins`, `./chat/stock`,
`./chat/stock/thread`, `./chat/skins/digichat`, `./chat/transcript`); no
existing specifier changed meaning. `Thread` stays off the main barrel.
The deleted `tokens-shadcn-bridge.css` export/file is unreferenced anywhere.

### 3. Theme / CSS ownership (WS1) — NO BLOCKERS
No duplicated `:root`/`.dark`/`@layer base` between the new
`digichat-app-theme.css` bridge and the entry sheets; the existing host
`@source …/packages/ui/src/components/chat` line covers the moved
`skins/` + `stock/` dirs with zero stylesheet changes; `apps/reference`
still loads the grammar via the package specifier.

### 4. Prefs plumbing (Step 3 interfaces) — NO BLOCKERS
All three `useStockChatPrefs` call sites (baseline + home Single/Memory) pass
equivalent config + deps; reset/newThread/compactThread re-init defaults are
unchanged; `message-error` renders identically with providers in place
(BYOK copy covered by the package test and the new app-side integration test).

### 5. Generalist — 1 MEDIUM, fixed
`packages/ui/.../stock/message-error.aui.test.tsx:75` asserted the BYOK copy
via stub parsers instead of the real `embed-chat-error` mapping, leaving the
banner↔mapping wiring unpinned (parsers themselves remain unit-tested).
Fixed by `apps/digichat/.../stock/message-error.integration.test.tsx`, which
renders the package `MessageError` with the real app parsers through both
injection paths (props and provider). 2/2 green.

## Deferred / not in scope (unchanged)
TooltipIconButton + caret unification and the sharp-vs-rounded tooltip split
await a product ruling; vendored `reference/assistant-ui-templates/` stays as
provenance; BFF/secret boundary untouched; `/baseline` isolation kept.

## Gaps in this review (honest)
- No full visual diff: Playwright MCP is unavailable in this session and
  chrome-devtools MCP is locked per repo rules — verification is build +
  suites + HTTP smoke + markers. Recommend a light+dark eyeball of
  `/baseline?skin=digichat` vs `/embed` before merge.
- CI on PR #4636 was not yet green at review time; re-check before merge.

## Verdict
Approve subject to CI green + the visual eyeball above. No blockers.
