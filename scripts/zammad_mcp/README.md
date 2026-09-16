# zammad_mcp

Read-only MCP server wrapping the Zammad helpdesk REST API for the OCC help
chat (`digithings.ai/chat/occ`). Lightweight demo tooling — v1 exposes ticket
search, retrieval, and a status report. No writes, by design.

## Tools

| Tool | What it does |
|------|--------------|
| `search_tickets(query, limit=10)` | Zammad ticket search (e.g. `state.name:open`, `group.name:Sitaas`) |
| `get_ticket(ticket_id)` | One ticket with its articles; relation names resolved via `expand=true` |
| `ticket_report()` | Status report across all visible tickets: unresolved vs closed, by state/group/priority, updated in the last 7 days |

Every request is a GET. The token only ever leaves this process as the
`Authorization: Token token=<token>` header to `ZAMMAD_BASE_URL`.

## Configuration

| Env | Default | Notes |
|-----|---------|-------|
| `ZAMMAD_BASE_URL` | `https://ticket.sitaas.de` | Zammad root, no `/api/v1` suffix |
| `ZAMMAD_API_TOKEN` | — | Zammad API token — raw value or the full `Token token=<x>` header value; server-side only, never commit or send to a browser |
| `ZAMMAD_MCP_HOST` | `127.0.0.1` | Bind host for streamable HTTP |
| `ZAMMAD_MCP_ALLOWED_HOSTS` | — | Comma-separated Host patterns allowed past FastMCP's DNS-rebinding guard (e.g. `zammad-mcp` for cross-container access; enforced only when the mcp build exposes transport_security — the 1.9.x stack image does not) |

```bash
ZAMMAD_API_TOKEN=... python -m scripts.zammad_mcp.server --port 8770
# stdio transport:
ZAMMAD_API_TOKEN=... python -m scripts.zammad_mcp.server --stdio
```

## Wiring into digichat (local dogfood)

The occ tenant entry lives in `cloudflare/digichat/config/examples/occ-embed.yaml`
(`mcp.servers`). The URL stays on the BFF and never reaches the browser;
Zammad's `Token token=<x>` scheme rides as the raw value under `Authorization`
(the `authHeader` behavior from #3841). `tokenEnv` is resolved from the digichat
container environment at load time, so `ZAMMAD_API_TOKEN` must hold the **full
header value** (`Token token=<x>`) — the same variable this server reads, where
both the raw token and the prefixed form are accepted.

```yaml
mcp:
  allowUserServers: false
  allowAddForm: false
  servers:
    - id: zammad
      url: http://zammad-mcp:8770/mcp
      label: Zammad tickets
      default: true
      tokenEnv: ZAMMAD_API_TOKEN
      authHeader: Authorization
```

Local dogfood (compose, from the worktree root):

```bash
# .env additions (untracked)
#   ZAMMAD_API_TOKEN=Token token=<raw token>
#   DIGICHAT_CONFIG_PATH=/app/config/examples/occ-embed.yaml
docker compose --profile digichat --profile zammad-mcp up -d --build
# then open http://127.0.0.1:3005/embed?host=occ.digithings.ai&layout=page
```

The compose service name `zammad-mcp` is dotless, so digigraph's remote-MCP
guard treats it as container-internal DNS; loopback URLs are never dialable
(`orchestration/mcp_client.py`, #3879).

### Production (digithings-stack container)

In production the server is **not** a separate container: it runs as the
`zammad-mcp` program inside the `digithings-stack` Cloudflare Container
(`cloudflare/digithings-stack-cloudflare/container/supervisor/supervisord.conf`),
bound to `0.0.0.0:8770`. The image ships the package (`COPY scripts/zammad_mcp`
in `Dockerfile.digithings-stack-cloudflare`) and the entrypoint aliases the
dotless name `zammad-mcp` to the container's own address in `/etc/hosts`, so
digigraph's remote-MCP guard can dial `http://zammad-mcp:8770/mcp` (dotless
names may resolve to private space; loopback is never dialable, #3879). Set the
token on the stack worker only — `wrangler secret put ZAMMAD_API_TOKEN` — with
the same `Token token=<x>` value. The MCP port is not published publicly; its
only external path is the key-gated route
`https://graph.digithings.ai/_stack/mcp/zammad/*` (the Worker checks
`x-digi-mcp-key` against the `MCP_EDGE_KEY` secret and fails closed with a 401).
The prod occ tenant entry in `DIGICHAT_EMBED_TENANTS` therefore carries
`url: https://graph.digithings.ai/_stack/mcp/zammad/mcp` with
`tokenEnv: MCP_EDGE_KEY` and `authHeader: x-digi-mcp-key`; the server still
authenticates to Zammad with its own environment (no Zammad token in the tenant
entry).

## Privacy & exposure

The OCC embed is anonymous and ungated, so the formatters are conservative:

- internal articles (`internal: true`) are not returned — `get_ticket` notes how many were omitted
- customer emails are masked (`k***@domain`)

The MCP transport itself carries no auth of its own: `tokenEnv` / `authHeader`
carry the Zammad token outbound to Zammad, they are not an auth boundary for the
MCP port. On the Cloudflare stack the only external ingress is the key-gated
worker route (`x-digi-mcp-key` vs `MCP_EDGE_KEY`, fail-closed 401); the
container port stays unpublished. Compose deployments keep it on loopback or
the compose network.

## Tests

```bash
pytest tests/scripts/test_zammad_mcp.py -v
ruff check scripts/zammad_mcp/
```
