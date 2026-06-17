# digidev integrations

digidev layers agentic workflow structure **on top of the tools you already use**. It does not replace your issue tracker, communication platform, or database — it wires them together.

Every integration here is an **off-the-shelf MCP server** (Model Context Protocol). You install the server once, add it to Claude Code's MCP config, and your agents can read/write your existing tools directly from the editor.

---

## Which integrations should I set up?

Answer these questions — then follow the guide for each tool you use:

| Question | Guide |
|---|---|
| Git platform? | [github/](github/) · [gitlab/](gitlab/) |
| Issue / task tracker? | [github/](github/) · [jira/](jira/) · [linear/](linear/) · [notion/](notion/) |
| Team communication? | [slack/](slack/) |
| Database? | [supabase/](supabase/) · [postgres/](postgres/) |

You don't need all of them. Set up only what your team uses.

---

## How MCP integrations work with digidev

```
Your tool (Jira / Slack / Supabase / …)
       ↑
  MCP server (runs locally, speaks MCP protocol)
       ↑
  Claude Code (reads/writes your tools via MCP)
       ↑
  digidev agents + skills (structured workflows on top)
```

The digidev agents (spec-writer, component-router, etc.) automatically use MCP tools when available. For example:

- `spec-writer` creates issues in GitHub **or** Jira **or** Linear, depending on which MCP server is active.
- `ci-triage` reads GitHub Actions logs via the GitHub MCP server.
- `finish-task` posts a Slack message when a PR is opened (if Slack MCP is configured).

---

## Adding MCP servers to Claude Code

Each integration folder contains a `mcp-config.json` snippet. Add the server block to your Claude Code MCP config:

**Project-level** (`.mcp.json` in repo root — shared with team):
```json
{
  "mcpServers": {
    "github": { ... }
  }
}
```

**User-level** (`~/.claude/mcp_settings.json` or via `claude mcp add`):
```bash
claude mcp add <server-name> -- <command> [args]
```

Claude Code's MCP documentation: https://docs.anthropic.com/en/docs/claude-code/mcp

---

## Generating your MCP config automatically

The digidev installer can generate a ready-to-use `.mcp.json` for you:

```bash
bash digidev/install.sh --setup-mcp
```

It will ask which tools you use and output the combined config.

---

## Available integrations

| Folder | Tool | MCP server | Notes |
|---|---|---|---|
| [github/](github/) | GitHub Issues, PRs, Actions | `ghcr.io/github/github-mcp-server` (Docker) | Official GitHub binary |
| [gitlab/](gitlab/) | GitLab MRs, Issues, Pipelines | `@modelcontextprotocol/server-gitlab` | npm |
| [jira/](jira/) | Jira issues, sprints | `mcp-atlassian` (Python — `uvx`) | Community Python package |
| [linear/](linear/) | Linear issues, cycles | `https://mcp.linear.app/sse` (SSE) | Official hosted endpoint, OAuth |
| [slack/](slack/) | Slack messages, channels | `@modelcontextprotocol/server-slack` | npm |
| [notion/](notion/) | Notion pages, databases | `@notionhq/notion-mcp-server` | npm |
| [supabase/](supabase/) | Supabase DB, Edge Functions | `@supabase/mcp-server-supabase` | npm |
| [postgres/](postgres/) | Any PostgreSQL database | `@modelcontextprotocol/server-postgres` | npm |
