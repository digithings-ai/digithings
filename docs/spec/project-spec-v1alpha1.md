# DigiProject Spec — v1alpha1

**Status:** Draft  
**Reference implementation:** `projects/sitaas/` (gitignored; canonical local copy)

---

## Overview

A *DigiProject* is a self-contained deployment of the DigiThings stack customised for a specific use-case (tenant, domain, or product). The project YAML (`config.yaml` or `digiproject.yaml`) is the single source of truth for all runtime tunables that differ from the defaults.

The spec is intentionally minimal for Phase 1: every field is optional, and every default produces a valid (if uncustomised) deployment.

---

## Loading

DigiGraph loads the project config from:

1. `DIGI_PROJECT_CONFIG` env var (absolute path or path relative to the working directory)
2. Fallback: `config/digi_project.yaml` in the working directory
3. If neither exists: all defaults apply

`${ENV_VAR:-default}` substitution is performed in the YAML before parsing (same syntax as Docker Compose).

---

## Schema

```yaml
# digiproject.yaml — v1alpha1
# All fields are optional; defaults shown in comments.

project:
  name: string            # Short identifier, e.g. "sitaas" (default: "default")
  description: string     # Human-readable description (default: "")
  version: string         # SemVer, e.g. "0.1.0" (default: "0.0.0")

agents:
  enabled:                # List of agent IDs to activate (default: ["research"])
    - research            # Only "research" is supported in Phase 1
  llm_mode: string        # "test" | "medium" | "best" (default: env DIGI_LLM_MODE or "test")
  planning_mode: bool     # Enable plan-then-execute flow (default: false)
  workflow_profile: string # Workflow graph profile name (default: "default")
  allowed_tools:          # Restrict tool names available to the research node (default: all)
    - digisearch
    - visualization_agent

  research_system_prompt: |
    # Custom system prompt for the research node.
    # Replaces the default quant-extraction prompt.
    # When set, the node runs in document-mode RAG (tool loop + DigiSearch).
    # When omitted, quant strategy extraction is used.

run_data_dir: string      # Absolute path to session dataset storage (default: null — disables Digistore).
                          # In Docker: mount a named volume here (e.g. /data/run).
                          # When set, enables the sitaas_rag skill:
                          #   digistore_list, digistore_profile, visualization_agent,
                          #   analysis_agent, data_prep_agent, data_manipulation_agent,
                          #   data_engineer_agent (+ DIGI_ALLOW_CODE_EXEC=1 for data_engineer).

indexes_dir: string       # Directory of index *.yaml files (default: null — no indexes).
                          # Each file becomes one DigiSearch index tool.
                          # Path is relative to DIGI_PROJECT_CONFIG's parent directory.

mcp:
  enabled: bool           # Expose an MCP server (default: false)
  port: int               # MCP server port (default: 8765)
  tools:                  # MCP tool names to expose (default: ["digigraph_workflow"])
    - digigraph_workflow

services:
  digisearch_url: string  # DigiSearch base URL (default: env DIGISEARCH_URL)
  litellm_url: string     # LiteLLM / LLM proxy URL (default: env OPENAI_API_BASE)
  digiquant_url: string   # DigiQuant base URL (default: env DIGIQUANT_URL)
```

---

## JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DigiProject v1alpha1",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "project": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "name":        { "type": "string" },
        "description": { "type": "string" },
        "version":     { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+" }
      }
    },
    "agents": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "enabled":               { "type": "array",  "items": { "type": "string" } },
        "llm_mode":              { "type": "string",  "enum": ["test", "medium", "best"] },
        "planning_mode":         { "type": "boolean" },
        "workflow_profile":      { "type": "string" },
        "allowed_tools":         { "type": "array",  "items": { "type": "string" } },
        "research_system_prompt":{ "type": "string" }
      }
    },
    "run_data_dir": { "type": ["string", "null"] },
    "indexes_dir":  { "type": ["string", "null"] },
    "mcp": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "enabled": { "type": "boolean" },
        "port":    { "type": "integer", "minimum": 1, "maximum": 65535 },
        "tools":   { "type": "array", "items": { "type": "string" } }
      }
    },
    "services": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "digisearch_url": { "type": "string", "format": "uri" },
        "litellm_url":    { "type": "string", "format": "uri" },
        "digiquant_url":  { "type": "string", "format": "uri" }
      }
    }
  }
}
```

---

## Environment Variable Contract

| Field | Env override | Notes |
|---|---|---|
| `agents.llm_mode` | `DIGI_LLM_MODE` | Project YAML wins if set |
| `run_data_dir` | `DIGI_RUN_DATA_DIR` | Env wins if set; YAML is fallback |
| `services.digisearch_url` | `DIGISEARCH_URL` | Env wins |
| `services.litellm_url` | `OPENAI_API_BASE` | Env wins |
| `services.digiquant_url` | `DIGIQUANT_URL` | Env wins |
| `mcp.enabled` | — | YAML only |
| `indexes_dir` | — | YAML only |

DigiGraph reads the project config on every request (cached by mtime). No restart required for non-secret field changes.

---

## Enabling / Disabling Paths

| Capability | How to enable | How to disable |
|---|---|---|
| Custom research prompt (document RAG) | Set `agents.research_system_prompt` | Remove field → quant mode |
| Digistore + delegate tools | Set `run_data_dir` | Remove field or set to `null` |
| DigiSearch tool | Set `DIGISEARCH_URL` | Unset env var |
| Code execution (`data_engineer_agent`) | `run_data_dir` + `DIGI_ALLOW_CODE_EXEC=1` | Remove env var |
| MCP server | `mcp.enabled: true` | `mcp.enabled: false` or remove |
| Specific tools only | `agents.allowed_tools: [...]` | Remove field → all tools available |

---

## Migration from Pre-Spec `config.yaml`

Legacy projects used an ad-hoc `config.yaml` shape that predates v1alpha1. Run
`digi project migrate <old-config.yaml>` to convert it to a valid
`digiproject.yaml`. The tool applies the field renames and section-nesting
changes below; unknown top-level keys emit a `UserWarning` to stderr rather than
being silently dropped.

| Legacy path | v1alpha1 path | Notes |
|---|---|---|
| `run_storage.dir` | `run_data_dir` | Other `run_storage.*` subkeys are dropped with a warning. |
| `graph.workflow_profile` | `agents.workflow_profile` | Other `graph.*` subkeys are dropped with a warning. |
| top-level `indexes:` list | — (use `indexes_dir`) | No direct mapping: split each legacy entry into its own file under `indexes_dir`. Dropped with a warning. |
| `project`, `agents`, `mcp`, `services`, `run_data_dir`, `indexes_dir` | unchanged | Passthrough sections are copied verbatim. |

The migrated file is re-validated against the v1alpha1 JSON Schema before it is
written — if validation fails, the migration aborts without touching the
destination.

---

## Versioning Policy

- **v1alpha1** (current): schema is unstable; breaking changes possible without notice.
- **v1beta1** (planned): backwards compatibility within minor; breaking changes require new `version` field.
- **v1** (future): stable; additive changes only; removals via deprecation cycle.

`DigiProjectConfig` will emit a warning when loading a file that declares an unsupported version.

---

## Rendering Story

**Phase 1 (current):** Project configs are hand-authored YAML. Docker Compose files in each project directory reference the YAML via `DIGI_PROJECT_CONFIG`. No tooling generates compose files.

**Phase 2 (planned):** `digi project render` CLI command reads `digiproject.yaml` and emits a `docker-compose.override.yml` with the correct env vars, volume mounts, and port bindings. Tracked in the agent backlog.

---

## Reference: SITAAS v1alpha1

```yaml
# projects/sitaas/config.yaml (gitignored — local only)
project:
  name: sitas
  description: "Sitaas: orchestration agent with DigiSearch document context."
  version: "0.1.0"

agents:
  enabled: [research]
  llm_mode: test
  research_system_prompt: |
    You are an exploration assistant over a unified content index ...

run_data_dir: /data/run
indexes_dir: indexes

mcp:
  enabled: true
  port: 8765
  tools: [digigraph_workflow]

services:
  digisearch_url: ${DIGISEARCH_URL:-http://digisearch:8002}
  litellm_url: ${OPENAI_API_BASE:-http://litellm:4000/v1}
```

This config activates:
- Custom research prompt (document RAG mode)
- Digistore + delegate agent tools (via `run_data_dir`)
- Multi-index discovery (via `indexes_dir`)
- MCP server

See `digigraph/AGENTS.md` → SITAAS / Project-Mode Capabilities for the full tool set table.
