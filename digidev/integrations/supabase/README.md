# Supabase integration

The Supabase MCP server lets agents introspect your database schema, run migrations, and check logs — directly in Claude Code without switching context.

---

## What it enables

- Agents can read your table schema to generate accurate migrations
- `make score` can check database query patterns in staged diffs
- Agents can verify migration safety before applying
- Edge Function logs accessible during CI triage

---

## Setup

### 1. Install the Supabase MCP server

```bash
claude mcp add supabase -- npx -y @supabase/mcp-server-supabase \
  --access-token $SUPABASE_ACCESS_TOKEN
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server-supabase",
               "--access-token", "${SUPABASE_ACCESS_TOKEN}"]
    }
  }
}
```

### 2. Get your access token

```bash
# Option A: personal access token (for local dev)
# Go to: https://supabase.com/dashboard/account/tokens
export SUPABASE_ACCESS_TOKEN=sbp_...

# Option B: service role key (for specific project)
export SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

### 3. Configure agents.yml

```yaml
database: supabase

supabase:
  project_ref: "abcdefghijklmno"     # your project ref from dashboard URL
  region: "us-east-1"
```

---

## What agents can do with the Supabase MCP

Once configured, Claude Code can:

```
"Show me the schema for the users table"
→ reads table definition directly from your DB

"Is this migration safe to run?"
→ checks for destructive operations, missing rollback, lock issues

"Check the edge function logs for errors"
→ reads logs from Supabase dashboard

"Generate TypeScript types for my schema"
→ runs supabase gen types typescript --project-id ...
```

---

## Using plain PostgreSQL instead?

```bash
claude mcp add postgres -- npx -y @modelcontextprotocol/server-postgres \
  postgresql://user:password@localhost/dbname
```

`agents.yml`:
```yaml
database: postgres
postgres:
  connection_string: "${DATABASE_URL}"
```

---

## MCP config snippet

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": [
        "-y",
        "@supabase/mcp-server-supabase",
        "--access-token",
        "${SUPABASE_ACCESS_TOKEN}"
      ]
    }
  }
}
```

---

## Security note

Never commit `SUPABASE_ACCESS_TOKEN` or `SUPABASE_SERVICE_ROLE_KEY` to source control. Add to `.gitignore`:

```
.env
.env.local
.claude/.env
```

The digidev `network-host-guard.sh` hook already blocks outbound calls to non-allowlisted hosts. Add `supabase.com` and `supabase.io` to your `allowed_hosts` in `digidev.yml` if needed.
