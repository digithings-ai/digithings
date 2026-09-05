# @digithings/digichat-ui — architecture

Shared digichat helpers and CSS. digichat **2.0** renders the session through
assistant-ui (`CliThread` in `frontend/digichat`). This package is **not** a
session shell.

Parents (digithings-web, dashboard popup, `widget.js`) **iframe** digichat
`/embed`. Client installs may use the same `/embed` UI or call the BFF
headless. Backend (`digigraph` | `foundry`) is selected per tenant — the UI
does not branch on it.

`DigiChatSession` and `ChatActivities` were removed from the 2.0 session path.
Do not reintroduce a second transcript renderer here.

## Module map

| File | What it is |
|---|---|
| `src/slash-commands.ts` | Public slash palette: `/search`, `/vault` (alias `/docs`), `/lang`, `/websearch`, `/byok`, `/settings`, plus `/help` `/new` `/copy` `/export`. |
| `src/activity-view.ts` | Pure helpers (`citationHits`, …) for markdown export / legacy hydrate. No JSX. |
| `src/transcript-markdown.ts` | Shared serializer for last-answer + full-thread markdown export. |
| `src/components/DigiChatMark.tsx` | Brand mark / wordmark (digithings-web nav). |
| `src/components/CopyButton.tsx` | Markdown copy affordance. |
| `src/components/DocumentPane.tsx` / `MiniMarkdown.tsx` | Optional helpers — **not** mounted by digichat 2.0 `CliThread`. |
| `src/styles/session.css` | `.dc-*` session grammar (thread, rows, form). |
| `src/styles/cursor.css` | `.dt-cur` caret + `dt-bl` keyframes, `.dtc-chip` / `.dtc-error`. |
| `src/types.ts` | `DigiChatActivity`, `DigiChatMessage`, `DigiChatController` (embed adapter shape — not a React session). |

## Public API contract

- **Exports** (`src/index.ts`): `CopyButton`, `DigiChatMark`/`DigiChatWordmark`,
  activity-view helpers, transcript markdown helpers, slash-commands helpers,
  optional `DocumentPane`/`MiniMarkdown`, and the types above.
- **Class names are API.** Consumers style/target `.dc-*` and `.dt-*`/`.dtc-*`
  directly. digichat layers `.dc-term-*` chrome around `CliThread`.
- Styles read canon tokens (`--ink`, `--accent`, `--hair`, …) under the
  consumer's `[data-theme]`; this package defines no tokens of its own.

## Delivery model

| Surface | How digichat UI is delivered |
|---|---|
| digithings-web `/chat`, `/chat/occ` | iframe → digichat `/embed` (`ChatEmbedShell`) |
| dashboard popup / `DigichatLauncher` | iframe → digichat `/embed` |
| `widget.js` | iframe → digichat `/embed` |
| digichat first-party `/chat` | in-process `CliThread` (assistant-ui) |
| digichat `/embed` | in-process `CliThread` (assistant-ui) |
| Client-owned UI / plugin | headless `POST /api/chat` only |

## Anti-patterns

- Do not mount a second React session shell here for marketing `/chat`.
- Do not put digichat BFF / `@/` aliases into this package.
- Do not invent Digi product CamelCase in prose — code identifiers only.
- Do not revive `ChatActivities` as the session renderer — assistant-ui parts own that.
