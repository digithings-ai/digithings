# digichat Gloomberb Attribution Surfacing — Design Spec

> **For agentic workers:** This is a DESIGN SPEC, not an implementation plan.
> Do not implement from this file. The implementation plan is
> `docs/superpowers/plans/2026-09-16-digichat-gloomberb-surfacing.md`; the plan
> argues from this spec, so executors read both.

- **Date:** 2026-09-16
- **Status:** draft — for owner review
- **Issue:** [#4098](https://github.com/digithings-ai/digithings/issues/4098)
  (open, `component:digiquant`, `priority:medium`) — "surface Gloomberb deep
  links + attribution in digiquant pages and digichat". The dashboard half
  shipped (#4193 via PR #4195, refined by #4204); this spec covers the remaining
  **digichat half**.
- **Verified against:** worktree `gloomberb-specs`, `origin/develop` `118966117`;
  every anchor below was re-read on 2026-09-16.
- **Gate:** UI-surfacing only — it renders fields already fetched by the tools.
  No new dependency, no new network call, no iframe, no auth/broker path.
  Not on the human-gate list (`AGENTS.md` § Human gate); agent merge applies.

---

## 1. Goal and scope

**Goal.** Every digichat tool row that can render a `digifetch_*` (Gloomberb)
result credits the source, shows the free-tier delay notice, and links out to
`https://term.gloom.sh/?ticker=<SYM>` — with the exact shipped strings, no new
dependencies, and clean disappearance when the payload carries no attribution.

**In scope**

- digichat's own vendored tool fallback,
  `apps/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx` (the only
  digichat-owned tool renderer), used by the `base` and `chatgpt` skins and the
  `/baseline` preview.
- Reuse of the shipped frontend helper
  `packages/ui/src/lib/gloomberb.ts` through the existing
  `@digithings/ui` workspace dependency.
- Tests (vitest) and a documented amendment to the vendored-file rules
  (`apps/digichat/src/app/(baseline)/stock/SOURCE.md`).

**Not in scope** (see §9): the first-party `digichat` skin (already renders the
line through #4130), the digigraph clipping behaviour (#4131, separate issue),
the dashboard (shipped), and catalog skins that never render tool parts.

---

## 2. Background (all anchors verified 2026-09-16)

### 2.1 The payload carries attribution

- `digiquant/src/digiquant/data/gloomberb/attribution.py:21-23` —
  `GLOOMBERB_ATTRIBUTION = "Sourced from Gloomberb"`,
  `GLOOMBERB_DELAY_NOTICE = "Data delayed up to 15 minutes"`,
  `GLOOMBERB_TERMINAL_URL = "https://term.gloom.sh/"`; `:26-28`
  `terminal_ticker_url(symbol)` builds the `?ticker=` deep link (`quote(...)`
  on the symbol); `:31-39` `attribution_fields(symbol)` returns
  `{attribution, delay_notice, source_url?}` — `source_url` only when a single
  listing is addressed.
- `digiquant/src/digiquant/data/gloomberb/agent_tools.py:152-166` —
  `gloomberb_envelope_json(...)`; `:165`
  `payload.update(attribution_fields(symbol))` appends the block at the JSON
  top level. `attributed=False` is passed for the Yahoo-backed earnings
  calendar (`:153`, `:157-159`), which therefore carries no attribution.
- MCP tools return that JSON string: e.g.
  `digiquant/src/digiquant/mcp_server.py:897-909` (`digifetch_quote`); the
  family contract is restated at `:890-894` ("Cloud payloads carry §7
  attribution … the Yahoo earnings tool is explicitly NOT attributed").

### 2.2 What already renders in digichat

- The shared frontend helper:
  `packages/ui/src/lib/gloomberb.ts:10-12` (constants), `:21-23`
  (`gloomberbTickerUrl`), `:50-73` (`readGloomberbAttribution` — unwraps a
  `result` envelope and JSON-string results, requires a non-blank `attribution`,
  and only surfaces `source_url` when it `startsWith` `GLOOMBERB_TERMINAL_URL`,
  `:68-70`).
- Barrel export: `packages/ui/src/index.ts:482-489`
  (`GLOOMBERB_*`, `gloomberbTickerUrl`, `readGloomberbAttribution`,
  `GloomberbAttribution`).
- The first-party line: `ToolFallbackAttribution` at
  `packages/ui/src/components/chat/gallery-thread/tool-fallback.aui.tsx:315-348`,
  wired under the Result pane at `:802-806`; tests at
  `packages/ui/src/components/chat/digichat-thread.render.test.tsx`
  (fixture `:57-77`, positive assertion `:380-401`, negative `:403-418`).
- That gallery thread *is* the first-party `digichat` skin:
  `apps/digichat/src/components/assistant-ui/skins/digichat.tsx:21`
  imports `DigichatThread` from `@digithings/ui/chat/thread`; `:289-303`
  renders it; the behaviour is documented at
  `apps/digichat/ARCHITECTURE.md:1327` ("the first-party gallery thread
  also renders the attribution line … unattributed payloads … render nothing
  extra").

**So "digichat has zero Gloomberb references" is narrower than it reads:**
`apps/digichat/src` has none (rg, 2026-09-16), but the first-party skin
inherits the line from the shared package. What is missing is digichat's **own
vendored fallback**.

### 2.3 What does not render

- `apps/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx` is a
  vendored copy of the public assistant-ui `base` registry (rules in
  `(baseline)/stock/SOURCE.md`: "Do not restyle these files for digichat") that
  already carries a digichat edit (`toolRowTitle`, `:27` / `:744`). Its Result
  pane lives at `:293-316`; `ToolFallbackImpl` wires only `ToolFallbackResult`
  (`:763-765`); the module has no Gloomberb import or reference.
- Consumers of that fallback:
  `apps/digichat/src/components/assistant-ui/skins/base/thread.tsx:11,673`
  (the `base` skin — the default for non-first-party hosts, per
  `apps/digichat/src/lib/thread-skins.ts` `DEFAULT_THREAD_SKIN = "base"`),
  `apps/digichat/src/components/assistant-ui/skins/chatgpt.tsx:39,288-289`,
  and `apps/digichat/src/app/(baseline)/stock/thread.aui.tsx:19,456` (the
  `/baseline` stock thread).
- The other clone skins (`claude`, `grok`, `gemini`, `perplexity`) render no
  tool parts — only the two files above import a tool fallback — and
  `apps/digichat/src/components/assistant-ui/tool-fallback.tsx` is a
  placeholder with zero non-test importers.

### 2.4 How a tool result reaches the row

digigraph SSE `tool_result` trace →
`apps/digichat/src/lib/adapters/digithings/activity/index.ts:102-128`
(maps `payload.result` onto the span's `toolResult`; sanitized at
`apps/digichat/src/lib/chat-activity.ts:320-322`) →
`apps/digichat/src/lib/ui-stream-parts.ts:200-223` — `writeToolOutput`
emits `tool-output-available` with
`output = {...input, result: <MCP JSON string>, durationMs}` (`:213`, `:220`) →
the assistant-ui tool part's `result` prop → the ToolFallback. The helper's
`result`-envelope unwrap (`gloomberb.ts:51-54`) matches exactly this shape.

### 2.5 The clipping dependency (#4131)

digigraph replaces a tool result whose JSON exceeds
`_MAX_TOOL_RESULT_CHARS = 12_000` (`digigraph/src/digigraph/workflow.py:115`)
with `{truncated: true, preview: "…"}` (`:704-718`; scalar strings capped at
2 000, `:118-121`). The attribution block is appended last, so large payloads
lose it before digichat sees them — values remain visible in the Result pane
while the credit disappears. That is issue #4131 ("fix(digigraph): preserve
Gloomberb attribution when tool results are clipped", open) and is **not fixed
here**. This design keys on presence and therefore degrades to *nothing* for
clipped payloads (no empty line, no orphan label) and needs no change when
#4131 lands.

---

## 3. Target architecture

**Chosen render location: the tool-call result card footer line** — a
`ToolFallbackAttribution` row rendered inside `ToolFallbackContent`, directly
under `ToolFallbackResult`, visible when the row is expanded. That is the
surface and markup contract #4130 already shipped in the first-party gallery
thread; this spec extends the same choice to digichat's vendored fallback.

Options considered:

| Option | Shape | Verdict |
|--------|-------|---------|
| **(a) Result-card footer line** | one presentational function in the existing fallback; no stream/adapter change | **Chosen.** Smallest delta; per-call provenance next to the data; mirrors the shipped #4130 line (`data-slot="tool-fallback-attribution"`); degrades to `null`. |
| (b) A `source` part | adapter synthesizes an assistant-ui source part per attributed result | Rejected. Re-plumbs the stream contract (`activity/index.ts` + `ui-stream-parts.ts`), conflates RAG citations with tool provenance, detaches the credit from its row, and would still need #4131 to work at all. |
| (c) The activity line | extend the branded activity chain | Rejected. digichat retired branded activity parts in favour of standard tool parts (`apps/digichat/ARCHITECTURE.md:1339`: "1.4 `data-digichatActivity` is not written"); extending it would resurrect a retired path. |

Wiring is a single render branch in `ToolFallbackImpl`
(`(baseline)/stock/tool-fallback.aui.tsx:763-765`); every consumer of the
vendored fallback gets it with no per-skin change. The deep link is the
payload's `source_url` verbatim — the renderer performs no URL construction.

---

## 4. Contracts (load-bearing)

1. **Attribution-presence contract.** The line renders iff
   `readGloomberbAttribution(result)` returns non-null: the result envelope
   (`{...input, result, durationMs}`) unwraps to a payload with a non-blank
   `attribution` string. Unattributed payloads (e.g.
   `digifetch_earnings_calendar`) and clipped payloads render nothing — never a
   placeholder, never an empty row.
2. **Deep-link contract.** The href is the payload's `source_url`; digichat
   **never constructs a ticker URL client-side** and never reads tool args for
   a symbol. `source_url` is present only when the tool addressed a single
   listing (`gloomberb_envelope_json(..., symbol=...)`); when absent, the line
   renders the source + delay notice without an anchor. Args are not a
   contract: shapes vary (`symbol`, `symbols[]`, `series_ids`, `cik`, `query`),
   batch/macro calls have no single listing, and a synthesized link would
   misstate provenance. The only client-side predicate is the helper's
   `term.gloom.sh` prefix check (`gloomberb.ts:68-70`).
3. **Copy contract.** All render text comes from the payload/helper. The only
   literal is the shipped anchor label `Open in Gloomberb` (identical to
   #4130, `gallery-thread/tool-fallback.aui.tsx:343`). No new copy, no i18n.
4. **Link contract.** External anchors only:
   `target="_blank" rel="noopener noreferrer"`. Iframing is ruled out —
   `term.gloom.sh` sends `X-Frame-Options: DENY` + `frame-ancestors 'none'`
   (`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md` §7-§8).
5. **Surface contract.** `data-slot="tool-fallback-attribution"` on the row;
   the anchor carries `target`/`rel`; the row lives inside the collapsible
   content below the Result pane, so collapsed rows are unchanged.
6. **Dependency contract.** Reuse `@digithings/ui`, already a digichat
   dependency (`apps/digichat/package.json`); the barrel is CSS-free
   (verified 2026-09-16: no `.css` imports in
   `packages/ui/src/index.ts`). No new package, no fetch, no new
   origin.
7. **Vendoring contract.** The vendored file gains one documented, additive
   divergence (SOURCE.md edit list); no restyle of existing markup or classes.

---

## 5. Normative copy and values

| Value | Origin | Use |
|-------|--------|-----|
| `Sourced from Gloomberb` | payload `attribution` (`attribution.py:21`) | line text |
| `Data delayed up to 15 minutes` | payload `delay_notice` (`attribution.py:22`) | `· <notice>` fragment |
| `https://term.gloom.sh/?ticker=<SYM>` | payload `source_url` (`attribution.py:26-28`) | anchor href |
| `Open in Gloomberb` | shipped #4130 label (`gallery-thread/tool-fallback.aui.tsx:343`) | anchor text |
| `data-slot="tool-fallback-attribution"` | shipped #4130 slot | render/test contract |
| `target="_blank" rel="noopener noreferrer"` | shipped #4130 / spec §8 | anchor attributes |

Render states (normative):

| Payload | Line | Anchor |
|---------|------|--------|
| `attribution` + `delay_notice` + `source_url` | rendered | rendered, `term.gloom.sh` href |
| `attribution` + `delay_notice` (no `source_url`) | rendered | none |
| no `attribution` (unattributed or clipped) | **nothing** | — |
| off-terminal `source_url` | rendered (helper drops the URL) | none |

---

## 6. Workstreams and sequencing

Single workstream, one task branch (`task/4098-*` cut from `module/digiquant`
per `scripts/project_routing.json`), one PR:

1. Branch + shared-helper availability verification (commands only).
2. `ToolFallbackAttribution` component + unit tests (attributed, no-URL,
   unattributed, clipped, JSON-string).
3. Wiring into `ToolFallbackImpl` + integration tests (expand → line + anchor)
   + a source guard pinning the shared-helper import and banning hardcoded
   strings.
4. Manual dev verification (digichat dev server) + docs
   (`(baseline)/stock/SOURCE.md`, `apps/digichat/ARCHITECTURE.md`).
5. Ship — PR into `module/digiquant`, review coverage, merge when ready.

No step touches `digikey/`, `digiquant/brokers/`, dependencies, or network
egress — no human gate.

---

## 7. Verification (measurable)

- Unit/integration: `npm run test --workspace digichat` (vitest; component tests
  use the per-file `// @vitest-environment happy-dom` pragma) — new cases:
  an attributed payload renders exactly one
  `[data-slot="tool-fallback-attribution"]` with the canonical string, the
  notice, and exactly one anchor whose `href`/`target`/`rel` match;
  unattributed and clipped payloads render zero nodes and no
  `Sourced from Gloomberb` text; a JSON-string envelope resolves the same link.
- Static: `npx tsc --noEmit` in `apps/digichat`;
  `npm run lint --workspace digichat`; `python3 scripts/check_frontend_canon.py`
  (no CSS added).
- Manual: `make digichat-dev` → `/baseline?skin=base`,
  `/baseline?skin=chatgpt`, and the product route; a digifetch call (if the
  stack/egress is up) expanded shows the line + link; with no attributable
  result the row is unchanged.
- Copy drift: the source guard test fails if the component hardcodes
  `Sourced from Gloomberb` / the terminal URL instead of importing the helper.

---

## 8. Risks

| Risk | Mitigation |
|------|-----------|
| Vendored preview fidelity | Additive line renders only on attributable payloads; documented in SOURCE.md; JS-only import (barrel verified CSS-free) keeps the `(baseline)` CSS isolation tests green. |
| Clipped payloads show values without attribution (#4131) | Accepted, named dependency: the UI degrades to nothing; #4131 owns the upstream fix and needs no UI change on landing. |
| Payload field drift | Single seam (`readGloomberbAttribution`), pinned by `packages/ui/src/lib/gloomberb.test.ts`; a rename fails closed (no line), never renders wrong copy. |
| Barrel import weight | Barrel has no CSS side effects; the dashboard and digichat `components/ui/*` already import it. The package declares no `sideEffects: false`, so unused re-exports may not tree-shake; escape hatch: add a `./lib/gloomberb` subpath export (open question Q1). |
| False credit (Yahoo-backed tools) | The earnings calendar carries no attribution (`attributed=False`, `agent_tools.py:153`); the line keys on presence. |
| Review/merge discipline | Standard task-PR flow (`/review`, `reviewed:agent`, merge when CI green + mergeable); no human gate applies. |

---

## 9. Out of scope

- #4131's digigraph clipper fix; any adapter-level attribution lifting.
- Changes to the first-party gallery line or to `@digithings/ui`.
- Replacing the vendored fallback with the gallery component.
- Dashboard / twelve-x surfaces (shipped; twelve-x excluded by #4204).
- New copy, i18n, iframes, per-widget embedding, or share-page (`/s/<id>`) links.
- `src/components/assistant-ui/tool-fallback.tsx` (zero importers) and clone
  skins without tool rendering.

---

## 10. Open questions

1. **Package entry point.** Barrel import (chosen; precedent in
   `apps/dashboard/components/sidebar.tsx:7-13` and digichat
   `components/ui/*`) vs adding a `./lib/gloomberb` subpath export to
   `@digithings/ui`. Switch only if a bundle check flags the barrel.
2. **Collapsed visibility.** The line is visible only when a row is expanded
   (mirrors #4130). Keep, or show attribution on the collapsed row?
   Recommendation: keep.
3. **Post-#4131 behaviour.** No change expected; revisit only if #4131 lands a
   structured "attribution survives clipping" contract worth pinning in tests.
