# @digithings/digichat-ui — architecture

Shared digichat helpers and CSS for the terminal-styled chat surface.

digichat 2.0 (`/chat` and `/embed` in `frontend/digichat`) renders through
assistant-ui (`CliThread`) and consumes this package for `.dc-*` CSS, slash
parsing, `ChatActivities`, brand marks, and transcript markdown helpers.
Parents (digithings-web, dashboard popup, `widget.js`) **iframe** digichat
`/embed` — they do not mount an in-process session widget.

`DigiChatSession` was removed in digichat 2.0. Do not reintroduce a second
session shell here.

## Module map

| File | What it is |
|---|---|
| `src/slash-commands.ts` | Public slash palette (#3418 / #3556): `/search`, `/vault` (alias `/docs`), `/lang`, `/websearch`, `/byok`, `/settings`, plus `/help` `/new` `/copy` `/export`. |
| `src/components/MiniMarkdown.tsx` | Thin delegate to `@digithings/web`'s `<ChatMarkdown source>`. |
| `src/activity-view.ts` | Pure projection of the `DigiChatActivity` wire vocabulary onto shared chat-family props. No JSX. |
| `src/components/ChatActivities.tsx` | Agent-step feed on `@digithings/web` chat primitives. |
| `src/components/CopyButton.tsx` | Markdown copy affordance. |
| `src/transcript-markdown.ts` | Shared serializer for last-answer + full-thread markdown export. |
| `src/components/DigiChatMark.tsx` | Brand mark / wordmark (digithings-web nav). |
| `src/components/DocumentPane.tsx` | Vault/document side pane. |
| `src/styles/session.css` | `.dc-*` session grammar (thread, rows, form, activities). |
| `src/styles/cursor.css` | `.dt-cur` caret + `dt-bl` keyframes, `.dtc-chip` / `.dtc-error`. |
| `src/styles/tokens-shadcn-bridge.css` | Legacy bridge — retired by #1403, kept only for its package export. |
| `src/types.ts` | `DigiChatActivity`, `DigiChatMessage`, `DigiChatController` (embed adapter shape — not a React session). |

## Public API contract (do not break)

- **Exports** (`src/index.ts`): `CopyButton`, `DigiChatMark`/`DigiChatWordmark`,
  `ChatActivities`, `MiniMarkdown`, `DocumentPane`, activity-view helpers,
  transcript markdown helpers, slash-commands helpers, and the types above.
- **Class names are API.** Consumers style/target `.dc-*` and `.dt-*`/`.dtc-*`
  directly. digichat layers `.dc-term-*` chrome around CliThread.
- Styles read canon tokens (`--ink`, `--accent`, `--hair`, …) under the
  consumer's `[data-theme]`; this package defines no tokens of its own.

## Delivery model

| Surface | How digichat UI is delivered |
|---|---|
| digithings-web `/chat`, `/chat/occ` | iframe → digichat `/embed` (`ChatEmbedShell`) |
| dashboard popup / `DigichatLauncher` | iframe → digichat `/embed` |
| `widget.js` | iframe → digichat `/embed` |
| digichat first-party `/chat` | in-process `CliThread` |
| digichat `/embed` | in-process `CliThread` |

## Chat-family convergence (#1418)

`@digithings/web` ships the promoted chat grammar (`components/chat/*` +
`styles/chat-core.css` / `chat-widgets.css`). This package projects activities
onto those primitives and keeps digichat-specific `.dc-*` session chrome.

## Anti-patterns

- Do not mount a second React session shell here for marketing `/chat`.
- Do not put digichat BFF / `@/` aliases into this package.
- Do not invent Digi product CamelCase in prose — code identifiers only.
