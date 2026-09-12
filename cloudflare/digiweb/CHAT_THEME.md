# First-party digichat theme

The gallery is a **blank slate** on the official assistant-ui `Thread`.
Theming is CSS variables. We do not rebuild markdown, reasoning, tools, or
message layout. For the full upstream elements catalog (every slug, fetch
command, digichat attach kind) see [`ASSISTANT_UI_ELEMENTS.md`](./ASSISTANT_UI_ELEMENTS.md).

Live: design-reference [`/chatbot`](http://127.0.0.1:4013/chatbot/).

`/chatbot` is its own Next root (`app/(chatbot)/`) so webpack does not compile
the rest of the gallery. Open only that URL. Do not load `/` or other reference
pages in the same session.

## How it is themed

assistant-ui has no theme CDN. Custom look is:

1. **One Thread module** — `@digithings/web/chat/thread` (`gallery-thread/thread.aui.tsx`
   + slots). Product `/embed` and this `/chatbot` page import that subpath.
   Do not keep a second registry copy under `reference/components/assistant-ui/`.
   The **composer-trigger-popover is the one deliberate exemption**: the digichat
   skin ships its own category implementation
   (`skins/base/elements/composer-trigger-popover.aui.tsx`, byte-identical to the
   reference base template) instead of the gallery's flat item list. Treat that
   second source as accepted until the popover gets its own design pass (#3818).
2. **shadcn token names → digiweb tokens** — `bg-background`, `text-foreground`,
   `bg-primary`, `border-border` read `--color-*`. Those aliases point at
   `--bg` / `--ink` / `--accent` / `--hair` so the gallery theme toggle and
   livery switcher re-theme the Thread without a second palette.
3. **Thread shell vars** — `--thread-max-width`, `--composer-bg`,
   `--composer-radius`, `--composer-padding` are inline on
   `ThreadPrimitive.Root`. Change them in the copied file, not from an outer
   class ([Thread — Restyle the shell](https://www.assistant-ui.com/elements/thread)).
4. **One portaled-menu sheet** — the portaled menu skin
   (`.aui-action-bar-more-content`, `.aui-composer-trigger-popover`,
   `.dc-composer-menu`, code-header buttons) is owned by the gallery sheet
   (`reference/app/(chatbot)/chatbot/chatbot.css`), which the product wrapper
   `@digithings/web/styles/chatbot.css` imports. `chat-aui.css` loads first and
   keeps only the rules the gallery sheet has no twin for: catalog-skin popover
   items, tooltip/dialog accent tokens, hidden tooltip arrows, launcher
   overrides. Do not re-declare the base menu rules in both files (#3818).

Keep defaults. Prefer a CSS-variable change over a slot override; prefer a
`components` slot over forking `thread.aui.tsx`.

## Increments

1. **Shell** — radius 0, monochrome ink on canvas (`chatbot.css`, `--composer-radius`).
2. **Welcome** — `Thread` `components.Welcome` in `ViewportFooter`,
   immediately above the composer. Bottom-aligned in the thread. Left-aligned
   title + body from deploy-shaped config (`GALLERY_WELCOME` / `chrome.welcome`).
   Optional example rows from `chrome.suggestions` (`GALLERY_SUGGESTIONS`),
   each with an `example` four-cube diamond — not chips, not a top-of-thread empty
   state. Draft text in the composer does **not** hide title, body, or
   examples — only a sent message / non-empty thread does. Not the
   standalone EmptyState element (that duplicates the composer). Gallery copy
   is “Ask the stack.” / “It reads the docs, then answers.” Product YAML keeps
   its own welcome strings.
3. **Composer** — registry `ComposerPrimitive` in Thread. `placeholder` from
   `chrome.placeholder` (`Ask digichat…`). Two layouts on `Thread`:
   `expanded` (input, then attach + send on the next row) and `compact`
   (attach · input · send on one row). Compact popup / embed locks one line
   until a newline; empty and one-line typed share that height (do not
   shorten `:placeholder-shown`). Empty uses `field-sizing: fixed` at `1lh`
   so `content` + nowrap cannot fill `max-height`. A newline autosizes taller.
   Send is cubes only: mute when disabled, slightly brighter when there is
   text, white cubes on hover. No ink/white button fill. Click and Enter both
   send (`submitMode="enter"`). Do not assemble a second Composer element.
4. **Transcript** — both roles left. Marker column is cubes, not characters:
   `user` is a compact open `>`; `example` is a four-cube diamond. There is
   **no assistant role `▸`**. Role cubes and tool-call checks sit on the first
   line's midline (`items-start`) — not centered on the block. No user bubble.
   Registry action bars stay; every chrome mark is a 5×5 snap cube (`copy`,
   `refresh` / Redo, `more`, `edit`, `export`, `download`, `stop`, `remove`,
   `scroll`, `up` / `down`, `prev` / `next`, `attach`, `newChat`, `dictate`,
   `thumbsUp` / `thumbsDown`). Undo is on by default; thumbs only when
   `features.feedback: true`. Streaming markdown uses a block caret
   (`::after`), not the registry `●` from `dot.css`. The More menu is
   portaled: hairline border, radius 0, mute mono label — no accent fill.
   Style `.aui-action-bar-more-*` globally (it leaves `.aui-root`).
5. **Reasoning** — registry `ReasoningRoot` `variant="ghost"`. Lowercase mono
   label, hairline rail on the trace (gapped below the header). Body is smaller
   and more faded than the reply. No brain icon, no pill, no fade wash.
   While streaming, the left cube is `thinking` (Chebyshev rings). When done,
   it is `thought` (light-bulb silhouette) — not a tool check. The expand
   caret is a 3-cube `>` (`expand`) that rotates 90° in place around
   `50% 50%` when open (`transform: none` when collapsed). No
   `active:scale-[0.98]` / `origin-left` on reasoning or tool triggers.
   `scrollbar-gutter: stable` on the thread viewport.
6. **Loader** — `DotMatrix` lives in `@digithings/web/chat/dot-matrix`
   (re-exported from `components/ui/dot-matrix.tsx`). Cubes snap on/off (no
   opacity ease). Unlit cells are omitted — only lit cubes show; no hairline
   grid. Motion states: `loading` (thick rim arc), `thinking` (rings in/out),
   `tool` (press: two bars close on the middle, hold, open), `executing`
   (row scan), `searching` (column scan), `compacting` (filled shrink).
   Status glyphs: `warning`, `error`, `success`, `thought`. Chrome glyphs:
   `copy`, `edit`, `attach`, `send`, `more`, `refresh`, `export`, `download`,
   `stop`, `remove`, `scroll`, `up`, `down`, `prev`, `next`, `dictate`,
   `newChat`, `expand`, `thumbsUp` / `thumbsDown`, plus role marks `user` /
   `example` / `system`. Thread `indicator` uses `loading` at the same
   0.85rem as a tool-call matrix. Hide that indicator while any tool-call
   part is running so parallel tools keep their own cubes and the thread
   does not double them. Do not use the shadcn Spinner.
7. **Markdown / code** — headings stay body size, weight 500. Tables: mute
   header row, row hairlines, no fill. Fences: one hairline frame, no wash;
   language label mute; copy is the `copy` cube (snaps to `success`).
8. **Tools** — no group panel. Each call is one row: cube matrix, then the
   tool name (`digisearch_query`, not `tool(name)`) and mute duration. The
   cube is the status (no `complete` label). Running uses the `tool` press
   animation. Click opens a hairline slab (`args` / `result` lowercase
   labels, mono body, `max-height: 8.5rem; overflow: auto`). Settled calls
   **stay collapsed**. Auto-open only for `requires-action` / approval.
9. **Attachments** — composer and sent turn use the same hairline chip:
   `filename · type` plus a `remove` cube in the composer. No thumbnail tile.
   Image click opens a portaled lightbox (radius 0). Upload/error use the
   cube matrix, not a Lucide spinner. Attach is a lit plus; new chat is the
   inverse plus (`newChat`, 2×2 in each corner).
10. **Chrome** — desk specimen: terminal list (header **digichat**, new-chat
    cube, title only — no cube beside titles) left of a compact Thread.
    Launcher specimen: contained `DigichatLauncher` (`portal={false}`), 30px
    square, types `digichat` on hover, two-step expand, **New chat** in the
    header, solid canvas (no glass). Do not portal to the page corner.

## Non-goals

- Do not compose a parallel Thread from `ChatMarkdown` / `ChatThinking` /
  `ChatToolCall` on this page
- Do not restyle or fork the 11 official catalog templates in the product
- Do not import `ink` or `@assistant-ui/react-ink` into Next
- Do not change `DEFAULT_THREAD_SKIN` as part of gallery iteration

## Product

`chrome.skin: digichat` is the only first-party look. It **renders this
gallery Thread** — the same `@digithings/web/chat/thread` subpath the isolated
`/chatbot` page imports (never the `@digithings/web` main barrel). CSS is
`@digithings/web/styles/chatbot.css` (Container COPY of gallery
`chatbot.css` is required — #3717). Welcome in `ViewportFooter`, radius 0,
Geist Mono, both roles left, cube status/action glyphs, no assistant role
arrow, hover hints a hairline box with no rotated-square arrow (same as
`/chatbot`), tools collapsed when settled. Catalog / third-party default remains
`base`. First-party hosts default unset `skin` to `digichat`. Do not add a
third custom theme. Do not restyle the 11 catalog templates.
