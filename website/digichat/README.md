# Digichat (legacy static demo)

**Production DigiChat** lives in the monorepo **[digichat/](https://github.com/digithings/digithings/tree/main/digichat)** (Next.js + BFF). Read **[DIGICHAT.md](../../DIGICHAT.md)** for Docker, OIDC, and API keys.

This folder remains a **zero-dependency static** chat for GitHub Pages / quick tests: **DigiGraph** (`POST /v1/chat/completions`). Styled like the [digithings landing page](../index.html).

## Setup

1. Copy `config.example.json` → `config.json` (gitignored if you add secrets).
2. Set `digraphUrl` to your DigiGraph base URL (e.g. `http://127.0.0.1:8000` when Compose is up).
3. If you set `DIGI_API_KEY` on DigiGraph, put the same value in `apiKey` (sent as `Authorization: Bearer …`).
4. **CORS:** DigiGraph allows origins from `DIGI_ALLOWED_ORIGINS` (comma-separated). Defaults include `http://localhost:3000`, `http://localhost:8000`. For GitHub Pages or another host, add your origin, e.g. `https://digithings.ai` or `http://127.0.0.1:5500` for VS Code Live Server.

Optional query override: `digichat/?digigraphUrl=http://127.0.0.1:8000`

## Run locally

Serve the `website/` directory over HTTP (fetch requires a origin, not `file://`). Examples:

```bash
cd website && python3 -m http.server 5173
```

Open `http://127.0.0.1:5173/digichat/`.

## Deploy

Ship `website/` to GitHub Pages as today; Digichat lives at `/digichat/`. Point `config.json` at a reachable DigiGraph (typically tunnel or same-VPC URL in production).

## Stack notes

- Markdown rendering: [marked](https://marked.js.org/) + [DOMPurify](https://github.com/cure53/DOMPurify) (CDN).
- Conversation isolation: `X-Session-Id` + JSON `session_id` per tab; **New chat** rotates the session id.
- Streaming follows DigiGraph SSE (`data: …`, `[DONE]`). `openwebuiFormat: true` matches Open WebUI tool blocks; see `digigraph/docs/OPENWEBUI.md`.
