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

1. **Copied registry source** — `npx shadcn add @assistant-ui/thread` lands
   `reference/components/assistant-ui/elements/thread.aui.tsx` and its slots
   (markdown, reasoning, tool-fallback, attachment). That file *is* the UI.
2. **shadcn token names → digiweb tokens** — `bg-background`, `text-foreground`,
   `bg-primary`, `border-border` read `--color-*`. Those aliases point at
   `--bg` / `--ink` / `--accent` / `--hair` so the gallery theme toggle and
   livery switcher re-theme the Thread without a second palette.
3. **Thread shell vars** — `--thread-max-width`, `--composer-bg`,
   `--composer-radius`, `--composer-padding` are inline on
   `ThreadPrimitive.Root`. Change them in the copied file, not from an outer
   class ([Thread — Restyle the shell](https://www.assistant-ui.com/elements/thread)).

Keep defaults. Prefer a CSS-variable change over a slot override; prefer a
`components` slot over forking `thread.aui.tsx`.

## Increments

1. **Shell** — radius 0, monochrome ink on canvas (`chatbot.css`, `--composer-radius`).
2. **Welcome** — `Thread` `components.Welcome`. Left-aligned title + body from
   deploy-shaped config (`GALLERY_WELCOME` / `chrome.welcome`). No kicker. No
   starter chips unless `chrome.suggestions` is set. Not the standalone EmptyState
   element (that duplicates the composer).
3. **Composer** — registry `ComposerPrimitive` in Thread. `placeholder` from
   `chrome.placeholder` (`Ask digichat…`). Two layouts on `Thread`:
   `expanded` (input, then attach + send on the next row) and `compact`
   (attach · input · send on one row). Send is a squared enter keycap: quiet
   outline while empty, ink fill once there is text. Click and Enter both
   send (`submitMode="enter"`). Do not assemble a second Composer element.
4. **Transcript** — both roles left. Marker column `>` user, `▸` assistant
   (same grid as `ChatMessage`: `1.25rem` + body). No user bubble. Registry
   action bars stay. Streaming markdown uses a block caret (`::after`), not
   the registry `●` from `dot.css`. The More menu is portaled: hairline border,
   radius 0, mute mono label — no accent fill.
5. **Reasoning** — registry `ReasoningRoot` `variant="ghost"`. Lowercase mono
   label, hairline rail on the trace (gapped below the header). Body is smaller
   and more faded than the reply. No brain icon, no pill, no fade wash, no
   second caret. Tool group is label-only. Tool status uses the cube-matrix
   check (not Lucide). Code-fence copy uses the same squared glyph as the
   action bar.
6. **Loader** — assistant-ui DotMatrix forked in `components/ui/dot-matrix.tsx`.
   Cubes snap on/off (no opacity ease). Motion states: `loading` (rim orbit),
   `thinking` (ring in/out), `tool` (inner orbit), `executing` (row scan),
   `searching` (column scan), `compacting` (filled shrink). Glyphs: `warning`,
   `error`, `success`. Unlit cells keep a hairline so the grid reads. Thread
   `indicator` uses `loading` at the same 0.85rem as a tool-call matrix.
   Hide that indicator while any tool-call part is running so parallel
   tools keep their own cubes and the thread does not double them. Do not
   use the shadcn Spinner.
7. **Markdown / code** — headings stay body size, weight 500. Tables: mute
   header row, row hairlines, no fill. Fences: one hairline frame, no wash;
   language label mute; copy is the squared action glyph.
8. **Tools** — no group panel. Each call is one row: cube matrix, then
   `tool(name)` and mute duration. The cube is the status (no `complete`
   label). Click opens a hairline slab (`args` / `result` lowercase
   labels, mono body, no wash). Settled calls open so the slab is visible.
9. **Attachments** — composer and sent turn use the same hairline chip:
   `filename · type` plus a squared × in the composer. No thumbnail tile.
   Image click opens a portaled lightbox (radius 0). Upload/error use the
   cube matrix, not a Lucide spinner.
10. **Chrome** — desk specimen: terminal list (`chats`, `+ new`, `· title`)
    left of a compact Thread. Launcher specimen: contained
    `DigichatLauncher` (`portal={false}`), 30px square, types `digichat` on
    hover, two-step expand, solid canvas (no glass). Do not portal to the
    page corner.

## Non-goals

- Do not compose a parallel Thread from `ChatMarkdown` / `ChatThinking` /
  `ChatToolCall` on this page
- Do not restyle or fork the 11 official catalog templates in the product
- Do not import `ink` or `@assistant-ui/react-ink` into Next
- Do not change `DEFAULT_THREAD_SKIN` as part of gallery iteration

## Product

`chrome.skin: digichat` remains a separate product id (default is still
`base`). Promote a gallery look into the product only after it is approved
here.
