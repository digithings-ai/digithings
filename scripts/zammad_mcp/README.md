# zammad_mcp

Read-only MCP server wrapping the Zammad helpdesk REST API for the OCC help
chat (`digithings.ai/chat/occ`). Lightweight demo tooling — v1 exposes ticket
search, retrieval, and a status report. No writes, by design.

## Tools

| Tool | What it does |
|------|--------------|
| `search_tickets(query="", limit=10, state_category=None, since_days=None, until_days=None)` | Zammad ticket search. Plain keywords always work; field syntax (`state.name:open`, `group.name:Sitaas`, `customer.email:<addr>`, `title:<term>`, `article.body:<term>`, AND/OR) only works when the instance has Elasticsearch — without it those queries silently match nothing. `state_category` (`open`\|`closed`\|`pending`) expands to the OR of that category's state names from the cached state types (never the bare `state.name:open` trap). `since_days`/`until_days` restrict `created_at` to a date-only window. When the raw query returns no tickets, the tool retries the extracted keywords one by one (at most 10 terms, all-terms-AND first, merged by id newest-`updated_at` first) and the header says `matched via keywords: ...` |
| `get_ticket(ticket_id)` | One ticket with its articles; takes the internal id (`231`) or the displayed ticket number (`#28312`), and resolves a number through search when the id lookup 404s. Relation names resolved via `expand=true`. Adds best-effort `Owner:` (id resolved to display name via `resolve_user`) and `Category:` (`open`\|`closed`\|`pending` from state types); raw values shown / line omitted when resolution fails |
| `list_tickets(page=1, per_page=50)` | Browse the visible tickets page by page, newest updated first (the Zammad list API is id-ordered; this tool re-sorts by `updated_at`). Use it when keyword search misses: tickets mix German and English and search is a literal substring match, so read titles in their original language and pull threads with `get_ticket`; covers the 500 most recently updated visible tickets |
| `ticket_report(since_days=None, group_by=None)` | Status report over the visible scan (up to 500 tickets): unresolved vs closed, by state/group/priority, updated in the last 7 days by default. `since_days` keeps only tickets updated in the window (client-side filter); `group_by` (`state`\|`group`\|`priority`) appends a top-values section. "Closed" here is the cheap name heuristic (states *named* `closed`/`merged`); for type-derived open/closed counts use `aggregate_tickets` |
| `aggregate_tickets(group_by="customer", metric="count", since_days=None, top_n=5)` | Windowed ranking for analytics questions. `group_by`: `customer`\|`owner`\|`state`\|`group`\|`priority`\|`title`. `metric`: `count`\|`open_count`\|`closed_count`, where open/closed derives from the cached state-type ids (custom open-type states such as `gelöst von Dev` count as open — never the state *named* `open`). Window is `created_at` within `since_days`, fetched in one call (limit 500). Counting/delegation reuses the generic `digisearch.core.tables` ops (`group_count`, `enrich_rows`). Owner logins are UUIDs — names resolve automatically; automation accounts (`jirasync@sitaas.de`, `-`, `auto`) are excluded from owner rankings and footnoted. Customers render masked (see Privacy) |

## Analytics workflows (per question class)

Question classes A (content search), B (resolution), C (statistics) from #4717.
Each row is the tool sequence the model should run; field syntax is concrete.

| Q | Example | Tool calls |
|---|---------|------------|
| A1 | "Which tickets mention <topic>?" | `search_tickets(query="<keywords>")` → keyword fallback if empty → `get_ticket` on the top hits |
| A2 | "What came in about <topic> this week, grouped?" | `search_tickets(query="<keywords>", since_days=7)` → `aggregate_tickets(group_by="title", since_days=7)` title-grouping baseline over the window rows; the model clusters the window rows for the final grouping |
| A3 | "Who reports the most tickets?" | `aggregate_tickets(group_by="customer", metric="count", since_days=30, top_n=5)` |
| A4 | "What did customer <addr> report before?" | `search_tickets(query="customer.email:<addr>")` → latest hit first (client sorts `created_at` desc, `limit=1`) → `get_ticket(<id>)` → read customer + articles |
| A5 | "What happened in ticket #<number>?" | `get_ticket("#<number>")` (or the internal id) → `Owner:` / `Category:` + articles |
| B1 | "How was <problem> fixed?" | Tokenize the question → one `title:<term>` / `article.body:<term>` search per term with `state_category="closed"` (resolved-first) → score each hit with `coverage_score(title + " " + snippet, terms)` → rank by (coverage desc, `updated_at` desc) → `get_ticket` on the top 3–5 → cross-check the `occ_help` docs before answering |
| B2 | "Is <problem> resolved / who solved it?" | Same resolved-first recipe as B1; `Owner:` / `Category:` on the `get_ticket` reads name the solver and confirm the category |
| C1 | "Ticket counts per customer this month?" | `aggregate_tickets(group_by="customer", metric="count", since_days=30, top_n=5)` |
| C2 | "What is still open / how big is the backlog?" | `aggregate_tickets(group_by="<state\|group\|priority>", metric="open_count", since_days=30)` — open from state types, never `state.name:open` |
| C3 | "Who closed the most tickets recently?" | `aggregate_tickets(group_by="owner", metric="closed_count", since_days=30, top_n=5)` — owner names resolved, automation accounts excluded and footnoted |

## Constraints (model and operator notes)

- **Sort whitelist (client-level):** `ZammadClient.search_tickets` accepts `sort_by`/`order_by` only for `created_at`, `updated_at`, `close_at`, `id`, `number` (anything else fails closed). The MCP `search_tickets` tool itself takes no sort params; the A4 customer-history recipe (latest first, `limit=1`) runs at the client/REST layer.
- **Date-only windows:** `since_days`/`until_days` render as `created_at:>=YYYY-MM-DD` / `created_at:<YYYY-MM-DD` day boundaries (UTC), never timestamps. `aggregate_tickets` windows on `created_at`; `ticket_report(since_days=)` filters client-side on `updated_at`.
- **`owner_id` handling:** integer owner ids resolve to `firstname lastname` (fallback: login) via the cached `resolve_user`; non-integer lookups fail closed. In aggregate output, owner UUIDs resolve automatically and unresolvable values fall back to the raw string — one bad owner never fails the ranking.
- **Category semantics:** `state_category` and `Category:` derive from `get_state_types()` (`{lower_name: state_type_id}`, cached, merged over a known-state table when the states endpoint is unreachable). Closed-type = Zammad closed/merged type names; pending = type ids 3/4; everything else is open. Instance custom states classify by type: `gelöst von Dev` is open-type, `warten auf Kunden` / `warten auf Dev` are pending-type. `ticket_report`'s closed count is the cheaper *name* heuristic instead (`closed`/`merged` names only).
- **Automation accounts:** `jirasync@sitaas.de`, `-`, `auto` are excluded from `owner` rankings (pre-filter on raw values, post-filter on resolved names) and listed in the output footnote.
- **Privacy (unchanged):** internal articles omitted (count noted), customer emails masked (`k***@domain`, including inside aggregate output), no article bodies in rankings. Every tool is GET-only and fails closed (`zammad error: ...`, missing token aborts before any HTTP).
- **Caps:** window fetch and report scan cover at most 500 tickets each; keyword fallback uses at most `MAX_KEYWORD_TERMS=10` terms (German + English stopwords dropped).

Every request is a GET. The token only ever leaves this process as the
`Authorization: Token token=<token>` header to `ZAMMAD_BASE_URL`.

## Configuration

| Env | Default | Notes |
|-----|---------|-------|
| `ZAMMAD_BASE_URL` | `https://ticket.sitaas.de` | Zammad root, no `/api/v1` suffix |
| `ZAMMAD_API_TOKEN` | — | Zammad API token — raw value or the full `Token token=<x>` header value; server-side only, never commit or send to a browser |
| `ZAMMAD_MCP_HOST` | `127.0.0.1` | Bind host for streamable HTTP |
| `ZAMMAD_MCP_ALLOWED_HOSTS` | — | Comma-separated Host patterns allowed past FastMCP's DNS-rebinding guard (e.g. `zammad-mcp` for cross-container access; enforced only when the mcp build exposes transport_security — older mcp versions do not) |

```bash
ZAMMAD_API_TOKEN=... python -m scripts.zammad_mcp.server --port 8770
# stdio transport:
ZAMMAD_API_TOKEN=... python -m scripts.zammad_mcp.server --stdio
```

## Wiring into digichat (local dogfood)

The occ tenant entry lives in `apps/digichat/config/examples/occ-embed.yaml`
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
(`apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf`),
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
`url: https://graph.digithings.ai/_stack/mcp/zammad/mcp`, `authHeader:
x-digi-mcp-key`, and a literal `token` holding the `MCP_EDGE_KEY` value
(`tokenEnv` only resolves variables present in the digichat Container's own
environment, and the Worker secret is deliberately not forwarded there); the
server still authenticates to Zammad with its own environment (no Zammad token
in the tenant entry).

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
pytest tests/scripts/test_zammad_mcp.py tests/scripts/test_zammad_mcp_stack.py -v
ruff check scripts/zammad_mcp/
```
