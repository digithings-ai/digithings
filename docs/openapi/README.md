# OpenAPI snapshots

Committed OpenAPI 3 documents for digithings HTTP surfaces.

| File | Source |
|------|--------|
| `digikey.json` … `digivault.json` | Generated from FastAPI `app.openapi()` via `make openapi-export` |
| `digichat.json` | Authored BFF contract (Next.js has no FastAPI auto-docs) |

## Commands

```bash
PATH="$PWD/.venv/bin:$PATH" make openapi-export   # regenerate FastAPI specs
PATH="$PWD/.venv/bin:$PATH" make openapi-check    # fail on drift
```

Interactive Swagger UI: `http://127.0.0.1:<port>/docs` on each FastAPI service when the stack is up.

digiclaw has no HTTP OpenAPI (CLI / heartbeat container only).
