# digivault – Agent guide

## Purpose

digivault manages an Obsidian-style markdown vault: frontmatter, `[[wikilinks]]`,
backlinks, tags, and folder taxonomy. A pure-Python core library plus a thin
FastAPI + MCP + CLI service layer. First consumer: the project documentation
(`docs/vision/`).

## Read first

1. `digivault/ARCHITECTURE.md` — module map, public API, design decisions.
2. Root `AGENTS.md` — stack-wide non-negotiables (`CLAUDE.md` is a pointer).
3. `digifetch/ARCHITECTURE.md` — the library-conventions reference this mirrors.

## Pre-flight checklist

- [ ] `import digivault` stays FastAPI-free (core depends only on `pydantic` + `pyyaml`).
- [ ] New result data is a Pydantic v2 model in `models.py`, not a bare dict.
- [ ] Any new write path goes through `Vault._safe_path` (no traversal escapes).
- [ ] `frontmatter.split(frontmatter.dump(fm, body)) == (fm, body)` still holds.
- [ ] Wikilink rewrites skip code spans/blocks (use the helpers in `wikilinks.py`).
- [ ] Service routes carry the right scope in `path_scopes.py` (read vs write).
- [ ] New vault tools register in `tool_dispatch.py` only (see [Adding a vault tool](#adding-a-vault-tool)).

## Adding a vault tool

All digivault tool names and vault-local handlers live in `tool_dispatch.py`.
Do **not** add a second `@mcp.tool` in `mcp_server.py` or a parallel if/elif in
`server.orchestrator_invoke` — both surfaces already route through
`dispatch_vault_tool` / `register_mcp_tools`.

1. Add a `TOOL_VAULT_*` constant and put the name in `DISPATCH_TOOL_NAMES`
   (and either `VAULT_TOOL_NAMES` or `RUNTIME_ONLY_TOOL_NAMES`).
2. **Vault-local (filesystem / `Vault`):** implement a handler, add it to
   `VAULT_HANDLERS`, and extend `register_mcp_tools` so MCP discovery stays equal
   to `mcp_tool_names()`. `orchestrator_invoke` picks it up automatically.
3. **Runtime-only (D1 / tenant / HTTPException):** implement the body in
   `server.py`’s `orchestrator_invoke`, then `register_runtime_handler(name, …)`
   so `dispatch_tool_names()` still equals `DISPATCH_TOOL_NAMES`.
4. Add the OpenAI-style schema/description in `orchestrator_tools.build_orchestrator_tool_manifest`
   (names are re-exported from `tool_dispatch` — do not redefine string literals).
5. Add/extend tests in `tests/dv/test_tool_dispatch.py` (every tool name must
   dispatch) and any server invoke tests the behaviour needs.
6. Update this file and `ARCHITECTURE.md` (tool dispatch diagram) if the
   vault-local vs runtime-only split changes.

## Non-negotiable rules

- Do **not** import or modify `digikey` internals — reuse `DigiAuthMiddleware`
  and define scope policy locally in `path_scopes.py`.
- `/healthz` stays auth-exempt, secret-free, `{"ok": true}`, no downstream checks.
- No new hard dependency on the core library without a human gate; service-only
  deps belong in the `[service]` extra.

## Anti-patterns

- ❌ Importing `fastapi` from `digivault/__init__.py`, `vault.py`, `frontmatter.py`, or `wikilinks.py`.
- ❌ Returning dicts from `Vault` methods (use the models).
- ❌ Regex-rewriting wikilinks without masking code regions (breaks examples in docs).
- ❌ Adding standard Markdown link validation (the `[label]` + `(target)` inline form) here — that is `scripts/check_doc_links.py`'s job; digivault validates `[[wikilinks]]`.
- ❌ Hand-registering `@mcp.tool` handlers in `mcp_server.py` or duplicating vault tool if/elif branches in `server.py` — use `tool_dispatch.py` (#1188).

## Test commands

```bash
# Core only (pydantic + pyyaml):
pip install -e ./digivault && pytest tests/dv -m unit

# Full (service + cli):
pip install -e ./digibase -e ./digikey -e "./digivault[service,dev]"
pytest tests/dv -m unit
ruff check digivault/src tests/dv && ruff format --check digivault/src tests/dv

# Import-cost guard (must not pull FastAPI):
python -c "import sys, digivault; assert 'fastapi' not in sys.modules"
```
