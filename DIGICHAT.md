# DigiChat — client-facing chat UI (v1)

DigiChat is the **production** web client for tenants that run DigiGraph. The browser talks only to the **DigiChat BFF** (Next.js Route Handlers). The BFF calls DigiGraph’s OpenAI-compatible API using **`DIGIGRAPH_UPSTREAM_API_KEY`** (legacy shared secret) **or** a short-lived **DigiKey JWT** when **`DIGIKEY_URL`** and **`DIGIKEY_BFF_TOKEN`** are set (`POST /v1/oauth/token` with `grant_type=bff_session`). Machine clients may present **`dgk_live_…`** keys issued by DigiKey directly for the same exchange path. **Local full stack** (DigiKey, all services, seeding, env matrix): **[docs/LOCAL_STACK.md](docs/LOCAL_STACK.md)**.

## Design

DigiChat follows the **digithings.ai** marketing palette (see `website/style.css`): near-black page background (`#0a0a0a`), elevated panels (`#121212`), borders (`#2a2a2a`), primary text (`#e6e6e6`), secondary/muted (`#a3a3a3`). Typography uses **Inter**. The **starfield** and hero animation from the public site are intentionally **not** used in the app chrome so the chat stays readable and calm. The **browser tab icon** is the same QR mark as the landing site (`website/assets/qrw.svg`), vendored as [`digichat/src/app/icon.svg`](digichat/src/app/icon.svg) with a `#0a0a0a` rounded background; refresh the favicon or duplicate from `qrw.svg` if the brand asset changes.

## Features

- **Ecosystem** side panel: DigiGraph, DigiQuant, DigiSmith, and **DigiSearch** base URLs (httpOnly cookie overrides + health badges). On the host, use `127.0.0.1` ports **8000–8003** (graph / quant / search / smith).
- **React 19 + AI SDK** streaming chat (`useChat`, UI message parts).
- **Auth.js (OIDC)** for humans + **Bearer API keys** for machines (`digi_live_…`, hashed in Postgres).
- **Optional Postgres**: tenants, `api_keys`, `user_tenants` mapping (OIDC `sub` → tenant).
- **Docker** `digichat` + `digichat-db` under Compose **profile `digichat`**.
- **Health**: `GET /api/health` (DigiGraph + DB checks).

## Capability matrix (federated hub)

Deployments can describe which Digi ecosystem surfaces the BFF and UI treat as **enabled** (health checks, future admin toggles, copy in the ecosystem sheet):

| Env | Purpose |
|-----|---------|
| `DIGICHAT_ENABLED_SERVICES` | Comma-separated: `digigraph`, `digisearch`, `digiquant`, `digismith`. **Default when unset:** all four (DigiSearch included for local RAG parity). Set a narrower list only if a vertical is not deployed. |
| Existing URLs | `DIGIGRAPH_INTERNAL_URL`, `DIGIQUANT_INTERNAL_URL`, `DIGISMITH_INTERNAL_URL`; add **`DIGISEARCH_INTERNAL_URL`** when surfacing search health next to the hub. |

Trace payloads from DigiGraph may include **`service`** (`digigraph` \| `digisearch` \| `digiquant`) so the transcript can label **which vertical** emitted a span when using hub connector tools.

## DigiClone (end-to-end quant copilot)

**DigiClone** is the Compose-backed path **DigiChat → DigiGraph → DigiQuant** (optional **DigiSearch** for grounded research). OHLCV lives under [`digiquant/data`](digiquant/data) (mounted at `DIGIQUANT_DATA_DIR` in `docker-compose.yml`). **DigiKey** issues short-lived JWTs; the BFF exchanges OIDC sessions or `dgk_live_` machine keys and forwards **`Authorization: Bearer <JWT>`** to DigiGraph (and the graph forwards the same credential to DigiQuant/DigiSearch). After a workflow run, the chat shows a **quant comparison strip** when assistant/tool payloads contain `BacktestResult`-shaped JSON (`run_id`, `sharpe_ratio`, …). With Postgres, persist runs via `GET`/`POST` **`/api/conversations/[id]/quant-runs`** (apply migration `digichat/drizzle/0002_quant_runs.sql`). Optional post-backtest **optimization**: add **`optimize`** to project `agents.enabled` or set **`DIGI_GRAPH_OPTIMIZE_AFTER_BACKTEST=1`** on DigiGraph.

**Local RAG on EDGAR (dev):** To exercise document-mode research against a larger financial-text slice than [`digisearch/seeds`](digisearch/seeds/), export and ingest the optional **EDGAR-CORPUS** sample into Chroma index **`edgar_dev`** and set **`DIGISEARCH_INDEX=edgar_dev`** for DigiGraph (see [docs/LOCAL_STACK.md](docs/LOCAL_STACK.md): `make export-edgar-digisearch-dev`, `make seed-digisearch-edgar-dev` or `seed-digisearch-edgar-dev-host`). Same JWT chain applies to DigiSearch queries from the hub.

## Chat UI

- **Sidebar**: conversation list, **New chat**, rename/delete (overflow menu on each row). **Ctrl/Cmd+B** toggles the rail (shadcn sidebar). Layout is full-width with **digithings.ai-aligned** dark tokens (see Design above).
- **Transcript**: scroll stick-to-bottom with a **New messages** chip when scrolled up; **Copy** and **Regenerate** on assistant bubbles; reasoning and tool payloads in **collapsible** blocks. DigiGraph **`data-digigraphTrace`** parts render **Sources** (tier, year, title, snippet) and a compact **Research brief** card (themes + profiling questions) when trace events include `rag_sources` / `graph_update` payloads.
- **Composer**: auto-growing textarea (capped height), **Enter** to send, **Shift+Enter** for newline, **Stop** while streaming.

## Conversations & persistence

- **Local (always)**: threads and full message payloads are mirrored in `localStorage` under `digichat-threads:<user id>` (OIDC subject / dev id).
- **Server (optional)**: when `DIGICHAT_DATABASE_URL` is set and migrations are applied, DigiChat syncs to Postgres (`conversations` + `conversation_messages`). List/detail use the routes below; the active conversation id is sent to DigiGraph as **`X-Digichat-Session`** / **`X-Session-Id`** for stable upstream tracing.
- **REST** (session cookie or machine `Authorization: Bearer …`):
  - `GET /api/conversations` → `{ serverPersistence: boolean, conversations: [{ id, title, updatedAt }] }`
  - `POST /api/conversations` with `{ id?: string, title?: string }` → `{ id }` (optional client `id` to match the chat session UUID)
  - `GET /api/conversations/[id]` → `{ id, title, messages }` (AI SDK UI messages)
  - `PUT /api/conversations/[id]` with `{ title?: string, messages: UIMessage[] }` → `204` (replaces stored transcript)
  - `DELETE /api/conversations/[id]` → `204`

Machine API keys persist under owner key `machine:<tenantSlug>`.

Apply new tables with `cd digichat && npm run db:migrate` (see [drizzle/0001_conversations.sql](digichat/drizzle/0001_conversations.sql), [drizzle/0002_quant_runs.sql](digichat/drizzle/0002_quant_runs.sql) for quant run storage).

## Local dev (fast iteration — no DigiChat Docker image)

Use the **Next.js dev server** for hot reload. For the fastest loop, run **all backends on the host** (no Docker): DigiKey, DigiQuant, DigiSearch, DigiSmith, DigiGraph — same ports as Compose (**8005** DigiKey, **8000–8003** services, optional **4000** LiteLLM).

### Host backends only (recommended for iteration)

1. **Prereqs:** Repo **`.venv`** with editable installs per [scripts/run_stack_local.sh](scripts/run_stack_local.sh) (`digibase`, `digikey`, `digiquant`, `digigraph`, `digisearch`, `digismith`). Optional: `litellm` on PATH or set **`OPENAI_API_BASE`** in root `.env` to any OpenAI-compatible URL (e.g. Ollama on `127.0.0.1:11434/v1`).
2. **Start stack** (from repo root):

   ```bash
   make stack-local
   ```

   Stop: `make stack-local-stop`. Details, Ollama, and **`litellm_proxy_api_key`**: **[docs/LOCAL_STACK.md](docs/LOCAL_STACK.md)**.

3. **DigiChat env** — `cd digichat && cp -n .env.example .env.local`, then set at least:

   - `AUTH_SECRET` — use the **same** value as repo-root `.env` if you already use Auth.js elsewhere, **or** `openssl rand -base64 32`. Set **`NEXTAUTH_SECRET`** to the same string to avoid decrypt errors.
   - **`AUTH_URL`** and **`NEXTAUTH_URL`** — must match the origin you open in the browser. **`npm run dev`** serves **`http://127.0.0.1:3000`** by default (don’t mix `localhost` vs `127.0.0.1` for cookies). If repo-root `.env` uses **`AUTH_URL=...:3005`** for Docker DigiChat, your **host** `.env.local` should still use **:3000** when using `make digichat-dev`, unless you change the Next port.
   - **`DIGIKEY_URL=http://127.0.0.1:8005`** and **`DIGIKEY_BFF_TOKEN`** — **identical** to **`DIGIKEY_BFF_TOKEN`** on the running DigiKey process (same as repo-root `.env` when using `make stack-local`). Without this, chat returns **`upstream_auth`**.
   - `DIGIGRAPH_INTERNAL_URL=http://127.0.0.1:8000`, `DIGIQUANT_INTERNAL_URL=http://127.0.0.1:8001`, `DIGISMITH_INTERNAL_URL=http://127.0.0.1:8003`, **`DIGISEARCH_INTERNAL_URL=http://127.0.0.1:8002`**.
   - **`DIGICHAT_ENABLED_SERVICES=digigraph,digisearch,digiquant,digismith`** so the Ecosystem sheet, health probes, and hub tools see DigiSearch.
   - **`DIGICHAT_DEV_AUTH=1`** and **`DIGICHAT_DEV_PASSWORD`** (e.g. `dev`) — password login at `/login`.
   - **`DIGICHAT_LOCAL_AUTH_KEY`** (`openssl rand -hex 24`) — recommended: **real** Auth.js session on first load ([`local-bootstrap`](digichat/src/app/actions/local-bootstrap.ts)); same experience as signing in, without clicking through `/login` every time.

4. **Run UI:**

   ```bash
   make digichat-dev
   ```

   Open [http://127.0.0.1:3000](http://127.0.0.1:3000). With stub DigiSearch (`DIGISEARCH_ALLOW_STUB=1`, default when `CHROMA_PATH` is unset), RAG is smoke-test quality; use real Chroma + seeding per LOCAL_STACK for useful retrieval.

5. **Postgres for chat history (optional but recommended)** — Without `DIGICHAT_DATABASE_URL`, `/api/health` reports **database: skipped** and threads live in **localStorage** only. To run Postgres locally while keeping Python on the host:

   ```bash
   make up-digichat-db
   ```

   Then in `digichat/.env.local` set `DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat`, run `cd digichat && npm run db:migrate`, and restart DigiChat. The **Ecosystem** sheet shows when server DB is configured vs skipped. **Strategic direction:** platform data (chat DB, checkpoints, cache creds, etc.) should eventually route through a **DigiBase** data-plane service so secrets and policy live in one place — see [digibase/DIGIBASE.md](digibase/DIGIBASE.md). **v1** remains a normal Postgres URL per environment.

Older two-service-only script (DigiQuant + DigiGraph on **18001** / **18000**): [`scripts/run_local.sh`](scripts/run_local.sh).

**Backend in Docker, UI on the host** (optional):

1. From repo root, start the core stack **without** the `digichat` profile (DigiGraph, LiteLLM, DigiQuant, DigiSearch, DigiSmith on `127.0.0.1`):

   ```bash
   make up
   ```

2. Configure and run DigiChat:

   ```bash
   cd digichat
   cp -n .env.example .env.local
   ```

   In `.env.local` set at least:

   - `AUTH_SECRET` — any non-empty string for dev (e.g. `openssl rand -base64 32`)
   - `AUTH_URL=http://127.0.0.1:3000` — must match the URL you open in the browser (use **127.0.0.1** or **localhost** consistently, not both).
   - `NEXTAUTH_URL` — set to the **same origin** as `AUTH_URL` (e.g. `http://127.0.0.1:3000`) so `next-auth/react` client sign-in matches the dev password flow.
   - `DIGIGRAPH_INTERNAL_URL=http://127.0.0.1:8000`
   - `DIGIQUANT_INTERNAL_URL=http://127.0.0.1:8001`
   - `DIGISMITH_INTERNAL_URL=http://127.0.0.1:8003`
   - `DIGICHAT_DEV_AUTH=1` — password login without OIDC (use `DIGICHAT_DEV_PASSWORD`, default `dev`).
   - **`DIGICHAT_LOCAL_AUTH_KEY`** — optional random secret (`openssl rand -hex 24`); when set in **non-production**, the app performs a **real** Auth.js credentials sign-in on first load so you skip `/login` without faking sessions.
   - Optional: leave `DIGICHAT_DATABASE_URL` unset — conversations stay in **localStorage** only until you point at Postgres

3. `npm install` once, then:

   ```bash
   npm run dev
   ```

   Open [http://127.0.0.1:3000](http://127.0.0.1:3000). Or use `make digichat-dev` from the repo root.

**Fully local Python stack** (no Docker): see [scripts/run_local.sh](scripts/run_local.sh) for DigiGraph/DigiQuant on ports `18000`/`18001`, then set `DIGIGRAPH_INTERNAL_URL=http://127.0.0.1:18000` (and matching Quant URL) in `.env.local`.

## Quick start (local)

From repo root:

```bash
cd digichat
cp .env.example .env.local
# Set AUTH_SECRET, DIGIGRAPH_INTERNAL_URL, optional AUTH_OIDC_* , DIGICHAT_DATABASE_URL
npm install
npm test
npm run dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). For local sign-in without OIDC, set `DIGICHAT_DEV_AUTH=1` and use the dev password from `.env.local` (`DIGICHAT_DEV_PASSWORD`).

**Troubleshooting Auth.js:** If the server logs `JWTSessionError` / `no matching decryption secret`, your browser still has a session cookie from an **older `AUTH_SECRET`** (e.g. switched from Docker DigiChat to `npm run dev`, or rotated the secret). Clear site cookies for your dev host or use a private window, then sign in again. Set `NEXTAUTH_SECRET` to the **same value** as `AUTH_SECRET` if you rely on legacy env names.

**Auto sign-in locally (real session):** Set `DIGICHAT_LOCAL_AUTH_KEY` to a long random string in `.env.local`. On first visit, a server action calls `signIn("local-bootstrap", …)` with that key; you get a normal encrypted session cookie (`dev-local`), same as manual dev password login. The provider is **not registered** when `NODE_ENV=production`. You can still pass the key only when launching: `DIGICHAT_LOCAL_AUTH_KEY=… npm run dev`.

### Machine clients

Same chat contract as the browser, with a **Bearer** token:

- Bootstrap (env): `DIGICHAT_BOOTSTRAP_API_KEY` → tenant `DIGICHAT_BOOTSTRAP_TENANT_SLUG` (default `default`).
- Database keys: `npm run db:create-key -- default my-bot` (requires migrated DB + seed).

```bash
curl -N http://127.0.0.1:3000/api/v1/chat \
  -H "Authorization: Bearer digi_live_…" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"id":"u1","role":"user","parts":[{"type":"text","text":"ping"}]}]}'
```

Request bodies use the **AI SDK UI message** shape (`id`, `role`, `parts` with `type: "text"`). Session stickiness: send `X-Digichat-Session` (or `X-Session-Id`) with a stable UUID per conversation.

## Docker Compose

From repo root (starts core services + Postgres + DigiChat):

```bash
make up-digichat
```

Equivalent:

```bash
docker compose --profile digichat up -d --build
```

- **DigiChat**: default [http://127.0.0.1:3005](http://127.0.0.1:3005) (override host/port with `DIGICHAT_PUBLISH_HOST` / `DIGICHAT_PUBLISH_PORT` in `.env`; then set **`AUTH_URL`** to the same origin).
- **Postgres**: `127.0.0.1:5433` (user/db `digichat`)
- Set **`AUTH_URL`** to the URL users hit in the browser (OAuth redirect). For quick local testing without OIDC, set **`DIGICHAT_DEV_AUTH=1`** and use the dev password from `.env` (`DIGICHAT_DEV_PASSWORD`, default `dev`).
- **`DIGIGRAPH_UPSTREAM_API_KEY`**: optional static Bearer to DigiGraph if you are not using DigiKey exchange (bootstrap only).
- **`DIGICHAT_AUTO_MIGRATE=1`** runs Drizzle migrations on server boot (container image).

After first boot with Postgres:

```bash
cd digichat && DIGICHAT_DATABASE_URL=postgresql://digichat:digichat@127.0.0.1:5433/digichat npm run db:seed
npm run db:create-key -- default automation
```

Map OIDC users to tenants with SQL or a future admin UI: insert into `user_tenants` (`provider_account_id`, `tenant_id`).

## Environment reference

See [digichat/.env.example](digichat/.env.example). Critical variables:

| Variable | Purpose |
|----------|---------|
| `AUTH_SECRET` | Auth.js session encryption |
| `AUTH_URL` | Public origin of DigiChat (OAuth) |
| `AUTH_OIDC_*` | Generic OIDC provider |
| `DIGIGRAPH_INTERNAL_URL` | DigiGraph base URL (e.g. `http://digigraph:8000`) |
| `DIGIGRAPH_UPSTREAM_API_KEY` | Optional static Bearer to DigiGraph (if not using JWT from DigiKey) |
| `DIGICHAT_DATABASE_URL` | Postgres (optional; required for hashed machine keys + user→tenant) |

## Trace streaming (orchestration + DigiChat UI)

- **DigiGraph** streaming responses may include **`digigraph_trace`** objects on each SSE `choices[0].delta` (versioned `TraceEventV1`: `graph_update`, `rag_sources`, `code_block`, `span`, …). Tool results from `digisearch` / `digisearch_fetch_all` attach **`rag_sources`** summaries for citation cards.
- **DigiChat** (default): when `DIGICHAT_TRACE_UI` is not `0`, the BFF uses a UI message stream that forwards text **and** trace data parts (`data-digigraphTrace`). The chat panel renders **trace cards** (RAG sources, code/data-engineer tasks, graph updates) and **structured tool** rows instead of raw JSON blobs. Send `X-Digichat-Trace: 0` on the chat request to force the legacy `streamText`-only path. Set **`NEXT_PUBLIC_DIGICHAT_TRACE_UI=0`** in the browser bundle to stop advertising trace mode on requests.

## Chat troubleshooting

- **`upstream_auth` / missing JWT:** If `DIGIKEY_URL` points at DigiKey, **`DIGIKEY_BFF_TOKEN` must match** the secret on the DigiKey process (same value in root `.env` / compose and `digichat/.env.local`). Restart DigiChat after changing env. See [docs/LOCAL_STACK.md](docs/LOCAL_STACK.md) for the full matrix. Alternatives: call the BFF with **`Authorization: Bearer dgk_live_…`**, or set **`DIGIGRAPH_UPSTREAM_API_KEY`** for a static upstream Bearer.
- **DigiGraph** accepts both string `content` and OpenAI/AI-SDK **part lists** (`[{ "type": "text", "text": "..." }]`) on `/v1/chat/completions`. The **trace** BFF path normalizes AI SDK `ModelMessage` payloads to plain `{ "role", "content" }` strings before `POST /v1/chat/completions`, matching DigiGraph’s `ChatMessage` model and avoiding `422` from strict body validation. If a call still fails, the assistant bubble includes the **upstream response body** (e.g. FastAPI `detail`) after the status line.
- **Auth:** In production Docker you must **sign in** at `/login` (or use a machine `Authorization: Bearer …` key). `DIGICHAT_DEV_AUTH=1` enables the dev password provider; set **`AUTH_URL`** to the exact origin users use (e.g. `http://127.0.0.1:3005`) so the session cookie is issued correctly.

## Security notes

- Do **not** expose DigiGraph to the public internet for browser-driven flows; route users through DigiChat only.
- DigiGraph **rate limits** by caller IP; behind the BFF all requests may share one IP — tune limits or add trusted-forwarded handling if needed (see [digigraph/src/digigraph/server.py](digigraph/src/digigraph/server.py)).
- Never enable `DIGICHAT_DEV_AUTH` in production.

## Legacy static UI

[website/digichat/](website/digichat/) remains a zero-dependency demo; prefer **digichat/** for production.
