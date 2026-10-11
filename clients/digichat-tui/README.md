# digichat-tui

OpenTUI chat screen for digichat. Same labels as the web thread: session
rail, message list, a composer with no filled field, and the digichat credit.

Talks to the **DigiChat BFF** (Surfaces 1.0 C1 / ADR D3), not the digiquant
runner. Base URL comes from `endpoint("chat")` in `@digithings/surface-config`
(`DIGI_CHAT_URL`, else deprecated `DIGICHAT_DEVKIT_URL`, else
`http://127.0.0.1:3000` for `DIGI_ENV=local`).

| Call | Route |
| --- | --- |
| List / create threads | `GET` / `POST` `/api/conversations` |
| Load a thread | `GET` `/api/conversations/:id` |
| Send / stream | `POST` `/api/v1/chat` (AI SDK UI messages + SSE) |

Machine auth: set `DIGICHAT_API_KEY` to a `digi_live_…` Bearer (never printed).
A 502 or 503 stays an empty screen. The app does not invent a thread.

```bash
bun install
# optional: DIGI_CHAT_URL=http://127.0.0.1:3005 DIGICHAT_API_KEY=digi_live_… \
bun src/index.tsx
```

Set your terminal face to Geist Mono (TUIs cannot load a font). The composer is
focused on launch, same as the web thread. Escape leaves it. `j` / `k` move
between sessions. `n` or the header `+` asks for a new chat. `/` opens the
command palette. Tab arms attach, mic, and send. `q` quits when the composer
is idle.

This app is bun-managed and lives outside the root npm workspaces.
