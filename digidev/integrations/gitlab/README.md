# GitLab integration

Use GitLab instead of GitHub? digidev supports GitLab Issues, Merge Requests, and CI pipelines via the official GitLab MCP server.

---

## What it enables

- `spec-writer` creates GitLab Issues
- `finish-task` opens Merge Requests instead of PRs
- `ci-triage` reads GitLab CI pipeline logs
- `create_pr.sh` uses `glab` CLI to create MRs

---

## Setup

### 1. Install the GitLab MCP server

```bash
claude mcp add gitlab -- npx -y @modelcontextprotocol/server-gitlab
```

Or add to `.mcp.json`:

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-gitlab"],
      "env": {
        "GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_PERSONAL_ACCESS_TOKEN}",
        "GITLAB_API_URL": "https://gitlab.com/api/v4"
      }
    }
  }
}
```

### 2. Authenticate

Create a GitLab personal access token with `api` scope:
`GitLab → Settings → Access Tokens → Add new token`

```bash
export GITLAB_PERSONAL_ACCESS_TOKEN=glpat-...
```

Install the `glab` CLI for `create_pr.sh`:
```bash
brew install glab          # macOS
# or: https://gitlab.com/gitlab-org/cli
glab auth login
```

### 3. Configure agents.yml

```yaml
git_platform: gitlab
issue_tracker: gitlab         # or: jira / linear / notion

gitlab:
  base_url: "https://gitlab.com"    # or your self-hosted URL
  project_id: "myorg/myrepo"
```

### 4. Disable GitHub-only workflows

The digidev GitHub workflows won't apply to GitLab. When running the installer, answer `gitlab` to the "git platform" question — the installer will skip GitHub workflow installation.

If you've already installed them, remove the `.github/workflows/` files (they'll do nothing on GitLab).

---

## MCP config snippet

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-gitlab"],
      "env": {
        "GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_PERSONAL_ACCESS_TOKEN}",
        "GITLAB_API_URL": "https://gitlab.com/api/v4"
      }
    }
  }
}
```

---

## Notes

- The three-tier dispatch model still works on GitLab — use issue labels `exec:copilot`, `exec:cursor`, `exec:claude` manually (no workflow automation on GitLab unless you write `.gitlab-ci.yml` jobs).
- `make task ISSUE=N` works with GitLab issue numbers once `GITLAB_PERSONAL_ACCESS_TOKEN` is set.
