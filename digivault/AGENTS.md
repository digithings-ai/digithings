# DigiVault – Agent guide

## Purpose

DigiVault manages an Obsidian-style markdown vault: frontmatter, `[[wikilinks]]`,
backlinks, tags, and folder taxonomy. A pure-Python core library plus a thin
FastAPI + MCP + CLI service layer. First consumer: the project documentation
(`docs/vision/`).

## Read first

1. `digivault/ARCHITECTURE.md` — module map, public API, design decisions.
2. Root `AGENTS.md` and `CLAUDE.md` — stack-wide non-negotiables.
3. `digifetch/ARCHITECTURE.md` — the library-conventions reference this mirrors.

## Pre-flight checklist

- [ ] `import digivault` stays FastAPI-free (core depends only on `pydantic` + `pyyaml`).
- [ ] New result data is a Pydantic v2 model in `models.py`, not a bare dict.
- [ ] Any new write path goes through `Vault._safe_path` (no traversal escapes).
- [ ] `frontmatter.split(frontmatter.dump(fm, body)) == (fm, body)` still holds.
- [ ] Wikilink rewrites skip code spans/blocks (use the helpers in `wikilinks.py`).
- [ ] Service routes carry the right scope in `path_scopes.py` (read vs write).

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
- ❌ Adding standard Markdown link validation (the `[label]` + `(target)` inline form) here — that is `scripts/check_doc_links.py`'s job; DigiVault validates `[[wikilinks]]`.

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
