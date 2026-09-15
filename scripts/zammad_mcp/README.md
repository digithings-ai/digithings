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
| `ZAMMAD_MCP_ALLOWED_HOSTS` | — | Comma-separated Host patterns allowed past FastMCP's DNS-rebinding guard (e.g. `zammad-mcp` for cross-container access; protection stays on) |

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

Production hosting (public hostname vs. dedicated container) is a later,
owner-gated decision.

## Privacy & exposure

The OCC embed is anonymous and ungated, so the formatters are conservative:

- internal articles (`internal: true`) are not returned — `get_ticket` notes how many were omitted
- customer emails are masked (`k***@domain`)

The MCP endpoint itself is unauthenticated: `tokenEnv` / `authHeader` carry the
Zammad token outbound to Zammad, they are not an auth boundary for the MCP port.
Keep it on loopback or the compose network; do not publish the port until an
auth layer exists.

## Tests

```bash
pytest tests/scripts/test_zammad_mcp.py -v
ruff check scripts/zammad_mcp/
```
