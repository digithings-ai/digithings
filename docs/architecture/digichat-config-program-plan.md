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
| **D1** | Build `modal` and `sidebar` as **real config-driven presentation surfaces**, not a fold into `/embed` | user, 2026-09-22 | to implement (Phase 2d) |
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
3. **Pre-flight for any `apps/digichat` change:** `npm run test` (126 files /
   1250 tests), `npm run lint` (0 errors), `npm run build`. `npm run build`
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

- `cli.enabled` — advisory metadata by design (`CliSchema` comment: "Advisory
  for operators; the web app never imports Ink"); set by `local-cli.yaml`;
  `.strict()` schema, so removing it breaks that config.
- `gate.showLanguageSelector` — RESERVED. `ARCHITECTURE.md:1428` documents it as
  "Reserved; language chrome is not mounted on the stock baseline", and it is set
  by 9 shipped configs (`config/examples/local-app.yaml`, `occ-embed.yaml`,
  `datatap-mcp.yaml`, `digithings-ai-embed.yaml`, `dashboard-modal.yaml`, …).
  `GateSchema` is `.strict()`, so removing the field makes every one of those
  configs fail Zod validation at boot.
- `layout` (`page` | `embed`) — a validated `DIGICHAT_EMBED_TENANTS` tenant
  field (`embed-tenants.ts:126,391-392,533`; documented at `ARCHITECTURE.md:495`),
  not a dead derived value. Removing it is a contract change with no benefit.
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

The `auth: session` path silently ignores config that the embed path honours.

- **Foundry is unreachable for `auth: session`** — the server branches on
  `embedConfig`, which is `null` there, so it silently runs digigraph.
- `backend.digigraph.digisearchIndex` / `vaultPathPrefix` are not forwarded on
  the session path.
- `gate.requiredPlanTier`, `gate.llmAccess`, `gate.activityDetail` are not
  enforced on the session path.
- `models.available` enforcement: not applied on the Foundry path (early
  return) and bypassed for BYOK.
- `hosts[].auth: session` is not enforced for embeds.
- One regression test per gap.

## Phase 2c — app/embed parity, per field

Decide each field explicitly, then extend `EmbedTenantConfig` + `embed-bridge`
where the answer is "embed should honour it": `persistence`, `auth`,
`chrome.defaultLanguage`, `chrome.transcript.userAlign`, `chrome.attribution`,
`features.dictation` / `speech` / `sources` / `branchPicker` / `modelPicker`,
`tools.allowUserToggle`.

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
| `modal` | `/` renders the app chrome **plus** a launcher-mounted overlay panel built on `DigichatLauncher` + `embed-popup-config` | overlay, scrim, focus trap, Escape to close |
| `sidebar` | `/` renders the app chrome with the chat docked to one side | docked panel, resizable/collapsible, host content beside it |

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

**Open question for the user:** should `modal`/`sidebar` be **in-app surfaces**
(this plan) or remain **host-side** concerns (the host page decides and iframes
`/embed`)? D1 says implement, so this plan implements; the question is only
whether the host-side path should also stay supported as an alias.

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
- **5b — AI-SDK backends.** `openai-completions`, `openai-responses`,
  `anthropic`, `google-vertex`. Reuses the installed `ai` v7 +
  `@ai-sdk/*` providers; each new provider package is a **new dependency**.
  **Human gate.**
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
