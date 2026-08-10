# Notion integration

Use Notion as your project planning and documentation hub while digidev handles the code side. The Notion MCP server lets agents read specs from Notion pages and write summaries back.

---

## What it enables

- `spec-writer` can pull goals and acceptance criteria from a Notion database
- Agents can read architecture docs stored in Notion
- PR summaries written back to Notion sprint databases
- `AGENT_GUIDE.md` content can be kept in Notion and synced

---

## Setup

### 1. Install the Notion MCP server

```bash
claude mcp add notion -- npx -y @notionhq/notion-mcp-server
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_API_TOKEN": "${NOTION_API_TOKEN}"
      }
    }
  }
}
```

### 2. Create a Notion integration

1. Go to: https://www.notion.so/my-integrations
2. Click **+ New integration**
3. Name it (e.g., `digidev`) and select your workspace
4. Copy the **Internal Integration Secret**

```bash
export NOTION_API_TOKEN=secret_...
```

### 3. Share pages with the integration

For each Notion page or database your agents should access:
- Open the page in Notion
- Click **...** → **Connect to** → select your integration

### 4. Configure agents.yml

```yaml
issue_tracker: notion       # or: github, jira, linear (Notion for docs only is also valid)

notion:
  tasks_database_id: "abc123..."     # Notion database ID for agent tasks
  specs_database_id: "def456..."     # optional: specs/PRD database
  docs_page_id: "ghi789..."          # optional: architecture docs page
```

Database IDs come from the URL: `notion.so/<workspace>/<database-id>?v=...`

---

## Using Notion for task management

Create a Notion database with these properties:

| Property | Type | Values |
|---|---|---|
| Name | Title | Issue title |
| Status | Select | Backlog / In Progress / Done |
| Exec tier | Select | copilot / cursor / claude |
| Risk | Select | low / med / high |
| Component | Select | your component names |
| Acceptance criteria | Text | — |
| Issue number | Number | — |

The `spec-writer` agent will create database rows matching this schema when `issue_tracker: notion` is set.

---

## Hybrid: Notion for docs, GitHub for issues

Many teams use Notion for specs/planning and GitHub Issues for execution. Set:

```yaml
issue_tracker: github
notion:
  docs_page_id: "..."    # agents read architecture docs from Notion
```

Agents will create GitHub Issues for execution but read specs from Notion.

---

## MCP config snippet

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_API_TOKEN": "${NOTION_API_TOKEN}"
      }
    }
  }
}
```
