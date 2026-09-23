# digichat — config-driven container: program plan

Status: **proposed** (successor to the approved plan in
`~/.plannotator/plans/digichat-config-driven-contain-2026-09-22-approved.md`).
This document reorganizes the remaining work around three decisions taken on
2026-09-22 and adds the two new workstreams they create.

## North star

> A modular, easy-to-deploy chat container. One config file wires the backend,
> the skin, the theme, which settings are visible, how strict the app is, and
> whether it renders full-page, as an embed, as a pop-up, or as a side panel.
> Deploying it = install the release, edit the config. Everything else is
> maintenance: consolidate duplication, keep it simple, keep it scalable.

## Decision log

| # | Decision | Source | Status |
|---|----------|--------|--------|
| **D0** | Route digichat work through the **module tier** (`module/digichat` as the hop into `develop`) | user, 2026-09-22 | **done** (sync PR #4503) |
| **D1** | Build `modal` and `sidebar` as **real config-driven presentation surfaces**, not a fold into `/embed` | user, 2026-09-22 | done — Phase 2d (#4515) |
| **D2** | Maintain a **supported-backend matrix** where every backend yields the *same* chat end result (reasoning, tool calls, web search, all activity surfaced) | user, 2026-09-22 | to implement (Phase 5) |

Already shipped and merged into `develop`:

- **PR #4501 / issue #4500** — Phase 1: the release install is config-driven
  (every profile bind-mounts `./config:/app/config:ro`, `DIGICHAT_CONFIG_PATH`
  defaults to `/app/config/digichat.yaml`, `make digichat-config-check`
  validates and prints the resolved deployment).
- **PR #4499 / issue #4498** — `/baseline` catalog parity with `/embed`
  (scope marker, Geist Mono, block caret, welcome examples, full-bleed canvas,
  tooltip-arrow suppression, command palette).
- **PR #4503** — D0: `module/digichat` synced to `develop`.

## Operating rules for every phase

1. **One issue + one task branch per item.** Issue with `component:digichat`,
   branch `task/<N>-<slug>` cut from `origin/module/digichat`, PR **into
   `module/digichat`**, then promote `module/digichat` → `develop` →
   (human-gated) `main`.
2. **Module-tier friction is expected.** `module/digichat` drifts behind
   `develop` as other work lands, and `make task` refuses a `module/*` base
   that is behind `origin/develop`. `gh pr update-branch` is refused for
   `module/**`. So each task starts with a **sync PR** (`head=develop`,
   `base=module/digichat`) when the module branch is behind.
3. **Pre-flight for any `apps/digichat` change:** `npm run test` (125 files /
   1248 tests), `npm run lint` (0 errors), `npm run build`. `npm run build`
   creates `apps/digichat/.next/standalone/`, which breaks `make doc-check`
   until `rm -rf apps/digichat/.next/standalone`. `packages/ui` `npm run test`
   (62 files / 447 tests) whenever the package is touched.
4. **Review coverage** before merge: in-session fresh-context review + durable
   `review-<subject>.md` + PR comment opening `<!-- in-session-review -->`
   naming the reviewed 8-char sha + label `reviewed:agent`.
5. **Stop and ask** for: new external network exposure or service dependency
   (this gates most of Phase 5), `main` promotions, release-please PRs.

---

## Phase 2a — delete dead declarations

Nothing here changes behaviour; it removes config that lies.

**Done (issue #4508):**

- Delete `StockChromeBar` (`apps/digichat/src/components/stock/stock-chrome-bar.tsx`)
  and its test — imported only by its own test; two other tests assert its
  absence.
- Delete client-projected-but-unread `gate.activityDetail` from the client
  projection (`client-projection.ts` type + `DEFAULT_CLIENT_CONFIG` + the
  `toDigichatClientConfig` mapping). The server keeps it — `route.ts` reads it
  for the trace adapter; only the browser projection was dead.

**Investigated and RETAINED (not dead — do not retry the deletion):**

- `cli.enabled` — read and **gated** by the Ink CLI: `apps/digichat/cli/src/chat-request.ts`
  `assertCliEnabled` refuses to start when it is not `true`. It is set by
  `config/examples/local-cli.yaml` and `CliSchema` is `.strict()`, so removing it
  breaks that config and the CLI's `--config` gate.
- `gate.showLanguageSelector` — RESERVED. `ARCHITECTURE.md:1428` documents it as
  "Reserved; language chrome is not mounted on the stock baseline", and it is set
  by 9 shipped configs (`config/examples/local-app.yaml`, `occ-embed.yaml`,
  `datatap-mcp.yaml`, `digithings-ai-embed.yaml`, `dashboard-modal.yaml`, …).
  `GateSchema` is `.strict()`, so removing the field makes every one of those
  configs fail Zod validation at boot.
- `layout` (`page` | `embed`) — two different things share the name. The
  **tenant field** is live: it drives `chromeMode` (`loader.ts:75`, called from
  `loader.ts:280` and `route.ts:363,448`) and is validated at
  `embed-tenants.ts:391-392` (typed `:126`, mapped `:533`, documented at
  `ARCHITECTURE.md:495`) — removing it is a contract change with no benefit. The
  **client-projected** copy (`embed-client-config.ts:131` →
  `EmbedTenantClientConfig.layout` → `embed-ui-flags.ts:49`) is computed and
  never read (`embed-client.tsx:367` reads only `uiFlags.webSearch` and
  `uiFlags.showByok`); it is unread, not a dead tenant field.
- `?layout=embed` URL param — no reader today, but it is a documented popup
  contract (the panel is deliberately "not full-page wide") pinned by three
  tests (`embed-popup-config.test.ts`, `digichat-popup.test.ts`,
  `digichat-popup.test.tsx`). Wiring it to the tenant `layout` field is the
  better follow-up if it should become real; deleting it is not a clear win.
- `gate.consumeUrl` — already never client-projected (server-side quota consume
  only); nothing to remove.

**Still open from the original list:**

- Reconcile `features.modelPicker` vs `models.allowPicker` (both gate the same
  picker, disagree in defaults). Deferred to Phase 2c (app/embed parity), where
  the field set is decided per field.

## Phase 2b — authenticated-session gaps

The `auth: session` path silently ignored config that the embed path honours.
Root cause: the chat route resolved the deployment **twice from two sources** —
`embedConfigOf(tenantCtx)` (non-null only for embeds) drove every gate, while the
real host deployment was resolved later, inside the model-allowlist `try`, and
never consulted by the branches above it.

**Done (issue #4510):** one deployment is now resolved once, right after
`embedConfig`, and every gate reads from it with the embed config preferred so
the embed path stays byte-identical.

- Foundry now serves the session path (`backend?.type === "foundry"`).
- `backend.digigraph.digisearchIndex` / `vaultPathPrefix` reach digigraph on the
  session path.
- `gate.requiredPlanTier` is enforced on the session path (passed to
  `isPlanTierSatisfied` as `{ requiredPlanTier }`; its param narrowed to
  `Pick<EmbedTenantConfig, "requiredPlanTier">`).
- `gate.activityDetail` is honoured on the session path (previously hard-coded
  `"full"` for the trace adapter).
- `models.available` now applies to the Foundry path too (the allowlist moved
  ahead of the backend branch).
- The redundant second `dep` resolution in the MCP/forced-tool header block was
  removed.
- 4 regression tests added, all on a session request (`embedConfig === null`).

**Deliberately out of scope (with reasons):**

- **`gate.llmAccess`** — the plan listed it as a server gap; it is not one. No
  server code reads `llmAccess` anywhere: it is a client-side presentation /
  error-copy policy consumed only by `embed-client.tsx`, `embed-chat-error.ts`
  and `embed-send-gate.ts`, and it is already projected to the browser via
  `DigichatClientConfig.gate.llmAccess`. There is nothing to hoist.
- **`gate.trial_form`** — a per-IP anonymous-visitor counter. Wiring it to
  authenticated sessions would impose a 3-turn limit on existing signed-in
  users; the trial gate stays embed-only by design.
- **`gate.webSearch` for sessions** — the `DIGICHAT_WEB_SEARCH=1` env fallback
  remains the documented session toggle.
- **`hosts[].auth: session` for embeds** — still open; deferred.

**KEEP:** the BYOK model bypass (`if (byokKey) { … }`, cites #3829) — a bound
BYOK key spends the visitor's provider models, so the CI picker must not reject
those ids.

## Phase 2c — app/embed parity, per field

Decide each field explicitly, then extend `EmbedTenantConfig` + `embed-bridge`
where the answer is "embed should honour it": `persistence`, `auth`,
`chrome.defaultLanguage`, `chrome.transcript.userAlign`, `chrome.attribution`,
`features.dictation` / `speech` / `sources` / `branchPicker` / `modelPicker`,
`tools.allowUserToggle`.

**Done (issue #4532, PR into `module/digichat`):** an embed tenant can now set
the four feature flags and the seed language; before this it silently inherited
the client defaults because neither `EmbedTenantConfig` nor `toEmbedClientConfig`
nor `clientConfigFromEmbedTenant` carried them.

| field | decision |
|-------|----------|
| `features.dictation` / `speech` | **Embed honours it.** Added to `EmbedTenantConfig` (validated boolean) → `toEmbedClientConfig` (explicit `true` only, matching `attachments`) → bridge (`?? base.features`). |
| `features.sources` / `branchPicker` | **Embed honours it.** Same chain, but `typeof === "boolean"` in the projection so an explicit `false` survives — these default **on**, so `false` is the only way to turn them off. |
| `chrome.defaultLanguage` | **Embed honours it.** Validated against `LANGUAGE_CODES` (same set `schema.ts` builds); omit → the client default (`en`). |
| `chrome.attribution` | **Already carried** (direct copy in the bridge). No change. |
| `chrome.transcript.userAlign` | **Documented, not configurable.** The first-party `digichat` skin forces left alignment regardless of the value (`product-shell.tsx:349-350`), so exposing it on the embed would be a no-op for the one skin the embed ships. Other skins would honour it, but the embed cannot set it today. |
| `tools.allowUserToggle` | **Documented, embed-fixed `true`.** The anonymous embed has no per-tool toggle UI of its own; the operator's `tools.catalog` is the control surface. |
| `persistence` / `auth` / `chrome.mode` | **Embed-fixed by design** (`none` / `anonymous` / `embed`). A persisted, authenticated session is the `app` surface, not the iframe. |
| `features.modelPicker` vs `models.allowPicker` | **`models.allowPicker` is the authoritative client-facing knob; `features.modelPicker` is the legacy YAML alias** kept for config back-compat. They are OR-ed at every consumer (`client-projection.ts:176-178`, `product-shell.tsx:366`, `stock-chat-prefs-host.tsx:61`, `embed-client.tsx:1025`), and the projection already folds the legacy flag into `allowPicker`, so the consumer re-OR is idempotent. They disagree only in `DEFAULT_CLIENT_CONFIG` (`models.allowPicker: true` vs `features.modelPicker: false`); flipping either risks the `/baseline` picker, so behaviour is kept and the redundancy documented. |

Regression coverage: `apps/digichat/src/lib/embed-tenants.parity.test.ts` walks
the whole chain (registry JSON → `parseEmbedTenants` → `toEmbedClientConfig` →
`clientConfigFromEmbedTenant`) and asserts the four flags + `defaultLanguage`
reach `DigichatClientConfig.features` / `.chrome.defaultLanguage`, that omitted
keys keep the app defaults, and that a non-boolean flag or unknown language
throws.

---

## Phase 2d — presentation modes (D1: implement)

**Goal:** `chrome.mode` selects how the chat renders, from the deployment
config, in-app — not by redirecting everything to `/embed`.

Today `apps/digichat/src/app/(digichat)/page.tsx:29` folds
`embed | modal | sidebar` into a redirect to `/embed`. Pop-up exists only as a
host-side script (`apps/digichat/public/widget.js` + the dashboard popup), and
"side panel" exists only as static chrome inside the `webpage-assistant` skin.

### Design

| mode | surface | rendering |
|------|---------|-----------|
| `app` | `/` → `ChatShell` (server persistence) or `HomeStockClient` | unchanged |
| `embed` | `/embed` | unchanged (iframe-only, no shell) |
| `modal` | `/` mounts a corner launcher (30px trigger) that opens the chat in a launcher-mounted overlay panel built on `DigichatLauncher` + `embed-popup-config` | overlay, scrim, focus trap, Escape to close |
| `sidebar` | `/` mounts the chat docked to one side (canvas reserved beside it) | docked panel, resizable/collapsible, host content beside it |

Work items:

1. **Mode router.** Replace the blanket redirect with a real branch in
   `(digichat)/page.tsx`; keep `embed` → `/embed`.
2. **One launcher implementation.** Extract the pop-up behaviour into a
   single in-app component built on `packages/ui/.../DigichatLauncher` +
   `embed-popup-config.ts`, and have the dashboard popup and `public/widget.js`
   consume the same config shape. Retire the duplicate.
3. **`sidebar` surface.** New layout component; reuse `ProductStockShell` with
   a docked wrapper. Respect `LAYOUT_SKINS` (skins that own the page must not
   be wrapped).
4. **Bind `launcher.hotkey`.** It is currently stored as `data-hotkey` and
   never bound to a key handler.
5. **Per-mode formatting.** Each mode gets its own stylesheet hook
   (`[data-chrome-mode="modal"]`, `[data-chrome-mode="sidebar"]`) so spacing,
   radius, and composer layout can differ without forking the Thread.
6. **Config surface.** Keep `chrome.mode` as the selector; add `chrome.launcher`
   fields only if needed. Document each mode in `docs/digichat/`.

**Done (issue #4515, PR into `module/digichat`):**

- **Mode router** — `(digichat)/page.tsx` redirects only `embed`; `modal` and
  `sidebar` now flow through the app paths (`const framed =
  isFramedPresentation(mode) && !layoutSkin` keeps `ChatShell` for the
  full-page surface only).
- **Frame** — new `apps/digichat/src/components/stock/presentation-frame.tsx`
  (`PresentationFrame`, `isFramedPresentation`): `modal` mounts the existing
  `DigichatLauncher` (title/aria-label from `chrome.title`/`chrome.launcher`),
  `sidebar` mounts a docked `aside.dc-presentation__panel` beside a
  reserved canvas. Both wrap the same `ProductStockShell`, so skin, chrome and
  theme are identical across modes. **`LAYOUT_SKINS` are skipped** — a
  page-owning skin (docs / dashboard / expo) keeps the page even when
  `chrome.mode` asks for a frame, because a launcher panel or a 380px dock would
  strip the template it renders.
- **Mode reaches the shell** — `home-stock-client.tsx` now passes
  `data-chrome-mode={mode}` (was hard-coded `"app"`). The page wrapper stays
  `h-dvh` for every mode: `modal` portals its panel to `document.body`
  (`DigichatLauncher`), so the wrapper only sizes the non-framed and `sidebar`
  cases.
- **Hotkey bound** — `DigichatLauncher` gained a `hotkey?: string` prop plus an
  exported `matchesHotkey(event, hotkey)` helper (`mod` = exactly one of
  ctrl/meta; unnamed modifiers must be absent; a malformed string such as `k+`
  matches nothing; `matchesHotkey` unit-tested). The listener only
  opens — Escape and the backdrop keep owning dismissal.
- **Per-mode formatting** — `apps/digichat/src/styles/product-chrome.css` has
  `.dc-presentation--sidebar`, `__canvas`, `__panel` (the modal mode needs
  no rules: `digichat-launcher.css` already sizes the panel body).

**Persistence in the framed modes:** a `modal`/`sidebar` deployment mounts the
stock shell, so `persistence: server` is **not** available there — only the
full-page `app` mode reaches `ChatShell`. `modal`/`sidebar` behave like
`persistence: none` for the session surface (this is unchanged from before
Phase 2d, when both modes redirected to `/embed`, which is also persistence-free).
A deployment that needs server-side history must use `chrome.mode: app`.

The host-side path (`public/widget.js` + the dashboard popup, both built on
`buildPopupEmbedSrc`) stays supported and unchanged — an in-app `modal` surface
and a host-side iframe popup are complementary, not alternatives.

**Deferred within 2d:** the launcher panel is fixed-size (no resize/collapse
affordance) and the sidebar width is a constant `min(380px, 100vw)` rather than
`chrome.launcher`-driven. Revisit only if a deployment needs it.

---

## Phase 5 — supported-backend matrix (D2)

**Goal:** a maintained list of backend types where **every backend produces the
same chat end result** — reasoning displayed, tool calls displayed, web search
and all tool/activity surfaced.

### Finding (research, 2026-09-22)

assistant-ui normalizes every backend onto **six** wire part types
(`text`, `reasoning`, `tool-call`, `source`, `file`, `data`). digichat already
has the right architecture: **one BFF-side normalizer in front of a single
transport**, not per-backend runtime adapters.

- The client is backend-agnostic: `AssistantChatTransport` only POSTs to
  `/api/chat`, and `useAISDKRuntime` is used for every backend today.
- The BFF owns dispatch and credentials, branching once on
  `embedConfig.backend.type` (`api/chat/route.ts` — foundry, digigraph).
- `lib/ui-stream-parts.ts` already normalizes `ActivitySpan` → standard UI
  chunks and is called by **both** adapters.
- `lib/chat-activity.ts` is the backend-neutral vocabulary, sanitizer, and
  `activityDetail` disclosure gate.
- Per-backend assistant-ui runtime adapters (`useLangGraphRuntime`,
  `useAdkRuntime`, `useA2ARuntime`, `useAgUiRuntime`, …) are **not** the right
  fit here: the BFF rule forbids upstream URLs/credentials reaching the
  browser, so they would have to be proxied anyway, and they fragment
  reasoning/tool rendering across N packages. They are also not installed.

### Design — a `BackendAdapter` registry

Keyed by `backend.type`, each entry supplies connection/identity config, an
auth source, a **protocol** (which picks the mapper), a **capabilities** object,
and a `stream(opts) => Promise<Response>` that emits the same UI-message stream
for every backend.

Two normalizers converge on the same output:

- **(a) AI SDK v7's own `toUIMessageStream`** for anything run through
  `streamText` — OpenAI Completions, OpenAI Responses, Anthropic, Google
  Vertex/Gemini. AI SDK v7 is already installed.
- **(b) digichat's `ui-stream-parts.ts`** for non-AI-SDK protocols — digigraph
  SSE, Foundry Responses, AG-UI, A2A, LangGraph.

Proposed shape (grounded in the existing `embed-tenants.ts` union and
`schema.ts` backend schema):

```ts
type BackendConfig =
  | { type: "digigraph"; digisearchIndex?: string; vaultPathPrefix?: string }
  | { type: "foundry"; projectEndpoint: string; agentName: string }
  | { type: "openai-completions"; baseUrl: string; model: string; apiKeyEnv: string }
  | { type: "openai-responses";   baseUrl: string; model: string; apiKeyEnv: string }
  | { type: "anthropic";          model: string; apiKeyEnv: string }
  | { type: "google-vertex";      project: string; location: string; model: string }
  | { type: "langgraph";          apiUrl: string; assistantId: string }
  | { type: "ag-ui";              url: string }
  | { type: "a2a";                baseUrl: string };

type BackendEntry = {
  config: BackendConfig;
  auth: "managed-identity" | "env" | "upstream-bearer" | "byok";
  protocol: "digigraph-trace" | "foundry-responses" | "openai-completions"
          | "openai-responses" | "anthropic-messages" | "gemini" | "langgraph"
          | "ag-ui" | "a2a";
  capabilities: {
    reasoning: boolean;
    reasoningSummary?: boolean;
    toolCalls: boolean;
    webSearch: boolean;
    sources: boolean;
    turnMutation: "send" | "regenerate" | "edit_last_user";
    conversationContinuity: boolean;
    attachments: boolean;
    mcp: boolean;
  };
  stream: (opts) => Promise<Response>;
};
```

**Uniformity is enforced, not assumed.** The `capabilities` object drives the
UI (a backend that cannot reason hides the reasoning row; a backend that can
must emit it). A **parity test per backend** asserts that a canned upstream
stream produces the same normalized `ActivitySpan` sequence — the acceptance
criterion for "every backend has the same end result".

### Sub-phases

- **5a — registry refactor, no new backends.** Extract the two hard-coded
  branches into the registry; digigraph and foundry behave identically to
  today. Ships behind the existing config. No new dependency. **Low risk.**
  **Done (issue #4522):** `apps/digichat/src/lib/backend-adapters.ts` is the
  registry — one entry per `backend.type` carrying `protocol` (`digigraph-trace`
  | `foundry-responses` | …), `auth` (`upstream-bearer` | `managed-identity` |
  `env` | `byok`), and a `capabilities` object (reasoning, reasoningSummary?,
  toolCalls, webSearch, sources, turnMutation, conversationContinuity,
  attachments, mcp, corpus). The handler resolves the adapter once
  (`backendAdapterFor(backend?.type)`) and chooses its streaming path from
  `adapter.protocol` and `adapter.capabilities.corpus` — there is no
  `backend.type === "…"` comparison left in `route.ts`. Exhaustiveness is pinned
  by the `Record<BackendType, BackendAdapter>` type; `backend-adapters.test.ts`
  pins the key set at runtime, both adapters' protocol/auth/capabilities, the
  reasoning+toolCalls parity invariant, the digigraph default, the type guards,
  and (as a source guard) that the handler never compares `backend.type`.
  Note: in 5a only `protocol` and `capabilities.corpus` are read by the handler;
  the rest are declared for 5b/5c and asserted by the parity test. A second
  `backend.type` dispatch site remains in the tenant validator
  (`lib/embed-tenants.ts` — `DIGICHAT_EMBED_TENANTS` parsing); migrating it to
  the registry is a 5b/5c follow-up, out of 5a's chat-route scope.
- **5b — AI-SDK backends.** `openai-completions`, `openai-responses`,
  `anthropic`, `google-vertex`. Reuses the installed `ai` v7 +
  `@ai-sdk/*` providers; each new provider package is a **new dependency**.
  **Human gate.**
  - **Done (issue #4535, PR into `module/digichat`) — the OpenAI pair, no new
    dependency.** `@ai-sdk/openai` is already installed and exposes `.chat()`
    (Completions) and `.responses()` (Responses API), so both new types ship
    without a package. Added: the `openai-completions` / `openai-responses`
    schemas (https-only `baseUrl`, `model`, and `apiKeyEnv` constrained to the
    `DIGICHAT_BACKEND_*` prefix so a tenant config can never name `AUTH_SECRET`
    and have the BFF ship it to an attacker `baseUrl`); the two `BACKEND_ADAPTERS`
    entries (`auth: "env"`, `protocol` = the type); `AI_SDK_PROTOCOLS` +
    `isAiSdkConfig`; the provider factory
    `apps/digichat/src/lib/adapters/ai-sdk/providers.ts`; the shared mapper
    `apps/digichat/src/lib/adapters/ai-sdk/stream.ts` (`streamText` →
    `toUIMessageStream`, the same six wire parts the UI already renders); the
    route branch (after `coreMessages`, before the BYOK guard); the tenant
    validator branches (closing the 5a second-dispatch follow-up); and the
    widened `backendType` union in both projections.
  - **Done (issue #4539, PR into `module/digichat`) — the last two AI-SDK
    backends.** Added `@ai-sdk/anthropic` and `@ai-sdk/google-vertex` (the two
    approved new dependencies). `anthropic` is `{ model, apiKeyEnv }` with the
    same `DIGICHAT_BACKEND_*` guard and no `baseUrl` (the provider defaults to
    `https://api.anthropic.com`; use `openai-completions` for a proxy);
    `google-vertex` is `{ project, location, model }` with **no credential in
    config** — Vertex reads Application Default Credentials from the ambient
    environment. Both ride the same `streamText` → `toUIMessageStream` mapper
    (protocols `anthropic-messages` / `gemini`, both already in
    `AI_SDK_PROTOCOLS`), so reasoning, tool calls and sources render identically.
    `resolveAiSdkModel` is now a four-arm exhaustive switch.
- **5c — non-AI-SDK protocols.** `langgraph`, `ag-ui`, `a2a`. Each needs its
  own mapper; each is a **new dependency / new external surface**.
  **Human gate.**
- **5d — capability + parity tests** and the docs table.

**Note:** 5b/5c add third-party runtime dependencies and network surfaces.
Per AGENTS.md that is the human-gated "new external network exposure or service
dependency" class, so the plan proposes the *order* and asks for approval per
backend type rather than adding them unilaterally.

---

## Phase 4 — docs truth

- Fix the `apps/digichat/AGENTS.md` claim that only `/api/health` is public
  (`deploy/chrome`, `embed/tenant-config`, `mcp/oauth/callback`, `plan-proof`
  and the dev-only `baseline-chat` are also unauthenticated).
- Single-source the version (docs currently say 1.0.0 / v0.9.3 / v2.3.1; the
  real version is 2.3.2).
- Add a docs index so `docs/digichat/*` and `docs/architecture/digichat-*`
  are discoverable.
- Fold this plan and `digichat-ui-simplification.md` into the docs set.

## Phase 6 — ownership consolidation

Carried over from the approved plan (unchanged intent):

- **6.1** Move the canonical theme sheet out of
  `apps/reference/app/(chatbot)/chatbot/chatbot.css` into
  `packages/ui/src/styles/`; delete the 4-line re-export shim; collapse the two
  app `@theme inline` bridges.
- **6.2** Add `hideArrow` to `packages/ui/src/ui/tooltip.tsx`; delete the
  gallery tooltip adapter; one `TooltipIconButton`; one caret.
- **6.3** Skin encapsulation — a descriptor carrying provider + styles per skin.
- **6.4** Move the skin registry, dispatch, the 12 skins, and
  `(baseline)/stock/` into the package.
- **6.5** Package boundary cleanup (`ui` vs `digichat-ui`, dead exports,
  relocate the vendored archive).

Non-goals (unchanged): do not merge `packages/ui` into `apps/digichat`; do not
touch the BFF/secret boundary; do not remove `/baseline` isolation; do not
unify all apps' CSS.

---

## Suggested order

```
D0 module sync            ✅ done
Phase 2a dead config      → small, unblocks clarity
Phase 2b session gaps     → correctness (foundry/session, allowlists)
Phase 2d modal + sidebar  → D1, the visible feature
Phase 5a backend registry → D2 foundation, no new deps
Phase 2c app/embed parity → after 2b/2d so the field list is settled
Phase 5b/5c backends      → per-backend, human-gated
Phase 4 docs truth        → alongside each
Phase 6 ownership         → last (largest, highest churn)
```

Rationale: 2a/2b/2d/5a are all inside `apps/digichat` and pay off immediately;
2c depends on decisions made in 2b/2d; 5b/5c need per-backend approval; 6 is a
large refactor that should land once the feature surface is stable.

## Open items needing a user decision

1. **Phase 5 backend order and scope.** Which backend types do you want first,
   and do you accept the new dependencies for 5b/5c? (`openai-completions` and
   `openai-responses` are the cheapest and cover most self-hosters; `anthropic`
   and `google-vertex` need provider packages; `langgraph`/`ag-ui`/`a2a` need
   their own protocol mappers.)
2. **Phase 2d** — confirm `modal`/`sidebar` are in-app surfaces, and whether
   the host-side popup (`widget.js` / dashboard) stays supported as an alias.
3. **Module sync cadence** — accept one sync PR per task, or batch several
   tasks per sync cycle to reduce churn?
