# DIG-5204 — QA acceptance findings (QA Engineer seat)

## Setup
- Worktree: `.paperclip/worktrees/DIG-5204-qa-acceptance-...`, branch `DIG-5204-qa-acceptance-...`.
- Base: `origin/develop` = `9e35c905ab` (contains #6264 dashboard slice, commit `59c0d03c24`).
- PR #6271 (digichat exporter) is OPEN, head `3c551ad0aff55cf53964abf0a822019daf8fd5fb`, CI green, QA Lead approved
  (comment 6334253516). NOT merged at run time.
- Simulated "both in develop": local merge `192765067d` of `origin/DIG-2698-d9-digichat-tui-exporter` into the branch.
  Product tree restored afterwards; only `.qa/` is untracked. `package-lock.json` restored after `npm install`.

## The three acceptance conditions (both in develop)
1. manifest names the digichat frame with exporter + route  → FAIL
2. dashboard renders that frame                            → FAIL
3. record shape agrees field for field producer ↔ consumer → PASS

## Evidence
### A. Manifest (apps/dashboard/fixtures/tui-frames/manifest.json)
- develop manifest `frames` = exactly one entry: `digiquant-tui` / `/brief` / `digiquant-tui.json` /
  exporter `clients/digiquant-tui/src/export-frame.ts`. No digichat entry.

### B. Dashboard copy + render
- digichat exporter writes `clients/digichat-tui/fixtures/digichat-tui.json` (DEFAULT_OUT, src/export-frame.ts:24).
  No copy under `apps/dashboard/fixtures/tui-frames/`.
- digiquant exporter writes STRAIGHT into the dashboard tree: `clients/digiquant-tui/src/export-frame.ts`
  DEFAULT_OUT = `apps/dashboard/fixtures/tui-frames/digiquant-tui.json`. This asymmetry is the root cause.
- `apps/dashboard/components/tui-recorded-frames.tsx:17,27` hardcodes
  `COMMITTED_FRAMES = [digiquantTuiFrame]`. The render path never reads the manifest.
- Consequence: the main desk pane can show only the digiquant frame.

### C. Record shape (PASS)
- Producer `clients/digichat-tui/src/frame.ts` `RecordedFrame` = {source, path, capturedAt, width, height, frame}
- Consumer `apps/dashboard/lib/tui-preview.ts` `RecordedTuiFrame` = {source, path, capturedAt, width, height, frame}
- Identical member names and types (checked with the TypeScript compiler API).
- Fresh exporter run reproduced the committed fixture byte-for-byte except `capturedAt`
  (fresh 2026-10-22T07:23:33.681Z, committed 2026-10-22T05:45:00.868Z); frame text identical; 70x40.
- Producer record keys exactly the six consumer fields; `isRecordedTuiFrame(record)` = true.

## Evals run
- Acceptance kit `.qa/acceptance/tui-frame-acceptance.test.ts` (11 checks) with
  `.qa/acceptance/vitest.config.ts` (root = repo root, aliases like the dashboard config):
  - on the merged tree: **4 passed, 7 failed** (7 red = the gap).
  - after applying the minimal dashboard fix in the worktree (manifest entry + fixture copy +
    COMMITTED_FRAMES import): **11 passed, 0 failed**. Tree restored afterwards. So the kit is a real gate.
- `cd apps/dashboard && npx vitest run lib/tui-frames-manifest.test.ts lib/tui-preview.test.ts
  components/tui-recorded-frames.test.tsx` → 3 files, 19 tests, all PASS. The shipped suite does not
  pin the digichat frame; that is why the gap ships green.
- `cd clients/digichat-tui && bun test` → **70 pass, 1 fail**. The single failure is pre-existing on develop:
  `src/read.test.ts` "chat base URL is the surface-config chat endpoint, not the desk runner"
  (expects 127.0.0.1:3000; surface-config default is 127.0.0.1:3005, changed in bbdb19acb5).
- `bun src/export-frame.ts` twice: reproduced the committed fixture (see C).

## Recorded, not fixed (per the issue: "Do not fix the duplicated exporter files here, only record them")
- The exporter is implemented twice: `clients/digiquant-tui/src/{frame,capture,export-frame,fixture-api}.ts`
  and `clients/digichat-tui/src/{frame,capture,export-frame,fixture-api}.ts`. The record type is declared a
  third time in the dashboard (`RecordedTuiFrame`). Drift has started: the dashboard doc comment says
  "Captured width in terminal columns" while both producers write the ink extent of the crop (70 of 100).
  A shared `packages/tui-frame` would remove the drift. Not fixed here.

## Final re-verification (after the fix landed)

- Trigger: comment `e95a8d1f-9832-4876-8940-601b1806ad07` from the Frontend Engineer — DIG-5209 closed
  by PR #6295, merged into develop 2026-10-22T12:43:36Z, merge commit `5302004aff`.
- `origin/develop` head at this run: `5302004aff`. The kit moved to `apps/dashboard/lib/tui-frame-acceptance.test.ts`
  and the producer record type moved to `packages/tui-frame/src/record.ts` (DIG-5212 / PR #6290).
- Branch state: `9cdf440a8e` = merge of `origin/develop` into the QA branch. `git diff origin/develop` over
  `apps/dashboard clients/digichat-tui clients/digiquant-tui packages/` is empty, so the evaluated tree is
  merged develop.

### The three conditions, re-measured

1. manifest names the digichat frame with exporter + route → PASS
   - `apps/dashboard/fixtures/tui-frames/manifest.json` now holds two frame entries; the digichat one is
     source `digichat-tui`, path `/thread`, file `digichat-tui.json`, exporter `clients/digichat-tui/src/export-frame.ts`.
   - The route is read by the test from the exporter's own `DEFAULT_PATH` in `clients/digichat-tui/src/capture.tsx`.
2. dashboard renders that frame → PASS
   - `apps/dashboard/fixtures/tui-frames/digichat-tui.json` exists; `cmp` says it is byte-identical to
     `clients/digichat-tui/fixtures/digichat-tui.json` (70x40, capturedAt 2026-10-22T05:45:00.868Z).
   - `apps/dashboard/components/tui-recorded-frames.tsx` lines 17-18 import both frames, line 28 sets
     `COMMITTED_FRAMES = [digiquantTuiFrame, digichatTuiFrame]`.
3. record shape agrees field for field → PASS, now structurally
   - `packages/tui-frame/src/record.ts` declares `RecordedFrame`; `apps/dashboard/lib/tui-preview.ts:23`
     declares `export type RecordedTuiFrame = RecordedFrame` — one declaration, two consumers.
   - The drift recorded below is gone: the shared comment says "Columns of ink in the cropped frame … a
     100-column terminal whose pane ends at column 70 records 70", and the record says `width: 70`.

### Evals on merged develop

- `cd apps/dashboard && npx vitest run lib/tui-frame-acceptance.test.ts components/tui-recorded-frames.test.tsx
  lib/tui-frames-manifest.test.ts` → **3 files, 21 tests passed**.
- `diff .qa/acceptance/tui-frame-acceptance.test.ts apps/dashboard/lib/tui-frame-acceptance.test.ts` → four
  changes, all neutral or stronger: repo root one level deeper; producer type file → `packages/tui-frame/src/record.ts`;
  a `renderPane()` helper that pins `NEXT_PUBLIC_DIGI_TUI_PREVIEW=1`; the copy check no longer returns silently
  when the producer record is missing. Same 11 checks, same intent.
- `apps/dashboard/vitest.config.ts` includes `lib/**/*.test.ts`, so the acceptance file runs in the plain
  `vitest run`, not only when named by hand.
- Negative control (mine): product files reverted to pre-fix `b94bab0310`, new test kept → **7 failed / 4 passed
  of 11**, the same gap as before the fix. The shipped test has teeth.
- Full dashboard suite: 250 files passed, 1 failed (`components/app-shell-context.test.tsx`, 2 tests).
  Pre-existing and unrelated: identical failure at `b94bab0310`; cause is `localStorage` undefined in the node
  environment ("localStorage is not available because --localstorage-file was not provided").
- `packages/tui-frame` `bun test` → 21 pass, 0 fail. `clients/digichat-tui` `bun test` → 73 pass, 0 fail
  (the pre-existing `src/read.test.ts` failure reported earlier is gone on this head).

### Residual (recorded, not blocking)

- The exporter asymmetry is unchanged: `clients/digichat-tui/src/export-frame.ts:23` writes into the client tree,
  `clients/digiquant-tui/src/export-frame.ts:32` into the dashboard tree. The gap can no longer ship silently:
  the acceptance copy check fails whenever the dashboard copy stops matching the producer record.
- The render path still hardcodes `COMMITTED_FRAMES` instead of reading the manifest, but the shipped checks now
  pin both frames and the count (dashboard suite pins the digiquant frame's text, acceptance suite pins the
  digichat label and text, count must equal the manifest's frame count).

## Board facts
- Frontend Engineer (dashboard owner) = eb3a7393-3939-431b-87d7-056288ed84e6 (reports to EM 6f361355).
  Owns DIG-2698, DIG-5138, DIG-5139.
- QA Engineer = 2070ef88-9002-422c-ae3d-781c5bbfcada (reports to QA Lead 54a431af).
- `dt-close-guard DIG-5204` → OK, safe to close, pending human_only=0.
- Precedent DIG-5134 (same seat, same kind of ticket, also FAIL): verdict comment + defect child issues
  of DIG-2698.

## Plan
1. File child of DIG-2698: the dashboard slice (manifest entry + fixture copy + COMMITTED_FRAMES wiring
   + ship the acceptance kit). Assignee Frontend Engineer.
2. Post the verdict comment on DIG-5204: `Review verdict: changes requested`, blockers first.
3. Set DIG-5204 blocked with `blockedByIssueIds` = [child id] so QA re-verifies when the fix lands.
