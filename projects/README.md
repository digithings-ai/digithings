# Per-Project Deployments

Each project lives in its own folder with config, env, and a self-contained Docker stack. All services and secrets stay within that project.

## Structure

```
projects/<name>/
├── config.yaml       # Project config (agents, indexes, MCP)
├── indexes/          # Index definitions (schema, field mapping per index)
│   └── <index>.yaml
├── .env.example      # Env var template
├── .env              # Connection only: endpoint, api_key (gitignored)
├── docker-compose.yml
└── README.md
```

**Index config**: Each index has a YAML file with `index_name`, `field_mapping`, and `schema` (column descriptions). Connection credentials stay in `.env`.

**Skills**: Optional `skills.enabled` in project config (e.g. `config.yaml` or the file pointed to by `DIGI_PROJECT_CONFIG`) sets which skill bundles the research node can use. Default is `["search", "sitaas_rag"]`. Use `["search"]` for search-only (no delegate agents), or keep both for full RAG with visualization/analysis/data agents when `run_data_dir` is set.

**Plan-and-execute**: Set `agents.planning_mode: true` in project config to enable the executor. When the LLM calls the `create_plan` tool with a structured plan (steps with id, agent, args, depends_on), the executor runs steps in dependency order and in parallel when independent, then a synthesis turn summarizes results. Use placeholders like `{{1.dataset_ref}}` in step args to reference prior step outputs.

**Ports**: Each project uses its own host ports (e.g. Sitaas: 8010, 8012, 4010) to avoid conflicts with the default stack (8000, 8002, 4000). Override via `DIGIGRAPH_PORT`, `DIGISEARCH_PORT`, `LITELLM_PORT` in `.env`.

## Usage

```bash
cd projects/<name>
cp .env.example .env
# Edit .env with your credentials
docker compose up --build
```

## Projects

| Project | Description |
|---------|-------------|
| `local/` | **Local dev / testing.** Basic chat via local Ollama. No external deps. Start here. |
| `sitaas/` | Orchestration + DigiSearch (Azure). No DigiQuant. |

## Security

- `.env` is gitignored per project
- No project config in shared `config/` folder
- Each project is self-contained for deployment
