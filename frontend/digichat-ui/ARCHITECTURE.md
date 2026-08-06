# @digithings/digichat-ui — architecture

Shared digichat terminal-session UI. Two consumers render it today:
**digichat** (`src/app/embed/page.tsx`, customer iframe embeds) and
**digithings-web** (`components/DigiChatSession.tsx` → `/chat`, native Pages —
no iframe). Both also `@import` this package's stylesheets from their
`globals.css`.

Since #1450 (F3) the surfaces hold **zero forked copies** of this package's
components: digithings-web deleted its local `miniMarkdown` / `MermaidBlock` /
`CopyButton` / `DigiChatMark` and renders assistant content through this
package's default `MiniMarkdown` (no `renderAssistantContent` override).
Everything app-specific arrives through the session's parametrization
(below); the apps keep only their transport (`DigiChatController` wiring),
BYOK settings UI, and handoff/seed logic.

## Module map

| File | What it is |
|---|---|
| `src/DigiChatSession.tsx` | The session shell: intro typewriter, thread, suggestions, quota/error banners, composer form. Controlled through a `DigiChatController` (`chat` prop). |
| `src/useStreamingIntro.ts` | Character-streamed intro text hook. |
| `src/components/MiniMarkdown.tsx` | react-markdown + remark-gfm renderer mapping nodes onto `.dc-md-*` classes; fenced ```mermaid → `MermaidBlock`. |
| `src/activity-view.ts` | Pure projection of the `DigiChatActivity` wire vocabulary onto the shared chat family's props. The boundary adapter — no JSX, node-testable. |
| `src/components/ChatActivities.tsx` | Agent-step feed, rendered on the shared `@digithings/web` chat primitives (see the mapping table below). Holds no mapping logic — that is `activity-view.ts`. |
| `src/components/CopyButton.tsx` | Clipboard copy affordance (silently no-ops where the API is unavailable — cross-origin iframes). |
| `src/components/DigiChatMark.tsx` | Brand mark / wordmark. |
| `src/components/MermaidBlock.tsx` | Client-rendered mermaid SVG with view-source toggle. |
| `src/styles/session.css` | `.dc-*` session grammar (thread, rows, markdown, form, activities, settings-adjacent chrome). |
| `src/styles/cursor.css` | `.dt-cur` caret + `dt-bl` keyframes, `.dtc-chip` / `.dtc-error`, wordmark colors. |
| `src/styles/tokens-shadcn-bridge.css` | Legacy bridge — retired by #1403, kept only for its package export. |

## Public API contract (do not break)

- **Exports** (`src/index.ts`): `DigiChatSession`, `useStreamingIntro`,
  `CopyButton`, `DigiChatMark`/`DigiChatWordmark`, `ChatActivities`,
  `MiniMarkdown`, `MermaidBlock`, `toCanonRows`/`outcomeMeta` +
  the types in `src/types.ts` and `CanonActivityRow`.
- **Class names are API.** Consumers style/target `.dc-*` and `.dt-*`/`.dtc-*`
  directly (digithings-web reuses `.dc-code-inline`, `.dc-mermaid-*`,
  `.dt-cur`; digichat layers `.dc-term-*` chrome around the widget). The
  #1403 behavioral assertion set (compiled-CSS: `dt-bl` / `dc-term-blink`
  keyframes, `.dc-msg` grid, `.dc-form`, streaming ▍) must stay
  byte-identical across changes here.
- Styles read canon tokens (`--ink`, `--accent`, `--hair`, …) under the
  consumer's `[data-theme]`; this package defines no tokens of its own.

## Session parametrization (how the two surfaces share one component)

`DigiChatSessionProps` (`src/types.ts`) is the whole divergence budget between
`/chat` and `/embed` — anything not expressible here belongs in the consumer,
not in a fork:

| Prop | digithings-web `/chat` | digichat `/embed` |
|---|---|---|
| `chat: DigiChatController` | `useStackChat` + BYOK headers | `useEmbedDigiChat` + gate-wrapped `send` |
| `layout` | `"page"` (full viewport under nav) | `"embed"` (flex child, no copy buttons — cross-origin clipboard) |
| `showStatusBar` / `showByok` | status bar + BYOK affordances | no bar; BYOK only when gated |
| `settingsPanel` + `chat.openSettings` | `ProviderSettings` panel | — (BYOK lives in the paywall card) |
| `headerSlot` / `footerSlot` | — | tenant title, turn meter, attribution |
| `formReplacement` | — | paywall card when the free-turn gate locks |
| `showIntro` | `false` after a handoff seed resumes a transcript | `false` when the gate is locked |
| `renderAssistantContent` | — (package `MiniMarkdown` default) | — (package `MiniMarkdown` default) |

The `/chat` handoff seed (homepage quick-ask → `lib/chatHandoff.ts`) stays
app-owned: the wrapper seeds the controller's messages and flips `showIntro`;
the session itself has no storage or routing knowledge.

## Chat-family convergence (#1418)

`@digithings/web` now ships the promoted chat grammar (`components/chat/*` +
`styles/chat-core.css` / `chat-widgets.css`). Adoption state here:

**Adopted**
- `DigiChatSession` streaming/intro carets compose `<ChatStreamCursor
  className="dt-cur" />`. The element keeps `.dt-cur` (consumed API);
  `cursor.css` keeps the rule set (the byte-identical contract above), and
  consumers import `chat-core.css` *before* `cursor.css` so `.dt-cur` wins
  the animation-shorthand tie. Net visual delta: `.chat-cursor`'s
  `margin-left: 2px` — the same 2px the digichat app caret
  (`.dc-term-streaming::after`) already carries.
- **`ChatActivities` — the agent chain (was gap 6).** The flat bordered
  `.dc-activities` box is gone; every row is now a shared primitive, so the
  embed shows the tool chain, the reasoning disclosure and its citations
  instead of a list of prose lines:

  | activity | primitive |
  |---|---|
  | `tool_call` | `<ChatToolCall status="running">` — bodyless, breathing |
  | `tool_result` | `<ChatToolCall status="ok">` + a source list body |
  | `trace` | `<ChatToolCall>` — bodyless step row |
  | `reasoning` | `<ChatThinking>` disclosure (blob in `children`) |
  | `brief` | `<ChatWidgetFrame variant="card">` |
  | `status` | `<ChatMessage role="system">` — the `·` aside |

  The wire-model → props mapping is `src/activity-view.ts` (pure, tested);
  the component only renders. Three seams worth knowing:

  1. **No timings exist.** `ActivitySpan` carries no duration, so
     `ChatToolCall`'s `duration` slot — its head-right mono meta — is spent on
     the outcome count (`3 notes` / `no hits`), which is what keeps a folded
     result row honest about whether the search found anything.
  2. **Citations start expanded**, everything else folded. `ChatToolCall`
     renders no body while closed, so folding them would drop the sources from
     the server markup entirely — invisible without client JS and to crawlers.
     Citations are this product's central claim; reasoning and bare traces are
     noise and stay folded.
  3. **`status` rows arrive as prose.** By the time a withheld-documents or
     failed-search outcome reaches the UI, its tool name and query have been
     folded into a sentence upstream (`toDigiChatActivity` in digichat's
     `lib/chat-activity.ts`). Recovering them would mean parsing prose, so
     they render as system asides rather than as reconstructed tool rows. If
     these ever need to render as real tool rows, widen the *protocol* — do
     not parse strings here.

  `.dc-act-*` selectors that no primitive needs any more (`-tool`, `-label`,
  `-code`, `-query`, `-line`, `-check`, `-result`) were dropped from
  `session.css` along with their markup; the survivors dress content nested
  *inside* a primitive (the source list, reasoning blob, brief body). That
  split is deliberate: no consumer `@source`s this package, so Tailwind
  utilities authored here would never generate — only the primitives' own
  utilities do, via each app's `@source ".../digiweb/web/src/components/chat"`.

**Not adopted — primitive gaps (follow-ups for @digithings/web)**
1. `ChatTranscript` has no chrome-less mode: `flat` only drops the shadow,
   the term-surface border/background/radius/pane-padding utilities are
   unconditional. `.dc-thread` is a bare transparent scroll region inside
   `.dc-session`, so it cannot rebuild on the primitive yet. (Its
   scroll/live mechanics — `overflow-y auto`, thin scrollbar,
   `overscroll-contain`, polite live region — already match
   `ChatTranscript scroll live` 1:1.)
2. `ChatMessage` fixes the row geometry as utilities
   (`grid-cols-[1.25rem_minmax(0,1fr)]`, `gap-[0.55rem]`, `items-baseline`)
   and offers no marker/body class hooks beyond `bodyClassName`. `.dc-msg`
   is `0.85rem` / `0.5rem` / `items-start` with `.dc-who` / `.dc-body` as
   consumed selectors — converging means either a geometry prop (or CSS-var
   knobs) on the primitive plus a `markerClassName`, or a sanctioned visual
   re-rating of both consumers.
3. `.chat-md` element combinators out-specify `.dc-md-*` (0-1-1 vs 0-1-0)
   and deliberately re-rate the typography (0.88rem body, display-face
   flattened headings, accent-washed italic blockquote, microtype table
   heads vs `.dc-md`'s 0.8rem mono scale). `MiniMarkdown` cannot wrap its
   output in `.chat-md` without visibly restyling both consumers and
   orphaning the `.dc-md-*` API — needs a density/legacy variant or a
   product-approved visual migration.
4. `ChatCopyButton` hardcodes its `.chat-md-copy` base class (mono
   microtype, uppercase, transparent); `CopyButton`'s `.dc-msg-copy` /
   `.dc-code-copy` are hover-revealed bordered chips. Identical clipboard
   mechanics, incompatible skin — the primitive needs an unstyled variant
   before `CopyButton` can delegate.
5. `ChatCodeBlock` always renders the figcaption caption row;
   `.dc-code-block` is a captionless `pre` with a floating hover copy chip.
   No variant matches, so `MiniMarkdown` keeps its own block.
6. ~~`ChatToolCall` / `ChatThinking` vs the flat `.dc-activities` box.~~
   **Closed** — see the agent-chain entry under *Adopted* above. The swap
   changed DOM, look and interaction wholesale as predicted, so it is worth a
   look on both surfaces before release; the `activity-view.ts` mapping and
   the `ChatActivities` render tests pin the behaviour meanwhile.
7. No primitive exists for the composer (`.dc-form` — asserted untouched by
   #1403 anyway), suggestions chips (`.dtc-chip`), status bar, or mermaid
   figures. `ChatMarkdown` additionally renders no mermaid/LaTeX yet; until
   that lands (in flight against `@digithings/web`) `MiniMarkdown` +
   `MermaidBlock` remain the only diagram path on both surfaces and must not
   be deleted — see the TODO in `MiniMarkdown.tsx`.

**Consumer wiring** (done in #1418): digichat `src/app/globals.css` and
digithings-web `app/globals.css` import `chat-core.css` + `chat-widgets.css`
*before* the digichat-ui sheets and `@source` the shared chat components.

## Extension guide

- New session affordances: add `.dc-*` rules to `session.css` and keep them
  token-backed; never rename existing `.dc-*` selectors (consumed API).
- Anything that looks like a transcript/message/markdown/tool-call grammar:
  check `@digithings/web` `components/chat/*` first and close one of the
  gaps above instead of growing a parallel implementation here.
- After interface or behavior changes, update this file and re-verify the
  #1403 compiled-CSS assertion set plus both consumers' `next build`.
