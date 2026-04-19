# SITAAS

SITAAS is a DigiThings Project that deploys the orchestration agent in
document-RAG mode with run storage, the full `sitaas_rag` delegate-agent
tool suite, and multi-index DigiSearch discovery.

## Convention note

Canonical project configs live under `projects/<name>/` (gitignored for
confidentiality). This public mirror lives under `docs/projects/sitaas/` so
it can be tracked without carving a `.gitignore` exception. At runtime a
deploy may symlink or copy this directory into `projects/sitaas/`. The actual
operator copy at `projects/sitaas/config.yaml` should be migrated to
`digiproject.yaml` (see Migration below).

## Stack requirements

| Service | Env var | Default |
|---|---|---|
| DigiGraph | — | port 8000 |
| DigiSearch | `DIGISEARCH_URL` | `http://digisearch:8002` |
| LiteLLM / LLM proxy | `OPENAI_API_BASE` | `http://litellm:4000/v1` |
| DigiQuant (optional) | `DIGIQUANT_URL` | `http://digiquant:8001` |

Run storage must be mounted at `run_data_dir` (default `/data/run`). Override
with `DIGI_RUN_DATA_DIR`.

## Quick start

```bash
cp docs/projects/sitaas/digiproject.yaml projects/sitaas/digiproject.yaml
# Edit digiproject.yaml (service URLs, LLM mode, indexes)
export DIGI_PROJECT_CONFIG=projects/sitaas/digiproject.yaml
docker compose up
```

Or with Docker Compose volumes:

```yaml
# docker-compose.override.yml
services:
  digigraph:
    environment:
      DIGI_PROJECT_CONFIG: /app/digiproject.yaml
      DIGI_RUN_DATA_DIR: /data/run
      DIGI_CHECKPOINTER: postgres       # memory | sqlite | postgres
      DIGI_ALLOW_CODE_EXEC: "1"         # enables data_engineer_agent
    volumes:
      - ./projects/sitaas/digiproject.yaml:/app/digiproject.yaml:ro
      - sitaas_run:/data/run
volumes:
  sitaas_run:
```

## Tool set

When `run_data_dir` is set, DigiGraph activates the `sitaas_rag` skill in
addition to the base `search` skill. All tools listed below are available to
the research node.

| Tool | Skill | Condition | Description |
|---|---|---|---|
| `digisearch` | search | `DIGISEARCH_URL` set | Semantic/keyword search over indexed documents |
| `digisearch_fetch_all` | search | `DIGISEARCH_URL` set | Paginated full-result fetch with filters |
| `digistore_list` | sitaas_rag | `run_data_dir` set | List named datasets from the current session |
| `digistore_profile` | sitaas_rag | `run_data_dir` set | Inspect schema, row count, and sample rows of a dataset |
| `visualization_agent` | sitaas_rag | `run_data_dir` set | Generate charts (ECharts JSON or PNG) from a `dataset_ref` |
| `analysis_agent` | sitaas_rag | `run_data_dir` set | Statistical summaries, correlations, histograms |
| `data_prep_agent` | sitaas_rag | `run_data_dir` set | Filter, sample, sort, export a dataset |
| `data_manipulation_agent` | sitaas_rag | `run_data_dir` set | Merge, join, reshape, or transform datasets |
| `data_engineer_agent` | sitaas_rag | `run_data_dir` set + `DIGI_ALLOW_CODE_EXEC=1` | Execute sandboxed Polars code for custom transformations |

`agents.allowed_tools` in `digiproject.yaml` can restrict the active set to a
named subset; remove the field to allow all tools.

## ECharts rendering

`visualization_agent` returns ECharts option JSON when the request includes
`X-Response-Format: openwebui` or uses the `sitaas-rag` model endpoint.
Without this header, it falls back to a PNG path. The frontend must handle the
`echarts_option` key in the tool result to render the chart inline.

## Multi-turn dataset context

When `stored_datasets` is in graph state the research node prepends a
`[Current session datasets: ...]` context block to the user message so the
LLM can reference previous search results by `dataset_ref` (e.g. "chart
search_1").

## Checkpointer

Dataset context is persisted across turns when `DIGI_CHECKPOINTER` is set.

| Value | Behaviour |
|---|---|
| `memory` (default) | In-process only; lost on restart |
| `sqlite` | Persisted to a local SQLite file |
| `postgres` | Recommended for production; persisted across restarts |

Set via environment variable: `DIGI_CHECKPOINTER=postgres`.

## Indexes

Place one `*.yaml` index manifest per DigiSearch index under `indexes/`. Each
file is discovered automatically via `indexes_dir`. Example manifest shape:

```yaml
index_name: my-index
backend: azure_search
description: "Optional human-readable description."
sources:
  - "docs/**/*.md"
```

A placeholder `indexes/.keep` file is included to preserve the directory in
version control.

## Migration from legacy config.yaml

If your operator copy uses the legacy `config.yaml` name or pre-v1alpha1
field layout, run:

```bash
digi project migrate projects/sitaas/config.yaml
```

See `docs/spec/project-spec-v1alpha1.md` for the full field rename table.

## Related

- Spec: [`docs/spec/project-spec-v1alpha1.md`](../../spec/project-spec-v1alpha1.md)
- Template: [`docs/templates/project/`](../../templates/project/)
- Project-mode capabilities: [`digigraph/AGENTS.md`](../../../digigraph/AGENTS.md) — SITAAS / Project-Mode Capabilities section
- Epic: [#14](https://github.com/digithings-ai/digithings/issues/14)
- Issue: [#27](https://github.com/digithings-ai/digithings/issues/27)
