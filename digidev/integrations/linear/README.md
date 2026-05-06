# Linear integration

Linear is a modern issue tracker built for engineering teams. If your team uses Linear, digidev can read and create issues, manage cycles, and dispatch tasks through Linear's official hosted MCP endpoint.

---

## What it enables

- `spec-writer` creates Linear issues with proper labels
- `make status` lists your Linear backlog
- `make new-task` opens Linear issues
- Agents read acceptance criteria from Linear issue descriptions
- Issue status updates when branches are pushed

---

## Setup

Linear offers a **hosted SSE MCP endpoint** — no npm package to install, no server to run locally.

### 1. Add the Linear MCP server via SSE

```bash
claude mcp add --transport sse linear https://mcp.linear.app/sse
```

This opens a browser window to complete the OAuth flow with your Linear account. No API key needed.

### 2. Add to `.mcp.json` (for team-wide config)

```json
{
  "mcpServers": {
    "linear": {
      "type": "sse",
      "url": "https://mcp.linear.app/sse"
    }
  }
}
```

Note: each team member must authenticate separately via OAuth (`claude mcp add --transport sse linear https://mcp.linear.app/sse`). The URL in `.mcp.json` is shared; the OAuth token is stored per-user in `~/.claude/`.

### 3. Configure agents.yml

```yaml
issue_tracker: linear

linear:
  team_id: "your-team-id"           # from Linear team settings URL
  agent_task_label: "agent-task"    # Linear label name
  project_id: ""                    # optional: Linear project ID
```

### 4. Create Linear labels

Create these labels in your Linear workspace (`Settings → Labels`):
- `agent-task`
- `exec:copilot`
- `exec:cursor`
- `exec:claude`
- `risk:low`, `risk:med`, `risk:high`
- One label per component (e.g., `component:api`)

---

## How the three-tier model works with Linear

| Tier | How to dispatch |
|---|---|
| `exec:copilot` | Label issue `exec:copilot` — use Linear Webhooks + GitHub Actions to assign |
| `exec:cursor` | Label issue `exec:cursor` — developer opens in Cursor, runs `/task` |
| `exec:claude` | Label issue `exec:claude` — developer runs `make task ISSUE=<linear-id>` |

`run_task.sh` will use the Linear MCP to fetch the issue title when `issue_tracker: linear` is set in `agents.yml`.

---

## MCP config snippet

```json
{
  "mcpServers": {
    "linear": {
      "type": "sse",
      "url": "https://mcp.linear.app/sse"
    }
  }
}
```

Each developer authenticates once:
```bash
claude mcp add --transport sse linear https://mcp.linear.app/sse
```
