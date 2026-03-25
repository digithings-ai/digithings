# Docker setup – Digi Ecosystem

**Quick start:** copy `.env.example` → `.env`, set your LLM (OpenAI key, **Ollama Cloud**, or Ollama in Docker), then run `docker compose up --build`. DigiGraph talks to **LiteLLM** (port 4000); LiteLLM routes to your chosen provider. For one-click run and packaging for small firms, see **DEPLOY.md**.

---

## 1. Prerequisites

- **Docker Desktop** (or Docker Engine + Compose) running on your machine.
- **Apple Silicon (M1/M2/M3):** use the arm64 Docker Desktop build.
- **LiteLLM:** Runs by default in the stack. DigiGraph sends all LLM requests to LiteLLM. Choose one:
  - **Ollama Cloud (fastest for testing):** No local GPU or model pull. Create an account at [ollama.com](https://ollama.com), get an API key at [ollama.com/settings/keys](https://ollama.com/settings/keys), set `OLLAMA_API_KEY` and `OLLAMA_MODEL=ollama-cloud/qwen3.5:cloud` (or another cloud model below) in `.env`. No Ollama container required.
  - **Ollama in Docker:** Set `OLLAMA_MODEL=ollama/qwen3:8b`. After `docker compose up`, run `docker exec digi-ollama ollama pull qwen3:8b` once. Models are stored in the `ollama_data` volume.
  - **OpenAI:** Set `OPENAI_API_KEY`; DigiGraph uses the model from `DIGI_LLM_MODE` (default: ollama-cloud/minimax-m2.5:cloud) unless `OLLAMA_MODEL` overrides it.

**Ollama Cloud models (Qwen / DeepSeek; faster testing; no local pull):**

| Model (set as OLLAMA_MODEL) | Notes |
|-----------------------------|--------|
| `ollama-cloud/minimax-m2.5:cloud` | Default when DIGI_LLM_MODE=test (config/model_modes.yaml) |
| `ollama-cloud/qwen3.5:cloud` | Qwen 3.5 cloud (DIGI_LLM_MODE=medium) |
| `ollama-cloud/qwen3-coder:480b-cloud` | 480B, coding-focused |
| `ollama-cloud/deepseek-v3.1:671b-cloud` | DeepSeek 671B, strong reasoning |

**Ollama local (Docker) model suggestions:**

| Use case | Model | Notes |
|----------|--------|------|
| **General / chat (fast)** | `ollama/qwen3:8b` | 5.2 GB, good balance |
| **Reasoning / research** | `ollama/deepseek-r1:14b` | 9 GB, strong reasoning |
| **Embeddings (RAG)** | `qwen3-embedding:4b` or `0.6b` | For vector search / GraphRAG |

---

## 2. One-time setup

### 2.1 Environment file

```bash
cp .env.example .env
```

Edit `.env`:

- **Docker (default):** `OPENAI_API_BASE` is set by compose to `http://litellm:4000/v1` so DigiGraph uses LiteLLM. You only set:
  - **Ollama Cloud (fast testing):** Set `OLLAMA_API_KEY` (from [ollama.com/settings/keys](https://ollama.com/settings/keys)) and `OLLAMA_MODEL=ollama-cloud/qwen3.5:cloud` (or `qwen3-coder:480b-cloud`, `deepseek-v3.1:671b-cloud`). No Ollama container or model pull needed.
  - **OpenAI:** `OPENAI_API_KEY=sk-...`. DigiGraph uses the model from `DIGI_LLM_MODE` (default: ollama-cloud/minimax-m2.5:cloud per config/model_modes.yaml). Set `OLLAMA_MODEL` to override.
  - **Ollama in Docker:** Set `OLLAMA_MODEL=ollama/qwen3:8b` (or `ollama/deepseek-r1:14b`). Leave `OPENAI_API_KEY` empty. After first `docker compose up`, run `docker exec digi-ollama ollama pull qwen3:8b` (or the model you chose).
  - **Model mode (minimal tokens):** Set **DIGI_LLM_MODE=test** (default) for smallest models and minimal token usage on Ollama free tier. Use **medium** or **best** for larger models. Mode defaults are in `config/model_modes.yaml`; see **config/MODELS.md** for how agents can update the model list.
- **Local run (no Docker):** Set `OPENAI_API_BASE=http://127.0.0.1:4000/v1` to use a local LiteLLM, or `OPENAI_API_BASE=http://host.docker.internal:11434/v1` for direct Ollama.

Optional:

- **`LITELLM_MASTER_KEY`** (`sk-...`): enables LiteLLM proxy admin/virtual-key auth. When set, also set **`LITELLM_PROXY_API_KEY`** to the same value (DigiGraph Bearer) and keep **`OPENAI_API_KEY`** for OpenAI upstream routing inside the LiteLLM container only. See **SECURITY.md**. Compose also defaults **`DIGIKEY_LITELLM_PROXY_KEY`** from **`LITELLM_MASTER_KEY`** so DigiKey can return **`litellm_proxy_api_key`** to DigiChat (**docs/LOCAL_STACK.md**).
- **`LITELLM_PROXY_API_KEY`**: Bearer sent by DigiGraph → LiteLLM; avoids using the upstream OpenAI key as the proxy token. Falls back to `OPENAI_API_KEY` if unset (dev stacks).
- **`REDIS_URL`**: e.g. `redis://redis:6379` when using Compose profile **`litellm-cache`** for Redis-backed proxy cache; then set **`cache_params.type: redis`** in `config/litellm.yaml` (see § LiteLLM upgrades). The default config uses **local** proxy cache without Redis.
- `GROQ_API_KEY`, `ANTHROPIC_API_KEY` in `.env` and in `config/litellm.yaml` for multi-provider routing.

Never commit `.env` (it’s in `.gitignore`).

### 2.2 DigiQuant data directories

The Compose file mounts:

- `./digiquant/data` → read-only input data
- `./digiquant/results` → backtest/output results

If they don’t exist, create them (they can be empty for Phase 0):

```bash
mkdir -p digiquant/data digiquant/results
```

---

## 3. Build and run

From the **repository root**:

```bash
docker compose up --build
```

- **DigiQuant** and **DigiSearch** become healthy first; **LiteLLM** exposes **`/health/liveliness`** (fallback **`/health`**) on port 4000.
- **DigiGraph** starts after DigiQuant, DigiSearch, and **LiteLLM** are all healthy (port 8000).
- Logs from both services stream in the same terminal. Stop with `Ctrl+C`.

Run in the background (detached):

```bash
docker compose up --build -d
```

---

## 4. Verify (Phase 0)

After both services are up:

```bash
curl -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech"}'
```

You should get a JSON backtest result in under ~10 seconds (see ROADMAP.md Phase 0).

Health checks:

```bash
curl -s http://127.0.0.1:8000/health   # DigiGraph
curl -s http://127.0.0.1:8001/health   # DigiQuant
```

LLM sanity check (Phase 1; DigiGraph → LiteLLM → Ollama/OpenAI):

```bash
curl -s http://127.0.0.1:8000/test_llm
```

Expect `{"ok":true,"model":"...","reply":"..."}` when the LLM is reachable.

---

## 5. LiteLLM and Ollama (Phase 1 – default)

LiteLLM runs in the default stack. The Compose image is **`docker.litellm.ai/berriai/litellm:main-stable`** (pinned track; avoid `main-latest` in production unless you monitor upstream changes). Config is loaded with **`litellm --config /app/config/litellm.yaml --port 4000`**.

DigiGraph sends all LLM requests to **http://litellm:4000/v1**. LiteLLM listens on **127.0.0.1:4000** (useful for debugging or calling from the host). **Ollama** runs as a Docker service; LiteLLM routes `ollama/*` models to `http://ollama:11434`. Edit `config/litellm.yaml` to add models (OpenAI, Ollama, Groq, etc.); use `OLLAMA_MODEL=ollama/qwen3:8b` in `.env` to test without OpenAI. Pull Ollama models: `docker exec digi-ollama ollama pull <model>`.

**Health:** `curl -s http://127.0.0.1:4000/health/liveliness` (or `/health` on older builds).

### 5.1 LiteLLM upgrades

1. Check [LiteLLM release notes](https://docs.litellm.ai/release_notes/) for breaking YAML or env changes.
2. Update the image tag or digest in `docker-compose.yml` (prefer a **digest** in production).
3. Run `docker compose pull litellm && docker compose up -d litellm` and verify **`/health/liveliness`**, then **`GET /v1/models`**.

### 5.2 Optional Redis cache profile

For **shared** proxy response caching (multiple LiteLLM replicas or persistence across restarts), start Redis and point LiteLLM at it:

```bash
docker compose --profile litellm-cache up -d
```

In `.env` set **`REDIS_URL=redis://redis:6379`**. In **`config/litellm.yaml`**, set under **`litellm_settings.cache_params`**: **`type: redis`** and a TTL as needed (see [LiteLLM caching](https://docs.litellm.ai/docs/proxy/caching)). The committed default uses **`type: local`** so the stack works without the profile.

---

## 6. Phase 3 – Heartbeat (optional)

To run the heartbeat agent every 30 minutes (health checks + audit log):

```bash
docker compose --profile heartbeat up -d
```

This starts the `heartbeat` service in addition to the main stack. Audit events are written to `digiquant/results/audit/events.jsonl`. See **HEARTBEAT.md** and **digiclaw/DIGICLAW.md**.

Without Docker, from repo root: `python -m digiclaw` (set `DIGIGRAPH_URL`, `DIGIQUANT_URL`, `AUDIT_LOG_PATH` as needed). Schedule via cron for 24/7 monitoring.

---

## 7. Security and binding

- All services in `docker-compose.yml` bind to **127.0.0.1** only (loopback). No ports are exposed to the network.
- For remote access use Tailscale, Cloudflare Tunnel, or similar – see **SECURITY.md**.

---

## 8. Troubleshooting

| Issue | What to do |
|-------|------------|
| Build fails (e.g. `digiquant` COPY) | Ensure `digiquant/data` exists (can be empty). |
| “Cannot connect to Docker daemon” | Start Docker Desktop and wait until it’s fully up. |
| DigiGraph can’t reach DigiQuant | Use `DIGIQUANT_URL=http://digiquant:8001` (compose sets this). Don’t use `localhost` from inside a container. |
| DigiGraph can’t reach LiteLLM | In Docker, `OPENAI_API_BASE` is set to `http://litellm:4000/v1`. Ensure LiteLLM is healthy (`curl -s http://127.0.0.1:4000/health/liveliness` or `/health`). If `LITELLM_MASTER_KEY` is set, ensure **`LITELLM_PROXY_API_KEY`** matches for DigiGraph. |
| Ollama model not found / 404 | Pull the model: `docker exec digi-ollama ollama pull qwen3:8b` (or the model name from `OLLAMA_MODEL`). List: `docker exec digi-ollama ollama list`. |
| Port 8000 or 8001 in use | Often local uvicorn (e.g. `uvicorn digigraph.server:app --port 8000`). Stop those processes (`kill <pid>`) or change host ports in `docker-compose.yml`. |

---

**Reference:** `ARCHITECTURE.md`, `ROADMAP.md`, `SECURITY.md`, `DEPLOY.md` (one-click and packaging), and the sub-folder docs (`DIGIGRAPH.md`, `DIGIQUANT.md`).
