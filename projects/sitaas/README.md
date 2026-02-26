# Sitas Project

Self-contained Digi stack: **DigiGraph** (orchestration) + **DigiSearch** (Azure index) + **LiteLLM**. No DigiQuant.

## Quick Start

```bash
# From repo root
cd projects/sitaas
cp .env.example .env
# Edit .env: set AZURE_SEARCH_*, OLLAMA_API_KEY (or OPENAI_API_KEY)

docker compose up --build
```

## Updating containers after code changes

After pulling repo changes or editing `digigraph` / `digisearch` code, rebuild and restart so Sitaas uses the latest images:

```bash
cd projects/sitaas
docker compose build --no-cache digigraph digisearch
docker compose up -d
```

Or in one step (rebuild and recreate only changed services):

```bash
cd projects/sitaas
docker compose up -d --build
```

From `projects/sitaas` you can also use **make**: `make update` (rebuild + up), or `make build-no-cache` then `make up` for a full rebuild.

**Endpoints** (project-specific ports; override via .env):
- DigiGraph: http://127.0.0.1:8010
- DigiSearch: http://127.0.0.1:8012
- LiteLLM: http://127.0.0.1:4010

## Environment Variables

| Variable | Required | Description |
|---------|----------|-------------|
| `AZURE_SEARCH_ENDPOINT` | Yes | Azure AI Search endpoint URL |
| `AZURE_SEARCH_API_KEY` | Yes | Azure AI Search admin API key |
| `DIGISEARCH_INDEX_CONFIG` | Yes | Path to index config (e.g. `indexes/unified-content-index.yaml`) |
| `DIGIGRAPH_PORT` | No | Host port (default: 8010) |
| `DIGISEARCH_PORT` | No | Host port (default: 8012) |
| `LITELLM_PORT` | No | Host port (default: 4010) |
| `OLLAMA_API_KEY` | For Ollama Cloud | Get at ollama.com/settings/keys |
| `OPENAI_API_KEY` | Alternative | For OpenAI models |
| `DIGI_LLM_MODE` | No | `test` \| `medium` \| `best` (default: test) |

See `.env.example` for the full list.

## Project Structure

```
projects/sitaas/
├── config.yaml       # Project config (agents, indexes, MCP)
├── indexes/          # Index definitions (schema, field mapping)
│   └── unified-content-index.yaml
├── .env.example      # Env var template (copy to .env)
├── .env              # Connection only: endpoint, api_key (gitignored)
├── docker-compose.yml
└── README.md
```

**Index config**: `indexes/*.yaml` define index name, field mapping, and schema. Connection (endpoint, api_key) stays in `.env`.

## Workflow

1. User sends prompt → DigiGraph `POST /workflow`
2. Research node queries DigiSearch (Azure index) for document context
3. LLM receives prompt + search results, discusses/summarizes
4. Returns research response (no backtest)

**Run storage and sub-agents:** This project has `run_data_dir` set (`config.yaml`), so search results are written under `/data/run` (Docker volume `sitas-run-data`). The research node has access to **digisearch**, **visualization_agent**, **analysis_agent**, and **data_prep_agent**. After a search, the model receives a `dataset_ref` and can call the sub-agents for charts, correlations, exports, filters, etc.

**Test the flow:**
```bash
docker compose up -d
./test_workflow.sh "what do we have about teams?"
# Or: curl -X POST http://127.0.0.1:8010/workflow -H "Content-Type: application/json" -d '{"prompt":"your query"}'
```

## Run from Repo Root

```bash
docker compose -f projects/sitaas/docker-compose.yml up --build
```

Ensure `projects/sitaas/.env` exists (copy from `.env.example`).

## Open WebUI Integration

### DigiGraph as a Model (recommended)

DigiGraph exposes an OpenAI-compatible API (`GET /v1/models`, `POST /v1/chat/completions`). Add it as a connection so **Sitaas RAG** appears in the model selector:

1. **Admin Settings → Connections → Add Connection (OpenAI)**
2. Use:

| Setting | Value |
|---------|-------|
| URL | `http://host.docker.internal:8010/v1` |
| API Key | Leave blank or use `not-needed` |

3. If connection verification fails (common for custom endpoints), **manually add the model**: in Model IDs (Filter), add `sitaas-rag` and save.
4. Select **sitaas-rag** in the chat model selector.

**Env var (for Docker deployment):** `OPENAI_API_BASE_URL=http://host.docker.internal:8010/v1`

**Note:** DigiGraph binds to all interfaces (`8010:8000`) so Open WebUI running in Docker can reach it via `host.docker.internal`. When you select Sitaas RAG, every message goes to DigiGraph, which runs the RAG flow (LLM + search) internally.

**Verify from host:**
```bash
# Model list (for Open WebUI discovery)
curl -s http://127.0.0.1:8010/v1/models | jq .

# Which LLM Sitaas RAG actually uses (validate test/medium/best config)
curl -s http://127.0.0.1:8010/v1/model-info | jq .
# With llm_mode: test in config.yaml → {"model":"ollama-cloud/minimax-m2.5:cloud","mode":"test",...}
```

**Tool-call display (streaming):** DigiGraph follows Open WebUI’s **Method 4** (see `digigraph/docs/OPENWEBUI.md` under the “Tool‑Specific Output” section): plain `<details>` (no type) so the dropdown title is under our control. Summary: **🔧 Tool Call: {tool_name}** (e.g. `🔧 Tool Call: digisearch`). Inside: **Query**, **Input** (JSON), **Output** (table). Avoids the generic “Executing…” label that OWU shows for `type="tool_calls"`.
- **Final answer** — Streamed token by token.
Request Open WebUI formatting via connection **header** `X-Response-Format: openwebui`, or use model **sitaas-rag** (same effect), or body `openwebui_format: true`. Without it, DigiGraph streams neutral format (no &lt;details&gt;).

### DigiSearch as a Tool (optional)

To use search with another model (e.g. qwen), connect DigiSearch as a tool:

| Setting | Value |
|---------|-------|
| URL | `http://host.docker.internal:8012` |
| Path | `openapi.json` |

**Env var:**
```bash
TOOL_SERVER_CONNECTIONS='[{"type":"openapi","url":"http://host.docker.internal:8012","spec_type":"url","spec":"","path":"openapi.json","auth_type":"none","key":"","config":{"enable":true},"info":{"id":"digisearch-sitaas","name":"Sitaas Search","description":"Search the document index"}}]'
```

The chat model will have access to `POST /query` and can call it to search, then summarize in one LLM pass.
