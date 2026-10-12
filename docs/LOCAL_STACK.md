# Local full stack (digikey + services + LiteLLM + digichat)

**This file has moved.** The content is now part of [SELF_HOST.md](SELF_HOST.md), the reference document for self-hosting digithings: modular Compose profiles, macOS and Linux, licence notes, authentication scopes, data seeding, health checks and parity with the hosted Cloudflare variant.

In short: run the backend with `make up` (Docker Compose, the recommended path) or `make stack-local` (host processes, no Docker); both use ports 4000 and 8000–8005 with JWT auth issued by digikey on 8005. That is the whole of it — everything else, including what the self-host plan adds later, is in the linked document.

This stub is kept because the repository, its Makefile, its deployment notes and its 2026-06 audit records all link here by name. It will be removed once those links are updated by the slices that own those files.

## Hostnames + reverse proxy (S4 / DIG-2772)

Prod fronts each backend with its own hostname and, for the MCP servers, its own path.
`make up-edge` runs Caddy in front of compose so local clients can be written against the
prod hostnames instead of `127.0.0.1:8000`-style ports.

Route table: [`infra/local-proxy/Caddyfile`](../infra/local-proxy/Caddyfile). It is derived
from `apps/digithings-stack-cloudflare/src/ports.ts`, `ARCHITECTURE.md` and a grep of the
repo for `<host>.digithings.ai/<path>` — nothing is invented.

| hostname | upstream | prod paths mirrored | profile |
| --- | --- | --- | --- |
| `graph.digithings.localhost` | `digigraph:8000` | `/v1/*`, `/healthz`, `/_stack/meta` | always-on |
| `graph.digithings.localhost/_stack/mcp/digisearch/*` | `digisearch-mcp:8765` | `…/digisearch/mcp` | `core` |
| `graph.digithings.localhost/_stack/mcp/digivault/*` | `digivault-mcp:8769` | `…/digivault/mcp` | `core` |
| `graph.digithings.localhost/_stack/mcp/zammad/*` | `zammad-mcp:8770` | `…/zammad/mcp` | `core` |
| `key.digithings.localhost` | `digikey:8005` | `/v1/admin/keys`, `/v1/oauth/token`, `/healthz` | always-on |
| `search.digithings.localhost` | `digisearch:8002` | `/health`, `/healthz`, `/v1/orchestrator_invoke` | always-on |
| `chat.digithings.localhost` | `digichat:3000` | `/api/health`, `/embed` | `chat` |
| `trace.digithings.localhost` | `digitrace:8003` | `/_langfuse/*`, `/api/public/otel` | `trace` |
| `mcp.digithings.localhost` | — | reserved in prod, route **not enabled** (HUMAN GATE) | returns 404 on purpose |

The three MCP routes use `handle_path`, which strips `/_stack/mcp/<service>` and leaves the
`/mcp` the servers actually expose — so a client written for prod works locally unchanged.

Port: `DT_PROXY_PORT` (default `8088`) to avoid colliding with the 3000-3005 / 8000-8005
service ports. `*.localhost` resolves to loopback on every current browser, so no
`/etc/hosts` edit is needed. Caddy is configured with `auto_https off` and TLS never
terminates locally.

### Service groups

| profile | selects |
| --- | --- |
| `core` | `digivault`, `litellm-cache`, `omniroute` + auth guard, `digisearch-mcp`, `digivault-mcp`, `zammad-mcp` |
| `chat` | `digichat`, `digichat-db` |
| `trace` | `otel-collector` (`digitrace` itself is always-on) |
| `edge` | `proxy` (this reverse proxy) |
| `all` | everything above, plus `heartbeat`, `prometheus`, `grafana` |

```bash
make up-core     # core backends + MCPs
make up-chat     # digichat + its postgres
make up-trace    # otel collector
make up-edge     # the *.digithings.localhost proxy
make up-all      # all of the above
make proxy-validate   # caddy validate the Caddyfile (needs the Docker daemon)
```

**The always-on backends are deliberately not gated.** `digikey`, `digigraph`,
`digisearch`, `digiquant`, `digitrace`, `ollama`, `searxng`, `valkey`, `litellm` and
`digikey-blocklist-redis` carry no `profiles:` key, because ADR-0001 requires the root
compose file and `make up` to stay the zero-config path. A service with a `profiles:` key
is *not* started by a bare `docker compose up`, so adding one to an always-on service would
silently make `make up` — and `make build` — start and build nothing.

`quant` exists for the backtest path (`digivault`, `digiquant-mcp`); digiquant itself
and ollama stay always-on with no `profiles:` key, per the constraint above.

Path B (`make stack-local`, services on the host, no Docker) is unchanged and still the
fastest loop for single-service work.

