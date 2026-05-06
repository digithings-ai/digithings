# GitHub integration

The GitHub MCP server gives your agents full read/write access to GitHub Issues, Pull Requests, Actions, and repositories — without leaving the editor.

This is the **default and recommended** integration for digidev. All three GitHub workflows (`claude-code-dispatch.yml`, `auto-assign-copilot.yml`, `route-issues-to-projects.yml`) are included in the digidev install.

---

## What it enables

| Agent / skill | GitHub capability used |
|---|---|
| `spec-writer` | Create issues with labels |
| `ci-triage` | Read Actions run logs |
| `finish-task` | Create draft PRs |
| `list_tasks.sh` | List issues by label |
| `create_pr.sh` | Open PRs from CLI |
| GitHub workflows | Auto-assign Copilot, dispatch Claude tasks, route to Project boards |

---

## Setup

### 1. Install the GitHub MCP server

The GitHub MCP server is included in Claude Code by default for most installations. Check if it's already active:

```bash
claude mcp list
```

If not listed, add it:

```bash
claude mcp add github -- npx -y @modelcontextprotocol/server-github
```

Or add to `.mcp.json` in your repo root (see snippet below).

### 2. Authenticate

```bash
gh auth login          # authenticate the GitHub CLI (used by digidev scripts)
```

For the MCP server, set `GITHUB_PERSONAL_ACCESS_TOKEN` in your environment:

```bash
export GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...
# or add to ~/.claude/.env
```

Permissions needed: `repo`, `read:org`, optionally `project` for Project board routing.

### 3. Install digidev GitHub workflows

The digidev installer copies these automatically:

```bash
bash digidev/install.sh
```

Workflows installed:
- `.github/workflows/claude-code-dispatch.yml` — posts local execution instructions when `exec:claude` label is added
- `.github/workflows/auto-assign-copilot.yml` — assigns @Copilot when `exec:copilot` label is added
- `.github/workflows/route-issues-to-projects.yml` — routes issues to Project boards by component label

### 4. Create GitHub labels

The installer prints the exact commands. Run them once per repo:

```bash
gh label create 'agent-task'   --color 'ededed' --description 'Task for a coding agent'
gh label create 'exec:copilot' --color 'cfd3d7' --description 'Assign to GitHub Copilot'
gh label create 'exec:cursor'  --color '0075ca' --description 'Assign to Cursor'
gh label create 'exec:claude'  --color '7057ff' --description 'Run with Claude Code (local)'
gh label create 'risk:low'     --color '0e8a16'
gh label create 'risk:med'     --color 'e4e669'
gh label create 'risk:high'    --color 'd93f0b'
```

Add one label per component:
```bash
gh label create 'component:api'    --color 'f9d0c4'
gh label create 'component:worker' --color 'f9d0c4'
```

---

## MCP config snippet

Add to `.mcp.json` (project-level) or `~/.claude/mcp_settings.json` (user-level):

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PERSONAL_ACCESS_TOKEN}"
      }
    }
  }
}
```

---

## agents.yml settings

```yaml
git_platform: github
issue_tracker: github

github_projects:
  default_project: 1          # Project board number (optional)

# Optional: map components to specific project boards
components:
  - name: api
    github_project: 1
  - name: worker
    github_project: 2
```
