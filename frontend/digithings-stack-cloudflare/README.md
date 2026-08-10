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

## OCC `occ_help` seed

Container entrypoint (before supervisord):

1. Copies vault notes into `/data/vault/clients/online-compliance-center/`
   (does not overwrite operator edits).
2. Once per volume (`/data/chroma/.occ_help_seeded`), runs
   `digisearch ingest --index occ_help /seed/occ_help` into **Chroma**
   (`CHROMA_PATH`). Seed runs *before* digisearch starts to avoid SQLite locks.

**Full crawl** of help.online-compliance-center.com remains **HOLD** until
explicit approval (`docs/projects/online-compliance-center/GAPLOG.md`). After
approval, run docs_onboard apply against the production stack (ops job that can
reach digisearch ingest with a JWT that has `digisearch:ingest`).

### Manual re-seed (local image / ops)

```bash
# Inside the stack container (volume wipe or seed failure):
rm -f /data/chroma/.occ_help_seeded
CHROMA_PATH=/data/chroma DIGISEARCH_ALLOW_STUB=0 \
  digisearch ingest --index occ_help /seed/occ_help
# Prefer stopping digisearch briefly if the marker was already set while the
# server held the Chroma PersistentClient open.
```

### digichat secrets (CF) — only when stack is reachable

Do **not** point digichat at `*.trycloudflare.com` tunnels.

Retarget only after `https://graph.digithings.ai/healthz` and
`https://key.digithings.ai/healthz` return 200 (custom domains enabled in
`wrangler.toml` / Dashboard). Until then, leave existing digichat secrets and
treat OCC RAG against the CF bundle as **blocked** on network cutover — local
Profile A bundle compose still validates corpus headers + seed.

## Smoke (backends only)

```bash
curl -sf https://graph.digithings.ai/healthz
curl -sf https://key.digithings.ai/healthz
curl -sf https://digithings.ai/api/health   # digraph should be ok; expect 200 once digiquant/digismith disabled or reachable
```

Do **not** treat `/chat` UI E2E as done here — leave for a smoke agent.

## Local — same image as Cloudflare (slim Mac Docker)

**Recommendation:** for website digichat (Profile A), run **one** stack container
instead of N monorepo services. Keep digichat (+ Postgres) separate — Node vs
Python, different secrets and scale. Do **not** put digiquant / digismith HTTP /
Ollama in this path unless you need them.

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
- ADR-0018: [`docs/adr/0018-digichat-path-routing.md`](../../docs/adr/0018-digichat-path-routing.md)
- OCC: [`docs/projects/online-compliance-center/README.md`](../../docs/projects/online-compliance-center/README.md)
