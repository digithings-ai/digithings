# Review — digichat `chrome.mode` modal + sidebar presentation surfaces (PR #4518)

- **Subject:** PR #4518 — `feat(digichat): make chrome.mode modal and sidebar real presentation surfaces`
- **Branch:** `task/4515-digichat-presentation-modes` → base `module/digichat`
- **Issue:** #4515
- **Reviewed revision:** `cc3d240b3` (fixes in the follow-up commit on the same branch)
- **Reviewer:** independent fresh-context read-only subagent (`general`, delegation `lively-indigo-owl`, 2026-09-22T22:56:46Z → 22:59:48Z). The author session did not review its own work. The reviewer had **no shell tool**, so it reconstructed the diff via the GitHub API and verified statically; it could not run test/lint/build. CI is the runtime gate.

## Verdict

**APPROVE WITH NITS** — 0 blocker / 1 major / 4 minor / 2 nit.

## Findings and resolutions

| # | Sev | Finding | Resolution |
|---|-----|---------|------------|
| MAJOR-1 | major | `LAYOUT_SKINS` (webpage-assistant, product-page-assistant, expo-react-native) were wrapped by `PresentationFrame` (`home-stock-client.tsx:144`, `:232`). A page-owning skin with `chrome.mode: modal\|sidebar` would render its whole template inside the launcher panel / 380px dock. Schema-legal but silently broken. | **Fixed.** `presentation-frame.tsx` now returns `children` unchanged when `skinOwnsPageChrome(chrome.skin)`. |
| MINOR-1 | minor | `border-inline-start: 1px solid var(--hair)` in `product-chrome.css:339` was invalid-at-computed-value-time: `--hair` is declared only inside `.digichat-thread` / `.digichat-thread-list` (`chat-aui.css:56,102,317,330`), both descendants of the panel. No divider. | **Fixed.** Now `var(--border)`. |
| MINOR-2 | minor | `isFramedPresentation` was exported but unused; `page.tsx:30` re-implemented the logic inline (dead export + duplicated invariant). | **Fixed.** `page.tsx` imports and uses `isFramedPresentation(mode) && !layoutSkin`. |
| MINOR-3 | minor | An authenticated `persistence: "server"` deployment in `modal`/`sidebar` silently downgrades to no persistence (`page.tsx:59` `!framed` → `HomeStockClient` → `HomeStockClientSingle` hard-codes `persistence="none"`). Not a regression (both modes redirected to `/embed` before) but undocumented. | **Fixed by docs.** The plan doc now states `modal`/`sidebar` mount the stock shell, so `persistence: server` needs `chrome.mode: app`. |
| MINOR-4 | minor | `matchesHotkey` was more permissive than its docstring: `"k+"` degraded to bare `k` (empty tokens were filtered), and `mod+k` fired with **both** ctrl and meta held. | **Fixed.** Malformed strings (any empty token) match nothing; `mod` requires exactly one of ctrl/meta. |
| NIT-1 | nit | The `h-full` vs `h-dvh` conditional for `modal` in `home-stock-client.tsx` was a no-op — `PresentationFrame` renders `DigichatLauncher` without `portal={false}`, so the panel portals to `document.body` and the wrapper div has no DOM children. | **Fixed.** Wrappers use `h-dvh` unconditionally, with a comment explaining the portal. |
| NIT-2 | nit | The plan doc mode table said `modal` "renders the app chrome **plus** a launcher-mounted overlay panel", but digichat owns `/` so only a bare 30px trigger shows until clicked. | **Fixed.** Table rows for `modal`/`sidebar` reworded. |

## Verified clean

- The 8 change claims in the PR body all check out against the diff.
- `matchesHotkey` falsification attempts (uppercase, aliases, empty string, `"+"`, duplicate modifiers) are sound apart from MINOR-4.
- `sidebar` overflow: the wrapper `flex h-dvh flex-col` gives `.dc-presentation--sidebar { height: 100% }` a definite height, and `__panel { height: 100% }` constrains `ProductStockShell`.
- No `data-chrome-mode="app"` consumer exists anywhere (repo-wide grep: only `chat-aui.css:350` `[data-thread-skin="digichat"][data-chrome-mode="embed"]`, `product-shell.tsx:463`, `chat-shell.tsx:450`, `embed-client.tsx:1226`, `product-shell.test.tsx:74`), so framed modes passing `modal`/`sidebar` is clean.
- `ChatShell` reachability with the `!framed` guard is correct for an authenticated server-persistence deployment.
- The new test path math `srcDir = join(here, "..", "..")` is correct; positive regex assertions are non-vacuous (they fail against the base revision).
- Diff is 7 files; no `route.ts` / auth change; no credential reachable to the browser.

## Noted, pre-existing (not introduced by this PR)

- `loader.ts:171` maps `modal` → `layout: "embed"` while `sidebar` → `"page"`, so a `modal` deployment loses its mode through the embed-tenant round-trip. `loader.ts` is not in this diff; recorded for a future cleanup.

## Post-fix verification

- `apps/digichat` `npm run test` → 126 test files / 1256 tests passed.
- `packages/ui` `npm run test` → 62 test files / 452 tests passed.
- `apps/digichat` `npm run lint` → 30 problems, 0 errors (all pre-existing warnings).
- `apps/digichat` `npm run build` → TypeScript clean, all routes generated.
- `python3 scripts/check_frontend_canon.py` → clean.
- `python3 scripts/check_doc_links.py` → OK (418 markdown files scanned).
