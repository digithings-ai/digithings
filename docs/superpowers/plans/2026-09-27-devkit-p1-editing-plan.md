# devkit P1 — editable sidebar + file save

## Context

P0 (issue #4691, PR #4692, branch `task/4691-devkit-p0`) shipped a read-only
devkit at `/devkit`: deployments menu (local `config/*.yaml` + env tenants,
secrets redacted server-side), shared `POST /api/devkit/validate`, and a live
saved-file preview through the baseline projection pipeline
(`resolveRouteClientConfig` → `ThreadSkinView` on the dev BFF).

P1 makes the sidebar editable and adds file save. Read-only P0 behavior and
all P0 safety properties (dev-only page + loopback-gated APIs, production
404s, secret redaction with `__DEVKIT_PRESERVED__` sentinel) are preserved.

Prior Q&A decisions (locked):
1. Sidebar collapse follows the digichat `chat-shell.tsx:99` app-shell pattern
   (`useState`, grid/flex animation, `Cmd/Ctrl+/` with input-focus guard,
   `aria-expanded`, slim rail with expand button when collapsed).
2. Save writes in place; new files are named `config/<slug>.yaml`; `hosts`
   sub-entries save into the parent file; env tenants stay view-only.
3. Secrets: preserve-plus-optional-replace via the sentinel (unchanged
   sentinel values restore from disk; explicitly replaced values are written).
4. Editors are accordion sections (native `<details>`), one per config area.
5. No named theme presets in v1 — skin + theme + accent controls only.

## Step 1 — `draft.ts` + text helpers

New `app/(devkit)/devkit/draft.ts`:
- `EntryDraft { entryId, text, parsed, issues, dirty }`; drafts are created
  from the served `redactedText` (secrets already sentinelized server-side).
- `dirty = text !== savedText` (plain string compare).
- Parse via `POST /api/devkit/validate`, debounced ~400ms; while invalid the
  preview keeps the last-valid `parsed` deployment.
- Switching entries with a dirty draft uses a native `confirm()` guard.
- New-file drafts carry no `entryId` until first save.
- Form edits go through tested text helpers
  (`setScalar` / `setBoolean` / `setStringList`) with round-trip unit tests.

Tests: `draft.test.ts` — dirty transitions, helper round-trips, sentinel
passthrough (sentinel values are never parsed as real secrets).

## Step 2 — `POST /api/devkit/save`

New `app/api/devkit/save/route.ts` (+ `route.test.ts`):
- Gate: `isLocalBaselinePreview()` (loopback + non-production), production 404.
- Body `{ entryId?, text }`; validate via the shared validator (same code path
  as `/api/devkit/validate`); fail closed on issues.
- Sentinel restore: any secret path still holding `__DEVKIT_PRESERVED__` is
  restored from the current disk value before validation; explicitly changed
  secret values are written (local dev only — the operator's explicit act).
- Write + `.bak` of the previous file; `realpath` containment inside the
  `config/` allowlist (hosts entries resolve to the parent file).
- Env-tenant ids are refused (view-only, enforced server-side, tested).

## Step 3 — shell rework (no top bar, collapse)

Rewrite `devkit-client.tsx` shell:
- Remove the top header bar; full-height flex row (sidebar + preview).
- Keep persisted sidebar width + drag handle; add collapse per the
  `chat-shell.tsx:99` pattern (state, animation, `Cmd/Ctrl+/` with
  input/textarea/contentEditable focus guard, `aria-expanded`, slim rail with
  expand button when collapsed).
- `DevkitPreview` receives the draft as its `deployment` prop — it keeps no
  saved/draft knowledge; optional unsaved dot in the preview header.

## Step 4 — accordion editors

Accordion (`<details>`) sections bound to the draft text via the Step-1
helpers (form edits rewrite the draft text, so raw YAML and forms can never
diverge):
- **Identity**: slug read-only for existing entries; editable in the new-file
  flow with `/^[a-z0-9-]+$/` validation + uniqueness check; aliases as CSV.
- **Backend**: type select switching variants with a discard warning;
  digigraph fields (`digisearchIndex`, `vaultPathPrefix`), foundry fields
  (`projectEndpoint` https, `agentName`); persistence / auth selects.
- **Appearance**: 12-id skin select, dark/light segmented control, mode
  select, title / welcome title+body / placeholder / suggestions list,
  accent color picker + hex input validated `#rrggbb`, attribution tri-state,
  launcher options. No named presets in v1.
- **Features**: 6 checkboxes (attachments, dictation, speech, sources,
  modelPicker, branchPicker) + view / thinking / pageContext selects.
- **Models**: default string, available list editor, allowPicker.
- **Tools**: catalog rows (id, label, default flag), allowUserToggle.
- **MCP**: server rows (id, url, label, default; token/tokenEnv as masked
  secret rows with preserve-or-replace semantics), allowUserServers,
  allowAddForm.
- **Gate**: mode, activityDetail, llmAccess, consumeUrl (masked secret row),
  lockedContact, showByok, showLanguageSelector, webSearch, requiredPlanTier.

Secret rows render masked with a per-row "replace" affordance; untouched rows
keep the sentinel.

## Step 5 — raw YAML collapse + new-file flow

- Raw YAML moves into a collapsed section at the bottom of the sidebar
  (textarea + server validation display; no yaml lib in the client bundle —
  parse/validate/dump stay server-side).
- "New deployment" button: blank draft with editable slug; on save writes
  `config/<slug>.yaml` inside the allowlist (slug validation + uniqueness,
  tested); the new entry appears in the picker.
- Save button (with dirty indicator) persists the draft via Step-2 API, then
  refreshes the entry list + saved text and clears dirty.

## Step 6 — verification

- New tests green; full `apps/digichat` + `packages/ui` suites green;
  `npm run lint` 0 errors; `npm run build` green.
- Manual on http://127.0.0.1:3001/devkit: edit a value in a form, watch the
  preview follow without saving; save (`.bak` on disk), reload, confirm
  persisted; invalid draft blocks save with issues shown; secret sentinel
  round-trip preserves disk secrets; env-tenant entries show no save UI;
  production build still 404s; non-loopback POST refused.
- Security self-check: secret values never appear in any GET response;
  path-escape attempts fail closed; no `AUTH_SECRET`/session material in
  responses.

## Explicitly deferred (still)

- Hosted/multi-user devkit, assistant-driven configuration.
- New skin component scaffolding.
- Remote configs; production exposure of any kind.
