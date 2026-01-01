# PostgreSQL integration

Connect agents to any PostgreSQL database (including Supabase, Neon, PlanetScale-compatible, RDS) for schema introspection and query review.

---

## Setup

```bash
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres \
  "${DATABASE_URL}"
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "postgres": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres",
               "${DATABASE_URL}"]
    }
  }
}
```

Set `DATABASE_URL` in your environment:
```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/mydb
```

---

## agents.yml

```yaml
database: postgres
postgres:
  connection_string: "${DATABASE_URL}"
```

---

## Security

- Use a **read-only** connection for the MCP server where possible.
- For staging/dev environments only — never connect to production from local Claude Code sessions.
- The `SECURITY.md` rubric checks for raw SQL built with string concatenation; the Postgres MCP helps agents verify parameterisation is correct.
