---
type: quickstart
title: digivault Quickstart
description: Use the digivault CLI and core Vault API, verify the FastAPI-free import, and run the test gates.
tags: [digivault, quickstart]
sources:
  - id: openwiki-source-a18bc9b1229d0282f121b666
    resource: repo://digivault/AGENTS.md
  - id: openwiki-source-177aa6b06017b843d46bc98a
    resource: repo://digivault/ARCHITECTURE.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digivault Quickstart

digivault (port 8004, dedicated Compose profile) works as a pure library
first — try the core without any service running.

## 1. Core API

```python
from digivault import Vault

vault = Vault("docs/vision")
vault.list_notes()
vault.backlinks("digigraph")
vault.search_by_tag("module")
vault.create_note("execution", frontmatter={"title": "execution"}, body="see [[digiquant]]")
vault.lint()
```

```bash
digivault init|lint|reindex|new-note
```

## 2. Verify

```bash
pip install -e ./digivault && pytest tests/dv -m unit
python -c "import sys, digivault; assert 'fastapi' not in sys.modules"
```

Full service tests add the service extra:
`pip install -e ./digibase -e ./digikey -e "./digivault[service,dev]"`,
then `ruff check digivault/src tests/dv && ruff format --check
digivault/src tests/dv`.

## Where next

- [digivault Architecture](/openwiki/digivault/architecture.md) — core
  vs service, module map, store precedence.
- [digivault Notes and Links](/openwiki/digivault/notes-and-links.md) —
  frontmatter, wikilinks, maintenance ops.
- [digivault Service and Operations](/openwiki/digivault/service-and-operations.md) —
  HTTP/MCP/CLI, scopes, container.
