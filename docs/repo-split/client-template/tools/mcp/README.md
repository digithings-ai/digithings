# tools/mcp

One folder per client-owned MCP server (`tools/mcp/<server>/`), with its own
Dockerfile or `wrangler.toml`. Deployed Workers are named `client-<client-slug>-*` (the repo is `digithings-ai/<client-slug>`) and are
reached from the shared stack by URL plus an edge key (name in `tenant/env/*.yaml`).
Generic MCP servers belong in R0, not here.
