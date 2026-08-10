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

## Public explorer (digithings.ai)

Interactive docs on the marketing site (Cloudflare Pages static export):

| Route | Purpose |
|-------|---------|
| [/docs/api](https://digithings.ai/docs/api/) | Index of all published specs |
| [/docs/api/&lt;service&gt;](https://digithings.ai/docs/api/digigraph/) | Swagger UI for one service |
| `/openapi/&lt;service&gt;.json` | Same-origin JSON (copied at site prebuild) |

Source of truth is this directory — not live FastAPI `/docs` on localhost. The site build (`scripts/build-digithings.sh` → digithings-web `prebuild`) syncs JSON into `public/openapi/` and vendors `swagger-ui-dist` under `public/swagger-ui/`. Private/loopback `servers` entries are stripped from the public copies.

Local FastAPI Swagger remains available when the stack is up: `http://127.0.0.1:<port>/docs`.

digiclaw has no HTTP OpenAPI (CLI / heartbeat container only).
