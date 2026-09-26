---
type: library
title: digichat-ui Library
description: Shared digichat helpers delivered as @digithings/digichat-ui — brand marks, slash-command palette, transcript-markdown serializers (re-exported from @digithings/ui), DocumentPane, MiniMarkdown, and session CSS. Not a session shell; the 2.0 session lives in apps/digichat via assistant-ui Thread.
tags: [digichat-ui, digichat, library, slash-commands, transcript-markdown, css]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-26T12:43:34.078Z
sources:
  - id: openwiki-source-81acdc975caf6a6f37fb8a3c
    resource: repo://packages/digichat-ui/ARCHITECTURE.md
  - id: openwiki-source-13cbba77ac1d52e9c2775224
    resource: repo://packages/digichat-ui/package.json
  - id: openwiki-source-dc41da192565e175539c83cc
    resource: repo://packages/digichat-ui/src/components/DocumentPane.test.tsx
  - id: openwiki-source-561e91a97fbf626fb20438b6
    resource: repo://packages/digichat-ui/src/components/DocumentPane.tsx
  - id: openwiki-source-67dcb15ecfd0da444ca0483b
    resource: repo://packages/digichat-ui/src/components/MiniMarkdown.tsx
  - id: openwiki-source-b3832d2eb67231a0d3b5ac8a
    resource: repo://packages/digichat-ui/src/index.ts
  - id: openwiki-source-6108b4d0d2dbbdbca610fe7a
    resource: repo://packages/digichat-ui/src/package.test.ts
  - id: openwiki-source-e3b58eb29b92a8ebce8f0c62
    resource: repo://packages/digichat-ui/src/slash-commands.ts
  - id: openwiki-source-065552ab9c5f1b02da709eb2
    resource: repo://packages/digichat-ui/src/styles/cursor.css
  - id: openwiki-source-f8932d65e7ac7859380e04a0
    resource: repo://packages/digichat-ui/src/styles/session.css
  - id: openwiki-source-7ea8e81095f128777cc2f93f
    resource: repo://packages/ui/src/components/chat/transcript/transcript-markdown.ts
  - id: openwiki-source-ec55eeaa37e6d1d788a8a5c5
    resource: repo://packages/ui/src/components/chat/transcript/types.ts
generated: { by: "openwiki/0.5.0", at: "2026-09-26T12:43:34.078Z" }
---

# digichat-ui Library

`@digithings/digichat-ui` is a private npm workspace package that delivers shared
digichat helpers: brand marks (`DigiChatMark`, `DigiChatWordmark`), a public
slash-command palette, transcript-markdown serializers (re-exported from
`@digithings/ui/chat/transcript`), an optional `DocumentPane`, the `MiniMarkdown`
markdown delegate, and session CSS. It is **not** a session shell — the 2.0 session
renders in `apps/digichat` via assistant-ui's stock `Thread`.

## Delivery model

Every parent surface iframes digichat `/embed`; this package provides the shared
pieces consumed within that embedded session and in the digichat first-party
`/chat` page.

| Surface | How digichat UI is delivered |
|---|---|
| digithings-web `/chat`, `/chat/occ` | iframe → digichat `/embed` (`ChatEmbedShell`) |
| dashboard popup / `DigichatLauncher` | iframe → digichat `/embed` |
| `widget.js` | iframe → digichat `/embed` |
| digichat first-party `/chat` | stock assistant-ui `Thread` |
| digichat `/embed` | stock assistant-ui `Thread` |
| Client-owned UI / plugin | headless `POST /api/chat` only |

The backend (`digigraph` or `foundry`) is selected per tenant — the UI does not
branch on backend type.

## Module map

| Source | What it is |
|---|---|
| `src/slash-commands.ts` | Public slash palette: `/digisearch`, `/digivault`, `/websearch`, `/mcp`, `/tools`, `/lang`, `/provider` (`/byok`), `/settings`, `/help`, `/new`, `/copy`, `/export` plus session commands (`/sessions`, `/compact`, `/undo`, `/redo`), model/effort/view/thinking toggles, and the parser/matcher/help helpers. |
| `src/index.ts` | Barrel: re-exports all public symbols. |
| `src/components/DigiChatMark.tsx` | Brand mark SVG icon and `DigiChatWordmark` text+caret component. |
| `src/components/DocumentPane.tsx` | Optional side pane for an original document (vault note body or PDF). |
| `src/components/MiniMarkdown.tsx` | Thin delegate to `@digithings/ui`'s `<ChatMarkdown>`. |
| `src/styles/session.css` | `.dc-*` session grammar: thread, rows, form, print hiding. |
| `src/styles/cursor.css` | `.dt-cur` blink caret, `.dtc-chip` chips, `.dtc-error` error rows. |
| Exports via `@digithings/ui/chat/transcript` | `serializeAssistantMarkdown`, `serializeThreadMarkdown`, `copyMarkdownWithFallback`, `downloadMarkdown`, `buildMailtoUrl`, `truncateForMailto`, `printTranscriptWithFallback`, `toCanonRows`, `outcomeMeta`, `citationHits`, `readableSnippet`, `toolDisplayName`, `stripFoundryCitationMarkers`, and related types. |

## Public API contract

### Exports (`src/index.ts`)

The package barrel exports:

- **Components**: `DigiChatMark`, `DigiChatWordmark`, `MiniMarkdown`, `DocumentPane`
- **Activity-view helpers** (re-exported from `@digithings/ui/chat/transcript`):
  `toCanonRows`, `outcomeMeta`, `citationHits`, `readableSnippet`, `toolDisplayName`,
  `stripFoundryCitationMarkers`, `CanonActivityRow`
- **Transcript-markdown helpers** (re-exported from `@digithings/ui/chat/transcript`):
  `serializeAssistantMarkdown`, `serializeThreadMarkdown`, `copyMarkdownWithFallback`,
  `downloadMarkdown`, `downloadTextFile`, `downloadPlainText`, `downloadHtml`,
  `markdownToPlainText`, `markdownToHtmlDocument`, `truncateForMailto`,
  `buildMailtoUrl`, `buildAnswerMailto`, `buildThreadMailto`,
  `openMailtoWithFallback`, `printTranscriptWithFallback`, and related constants/types
- **Slash-command helpers**: `parseSlashInput`, `matchingSlashCommands`, `slashHelpText`,
  `nextPaletteIndex`, `formatCliSettingLine`, `isLangCode`, `catalogToolSlashDef`,
  `SLASH_COMMANDS`, `SLASH_CATEGORIES`, plus language/effort/view/thinking code arrays,
  labels, and type guards
- **Types**: `DigiChatActivity`, `DigiChatController`, `DigiChatMessage`, `VaultHitSummary`,
  `SlashDef`, `SlashId`, `SlashCategory`, `SlashVisibility`, `CliSettingRow`,
  `LangCode`, `ViewCode`, `ThinkingCode`, `TranscriptTurn`, `TranscriptSource`,
  `CopyMarkdownResult`, `TruncateForMailtoResult`, `MailtoOpenResult`,
  `PrintTranscriptResult`

### CSS class names are API

Consumers style and target `.dc-*` and `.dt-*`/`.dtc-*` class names directly:

- `.dc-page`, `.dc-session`, `.dc-session--wide`, `.dc-session-embed` — layout
- `.dc-thread`, `.dc-msg`, `.dc-who`, `.dc-body` — message rendering
- `.dc-form`, `.dc-send`, `.dc-slash` — composer chrome
- `.dc-brand`, `.dc-brand-link`, `.dc-wordmark-header` — branding
- `.dc-doc-pane`, `.dc-doc-pane-head`, `.dc-doc-pane-body` — document pane
- `.dt-cur` — blink caret; `.dtc-chip` — chip component; `.dtc-error` — error rows

digichat layers `.dc-term-*` chrome around the assistant-ui `Thread`. Styles read
canon design tokens (`--ink`, `--accent`, `--hair`, `--bg`, `--ink-soft`,
`--ink-mute`, `--accent-weak`, `--down`, `--ease`, `--font-mono`) from the
consumer's `[data-theme]` scope. This package defines no tokens of its own.

### CSS delivery

`package.json` exports two stylesheet entrypoints:

- `@digithings/digichat-ui/styles/session.css`
- `@digithings/digichat-ui/styles/cursor.css`

Consumers import these directly (e.g., in `globals.css` or layout files). The
styles apply zero-radius ink/paper chrome with no border-radius except the
explicitly square `0` values — a deliberate "utilitarian-terminal v0.1" aesthetic.

## Slash-command palette

`src/slash-commands.ts` defines the complete public slash palette used in the
digichat composer. Every command is a `SlashDef` with an id, display names,
argument requirements, hint text, kind, and optional category.

### Command kinds

| Kind | Behavior |
|---|---|
| `tool` | Empty enter toggles the tool for the session; remainder becomes a force-query sent with that tool. `/digisearch`, `/digivault`, `/websearch`, plus any catalog/MCP extras via `catalogToolSlashDef()`. |
| `client` | Client-only action that never leaves the browser. `/lang`, `/effort`, `/view`, `/thinking`, `/new`, `/clear`, `/compact`, `/undo`, `/redo`, `/copy`, `/export`, `/help`. |
| `action` | Opens a UI affordance (settings panel, model picker, provider dialog, MCP config, tools list). `/settings`, `/models`, `/provider` (`/byok`, `/key`), `/mcp`, `/tools`, `/sessions`. |

### Choice commands

Several commands (`/lang`, `/effort`, `/view`, `/thinking`) carry `choiceOptions`
arrays. When selected, the palette presents an Up/Down choice list instead of
accepting freeform text:

- **`/lang`** — `en`, `nl`, `it`, `es`, `fr` (featured five; full ISO map lives in digichat's `languages.ts`)
- **`/effort`** — `low`, `medium`, `high`
- **`/view`** — `hidden` (answer only), `compact` (closed), `balanced` (collapse when done), `detailed` (stays open)
- **`/thinking`** — `auto`, `collapsed`, `open`

### Visibility filtering

`matchingSlashCommands()` and `slashHelpText()` accept a `SlashVisibility` object
that controls which commands appear:

- `webSearch`: hidden unless explicitly `true`
- `byok`, `digisearch`, `digivault`, `mcp`, `tools`: shown by default, hidden when `false`
- `sessions`: hidden unless explicitly `true` (embed surfaces hide session switching)
- `models`, `effort`: shown by default

### Extensibility

`parseSlashInput()` and `matchingSlashCommands()` accept an optional `extra:
readonly SlashDef[]` array. Callers add catalog/MCP tools at runtime via
`catalogToolSlashDef({ id, label? })`, which produces a `kind: "tool"` def with
the standard empty-toggles/remainder-sends contract.

## Transcript markdown serializers

The markdown serializers originate in `@digithings/ui/chat/transcript/transcript-markdown.ts`
and are re-exported by `digichat-ui` for backward compatibility. They produce safe,
sharable markdown from digichat conversation turns.

### Core serializers

- **`serializeAssistantMarkdown(content, sources?)`** — Single-turn markdown.
  Strips Foundry citation markers, appends a `### Sources` block from
  `TranscriptSource[]` (title + path only; never vault body, tool JSON, or BYOK keys).

- **`serializeThreadMarkdown(turns)`** — Full-thread markdown with `## You` /
  `## digichat` headings per turn, in chronological order.

### Copy with fallback chain

`copyMarkdownWithFallback(text, opts?)` implements an embed-safe copy pipeline:

1. **Clipboard** — `navigator.clipboard.writeText()` (blocked in cross-origin iframes)
2. **Download** — `.md` file download via `downloadMarkdown()`, plus parent `postMessage`
3. **postMessage** — `digichat:copy` message to parent window
4. **Textarea** — selectable textarea fallback (`#dc-copy-fallback`)

The chain never silently no-ops when `document` exists.

### Export formats

| Function | Output |
|---|---|
| `downloadMarkdown(filename, text)` | `.md` file |
| `downloadPlainText(filename, markdown)` | `.txt` file (fence delimiters stripped) |
| `downloadHtml(filename, markdown, title?)` | `.html` file (pre-wrapped markdown) |
| `buildMailtoUrl(subject, body, opts?)` | `mailto:` URL (truncation-safe) |
| `buildAnswerMailto(markdown, opts?)` | mailto with last-answer body |
| `buildThreadMailto(markdown, opts?)` | mailto with full-transcript body |

`truncateForMailto()` binary-searches the longest prefix that fits within
`MAILTO_MAX_ENCODED_LEN` (1800 bytes after `encodeURIComponent`) and appends the
truncation note. `openMailtoWithFallback()` and `printTranscriptWithFallback()`
degrade to `.md` download when mailto/print is blocked (`preferDownload` flag,
sandboxed iframe, no `window`).

### Safety invariants

- No vault body, tool JSON, BYOK keys, or HTTP headers ever enter serialized output.
- Sources blocks contain only `title` and `path` — never full document content.
- Searching/tool rows and slash notes are omitted; callers pass only user/assistant text turns.
- `stripFoundryCitationMarkers()` removes internal citation syntax before export.

## Activity-view helpers

Also re-exported from `@digithings/ui/chat/transcript/activity-view.ts`, these
pure functions bridge the wire protocol (`DigiChatActivity`) to the rendering
vocabulary (`CanonActivityRow`). No JSX, no DOM — testable in plain Node.

- **`toCanonRows(activities)`** — Converts `DigiChatActivity[]` into `CanonActivityRow[]`
  (tool calls, thinking disclosures, brief cards, system asides)
- **`outcomeMeta(count)`** — `"3 notes"` / `"1 note"` / `"no hits"`
- **`citationHits(messages)`** — Extracts citation cards from completed tool results
- **`readableSnippet(raw, max?)`** — Strips markdown chrome from a snippet
- **`toolDisplayName(name)`** — Maps wire tool ids to human labels (e.g., `digisearch` → `"Search the knowledge base"`)
- **`stripFoundryCitationMarkers(text)`** — Removes Foundry citation syntax

## Components

### DigiChatMark & DigiChatWordmark

`DigiChatMark` renders an SVG speech-bubble icon (56×56 viewBox, stroke-based,
`currentColor`-driven). Accepts `size` (default 18) and optional `title` for
accessibility.

`DigiChatWordmark` renders "digichat" text with an optional blink caret
(`.dt-cur`). The "digi" portion uses `.dc-wm-d` (ink color) and "chat" uses
`.dc-wm-s` (accent color).

### MiniMarkdown

A thin delegate to `@digithings/ui`'s `<ChatMarkdown>`. It exists as a migration
remnant — digichat and digithings-web once carried forked markdown renderers, but
`#1450` (2026-07-10) deleted the fork. Today both surfaces share a single
pipeline: GFM tables, fenced code with copy, Mermaid diagrams, and LaTeX, all
styled via `.chat-md` grammar from `@digithings/ui/styles/chat-core.css`.

### DocumentPane

An optional side pane (`<aside className="dc-doc-pane">`) for inspecting a
`VaultHitSummary`. Rendering depends on the hit's content:

| Condition | Rendered |
|---|---|
| `path` is an `http(s)` URL | "Download" link |
| `path` is an `http(s)` URL ending `.pdf` | Embedded `<object>` PDF viewer |
| `body` is non-empty | `MiniMarkdown` rendering of the note body |
| `snippet` is non-empty (no body) | `readableSnippet()` plain-text excerpt |
| None of the above | "No preview available." |

**Critical safety rule**: paths without an `http(s)` URL never become links.
Vault notes render from `body` loaded via `digivault_get_note` — `DocumentPane`
never invents a URL from a vault path.

## Embed controller type

`DigiChatController` (re-exported from `@digithings/ui/chat/transcript/types.ts`)
is the embed adapter shape, not a mountable React session component. It describes
the imperative surface that `useEmbedDigiChat` exposes in `apps/digichat`:

- `messages: DigiChatMessage[]` — the transcript
- `busy: boolean`, `error: string | null`, `quotaPrompt?: boolean`
- `send(question, opts?)`, `stop?()`, `onRetry?()`, `regenerate?()`, `editLastUser?(text)`, `reset?()`
- `modelLabel?`, `providerIsSet?`, `openSettings?()`

The digichat 2.0 UI (`CliThread` via assistant-ui) consumes this shape internally;
`DigiChatController` is not a component you mount.

## Anti-patterns

The ARCHITECTURE.md for this package defines explicit anti-patterns:

- **Do not mount a second React session shell here.** The 2.0 session is
  assistant-ui `Thread` in `apps/digichat`.
- **Do not put digichat BFF or `@/` aliases into this package.** It is shared
  across consumers; app-internal path aliases belong in `apps/digichat`.
- **Do not invent Digi product CamelCase in prose.** Code identifiers only.
- **Do not revive `ChatActivities` as the session renderer.** assistant-ui parts
  own the session rendering path.

## Dependencies

- **peer:** `react ^19.2.4`, `react-dom ^19.2.4`
- **runtime:** `@digithings/ui` (workspace `*`) — provides `ChatMarkdown`, `IconButton`,
  and the `chat/transcript` barrel (markdown serializers, activity-view helpers, types)
- **dev:** `vitest ^4.1.0`, `typescript ^6.0.2`

The package is `private: true` and `type: "module"`. It targets vitest for tests;
there is no build step — consumers resolve TypeScript source directly through the
workspace.
