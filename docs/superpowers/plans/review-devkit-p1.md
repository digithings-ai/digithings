# Review: devkit P1 (uncommitted diff on `task/4691-devkit-p0`)

- Reviewer: fresh-context subagent (did not write this code)
- Subject: uncommitted P1 work — editable sidebar + file save for `/devkit`
- Scope reviewed: `draft.ts` + `draft.test.ts`, `devkit-save.ts` + `devkit-save.test.ts`,
  `api/devkit/save/route.ts` + `save/route.test.ts`, `devkit-client.tsx`,
  `devkit-preview.tsx`, `devkit-editors.tsx` (+ new `devkit-summary.tsx`),
  `devkit-configs.ts` + tests, `api/devkit/validate/route.ts` + tests,
  `devkit-isolation.test.ts`, `devkit-wire-contract.test.ts`,
  plan `docs/superpowers/plans/2026-09-27-devkit-p1-editing-plan.md`
- Out of scope (not reviewed): `route-menu.tsx`, `docs/architecture/digichat-ui-simplification.md`, plan docs
- Verdict: **needs-changes**
- Severity counts: blocker 0 / major 1 / minor 9 / nit 3

## Verification record (run by reviewer)

- `npx vitest run` on all 8 devkit test files from `apps/digichat`:
  `devkit-save.test.ts`, `devkit-configs.test.ts`, `devkit-wire-contract.test.ts`,
  `draft.test.ts`, `devkit-isolation.test.ts`, `validate/route.test.ts`,
  `save/route.test.ts`, `configs/route.test.ts` → **8 files, 99 tests, all pass**.
- Ad-hoc probe (temp test, since removed): `setStringList` over a block-scalar
  string list returned `applied: true` and emitted corrupt YAML (see M1).
- `npx eslint` on all 8 P1 source files → clean (no output).
- `git status` confirms no `packages/ui` or skin changes; only `apps/digichat` + docs touched.
- Author's wider claims (full 1418/1418 suite, prod build, live browser E2E) were
  **not** re-run; devkit-scoped suites plus code inspection cover this review.

## What checks out (no finding)

- Dev-only gating: page 404s in production (`devkit/page.tsx:8`), all three APIs
  gate on `isLocalBaselinePreview()` (loopback + non-production,
  `baseline-preview.ts:14-22`); save/validate route tests pin both 404 legs.
- Secrets: browser receives only sentinelized text + stripped deployments
  (`redactSecretLines`, `stripDeploymentSecrets`); save restores sentinels from
  disk at the text level and refuses residual/tampered/typed sentinels
  (`devkit-save.ts:150-183,248-254`); `.bak` before overwrite; env ids refused
  server-side (`parseDevkitSaveId:52-61`, tested).
- Path containment: absolute/`..`/backslash/non-`.yaml` rejected, realpath
  re-checked for existing files (`resolveDevkitFilePath:101-133`).
- Hosts-scope saves write the parent file only, with a scope-presence check
  (`checkDevkitScope:186-216`, tested both directions).
- New-file slug/filename agreement enforced server-side (`saveDevkitNewFile:311-318`).
- Race guards: debounced validate has a seq guard + text match
  (`devkit-client.tsx:239-267`); draft recreation has a `selectedIdRef` microtask
  token (`devkit-client.tsx:226-230`); `withValidation` keeps last-valid `parsed`.
- Plan match: Steps 1–5 all present as specified (draft model, save API, shell
  rework + collapse pattern, 8 accordion sections, raw-YAML collapse + new-file +
  save button). Two deviations, both benign: (1) new `devkit-summary.tsx` (not in
  plan — justified read-only view for env entries); (2) new-file draft seeds dirty
  (plan silent — but see M2, it has a real UX consequence).
- zod `.strict()` already pervasive in `deploy-config/schema.ts`; all P1 paths
  validate through that schema. No upstream creds to browser; MCP `setup` stripped
  server-side (`devkit-configs.ts:99-106`).

## Major

### M1 — `setStringList` silently corrupts string lists containing block scalars
`apps/digichat/src/app/(devkit)/devkit/draft.ts:748-770` (`listBlockEnd`).
`listBlockEnd` stops at the first deeper-indented continuation line, so editing a
form string list (suggestions, aliases, welcome body, models.available) whose
current YAML contains a block scalar (`- |`) **applies** and orphans the
continuation lines onto the new item. Verified live:
input `- |\n wrapped line one\n wrapped line two\n- plain` + set `["One"]` →
`- One\n wrapped line one\n wrapped line two\n- plain` (value silently becomes
"One wrapped line one wrapped line two"). Result is schema-valid, so save persists
the corruption (`.bak` is the only backstop). This violates the module's own
contract (`draft.ts:12-14`: unsafe edits return `applied: false`).
Fix: refuse when any item spans multiple physical lines or a dash rest opens a
block/flow scalar — e.g. pre-scan with the existing `locateListItems` (which
already consumes continuations correctly) and return `{ text, applied: false }`
unless every item is single-line plain. Add a round-trip test with a `- |` item.

## Minor

### m1 — Phantom "Discard unsaved draft changes?" has a deterministic mechanism
`apps/digichat/src/app/(devkit)/devkit/draft.ts:81-90` + `devkit-client.tsx:284-294`.
`createNewFileDraft()` sets `savedText: ""` with non-empty `text`, so a pristine
new-file draft is dirty **by construction**. Pressing `+ new` twice (or `+ new`
then any entry switch) triggers the confirm with zero user edits — matches the
reported "transient" exactly; no StrictMode/double-fetch theory needed (both
re-create identical text, staying clean). Not data-unsafe (fail-safe direction),
but it is the reported bug, reproducibly.
Fix: seed `savedText` with the template text and track "never saved" separately
for save-button enablement (save stays disabled until first real edit — strictly
better, also prevents accidentally saving the `new-deployment` template).

### m2 — Keystrokes during in-flight save are silently discarded
`devkit-client.tsx:298-354`. `saveDraft` captures `text` and posts; the textarea
and all editors stay enabled while `saving` (only the button disables). The
post-save refresh rebuilds the draft from disk text, dropping anything typed
mid-flight with no notice.
Fix: disable the textarea + editors while `saving` (pass a `disabled` prop through
`DevkitEditors` or render a blocking overlay), or after save, compare current
`draft.text` to the saved snapshot and keep the newer edits dirty instead of
clobbering.

### m3 — `ensureMap`/`descendExisting` range overshoot past the parent map
`draft.ts:218-226`, `262-271`. When the scan finds no closing sibling, `close`
defaults to `next.length`/`lines.length` instead of the already-known
`current.end`. After an ancestor-level insertion, lines past the parent's end
(a following sibling map, e.g. a `hosts:` block) fall inside the descended range,
and `locateChild` can then match a same-indent, same-name key in the wrong map.
Trigger is narrow (insert-then-descend + trailing blanks + name collision), and
save-time validation fails closed, but the fix is one word: default `close` to
`current.end`.

### m4 — `slugFromDraftText` breaks on quoted slugs, error message misleads
`devkit-client.tsx:74-77`, `devkit-save.ts:227-235`. The regex captures `\S+`,
so `slug: "foo"` yields `"foo"` (with quotes) → id `new:"foo".yaml` → server
rejects with `(id): not a writable entry`, hiding the real problem. A trailing
comment likewise yields "no deployment slug found".
Fix: strip one layer of matching quotes (reuse the `unquoteScalar` idea) and/or
derive the slug from the last-valid `parsed` deployment instead of regexing text.

### m5 — Invalid slug/hex "reverts" only in the draft, not in the input
`devkit-editors.tsx:499-503,621-636`. `TextRow` is uncontrolled (`defaultValue`);
when `onCommit` drops an invalid value, `e.target.value` keeps displaying it while
the draft holds the old value — the comment "revert: input restores on blur" is
inaccurate and save then uses the old slug under the new display.
Fix: set `e.target.value = current` on the invalid path (as already done for the
`required`-empty path at line 81).

### m6 — Backend variant fields desync after raw-YAML backend-type edits
`devkit-editors.tsx:429-436`. `backendType` is local state initialized once per
mount; editing `backend.type` in raw YAML (or a disk refresh under the same
`entryId`) leaves the form showing the old variant's fields, and committing one
writes a foreign key under the new backend (caught by validation → save blocked,
so fail-closed, but confusing).
Fix: derive the displayed variant from the draft text (or sync `backendType` when
`draft.text` changes outside the select).

### m7 — New-file path skips the symlink realpath check
`devkit-save.ts:101-133` with `{ mustExist: false }`. The `mustExist: false` leg
does string-prefix containment only. A planted dangling symlink at
`config/<slug>.yaml` passes `existsSync` (false for dangling) and `writeFileSync`
then follows it outside the config dir. Pre-existing write leg is protected;
only creation is exposed. Dev-only + needs a local plant, hence minor.
Fix: in the `mustExist: false` leg, `realpathSync` the parent dir and require it
to stay inside root (or open with `O_NOFOLLOW` semantics).

### m8 — No `beforeunload` guard for dirty drafts
`devkit-client.tsx:271-280`. Entry-switch and `+ new` are guarded, collapse needs
none (draft kept), but navigating/reloading away drops a dirty draft silently.
Fix: add a `beforeunload` listener while `draft` is dirty (dev-only page; cheap).

### m9 — Save route happy-path/422 wiring untested at the route level
`apps/digichat/src/app/api/devkit/save/route.test.ts:1-37` covers 404×2 + 400
only. Lib-level coverage is thorough, but the route's own mapping (200 vs 422,
`join(process.cwd(), "config")` base — same expression as configs route, so
consistent) has no test.
Fix: add one route test with a temp `config/` dir (or injectable base) asserting
200-on-ok and 422-on-invalid.

## Nits

- n1 — `matchKeyLine` (`draft.ts:117-121`) false-matches dash lines (`- id: x`
  parses as key `"- id"`). Harmless on valid files (no `keyPath` segment ever
  equals `"- id"`, and first-child indent detection only matters on
  invalid-as-map structures), but a `^-` guard would make the invariant explicit.
- n2 — Doc inaccuracy: `devkit-configs.ts:53-57` says save "restores only
  schema-known secret paths", but `restoreDevkitSentinels` is purely textual and
  restores *any* masked line (superset — safe, just misdescribed). Fix the comment.
- n3 — Save route imposes no body-size bound (`save/route.ts:24-30`). Loopback
  dev-only makes this negligible; a 1 MB cap would be free hardening.

## Suggested fix order

M1 (data corruption, contract violation) → m1 (reported UX bug, mechanism found)
→ m2 (silent edit loss) → m7 (write-escape hardening) → m3/m4/m5/m6/m8/m9 →
nits. M1 + m1 + m2 are the needs-changes drivers; the rest could ride as
follow-ups without blocking.

## Resolution (author session, 2026-09-28)

All 13 findings fixed on `task/4691-devkit-p0`; devkit suites 103/103 green
(101 + 2 new M1 regression tests), eslint 0 errors on all touched files,
tsc error count unchanged at the 10 pre-existing baseline errors, zero new
ones:

- M1 — `listBlockEnd` now returns -1 on any nested content (block-scalar
  continuations, nested maps/lists) instead of cutting the owned region
  mid-item; both the replace and the clear (`key: []`) branches refuse.
  Pinned by `setStringList` "refuses a list with block-scalar items" +
  "refuses clearing a list with block-scalar items" tests (byte-identical
  refusal). Note: `locateListItems` (read path) still consumes continuations
  for display — only the write path refuses.
- m1 — `createNewFileDraft` seeds `savedText` from the exported
  `NEW_FILE_TEMPLATE`; pristine new drafts are clean, so +new/switch no
  longer confirm with zero edits (the "transient" confirm is explained and
  gone). Save stays dirty-gated. Test asserts starts-clean + dirty-after-touch.
- m2 — `commit()` refuses while `saving`; editors wrapped in a disabled
  fieldset plus textarea/picker/+new disabled during save.
- m3 — `ensureMap`/`descendExisting`/`locateScope` close defaults use
  `current.end`/`end` instead of `lines.length`.
- m4 — `slugFromDraftText` strips one matching quote layer.
- m5 — `commit` already returned boolean; now threaded through: TextRow /
  TextListRow / SelectRow / TriRow / BoolRow `onCommit`s return applied and
  revert the control's display on false; all braced inline sites + `commitBody`
  + slug/accent guards return the boolean; SecretRow stays open on refusal.
- m6 — `backendType` resyncs from the draft's parsed type via a
  queueMicrotask-deferred effect (repo lint pattern); `switchBackend`
  only moves local state when the commit applied.
- m7 — create leg realpaths the parent dir and contains it; missing
  intermediate dirs fail closed.
- m8 — `beforeunload` guard keyed on dirty state.
- m9 — `resolveDevkitConfigDir()` honors `DEVKIT_CONFIG_DIR` (dev-only);
  route happy-path test (seed → POST → 200 + disk content + `.bak`) plus a
  413 oversized-body test.
- n1 — `matchKeyLine` rejects dash-led lines.
- n2 — redaction comment rewritten to describe textual restore.
- n3 — 1 MB cap enforced on content-length header (413) and parsed text
  length (413).

Live re-verification (dev :3001, zero console errors): new-file loop
(+new → slug → backend switch → save → `config/zzscratch.yaml` on disk →
cleanup), hosts-scoped title edit → surgical 1-line parent save → `.bak`
→ restore. Production gates re-confirmed via `next start`: page + configs
GET → 404, validate/save POST → 404, configs POST → 405 (GET-only).
