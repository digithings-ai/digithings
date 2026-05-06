# Linear integration

Linear is a modern issue tracker built for engineering teams. If your team uses Linear, digidev can read and create issues, manage cycles, and dispatch tasks through the official Linear MCP server.

---

## What it enables

- `spec-writer` creates Linear issues with proper labels
- `make status` lists your Linear backlog
- `make new-task` opens Linear issues
- Agents read acceptance criteria from Linear issue descriptions
- Issue status updates when branches are pushed

---

## Setup

### 1. Install the Linear MCP server

```bash
claude mcp add linear -- npx -y @linear/mcp-server
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["-y", "@linear/mcp-server"],
      "env": {
        "LINEAR_API_KEY": "${LINEAR_API_KEY}"
      }
    }
  }
}
```

### 2. Create an API key

1. Go to: https://linear.app/settings/api
2. Click **Create key**
3. Set the environment variable:

```bash
export LINEAR_API_KEY=lin_api_...
```

### 3. Configure agents.yml

```yaml
issue_tracker: linear

linear:
  team_id: "your-team-id"           # from Linear team settings
  agent_task_label: "agent-task"    # Linear label name
  project_id: ""                    # optional: Linear project ID
```

### 4. Create Linear labels

Create these labels in your Linear workspace:
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
      "command": "npx",
      "args": ["-y", "@linear/mcp-server"],
      "env": {
        "LINEAR_API_KEY": "${LINEAR_API_KEY}"
      }
    }
  }
}
```
