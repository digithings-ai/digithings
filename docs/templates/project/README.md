# Project Template

Starter for a new DigiThings project. Copy this directory to `projects/<your-project>/` and customise.

## Quick start

```bash
cp -r docs/templates/project projects/my-project
cd projects/my-project
cp .env.example .env
# Edit digiproject.yaml and .env for your use-case
docker compose -f ../../docker-compose.yml -f docker-compose.yml up
```

## Files

| File | Purpose |
|---|---|
| `digiproject.yaml` | Project config (agents, indexes, MCP, services). All fields optional. |
| `docker-compose.yml` | Compose override — mounts `digiproject.yaml` into digigraph. |
| `.env.example` | Required env vars. Copy to `.env` and fill values. |

## Capabilities

Enable capabilities by setting fields in `digiproject.yaml`:

| Capability | How to enable |
|---|---|
| Custom research prompt (document RAG) | Set `agents.research_system_prompt` |
| Digistore + delegate tools | Set `run_data_dir` |
| DigiSearch tool | Set `DIGISEARCH_URL` env var |
| Multi-index discovery | Set `indexes_dir` pointing to a directory of `*.yaml` index files |
| MCP server | `mcp.enabled: true` |
| Restrict available tools | `agents.allowed_tools: [...]` |

See `docs/spec/project-spec-v1alpha1.md` for the full schema and environment variable contract.

## Notes

- `projects/` is gitignored — project configs are local-only (never push to public remotes).
- `.env` is gitignored — never commit secrets.
- Rename `digiproject.yaml` from `config.yaml` if migrating from the legacy filename (digigraph will warn and still load it).
