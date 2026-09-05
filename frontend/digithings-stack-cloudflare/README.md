# digithings Profile A stack on Cloudflare Containers

**Human gate — infra/network:** this Worker publishes `graph.digithings.ai`
(digigraph) and `key.digithings.ai` (digikey) on the public internet. APIs still
require digikey JWT / BFF token exchange. Secrets only via
`npx wrangler secret put` — never commit values.

One **multi-process** Cloudflare Container replaces Mac Docker Compose +
`*.trycloudflare.com` quick tunnels for production digichat.

| Host | Port inside Container | Role |
|---|---|---|
| `graph.digithings.ai` | digigraph `:8000` | Chat brain (OpenAI-compatible) |
| `key.digithings.ai` | digikey `:8005` | JWT + BFF token exchange |
| _(loopback only)_ | digisearch `:8002` | RAG / `occ_help` |
| _(loopback only)_ | digivault `:8004` | Vault notes |
| _(loopback only)_ | LiteLLM `:4000` | LLM router |
| _(loopback only)_ | Redis `:6379` | digikey blocklist |

```text
Pages digithings.ai/chat[/occ]
  → digichat Container /embed
       → https://graph.digithings.ai   (this Worker → digigraph)
       → https://key.digithings.ai     (this Worker → digikey)
            digigraph → 127.0.0.1 digisearch / digivault / LiteLLM
```

Mac Compose + quick tunnels remain **dev-only** — see
[`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

## Prerequisites

- Docker running (for `wrangler deploy` image build)
- Cloudflare account with **Workers Paid** (same zone as digithings.ai)
- `npx wrangler login`
- Provider keys for LiteLLM (e.g. `GROQ_API_KEY`)
- Stable `DIGIKEY_PRIVATE_KEY_PEM` (do **not** use ephemeral keys in prod)

## Deploy

From **repo root** (Dockerfile context is monorepo root):

```bash
cd frontend/digithings-stack-cloudflare
npm install

# Generate once; store in a password manager — never commit:
#   python -c 'from cryptography.hazmat.primitives.asymmetric import rsa; ...'
npx wrangler secret put DIGIKEY_PRIVATE_KEY_PEM
npx wrangler secret put DIGIKEY_BFF_TOKEN
npx wrangler secret put DIGIKEY_ADMIN_TOKEN   # optional
npx wrangler secret put GROQ_API_KEY
# optional: OPENROUTER_API_KEY OPENAI_API_KEY LITELLM_PROXY_API_KEY
# house Cheaper Inference (default when set): CHEAPERINFERENCE_API_KEY
# optional base / force OR: CHEAPERINFERENCE_API_BASE DIGI_HOUSE_UPSTREAM=openrouter

npx wrangler deploy
```

Custom domains `graph.digithings.ai` / `key.digithings.ai` are declared in
`wrangler.toml`. First deploy may take several minutes (image build + provision).

## Retarget digichat

On the **digichat** Worker (`frontend/digichat-cloudflare`):

```bash
cd frontend/digichat-cloudflare
printf '%s' 'https://graph.digithings.ai' | npx wrangler secret put DIGIGRAPH_INTERNAL_URL
printf '%s' 'https://key.digithings.ai'   | npx wrangler secret put DIGIKEY_URL
# DIGIKEY_BFF_TOKEN must match the stack secret
npx wrangler secret put DIGIKEY_BFF_TOKEN
```

Confirm OCC corpus fields remain in `DIGICHAT_EMBED_TENANTS` (server-only;
`digisearchIndex: "occ_help"`, `vaultPathPrefix: "clients/online-compliance-center"`).

## Chroma + vault seeds (`digithings_docs` + `occ_help`)

Boot order (critical for Cloudflare Containers port probes):

1. Entrypoint copies vault notes (`seed-*.md` always refreshed from the image;
   other filenames only if missing), then **starts supervisord immediately** so
   digigraph `:8000` / digikey `:8005` bind (do **not** block on Chroma seed).
2. Supervisord starts redis → digikey (waits for Redis PONG) → digigraph.
3. Oneshot `seed_chroma` waits for digigraph `/healthz`, then runs
   `digisearch ingest` for **`digithings_docs`** (`/seed/digithings_docs`) and
   **`occ_help`** (`/seed/occ_help`) into Chroma.
4. When remote-index credentials resolve — canonical
   `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN`, then legacy
   `VECTORIZE_ACCOUNT_ID` / `VECTORIZE_API_TOKEN`, then
   `D1_ACCOUNT_ID` / `D1_API_TOKEN` as a supported fallback — the
   container performs **no boot seeding at all**: `seed_chroma.sh` exits
   immediately and `start_digisearch.sh` skips the marker wait, starting
   digisearch straight away against the remote Vectorize index. Container
   disk is **ephemeral** either way — a fresh disk on every wake means a
   local Chroma volume never survives a sleep/wake cycle — so pointing at a
   remote index removes the re-parse/re-chunk/re-embed cost of every cold
   boot rather than just relocating it. Without those two vars set, digisearch
   still waits for `.stack_chroma_seeded_v4` (success) so CLI ingest and the
   HTTP server never share a PersistentClient — it does **not** treat
   `.stack_chroma_seed_failed_v4` as done; that marker only prevents
   `seed_chroma.sh` itself from short-circuiting on the next boot, so a failed
   run retries from scratch. Bump the `v4` suffix in `seed_chroma.sh` /
   `start_digisearch.sh` when seed markdown changes so existing volumes
   re-ingest.

**Firecracker note:** supervisord must log to `/var/log/supervisor/*.log`,
**not** `/dev/stdout`. Logging to `/dev/stdout` raises `ENXIO` and every
program stays `FATAL` (no ports ever bind — CF error 1101).

**Full crawl** of help.online-compliance-center.com remains **HOLD** until
explicit approval (`docs/projects/online-compliance-center/GAPLOG.md`). After
approval, run docs_onboard apply against the production stack (ops job that can
reach digisearch ingest with a JWT that has `digisearch:ingest`).

### Manual re-seed (local image / ops)

```bash
# Inside the stack container (volume wipe or seed failure):
supervisorctl stop digisearch
rm -f /data/chroma/.stack_chroma_seeded_v4 /data/chroma/.stack_chroma_seed_failed_v4
/bin/sh /seed_chroma.sh
supervisorctl start digisearch
```

### digichat secrets (CF) — only when stack is reachable

Do **not** point digichat at `*.trycloudflare.com` tunnels.

1. Confirm workers.dev health (also kept after custom domains — `workers_dev = true`):
   - `https://digithings-stack.<account>.workers.dev/healthz` → digigraph
   - `https://digithings-stack.<account>.workers.dev/_stack/key/healthz` → digikey
2. Custom domains `graph.digithings.ai` / `key.digithings.ai` are already declared
   as `[[routes]]` in `wrangler.toml` (human gate — public backends). Redeploy if
   you change routes.
3. Retarget digichat Worker secrets to `https://graph.digithings.ai` /
   `https://key.digithings.ai` (same `DIGIKEY_BFF_TOKEN` as the stack).

Until step 3, leave existing digichat secrets; Mac tunnels may still be required for local digichat.

## Smoke (backends only)

```bash
# workers.dev
curl -sf https://digithings-stack.<account>.workers.dev/_stack/meta
curl -sf https://digithings-stack.<account>.workers.dev/healthz
curl -sf https://digithings-stack.<account>.workers.dev/_stack/key/healthz

# custom domains (declared in wrangler.toml)
curl -sf https://graph.digithings.ai/healthz
curl -sf https://key.digithings.ai/healthz
```

Do **not** treat `/chat` UI E2E as done here — leave for a smoke agent.

## Local — same image as Cloudflare (slim Mac Docker)

**Recommendation:** for website digichat (Profile A), run **one** stack container
instead of N monorepo services. Keep digichat (+ Postgres) separate — Node vs
Python, different secrets and scale. Do **not** put digiquant / digismith HTTP /
Ollama in this path unless you need them.

### Chat-only service set

| Service | Where | Purpose |
|---|---|---|
| digikey `:8005` | edge | JWT / BFF |
| digigraph `:8000` | edge | Chat brain (`research_rag`) |
| digisearch `:8002` | loopback | RAG |
| digivault `:8004` | loopback | Notes |
| LiteLLM `:4000` | loopback | LLM router |
| Redis `:6379` | loopback | digikey blocklist |

**Omitted on purpose:** digiquant, digismith HTTP, Ollama, heartbeat.

digigraph chat-only env (set in `wrangler.toml` / entrypoint / bundle compose):

- `DIGI_PROJECT_CONFIG=/app/config/digiproject.yaml` — `research_rag`, research only,
  tools `digisearch` + `digivault_search_notes` + `digivault_get_note` (this stack has D1)
- `DIGI_WORKFLOW_PROFILE=research_rag`
- `DIGI_ALLOWED_TOOLS=digisearch,digivault_search_notes,digivault_get_note` — fallback
  only, read solely when `digiproject.yaml` fails to load; kept in sync with it
- `DIGIQUANT_URL=` (empty) — never route to `backtest_node`

digichat: `DIGICHAT_ENABLED_SERVICES=digigraph` (do not probe digiquant).

### Stop excess monorepo containers first

Published host ports clash (`8000` / `8005` / `3005` / `5433`):

```bash
# Full digi compose project (names like digi-digigraph, digi-litellm, …)
docker compose --profile digichat --profile digivault --profile litellm-cache down
# or surgically:
docker stop digi-digigraph digi-digikey digi-digisearch digi-digivault \
  digi-litellm digi-digismith digi-digiquant digi-ollama \
  digi-litellm-redis digi-digikey-blocklist-redis digi-digichat digi-digichat-db
```

Leave Supabase / other projects alone if you still need them.

### Stack-only (`docker run`)

From **repo root**:

```bash
docker build -f Dockerfile.digithings-stack-cloudflare -t digithings-stack:local .

docker run --rm -d --name digithings-stack \
  -p 127.0.0.1:8000:8000 -p 127.0.0.1:8005:8005 \
  -e DIGIKEY_BFF_TOKEN=dev-bff \
  -e DIGIKEY_ALLOW_EPHEMERAL_KEY=1 \
  -e GROQ_API_KEY \
  digithings-stack:local

curl -sf http://127.0.0.1:8000/healthz
curl -sf http://127.0.0.1:8005/healthz
```

Point host digichat / `digichat-dev` at `http://127.0.0.1:8000` and
`http://127.0.0.1:8005`.

### Stack + digichat (one Compose project, 3 containers)

Same Dockerfile as CF, plus digichat GHCR + Postgres:

```bash
cp infra/digichat-release/.env.profile-a-bundle.example \
   infra/digichat-release/.env.profile-a-bundle
# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_VERSION, provider keys
make digichat-profile-a-bundle-up
# tear down: make digichat-profile-a-bundle-down
```

| Path | Containers | When |
|---|---|---|
| This bundle | 1 stack + digichat + Postgres | Website digichat local / CF parity |
| `compose.profile-a.yml` | ~7 (per-service GHCR) | Client install mirroring separate images |
| Root `docker-compose.yml` | Many + profiles | Full monorepo / digiquant / observability |

### Local Worker

```bash
npm run dev    # wrangler dev — needs Docker for Container
npm test
```

## See also

- digichat Container: [`frontend/digichat-cloudflare/README.md`](../digichat-cloudflare/README.md)
- Operator runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md)
- Vectorize cutover runbook (create indexes, sync, verify before flipping traffic): [`docs/ops/vectorize-cutover.md`](../../docs/ops/vectorize-cutover.md)
- ADR-0018: [`docs/adr/0018-digichat-path-routing.md`](../../docs/adr/0018-digichat-path-routing.md)
- OCC: [`docs/projects/online-compliance-center/README.md`](../../docs/projects/online-compliance-center/README.md)
