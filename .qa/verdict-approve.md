Review verdict: approve

Re-ran the acceptance against merged develop. All three conditions pass. The blocker (DIG-5209) is gone.

- `origin/develop` head at this run: `5302004aff` — "feat(dashboard): render the digichat recorded frame in the desk pane (#6295)", merged 2026-10-22T12:43:36Z.
- I read the Frontend Engineer's note first and re-ran the checks myself rather than on the claim. Both adaptations it names are correct: the kit moved to `apps/dashboard/lib/tui-frame-acceptance.test.ts`, and the producer record type moved to `packages/tui-frame/src/record.ts` (DIG-5212 / PR #6290).

## Conditions

1. **Manifest names the digichat frame with its exporter and route — PASS.**
   `apps/dashboard/fixtures/tui-frames/manifest.json` holds two frame entries now. The digichat one: source `digichat-tui`, path `/thread`, file `digichat-tui.json`, exporter `clients/digichat-tui/src/export-frame.ts`. The test reads the route from the exporter's own `DEFAULT_PATH` in `clients/digichat-tui/src/capture.tsx` rather than hardcoding it, and the exporter file exists in the tree.

2. **The dashboard renders that frame — PASS.**
   - `apps/dashboard/fixtures/tui-frames/digichat-tui.json` exists, and `cmp` says it is byte-identical to the producer's own copy `clients/digichat-tui/fixtures/digichat-tui.json` (70x40, capturedAt 2026-10-22T05:45:00.868Z).
   - `apps/dashboard/components/tui-recorded-frames.tsx` lines 17-18 import both frames and line 28 sets `COMMITTED_FRAMES = [digiquantTuiFrame, digichatTuiFrame]`.
   - The pane renders two entries, the digichat summary is there, and the frame text sits in the DOM byte for byte from the dashboard copy.

3. **Record shape agrees field for field — PASS, and now structural.**
   `packages/tui-frame/src/record.ts` declares `RecordedFrame {source, path, capturedAt, width, height, frame}`, and `apps/dashboard/lib/tui-preview.ts:23` declares `export type RecordedTuiFrame = RecordedFrame` — one declaration, two consumers, no copy to drift. The producer record carries exactly those six keys and `isRecordedFrame` / `isRecordedTuiFrame` accepts it. The drift I recorded last time is gone: the shared doc comment now says "Columns of ink in the cropped frame … a 100-column terminal whose pane ends at column 70 records 70", and the record says `width: 70`.

## Evals

- Shipped suite on merged develop: `cd apps/dashboard && npx vitest run lib/tui-frame-acceptance.test.ts components/tui-recorded-frames.test.tsx lib/tui-frames-manifest.test.ts` → **3 files, 21 tests passed**. The 11 acceptance checks are the same 11, in count and in intent.
- The shipped file is a faithful port of my kit. `diff` against `.qa/acceptance/tui-frame-acceptance.test.ts` shows four changes, all of them neutral or stronger: the repo root path (one level deeper), the producer type file moved to `packages/tui-frame/src/record.ts`, a `renderPane()` helper that pins `NEXT_PUBLIC_DIGI_TUI_PREVIEW=1` so the render checks do not depend on the shell environment, and the copy check no longer returns silently when the producer record is missing — it now requires it.
- The suite runs in CI: `apps/dashboard/vitest.config.ts` includes `lib/**/*.test.ts`, so the acceptance file is picked up by the plain `vitest run` in `apps/dashboard`, not only when named by hand.
- Negative control, run by me: with the product files reverted to pre-fix `b94bab0310` (manifest, `COMMITTED_FRAMES`, dashboard fixture) and the new test kept, the suite goes **7 failed / 4 passed of 11** — the same gap as before the fix. The shipped test has teeth.
- Full dashboard suite on merged develop: **250 files passed, 1 failed** (`components/app-shell-context.test.tsx`, 2 tests). Pre-existing and unrelated: it fails identically at `b94bab0310`, with `localStorage` undefined in the node environment ("localStorage is not available because --localstorage-file was not provided"). Not caused by the frame work and not part of this acceptance. Recorded here, no ticket raised.
- `packages/tui-frame`: `bun test` → 21 pass, 0 fail.
- `clients/digichat-tui`: `bun test` → 73 pass, 0 fail. The single pre-existing failure I reported last time (`src/read.test.ts`, chat base URL port) is gone on this head.

## Notes, non-blocking

- The exporter asymmetry is unchanged: `clients/digichat-tui/src/export-frame.ts:23` writes into the client tree, `clients/digiquant-tui/src/export-frame.ts:32` into the dashboard tree. What changed is that the gap can no longer ship silently — the copy check fails whenever the dashboard copy stops matching the producer record, so a re-recorded frame turns CI red until the copy is refreshed. That closes my earlier suggestion 3 by a gate rather than by a script.
- The render path still hardcodes `COMMITTED_FRAMES` instead of reading the manifest, but the shipped checks now pin both frames and the count: the dashboard suite pins the digiquant frame's text, the acceptance suite pins the digichat label and text, and the rendered count must equal the manifest's frame count. My earlier suggestion 2 is covered by checks, not by structure.

## Evidence

- Branch `DIG-5204-qa-acceptance-the-digichat-recorded-frame-lands-in-the-dashboard-manifest-and-renders` at `9cdf440a8e` (merge of `origin/develop` into the QA branch). `git diff origin/develop` over `apps/dashboard clients/digichat-tui clients/digiquant-tui packages/` is empty, so the evaluated tree is merged develop.
- The kit and the findings live under `.qa/`.

Next: DIG-5204 closes as accepted. DIG-5209 is already closed by the merge.
