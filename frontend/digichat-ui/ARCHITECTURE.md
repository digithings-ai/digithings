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
| `src/DigiChatSession.tsx` | The session shell: intro typewriter, thread, suggestions, quota/error banners, composer form. Controlled through a `DigiChatController` (`chat` prop). `settingsPanel` renders **inside** `.dc-thread` (inline BYOK terminal flow). |
| `src/useStreamingIntro.ts` | Character-streamed intro text hook. |
| `src/components/MiniMarkdown.tsx` | Thin delegate to `@digithings/web`'s `<ChatMarkdown source>` — that package owns the `.chat-md` grammar, GFM tables, fenced code, mermaid and LaTeX. Carries no node map and no `.dc-md-*` classes of its own. |
| `src/activity-view.ts` | Pure projection of the `DigiChatActivity` wire vocabulary onto the shared chat family's props. The boundary adapter — no JSX, node-testable. |
| `src/components/ChatActivities.tsx` | Agent-step feed, rendered on the shared `@digithings/web` chat primitives (see the mapping table below). Holds no mapping logic — that is `activity-view.ts`. |
| `src/components/CopyButton.tsx` | Markdown copy affordance — clipboard first; embed falls back to `.md` download → parent `digichat:copy` postMessage → selectable textarea (#3465). Never a silent no-op. |
| `src/transcript-markdown.ts` | Shared serializer for last-answer + full-thread markdown export (`## You` / `## digichat`, optional Sources title+path). |
| `src/components/DigiChatMark.tsx` | Brand mark / wordmark. |
| `src/styles/session.css` | `.dc-*` session grammar (thread, rows, markdown, form, activities, settings-adjacent chrome). |
| `src/styles/cursor.css` | `.dt-cur` caret + `dt-bl` keyframes, `.dtc-chip` / `.dtc-error`, wordmark colors. |
| `src/styles/tokens-shadcn-bridge.css` | Legacy bridge — retired by #1403, kept only for its package export. |

## Public API contract (do not break)

- **Exports** (`src/index.ts`): `DigiChatSession`, `useStreamingIntro`,
  `CopyButton`, `DigiChatMark`/`DigiChatWordmark`, `ChatActivities`,
  `MiniMarkdown`, `toCanonRows`/`outcomeMeta`,
  `serializeAssistantMarkdown`/`serializeThreadMarkdown`/`copyMarkdownWithFallback`/
  `downloadMarkdown` (#3465), plus the types in `src/types.ts` and
  `CanonActivityRow`.
- **Class names are API.** Consumers style/target `.dc-*` and `.dt-*`/`.dtc-*`
  directly (digithings-web reuses `.dc-code-inline` and `.dt-cur`; digichat
  layers `.dc-term-*` chrome around the widget). `.dc-mermaid-*` was retired
  with `MermaidBlock` — diagrams are `.chat-md-mermaid*` from
  `@digithings/web` now. The
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
| `layout` | `"page"` (full viewport under nav) | `"embed"` (flex child; copy uses download fallback when clipboard is blocked) |
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
3. **Closed by #1941 — and worth reading as written, because it called the
   outcome exactly.** This entry warned that `MiniMarkdown` "cannot wrap its
   output in `.chat-md` without visibly restyling both consumers", the
   re-rating being 0.88rem body and display-face headings against `.dc-md`'s
   0.8rem mono scale, and that it therefore needed "a density/legacy variant **or** a
   product-approved visual migration". #1941 took neither branch.

   #1941 made the swap and did restyle both consumers — digichat `/embed` **and**
   digithings.ai/chat, because by then neither app overrode `renderAssistantContent`
   (see the props table above: both surfaces take the package default). digithings-web
   did carry a forked renderer until #1450 (`ae4d4a33`) deleted it, but it was
   byte-identical to this package's bar a docblock, so no output ever diverged —
   "has never been overridden" would be wrong, "is not overridden today" is the claim. The PR
   described the change as scoped to the embed, so the public page moved
   unreviewed. Caught in review afterwards; the owner then approved keeping the
   shared canon, so the re-rating stands deliberately rather than by accident.

   The lesson for the next primitive convergence: `MiniMarkdown` is shared by
   both surfaces, so **any** change to it is a change to digithings.ai/chat.
   There is no embed-only edit to make here.
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
   #1403 anyway), suggestions chips (`.dtc-chip`), or the status bar.
   Composer chrome is utilitarian-terminal v0.1: radius 0, `.dc-send` is an
   ink/paper rect, `.dtc-chip` is a hairline slab (not a pill).
   **Closed for diagrams and math:** `ChatMarkdown` gained mermaid and LaTeX in
   #1941, so `MermaidBlock` was deleted and `MiniMarkdown` became a delegate.
   An earlier revision of this section said the pair "must not be deleted" and
   pointed at a deferred-work marker in `MiniMarkdown.tsx`; both statements were
   falsified by the same PR that wrote them, and no such marker exists in that
   file.

**Consumer wiring** (done in #1418): digichat `src/app/globals.css` and
digithings-web `app/globals.css` import `chat-core.css` + `chat-widgets.css`
*before* the digichat-ui sheets and `@source` the shared chat components. Both
also import `chat-math.css` (after `chat-core.css`), which carries KaTeX's own
stylesheet and its ~1 MB of fonts — an app that renders no math must not import
it, which is why dashboard and the design reference do not.

## Extension guide

- New session affordances: add `.dc-*` rules to `session.css` and keep them
  token-backed; never rename existing `.dc-*` selectors (consumed API).
- Anything that looks like a transcript/message/markdown/tool-call grammar:
  check `@digithings/web` `components/chat/*` first and close one of the
  gaps above instead of growing a parallel implementation here.
- After interface or behavior changes, update this file and re-verify the
  #1403 compiled-CSS assertion set plus both consumers' `next build`.
