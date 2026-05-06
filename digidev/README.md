# digidev

A drop-in agentic coding workflow kit. Install it on any codebase — fresh or existing — and your AI coding agents (Claude Code, Copilot, Cursor) get structured tasks, quality gates, guardrails, and the ability to read and write your existing tools (Jira, Linear, Slack, Supabase, and more).

**digidev doesn't replace your tools. It layers on top of them.**

---

## What it does

| Problem | What digidev adds |
|---|---|
| Agents don't know what to work on | Structured issue backlog with execution tier (Copilot / Cursor / Claude) |
| No quality bar before PRs | 4-dimension self-scoring gate (Security / Quality / Optimization / Accuracy) |
| Agents write to the wrong files | Claude Code PreToolUse guardrails — 9 hook scripts block unsafe operations |
| Each agent re-discovers the codebase | `AGENTS.md` per component + root onboarding doc |
| No connection to your existing tools | MCP config generated for your Jira / Linear / Slack / Supabase setup |
| Agents commit messy history | Conventional commit enforcement, worktree-per-task isolation |
| Security issues reach PRs | Automated heuristic scan (hardcoded secrets, shell injection, N+1, etc.) |

---

## Quickstart

```bash
# 1. Get digidev
git clone https://github.com/digithings-ai/digithings.git /tmp/digithings
cp -r /tmp/digithings/digidev /path/to/your-repo/

# 2. Run the wizard — it asks what tools you already use
cd /path/to/your-repo
bash digidev/install.sh

# 3. Wire up Makefile
echo "include Makefile.digidev" >> Makefile

# 4. Done — start your first task
make status        # shows open agent-task issues
make new-task      # create one interactively
```

Or paste the prompt in [`AI_SETUP.md`](AI_SETUP.md) into Claude Code and it walks you through the whole setup interactively.

---

## Works with tools you already have

The setup wizard asks which tools you use. digidev generates an `.mcp.json` with the right server config for each.

| Tool | What digidev does with it |
|---|---|
| **GitHub Issues** | Issue template, label-based tier dispatch, PR template, Copilot auto-assign |
| **Jira** | Creates issues from `make new-task`, reads acceptance criteria during tasks |
| **Linear** | Creates and lists issues via the Linear MCP server |
| **Notion** | Reads specs from Notion databases, writes PR summaries back |
| **Slack** | Posts PR notifications and CI triage summaries to channels |
| **Supabase / PostgreSQL** | Schema introspection and migration review in-session |
| **GitLab** | MR creation, issue management, CI log reading via GitLab MCP |

No tool? Skip it. The core workflow (tasks → code → score → commit → PR) works without any integrations.

---

## What gets installed

```
.claude/
  settings.json          ← hook wiring + allowlisted commands
  agents/                ← 6 subagents (spec-writer, pr-reviewer, etc.)
  skills/                ← 6 skills (finish-task, score-and-fix, triage, etc.)
  commands/              ← 5 slash commands (/spec, /score, /task, /triage, etc.)

scripts/
  claude-hooks/          ← 9 PreToolUse guard scripts
  hooks/pre-push.sh      ← git pre-push hook
  score.py               ← quality gate runner
  run_task.sh            ← worktree task runner
  create_issue.sh        ← issue creation (GitHub / Jira / Linear)
  create_pr.sh           ← PR / MR creation
  list_tasks.sh          ← list open tasks
  commit_helper.sh       ← conventional commit validator

.github/
  ISSUE_TEMPLATE/        ← structured agent-task form
  PULL_REQUEST_TEMPLATE  ← self-score checklist + human gates
  workflows/             ← Copilot assign, Claude dispatch, project routing

agents.yml               ← project manifest (components, thresholds, tiers)
AGENTS.md                ← root onboarding doc for all agents
{component}/AGENTS.md    ← per-component pre-flight checklist (one per component)
docs/scoring/            ← 4 scoring rubrics (Security / Quality / Optimization / Accuracy)
Makefile.digidev         ← all agent workflow targets

.mcp.json                ← MCP server config for your chosen integrations
digidev-mcp-setup.md     ← setup instructions for each MCP server
```

---

## The workflow

Once installed, every task follows the same loop:

```
make new-task              # 1. Create a structured issue
                           #    - Prompts: component, tier, risk, goal, acceptance criteria
                           #    - Creates in GitHub Issues / Jira / Linear (your choice)

make task ISSUE=42         # 2. Start working in isolation
                           #    - Creates branch task/42-<slug>
                           #    - Opens isolated git worktree at .worktrees/task-42-<slug>

# ... implement and test ...

make score                 # 3. Quality gate
                           #    - Runs lint + heuristic security/quality checks
                           #    - Shows 4 rubrics for self-scoring
                           
make score SCORES="security=8,quality=9,optimization=7,accuracy=9"
                           #    - Validates self-scores against thresholds
                           #    - Exits 0 if passing, 1 if not

make commit MSG="feat(api): add /healthz (#42)"
                           # 4. Validated conventional commit

make pr                    # 5. Draft PR with pre-filled score + human gates
```

---

## Three-tier agent dispatch

digidev routes tasks to the right agent automatically:

| Tier | Agent | When to use | How it's dispatched |
|---|---|---|---|
| `exec:copilot` | GitHub Copilot | Housekeeping: deps, format, config, docs | Label added → workflow auto-assigns @Copilot |
| `exec:cursor` | Cursor | Clear spec, single component, measurable acceptance | Label added → developer opens in Cursor |
| `exec:claude` | Claude Code | Judgment, cross-module, auth, live systems | Label added → workflow posts `make task ISSUE=N` instructions |

The issue template enforces this: every task has a required "Execution tier" dropdown.

---

## Quality gate — 4 dimensions

Every PR must score above threshold in all 4 dimensions. Run `make score` before committing.

| Dimension | Default threshold | What it checks |
|---|---|---|
| Security | ≥ 8/10 | No secrets, no injection, auth checks, network exposure |
| Quality | ≥ 8/10 | Typed interfaces, linter clean, no orphans, focused scope |
| Optimization | ≥ 7/10 | No N+1, no blocking I/O, parallel-safe, caching |
| Accuracy | ≥ 9/10 | Matches issue spec, edge cases handled, tests pass |

Thresholds are set in `agents.yml` and can be adjusted per project.

---

## Guardrails (Claude Code hooks)

9 PreToolUse hook scripts block unsafe operations before they run:

| Hook | What it blocks |
|---|---|
| `project-root-guard` | Writes outside the repo root |
| `protected-path-guard` | Edits to sensitive paths unless on a `task/N-*` branch |
| `remote-guard` | Git push to non-origin remotes |
| `network-host-guard` | curl/wget to hosts not in the allowlist |
| `protected-path-bash-guard` | Shell redirects (`>`, `tee`, `sed -i`) to protected files |
| `branch-warn` | Non-blocking warning when on main/production branch |
| `component-router-preflight` | Non-blocking reminder to read `{component}/AGENTS.md` |
| `auto-format` | PostToolUse: runs `ruff format` / `eslint --fix` on save |
| `pre-push` | Git hook: branch name validation, blocks main push, human approval for sensitive paths |

Allowlisted hosts, protected paths, and the live-trading regex are all configurable in `digidev.yml`.

---

## Prerequisites

**Required:**
- `git` (any modern version)
- `bash` 4.0+
- `python3` 3.9+

**Required for full workflow:**
- `gh` CLI — `make task`, `make pr`, `make status` ([install](https://cli.github.com/))
- Claude Code CLI — for hooks to fire ([install](https://claude.ai/code))

**Optional:**
- `ruff` — Python auto-format hook: `pip install ruff`
- `pyyaml` — full YAML parsing: `pip install pyyaml` (falls back to regex without it)
- `glab` CLI — GitLab MR creation: [install](https://gitlab.com/gitlab-org/cli)

---

## Installation options

**Option A — copy** (simplest, no updates):
```bash
cp -r digidev /path/to/your-repo/
bash /path/to/your-repo/digidev/install.sh
```

**Option B — git subtree** (pull updates later):
```bash
cd /path/to/your-repo
git subtree add --prefix digidev \
  https://github.com/digithings-ai/digithings.git main --squash

# Pull updates later:
git subtree pull --prefix digidev \
  https://github.com/digithings-ai/digithings.git main --squash
```

**Option C — Claude Code** (fully guided, no terminal):
Open your repo in Claude Code and paste the prompt from [`AI_SETUP.md`](AI_SETUP.md).

---

## Configuration

All project settings live in `digidev/digidev.yml`. The wizard creates this for you.

Key fields:

```yaml
project_name: "myapp"
org_name: "myorg"
repo_name: "myrepo"
default_branch: "develop"
main_branch: "main"
contributor_handles: "alice|bob"

# Which tools you use — drives MCP config generation
git_platform: "github"       # github | gitlab | bitbucket | other
issue_tracker: "github"      # github | jira | linear | notion | other
communication: "slack"       # none | slack | teams | discord
database: "supabase"         # none | supabase | postgres | sqlite | other

components:
  - name: api
    description: "HTTP API service"
    test_cmd: "pytest -m unit -k api -v"
  - name: worker
    description: "Background job processor"
    test_cmd: "pytest -m unit -k worker -v"

scoring_thresholds:
  security: 8
  quality: 8
  optimization: 7
  accuracy: 9

protected_paths:
  - "SECURITY.md"
  - ".github/workflows/"
  - "docs/scoring/"

allowed_hosts:
  - "github.com"
  - "api.anthropic.com"
  - "pypi.org"
  - "localhost"
```

Re-run `bash digidev/install.sh --force` after editing to apply changes. Re-run with `--setup-mcp` to regenerate the MCP config.

---

## Customisation

| What to change | How |
|---|---|
| Scoring thresholds | Edit `scoring_thresholds` in `agents.yml` |
| Protected paths | Edit `protected_paths` in `digidev.yml`, re-run installer |
| Allowed network hosts | Edit `allowed_hosts` in `digidev.yml`, re-run installer |
| Component test commands | Edit `components[].test_cmd` in `digidev.yml` + `agents.yml` |
| Execution tier routing rules | Edit `execution_tiers` in `agents.yml` |
| Human gate conditions | Edit `human_gates` in `agents.yml` |
| Scoring rubrics | Edit `docs/scoring/*.md` directly |

---

## Makefile targets reference

```bash
make status [COMPONENT=x]          # list open agent-task issues
make new-task                      # create a new issue interactively
make task ISSUE=N                  # start task in isolated worktree
make batch-candidates              # group issues for parallel execution

make score                         # run automated checks + show rubrics
make score SCORES="s=8,q=8,o=7,a=9"  # validate self-scores
make commit MSG="type(scope): ..."  # conventional commit with validation
make pr                            # create draft PR

make hooks-install                 # install git pre-push hook
make agents-init                   # regenerate .claude/ from agents.yml
make module-switch MODULE=x        # switch to focused module branch
make module-pr MODULE=x            # open module sprint PR
make clean-imports [APPLY=1]       # remove unused imports
make find-stale                    # detect unused code
```

---

## Integrations

See [`digidev/integrations/`](integrations/) for setup guides:

- [GitHub](integrations/github/) — full GitHub MCP setup + workflow automation
- [GitLab](integrations/gitlab/) — GitLab MCP + MR creation
- [Jira](integrations/jira/) — Atlassian MCP + issue creation from CLI
- [Linear](integrations/linear/) — Linear MCP + issue management
- [Slack](integrations/slack/) — notifications on PR open, CI failures
- [Notion](integrations/notion/) — spec reading, PR summaries
- [Supabase](integrations/supabase/) — schema introspection, migration review
- [PostgreSQL](integrations/postgres/) — direct DB access for any Postgres

---

## Troubleshooting

**`make status` fails:**
Ensure `gh auth login` has been run and you have an internet connection.

**Hooks not firing:**
Verify `.claude/settings.json` has the hook entries and you're using Claude Code ≥ 1.x. Check scripts are executable: `ls -la scripts/claude-hooks/`.

**`make score` shows "rubric not found":**
Re-run the installer: `bash digidev/install.sh --force` to regenerate `docs/scoring/`.

**`make task` fails: "base branch not found":**
Ensure `default_branch` in `agents.yml` matches an existing branch. Run `git fetch origin` first.

**MCP servers not listed in `claude mcp list`:**
Check `.mcp.json` is in the repo root and restart Claude Code. Verify the environment variables in `~/.claude/.env`.
