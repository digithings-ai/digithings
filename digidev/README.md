# digidev

A drop-in developer kit that wires up a complete agentic coding workflow on any GitHub repository in under 10 minutes.

Once installed you get: Claude Code guardrails, structured GitHub issue management, three-tier agent dispatch (Copilot → Cursor → Claude Code), a four-dimension quality gate (Security / Quality / Optimization / Accuracy), and a worktree-based task runner — the same setup powering [digithings](https://github.com/digithings-ai/digithings).

---

## What gets installed

| Layer | What it installs | Where |
|---|---|---|
| **Claude Code hooks** | 9 PreToolUse guard scripts — block writes outside project root, protect sensitive paths, enforce task branches, guard network calls, auto-format on save | `scripts/claude-hooks/` |
| **Claude Code settings** | Hook wiring + allowlisted Bash commands | `.claude/settings.json` |
| **Git pre-push hook** | Rejects pushes to wrong remotes, blocks direct pushes to main, requires human trailer for sensitive path changes | `scripts/hooks/pre-push.sh` |
| **GitHub issue template** | Structured agent-task form (component, risk, execution tier, model, goal, acceptance criteria) | `.github/ISSUE_TEMPLATE/` |
| **GitHub PR template** | Self-score checklist (Security / Quality / Optimization / Accuracy), human gate declarations | `.github/PULL_REQUEST_TEMPLATE.md` |
| **GitHub workflows** | Claude dispatch acknowledgement, Copilot auto-assign with quota tracking, issue → project board routing | `.github/workflows/` |
| **Project manifest** | `agents.yml` — machine-readable project config (components, scoring thresholds, human gates, execution tiers) | repo root |
| **AGENTS.md files** | Root onboarding doc + per-component pre-flight checklist | repo root + `{component}/` |
| **Makefile targets** | `task`, `score`, `status`, `new-task`, `commit`, `pr`, `hooks-install`, `agents-init`, `module-*` | `Makefile.dividev` |
| **Scoring rubrics** | Four-dimension rubric docs agents score themselves against | `docs/scoring/` |
| **Agent guide** | Single-file complete workflow reference for any coding agent | `digidev/AGENT_GUIDE.md` |

---

## Prerequisites

**Required:**
- `git` (any modern version)
- `bash` 4.0+
- `python3` 3.9+ — used by the installer, hook scripts, and score runner
- `gh` CLI — used by `make pr`, `make new-task`, `make status` ([install](https://cli.github.com/))
- A GitHub repository with Actions enabled

**Required for Claude Code hooks to fire:**
- [Claude Code CLI](https://claude.ai/code) installed and configured

**Optional but recommended:**
- `ruff` — enables Python auto-format hook on every save (`pip install ruff`)
- `pyyaml` — enables full YAML parsing in the installer (`pip install pyyaml`); falls back to a regex parser without it
- GitHub Project boards — enables issue routing (requires a PAT, see [GitHub setup](#github-setup))

---

## Installation

### Step 1 — Get digidev into your repo

**Option A: copy the directory** (simplest)
```bash
# From the digithings repo (or wherever you have digidev)
cp -r digidev /path/to/your-repo/
cd /path/to/your-repo
```

**Option B: git subtree** (keeps it updatable)
```bash
cd /path/to/your-repo
git subtree add --prefix digidev \
  https://github.com/digithings-ai/digithings.git \
  main --squash
```

**Option C: clone and copy**
```bash
git clone https://github.com/digithings-ai/digithings.git /tmp/digithings
cp -r /tmp/digithings/digidev /path/to/your-repo/
```

### Step 2 — Configure for your project

```bash
cd /path/to/your-repo
cp digidev/digidev.example.yml digidev/digidev.yml
```

Open `digidev/digidev.yml` and fill in the required fields:

```yaml
project_name: "myproject"        # short name, used in display text and env vars
org_name: "myorg"                # GitHub org or username
repo_name: "myrepo"              # GitHub repository name
default_branch: "develop"        # integration branch (use "main" if no develop branch)
main_branch: "main"              # production branch
contributor_handles: "alice|bob" # GitHub handles of human contributors (pipe-separated)

components:
  - name: api
    description: "HTTP API service"
    test_cmd: "pytest -m unit -k api -v"
  - name: worker
    description: "Background job processor"
    test_cmd: "pytest -m unit -k worker -v"
```

Everything else has sensible defaults. See [`digidev.example.yml`](digidev.example.yml) for the full reference with comments.

### Step 3 — Run the installer

```bash
# Preview what will be installed (no files written)
bash digidev/install.sh --dry-run

# Install for real
bash digidev/install.sh
```

The installer:
- Copies all template files to their canonical locations
- Substitutes your `digidev.yml` values into every `{{PLACEHOLDER}}` in the templates
- Creates `{component}/AGENTS.md` for each component you listed
- Makes all hook scripts executable

Use `--force` to overwrite files that already exist.

### Step 4 — Wire up the Makefile

Add one line to your existing `Makefile`:

```makefile
include Makefile.digidev
```

If you don't have a Makefile yet, rename `Makefile.digidev` to `Makefile` and you're done.

### Step 5 — Install the git pre-push hook

```bash
make hooks-install
```

### Step 6 — Authenticate with GitHub CLI

```bash
gh auth login
```

### Step 7 — Verify

```bash
make status    # list open agent-task issues (empty in a new repo — that's fine)
make score     # should run without error (no staged changes to score yet)
```

### Step 8 — Commit the installed files

```bash
git add .claude/ .github/ scripts/ agents.yml AGENTS.md Makefile.digidev
git add */AGENTS.md docs/scoring/   # component checklists + scoring rubrics
git commit -m "chore: install digidev agentic workflow kit"
git push
```

---

## GitHub setup

### Required: create GitHub labels

The workflow uses labels to route issues to the right agent tier. Create these in your repo:

```bash
# Execution tier labels
gh label create "exec:claude"   --color "7057ff" --description "Tier 3 — Claude Code (local)"
gh label create "exec:cursor"   --color "0075ca" --description "Tier 2 — Cursor cloud agent"
gh label create "exec:copilot"  --color "cfd3d7" --description "Tier 1 — GitHub Copilot"

# Risk labels
gh label create "risk:low"  --color "0e8a16" --description "Low risk change"
gh label create "risk:med"  --color "e4e669" --description "Medium risk change"
gh label create "risk:high" --color "d93f0b" --description "High risk change"

# Task label
gh label create "agent-task" --color "ededed" --description "Work for a coding agent"

# Component labels (one per component — repeat for each)
gh label create "component:api"    --color "bfd4f2" --description ""
gh label create "component:worker" --color "bfd4f2" --description ""
```

### Optional: GitHub Project board routing

If you use GitHub Project boards, the `route-issues-to-projects.yml` workflow automatically adds issues to the right board based on component label.

**Setup:**
1. Create your project boards at `github.com/orgs/{org}/projects` (or personal projects)
2. Note the project numbers (visible in the project URL)
3. Add the mapping to `digidev.yml`:
   ```yaml
   github_projects:
     default_project: 1
     component_map:
       api: 2
       worker: 3
   ```
4. Create a GitHub PAT with `project` + `repo` scopes
5. Add it as a repository secret named `PROJECT_TOKEN` (or whatever you set `project_token_secret` to)

### Optional: Copilot auto-assign

The `auto-assign-copilot.yml` workflow assigns `@Copilot` when the `exec:copilot` label is applied. This works out of the box once you have GitHub Copilot enabled on your org.

To enable quota tracking (prevents over-assigning when Copilot quota is exhausted):
1. Create a "meta: Copilot quota state" issue in your repo
2. Set `copilot_quota_state_issue: <number>` in `digidev.yml`
3. Re-run the installer (`bash digidev/install.sh --force`) to regenerate the workflow

---

## First workflow

Once installed, here's the complete loop from task to PR:

### 1. Create a task issue

```bash
make new-task   # interactive — fills in component, risk, tier, goal, acceptance criteria
```

Or use the GitHub issue form (`/.github/ISSUE_TEMPLATE/agent_task.yml` appears in the UI).

### 2. Pick it up

```bash
make status          # see open agent-task issues
make task ISSUE=42   # creates worktree + branch task/42-{slug}
```

This drops you into an isolated git worktree at `.worktrees/task-42-{slug}` on branch `task/42-{slug}`. Your main working tree is unaffected.

### 3. Read the component checklist

Before writing any code:
```bash
# The component-router-preflight hook will remind you if you skip this
cat api/AGENTS.md
```

### 4. Implement and test

```bash
# Work normally, commit incrementally
make commit MSG="feat(api): add /healthz endpoint"

# Run tests when ready
make test-unit   # or your component's test command
```

### 5. Score before PR

```bash
make score
```

Output shows per-dimension scores. All must meet the thresholds in `agents.yml` (default: Security ≥8, Quality ≥8, Optimization ≥7, Accuracy ≥9).

Fix any failing dimension using the rubrics in `docs/scoring/`, then re-score.

### 6. Open the PR

```bash
make pr
```

The PR template opens pre-filled. Fill in the self-score checklist honestly and check any applicable human gate boxes.

---

## How Claude Code hooks work

When Claude Code is active, 9 guard scripts fire before every file write or shell command:

**Write/Edit/NotebookEdit hooks:**
- `project-root-guard` — blocks writes outside the project root
- `protected-path-guard` — blocks edits to protected paths (workflows, scoring docs) unless on a `task/N-*` branch
- `branch-warn` — non-blocking reminder when editing on `main` or the default branch
- `component-router-preflight` — non-blocking reminder to read `{component}/AGENTS.md` first

**Bash hooks:**
- `remote-guard` — blocks `git push` to any remote other than your pinned origin
- `network-host-guard` — blocks `curl`/`wget` to hosts not in the allowlist
- `protected-path-bash-guard` — blocks shell-redirect writes (`>`, `tee`, `sed -i`, `mv`) to protected paths

**Auto-format (PostToolUse):**
- `auto-format` — runs `ruff format` on Python saves, `eslint --fix` on JS/TS saves

None of the non-blocking hooks stop Claude Code — they only emit warnings to the transcript. The blocking hooks exit with code 2, which Claude Code surfaces as a guardrail message.

---

## Agent execution tiers

Three tiers control which agent handles which task:

| Label | Who runs it | Scope | Auto-executes? |
|---|---|---|---|
| `exec:copilot` | GitHub Copilot | Housekeeping only — deps, format, stale | Yes — @Copilot assigned automatically |
| `exec:cursor` | Cursor cloud agent | Clear spec, single component, no judgment | Yes — Cursor picks it up |
| `exec:claude` | Claude Code (you) | Judgment, cross-module, human-gated | No — run `make task ISSUE=N` locally |

Default routing (when not explicitly set): `risk:high` → claude, housekeeping → copilot, everything else → cursor.

---

## Customising after install

| What to change | Where |
|---|---|
| Add a component | `agents.yml` → `components`, re-run `make new-task` |
| Change score thresholds | `agents.yml` → `scoring_thresholds` |
| Change protected paths | `scripts/claude-hooks/protected-path-guard.sh` and `protected-path-bash-guard.sh` |
| Add allowed network hosts | `scripts/claude-hooks/network-host-guard.sh` → `allowed_hosts` array |
| Change branch naming rules | `scripts/hooks/pre-push.sh` → `branch_regex` |
| Add a human gate pattern | `agents.yml` → `orchestration.human_gates` |
| Add contributor handles | `scripts/hooks/pre-push.sh` → `CONTRIBUTOR_HANDLES` |

---

## Troubleshooting

**`make status` fails with "gh: command not found"**
Install the GitHub CLI: https://cli.github.com/

**`make status` returns "HTTP 401"**
Run `gh auth login` first.

**Claude Code hooks don't fire**
Check that `.claude/settings.json` exists and that you're running Claude Code (not just the API). Hooks require the Claude Code CLI or desktop app.

**`bash digidev/install.sh` fails on YAML parsing**
Install PyYAML: `pip install pyyaml`. The installer has a regex fallback but it only handles simple `key: value` lines, not nested YAML.

**Hook blocks a legitimate operation**
- For network hosts: add the host to `scripts/claude-hooks/network-host-guard.sh` → `allowed_hosts`.
- For protected paths: you need a `task/N-*` branch, or set `{PROJECT_NAME}_ALLOW_PROTECTED=1` in a human session.
- For remote pushes: you're pushing to a fork or different remote — only `origin` is allowed by default.

**`make task ISSUE=N` can't find the issue**
Run `gh auth login` and confirm you have access to the repo. The script uses `gh issue view` to fetch issue metadata.

**Pre-push hook rejects my branch name**
Branch names must match the taxonomy in `scripts/hooks/pre-push.sh` (`branch_regex`). Allowed patterns: `main`, `develop`, `task/N-slug`, `module/component`, `claude/slug`, `feat/slug`, `fix/slug`, your GitHub handle + `/slug`.

---

## Directory structure

```
digidev/
├── README.md                          this file
├── AGENT_GUIDE.md                     complete workflow reference for coding agents
├── digidev.example.yml                configuration template
├── install.sh                         installer — run once per repo
├── Makefile.include                   Makefile targets — add `include Makefile.digidev`
├── docs/
│   ├── agents/
│   │   ├── WORKFLOW.md               step-by-step task execution guide
│   │   └── EXECUTION_TIERS.md       Copilot / Cursor / Claude tier rules
│   └── scoring/
│       ├── README.md                 scoring overview
│       ├── SECURITY.md              security rubric (10 criteria)
│       ├── QUALITY.md               quality rubric (10 criteria)
│       ├── OPTIMIZATION.md          optimization rubric (10 criteria)
│       └── ACCURACY.md              accuracy rubric (10 criteria)
└── templates/                        source templates (substituted by installer)
    ├── agents.yml
    ├── AGENTS.md
    ├── COMPONENT_AGENTS.md
    ├── claude-settings.json
    ├── hooks/
    │   ├── claude/                   9 Claude Code PreToolUse hook scripts
    │   └── git/                      pre-push hook
    └── github/
        ├── ISSUE_TEMPLATE/           agent_task.yml + config.yml
        ├── PULL_REQUEST_TEMPLATE.md
        └── workflows/                claude-code-dispatch, auto-assign-copilot,
                                      route-issues-to-projects
```
