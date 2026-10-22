Review verdict: changes requested

QA acceptance for DIG-5204, run on the merged tree of both slices: exporter PR #6271 (head 3c551ad0aff55cf53964abf0a822019daf8fd5fb) on top of dashboard PR #6264 in develop. Two of the three acceptance conditions fail. PR #6271 is not the blocker, the QA Lead already approved it. The blocker is the dashboard slice, filed as DIG-5209.

Blockers

1. apps/dashboard/fixtures/tui-frames/manifest.json - the manifest names one frame only: digiquant-tui on /brief, file digiquant-tui.json, exporter clients/digiquant-tui/src/export-frame.ts. No digichat entry.
   Right: one more frame entry, source digichat-tui, path /thread, file digichat-tui.json, exporter clients/digichat-tui/src/export-frame.ts. /thread is the route clients/digichat-tui/src/capture.tsx records on (DEFAULT_PATH, line 30).

2. apps/dashboard/fixtures/tui-frames/digichat-tui.json - missing. The digichat exporter writes into the client tree, clients/digichat-tui/fixtures/digichat-tui.json (clients/digichat-tui/src/export-frame.ts line 24, DEFAULT_OUT), and nothing copies it into the dashboard fixture tree. The digiquant exporter writes straight into apps/dashboard/fixtures/tui-frames/digiquant-tui.json, which is why its frame is in the manifest and this one is not.
   Right: a committed copy under apps/dashboard/fixtures/tui-frames/, identical to the exporter output.

3. apps/dashboard/components/tui-recorded-frames.tsx lines 17 and 27 - the component imports only digiquantTuiFrame and sets COMMITTED_FRAMES = [digiquantTuiFrame]. The render path never reads the manifest, so a manifest entry alone does not put the frame on screen. The main desk pane can show the digiquant frame only.
   Right: the digichat frame imported and added to COMMITTED_FRAMES, so the desk pane renders one entry per committed frame.

Checks

- Manifest names the digichat frame with its exporter and route - FAIL (blocker 1).
- Dashboard renders that frame - FAIL (blockers 2 and 3).
- Record shape agrees field for field, producer to consumer - PASS. clients/digichat-tui/src/frame.ts declares RecordedFrame {source, path, capturedAt, width, height, frame}. apps/dashboard/lib/tui-preview.ts declares RecordedTuiFrame with the same six members and the same types. The produced JSON carries exactly those six keys and isRecordedTuiFrame accepts it.

Evals

- Acceptance kit, .qa/acceptance/tui-frame-acceptance.test.ts, run with npx vitest run --config .qa/acceptance/vitest.config.ts on the merged tree: 4 passed, 7 failed. The 7 red are the gap: 4 manifest checks, 2 render checks, 1 fixture copy check.
- The same kit after the minimal dashboard fix in the worktree (fixture copy, manifest entry, COMMITTED_FRAMES import): 11 passed, 0 failed. The tree was then restored, so the product branch is unchanged.
- apps/dashboard shipped suite, npx vitest run lib/tui-frames-manifest.test.ts lib/tui-preview.test.ts components/tui-recorded-frames.test.tsx: 3 files, 19 tests, all pass. Nothing in the shipped suite pins the digichat frame, which is why the gap ships green.
- clients/digichat-tui, bun test: 70 pass, 1 fail. The failure is pre-existing on develop and not caused by #6271: src/read.test.ts "chat base URL is the surface-config chat endpoint, not the desk runner" expects 127.0.0.1:3000 while packages/surface-config/src/endpoints.ts now defaults to 127.0.0.1:3005, changed in bbdb19acb5. #6271 touches neither file.
- Exporter reproduction, bun src/export-frame.ts with an out path: the output matches the committed clients/digichat-tui/fixtures/digichat-tui.json byte for byte except capturedAt. Frame text identical, 70x40, source digichat-tui, path /thread.
- I could not reproduce the fixed-port collision of finding 4, the fixture port 8792: two concurrent exporters both succeeded. Not claimed as a repro.

Recorded, not fixed (DIG-5204 asks to record only)

- The exporter is implemented twice: clients/digiquant-tui/src/{frame,capture,export-frame,fixture-api}.ts and clients/digichat-tui/src/{frame,capture,export-frame,fixture-api}.ts. The record type is declared a third time in the dashboard as RecordedTuiFrame. Drift has started: the dashboard doc comment calls the field "Captured width in terminal columns" while both producers write the ink extent of the crop, 70 columns of a 100-column terminal. A shared packages/tui-frame would remove the drift.

Suggestions

1. Ship the acceptance checks with the fix. The 11 checks in .qa/acceptance/tui-frame-acceptance.test.ts belong in the dashboard suite so the gap cannot come back. The shipped manifest contract test only checks that a listed frame matches its file, never that a produced frame reaches the dashboard.
2. Make the manifest the single source of truth for the render path, or add a check that fails when a committed fixture is missing from the manifest and from COMMITTED_FRAMES. Two hand-maintained lists is how this gap opened.
3. One exporter, one writer. Either the digichat exporter writes into the dashboard fixture tree like the digiquant one does, or a copy step runs in CI. A dashboard copy that depends on a person remembering to move it will go missing again.

Next: DIG-5209 carries the dashboard fix for the Frontend Engineer. DIG-5204 is blocked on DIG-5209 and QA re-verifies the three acceptance conditions, with the kit at 11 of 11, when DIG-5209 lands.
