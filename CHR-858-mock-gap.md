# DigiVoice banner — close v5.8 mock gap (follow-up to #4950)

Chris 2026-10-01 ~23:52 Rome: live Mac banner ≠ Desktop mock SoT.
#4950 (cb425bfb) density/grid/silence stays — close remaining mock locks on top.

## SoT (read these first)
1. Root AGENTS.md + digivoice/AGENTS.md + digivoice/hammerspoon/README.md
2. Mock HTML (pixel SoT): `./digivoice-banner-ux-v5.8-mock.html` (also Desktop + App Support mocks/banner-ux-v5.8.html)
3. This brief

## Edit only
- `digivoice/hammerspoon/banner_core.lua`
- `digivoice/hammerspoon/init.lua`
- settings/CLI only if spawn/persist needs it
- `tests/dvo/lua/*` as needed
- hammerspoon README / ARCHITECTURE touch only if behavior docs drift

Do NOT touch digiquant-web, digivoice TUI craft (#4959), other products.

## Must close vs mock (all 8)
1. StatusGrid top-left; hug content (no min-width gutter stretch); equal padding all densities
2. DigiChat light/dark flips (RYG status colors stay)
3. Hover: icon-only copy + × below banner (stack if mini; horizontal right-aligned if wider)
4. Hidden by default; spawn via CLI/hotkey (no dictation required to show)
5. Drag free + snap near 9 anchors (tl/tc/tr/ml/c/mr/bl/bc/br); persist position
6. Faster typewriter; peek→full continues caret; close = instant hide (no reverse TW)
7. Full ≤ ~50vh scroll, scrollbar hidden; uniform line widths; first line locks final width
8. Center pin keeps center on expand; edge pins grow outward

## Keep from #4950
Silence pause (~10s), density mini|peek|full, square StatusGrid, Esc discard, no chrome title/hint text, click cycles density.

## Constraints
- Pure logic in banner_core.lua (no hs.*); init.lua draws.
- Lowercase digivoice. No cloud STT/TTS. No shell=True.
- Do NOT revert density/grid/silence.
- Do NOT open hatch / undraft / ping Platform.
- After code: update lua unit tests; run `pytest tests/dvo/lua` path or whatever AGENTS says for lua; ruff if python touched.

## Git (you do this)
CWD is already this worktree on branch `task/4947-digivoice-banner-v58-gap` tracking origin/develop @ a99fb1f75.
1. Implement gaps → commit: `feat(digivoice): banner v5.8 mock-gap — hug, drag/snap, hover controls, TW`
2. Push to `github` remote: `git push -u github HEAD`
3. Open **draft** PR → develop with gh:
   - title: `feat(digivoice): banner v5.8 mock-gap follow-up (#4947 / after #4950)`
   - body must: refs #4947 follow-up to #4950; list the 8 gaps closed; say HOLD hatch until Chris Mac visual after digivoice reload / HS relaunch; do NOT say Fixes if that would auto-close wrongly — use `Refs #4947` / follow-up wording
   - `--draft`
4. Print: full PR URL, tip SHA, files changed.

## Stop conditions (report immediately, do not stall)
- FreeTierError / rate-limit / Muse hang with zero diff
- Any blocker preventing draft PR

When done print exactly: PR_URL=… TIP_SHA=… FILES=…
