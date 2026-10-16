# digichat devkit — local config workbench (plan)

## Goal

A local-first devkit surface for onboarding clients and configuring chats:
browse every deployment config, edit features/copy/models/tools/MCP/gate,
preview the result side-by-side in a live chat, and save back to YAML.
No chat-to-configure assistant in v1 (architecture keeps that door open).

Decisions (owner, 2026-09-26): name **digichat devkit** (lowercase per repo
naming canon); **forms + raw YAML**; **write back** to local YAML files;
preview **live from unsaved draft**.

## Non-negotiables

- Dev-only like `/baseline`: `notFound()` in production builds; file listing,
  reading, validating, and writing go through API routes gated by
  `isLocalBaselinePreview()` (`apps/digichat/src/lib/baseline-preview.ts`:
  non-production + loopback hostname). Per `apps/digichat/AGENTS.md`
  pre-flight, these routes claim the same dev-only exception as
  `POST /api/baseline-chat` (no `requireDigiChatAuth()`), and must be
  documented as such at the route.
- Local files only: `apps/digichat/config/*.yaml`, `config/examples/**`, and
  `DIGICHAT_EMBED_TENANTS` env tenants (**read-only badge**, never written).
- Save API confines writes: realpath containment inside the two config dirs,
  `.yaml` extension only, no dotfiles — fail closed on any escape.
- Secrets safety: secret scalars (`deployment.token`, `hosts.*.token`,
  `mcp.servers[].token`, `gate.consumeUrl`) are served redacted (sentinel)
  and restored from disk on save (see § Save modes). `tokenEnv` holds env
  var *names*, not secrets — passes through. MCP `url` values stay editable
  (local-only UI; internal hostnames, not credentials).
- No backend changes: preview reuses the existing dev BFF
  (`POST /api/baseline-chat` loopback route); no new upstream, auth, or
  persistence paths.
- New skin *code* (new `THREAD_SKINS` id + component) is out of v1 — v1
  covers new skin *configs* (clone an example skin YAML, pick any existing
  skin id, preview). Code scaffolding is a named follow-up.

## Projection fidelity (verified 2026-09-26)

- `toDigichatClientConfig`
  (`lib/deploy-config/client-projection.ts:174`) copies declared fields only
  and covers: full `chrome` (mode/theme/skin/title/welcome/suggestions/
  placeholder/accent/attribution/defaultLanguage/transcript/launcher),
  `persistence`, `auth`, all of `features` (spread), `models`, `cli`,
  tools catalog (`id`/`default`/`label`), MCP (`id`/`label`/`default` +
  allowUserServers/allowAddForm), `gate` (mode/llmAccess/lockedContact/
  showByok/showLanguageSelector/webSearch). It provably drops
  `url`/`token`/`tokenEnv`/`authHeader` (`client-projection.test.ts:25`).
- `clientConfigFromEmbedTenant` (`lib/deploy-config/embed-bridge.ts:16`)
  covers the same ground in embed shape; either projection feeds the preview.
- Schema is `.strict()` (`schema.ts`): **unknown keys are rejected, not
  passed through**. Consequences: files with unknown keys are invalid —
  selectable, raw-fixable, but preview stays off and Save stays disabled
  until valid. No silent key-dropping anywhere in v1.
- Preview-faithful vs saved-only fields. Transport stays on the dev BFF, so
  these are **saved but not previewed** and must carry a "saved, not
  previewed" badge in the form: `backend.*`, `mcp.servers[]` url/setup/token*,
  `gate.consumeUrl`/`requiredPlanTier`/`activityDetail`, `persistence`,
  `auth`, `cli`. Everything else in § Architecture previews live.

## Architecture

```text
/devkit (dev-gated route group app/(devkit)/devkit/)
├── left: deployments menu — server lists config/*.yaml + examples/**
│   (+ env tenants read-only), parses each with the existing schema loader.
│   Invalid files (incl. unknown-keys under .strict()) show inline with
│   their zod error, still selectable for raw fixing; preview off.
├── center: editor, two tabs over one DraftConfig (parsed-YAML object)
│   ├── Form — controlled inputs for: features.* toggles, models
│   │   default/available/allowPicker, chrome welcome/placeholder/suggestions,
│   │   tools catalog rows (default on/off), mcp.servers list (url + default;
│   │   token fields masked), gate mode/llmAccess/showByok/webSearch, skin,
│   │   attribution. Saved-only fields badged (see above).
│   └── Raw YAML — plain textarea, NO client yaml lib: text is POSTed
│       (debounced) to the validate endpoint; errors shown, Save disabled
│       while invalid.
├── right: live preview — ThreadSkinView (skin id from draft) with the dev
│   runtime, fed by projecting the UNSAVED draft through
│   toDigichatClientConfig / clientConfigFromEmbedTenant. What you see is
│   what save persists, modulo the badged saved-only fields.
└── Save bar — dirty indicator, Validate, Save (fail closed).
```

Draft model: single `DraftConfig` per selected file; form and raw tabs are
two views over it (raw edits re-parse into draft; form edits re-serialize).
Switching files with a dirty draft asks to save/discard (native confirm v1).

## Save modes (fidelity contract)

- **Raw save: verbatim.** Server `yaml.load`s the submitted text, validates
  against the schema (with secret-sentinel restore first), and writes the
  submitted text byte-for-byte. Comments, ordering, formatting preserved.
- **Form save: lossy dump.** Server validates the submitted draft object and
  writes via `yaml.dump`. First form-save normalizes formatting, strips
  comments, and reorders nothing (insertion order kept) — UI warns explicitly
  ("Form save normalizes formatting and drops comments — .bak kept") and
  every write keeps a `.bak` sibling.
- **Secret-sentinel restore:** served raw text redacts secret scalars to
  `__DEVKIT_PRESERVED__`; on save, any secret path still holding the sentinel
  is restored from the current disk value before validation. A changed
  secret value is written (local dev only — operator's explicit act).
- No `js-yaml` in the client bundle: parse/validate/dump all server-side;
  the single validator is the existing schema (one source of truth).

## Files (create / modify)

Create:

- `app/(devkit)/layout.tsx` — isolated dev layout (mirror baseline isolation)
- `app/(devkit)/devkit/page.tsx` — dev gate + shell mount
- `app/(devkit)/devkit/devkit-client.tsx` — menu + editor + preview shell
- `app/(devkit)/devkit/config-forms.tsx` — feature/copy/model/tool/mcp/gate
  fields + saved-only badges
- `app/(devkit)/devkit/raw-yaml-editor.tsx` — textarea + server validation
  display (no yaml lib client-side)
- `app/(devkit)/devkit/draft.ts` — draft type, parse/project helpers (wrap
  existing schema + projection; no new config semantics)
- `app/api/devkit/configs/route.ts` — GET list+parse+redact (loopback-gated)
- `app/api/devkit/validate/route.ts` — POST text/object → zod issues
  (loopback-gated; shared by editor and save)
- `app/api/devkit/save/route.ts` — POST validate (+sentinel restore) → write
  +.bak, realpath-contained (loopback-gated)
- `app/(devkit)/devkit/*.test.ts(x)` — draft roundtrip, gate tests,
  projection of edited draft, redaction/sentinel-restore, path-containment
  (no real file writes; tmp dir for the write path)

Modify (minimal):

- `docs/digichat/SKIN-GALLERY.md` — devkit section (flows, safety rules).
- Nothing in `packages/ui`, skins, shells, or deploy-config semantics.

Skin id list for the picker: import from the kit if a client-safe export
exists, else hardcode the 12 ids with a test pinning parity against the
registry (verify during P0; no new skin ids in v1 either way).

## Verification

- New tests green; full `apps/digichat` + `packages/ui` suites green;
  `npm run lint` 0 errors; `npm run build` green.
- Manual on http://127.0.0.1:3001/devkit: open each local YAML (incl. one
  invalid file), toggle a feature + edit copy, watch preview follow without
  saving, raw-save (byte-identical except edits), form-save (warning shown,
  `.bak` on disk), reload, confirm persisted; env-tenant entry read-only;
  production build 404s; non-loopback POST refused.
- Security self-check: secret values never appear in any GET response;
  sentinel round-trip preserves disk secrets; path escape attempts fail
  closed; no `AUTH_SECRET`/session material in responses (AGENTS.md checklist).

## Phases (subagent-deployable slices)

- P0: route shell + deployments menu (list + read-only redacted view +
  preview of saved file) + validate endpoint. Proves listing / redaction /
  projection. Skin-id sourcing verified here.
- P1: raw YAML edit + draft + live preview + verbatim save API. Core loop.
- P2: form tab for common knobs + MCP/tools defaults viewer + lossy-dump
  save with warning + .bak.
- P3: clone-as-new flow (new filename inside allowlist), dirty-guard
  polish, docs, review + merge.

## P0 task breakdown (build-session handoff)

T1 — server: configs list+redact.
`app/api/devkit/configs/route.ts`: loopback gate (`isLocalBaselinePreview`,
dev-only exception documented at the route per AGENTS.md pre-flight);
enumerate `config/*.yaml` + `config/examples/**/*.yaml`, parse each with the
existing schema loader, redact secret scalars to `__DEVKIT_PRESERVED__`,
return `{ path, ok, redactedText, issues }` per file; env tenants listed
read-only. Tests: gate refuses production/non-loopback; secrets absent from
every response; invalid file surfaces zod issues.

T2 — server: validate endpoint. `app/api/devkit/validate/route.ts`: POST
`{ text }` or `{ object }` → `{ ok, issues }` via the existing schema.
Shared by editor and save. Tests: valid/invalid/unknown-keys(strict) cases.

T3 — route shell + menu + read-only view. `app/(devkit)/layout.tsx` (mirror
baseline isolation), `devkit/page.tsx` (production `notFound()`), menu
listing from T1 with per-file validity, read-only redacted YAML view.
Verify skin-id sourcing here (kit client-safe export vs hardcoded + parity
test). Tests: gate test for the page; menu renders fixture list.

T4 — preview of saved file. `devkit-client.tsx` preview pane: project the
selected file's parsed deployment through `toDigichatClientConfig` /
`clientConfigFromEmbedTenant` into ThreadSkinView + dev runtime
(`POST /api/baseline-chat`). No editing yet. Manual: each local YAML
previews; invalid file shows issues, preview off.

T5 — P0 verification: new tests + full `apps/digichat` + `packages/ui`
suites green, lint 0 errors, build green; manual checklist (menu, redacted
view, preview per file, prod 404, non-loopback refusal); in-session review
with findings file before merge.

## Explicitly deferred

- Hosted/multi-user devkit with assistant-driven configuration (v2; draft
  model is JSON-serializable and API-first so an agent can drive it later).
- New skin component scaffolding (new THREAD_SKINS id + template files).
- Remote configs (other repos, live tenants beyond env) — local files only.
- Production exposure of any kind.
