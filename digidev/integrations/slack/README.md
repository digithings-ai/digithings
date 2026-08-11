# Slack integration

Connect digidev to Slack so agents can post status updates, surface CI failures, and notify the team when PRs are opened — all without leaving the editor.

---

## What it enables

- `finish-task` posts a message to a channel when a PR is created
- `ci-triage` can post a triage summary to your team's CI channel
- Agents can read threads for context on ongoing issues
- Automated notifications when `exec:claude` tasks are dispatched

---

## Setup

### 1. Install the Slack MCP server

```bash
claude mcp add slack -- npx -y @modelcontextprotocol/server-slack
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
      }
    }
  }
}
```

### 2. Create a Slack app

1. Go to: https://api.slack.com/apps
2. Click **Create New App → From scratch**
3. Name it (e.g., `digidev-bot`) and select your workspace
4. Under **OAuth & Permissions**, add scopes:
   - `channels:read`
   - `chat:write`
   - `chat:write.public`
   - `channels:history` (to read channel messages)
5. Install the app to your workspace
6. Copy the **Bot User OAuth Token** (`xoxb-...`)

```bash
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_TEAM_ID=T...      # your workspace ID (from workspace URL)
```

### 3. Configure agents.yml

```yaml
slack:
  enabled: true
  pr_channel: "#dev-prs"          # channel for PR notifications
  ci_channel: "#ci-alerts"        # channel for CI failure notifications
  task_channel: "#agent-tasks"    # channel for task dispatch notifications
```

### 4. Invite the bot to channels

```
/invite @digidev-bot
```

---

## How agents use Slack

With the Slack MCP active, agents can:

```
finish-task:   "PR opened: feat(api): add /healthz (#42) → #dev-prs"
ci-triage:     "CI red on PR #42: lint (ruff), 2 unit tests → #ci-alerts"
new-task:      "New agent-task: Add rate limiting to /auth endpoint → #agent-tasks"
```

The agents decide whether to post based on the channel config in `agents.yml`. You control which events trigger Slack messages.

---

## MCP config snippet

```json
{
  "mcpServers": {
    "slack": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-slack"],
      "env": {
        "SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}",
        "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"
      }
    }
  }
}
```

---

## Using Teams or Discord instead?

- **Microsoft Teams:** Use the [Teams MCP server](https://github.com/modelcontextprotocol/servers) or configure a webhook URL in `agents.yml` under `teams.webhook_url`.
- **Discord:** Use a Discord webhook; set `discord.webhook_url` in `agents.yml`. The `finish-task` skill will POST to it after PR creation.
