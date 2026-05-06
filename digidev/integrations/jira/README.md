# Jira integration

Already using Jira? digidev can create issues, read sprint boards, and update ticket status through the Atlassian MCP server — no migration to GitHub Issues required.

---

## What it enables

- `spec-writer` creates Jira issues with proper fields
- `create_issue.sh` and `make new-task` open Jira tickets
- `list_tasks.sh` and `make status` list your Jira backlog
- Agents read acceptance criteria from Jira issue descriptions
- Ticket status updated when PRs merge

---

## Setup

### 1. Install the Atlassian MCP server

`mcp-atlassian` is a Python package. Install with `uv` (recommended) or `pip`:

```bash
# Option A — uv (recommended, auto-manages environment)
claude mcp add jira -- uvx mcp-atlassian

# Option B — pip
pip install mcp-atlassian
claude mcp add jira -- python -m mcp_atlassian
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "jira": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "${JIRA_BASE_URL}",
        "JIRA_USERNAME": "${JIRA_EMAIL}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
      }
    }
  }
}
```

### 2. Create an API token

1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens
2. Click **Create API token**
3. Set environment variables:

```bash
export JIRA_BASE_URL=https://your-org.atlassian.net
export JIRA_EMAIL=you@yourcompany.com
export JIRA_API_TOKEN=your-token-here
export JIRA_PROJECT=PROJ   # your Jira project key
```

Add to `~/.claude/.env` or your shell profile to persist.

### 3. Configure agents.yml

```yaml
issue_tracker: jira

jira:
  base_url: "https://your-org.atlassian.net"
  project_key: "PROJ"
  agent_task_label: "agent-task"    # Jira label for agent issues
  exec_field: "customfield_10001"   # optional: custom field for exec tier
```

### 4. Map execution tiers to Jira labels

digidev uses labels `exec:copilot`, `exec:cursor`, `exec:claude`. Create these as Jira labels in your project:
`Project Settings → Labels → Add label`

---

## How the three-tier model works with Jira

| Tier | How to dispatch |
|---|---|
| `exec:copilot` | Add label `exec:copilot` to ticket — use Jira Automation to assign to a Copilot bot user |
| `exec:cursor` | Add label `exec:cursor` — developer opens ticket in Cursor, runs `/task` |
| `exec:claude` | Add label `exec:claude` — developer runs `make task ISSUE=<jira-key>` locally |

The GitHub Actions workflows (`auto-assign-copilot.yml`) won't fire for Jira — you'll use Jira Automation rules instead.

---

## MCP config snippet

```json
{
  "mcpServers": {
    "jira": {
      "command": "uvx",
      "args": ["mcp-atlassian"],
      "env": {
        "JIRA_URL": "${JIRA_BASE_URL}",
        "JIRA_USERNAME": "${JIRA_EMAIL}",
        "JIRA_API_TOKEN": "${JIRA_API_TOKEN}"
      }
    }
  }
}
```

---

## Combine with GitHub

If you use Jira for planning but GitHub for code/PRs, set both:

```yaml
issue_tracker: jira
git_platform: github
```

digidev will create issues in Jira and PRs in GitHub, linking them via the branch name.
