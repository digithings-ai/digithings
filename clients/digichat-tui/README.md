# digichat-tui

OpenTUI chat screen for digichat. Same labels as the web thread: session
rail, message list, a composer with no filled field, and the digichat credit.

Reads use the desk routes on the official API (`http://127.0.0.1:8788`,
override with `DQ_API_URL`): `/chat/sessions`, `/chat/sessions/current`,
`/chat/sessions/current/messages`. A 502 or 503 stays an empty screen. The
app does not invent a thread.

```bash
bun install
DQ_API_URL=http://127.0.0.1:8788 bun src/index.tsx
```

`i` or Enter focuses the composer. Escape leaves it. `j` / `k` move between
sessions. `n` asks for a new chat. `q` quits when the composer is idle.

This app is bun-managed and lives outside the root npm workspaces.
