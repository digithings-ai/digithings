# dividev

A drop-in developer kit that wires up a full agentic workflow on any GitHub repository: Claude Code guardrails, structured issue management, multi-tier agent dispatch, a four-dimension quality gate, and a worktree-based task runner.

## What you get

| Layer | What it installs |
|---|---|
| **Claude Code hooks** | PreToolUse guardrails — block writes outside project root, warn on protected paths, enforce task branches, guard network calls |
| **Git pre-push hook** | Rejects pushes to wrong remotes, blocks direct pushes to main, requires human trailer for sensitive paths |
| **GitHub issue template** | Structured agent-task form (component, risk, execution tier, goal, acceptance criteria) |
| **GitHub PR template** | Self-score checklist (Security / Quality / Optimization / Accuracy), human gate declarations |
| **GitHub workflows** | Claude dispatch acknowledgement, Copilot auto-assign, issue → project board routing |
| **agents.yml** | Machine-readable project manifest (components, scoring thresholds, human gates, execution tiers) |
| **Makefile targets** | `task`, `score`, `status`, `new-task`, `commit`, `pr`, `hooks-install`, `agents-init` |
| **Scoring docs** | Four-dimension rubrics your agents score themselves against before every PR |
| **AGENT_GUIDE.md** | Single-file onboarding document for any coding agent |

## Prerequisites

- `git` and `bash`
- `python3` (3.9+) — used by the installer and some hooks
- `gh` CLI — used by `make pr`, `make new-task`, `make status`
- Claude Code CLI — for the `.claude/` surface (hooks, skills, commands)

Optional (enhances hook behavior):
- `ruff` — Python auto-format hook
- `jq` — JSON helpers in some scripts

## Quick start

```bash
# 1. Copy dividev into your repo
cp -r dividev /path/to/your-repo/
cd /path/to/your-repo

# 2. Configure for your project
cp dividev/dividev.example.yml dividev/dividev.yml
$EDITOR dividev/dividev.yml   # fill in project name, org, repo, components

# 3. Install everything
bash dividev/install.sh

# 4. Verify
make hooks-install
make status
```

The installer copies template files into the right locations (`.claude/`, `.github/`, `scripts/`), applies your config, and makes hook scripts executable.

## For a coding agent

Read `dividev/AGENT_GUIDE.md` — that single document describes the complete workflow, branch taxonomy, scoring gate, and what to do at every step. If you are an agent setting up this kit in a new repo, read the "Installation" section at the bottom of that document.

## Customising

- **Add components:** edit `agents.yml` (or `dividev/dividev.yml` before install) — one entry per service / module.
- **Change score thresholds:** edit `agents.yml` under `scoring_thresholds`.
- **Change protected paths:** edit `scripts/claude-hooks/protected-path-guard.sh` and `scripts/claude-hooks/protected-path-bash-guard.sh`.
- **Add allowed network hosts:** edit `scripts/claude-hooks/network-host-guard.sh`.
- **Change branch taxonomy:** edit `scripts/hooks/pre-push.sh` (`branch_regex`).
- **Add human gates:** edit `agents.yml` under `human_gates` and `orchestration.human_gates`.

## Structure

```
dividev/
├── README.md                        this file
├── AGENT_GUIDE.md                   full workflow guide for coding agents
├── dividev.example.yml              copy to dividev.yml and fill in
├── install.sh                       installer — run once per repo
├── Makefile.include                 include in your Makefile
├── docs/
│   ├── agents/
│   │   ├── WORKFLOW.md              step-by-step task execution
│   │   └── EXECUTION_TIERS.md      Copilot / Cursor / Claude tier rules
│   └── scoring/
│       ├── README.md
│       ├── SECURITY.md
│       ├── QUALITY.md
│       ├── OPTIMIZATION.md
│       └── ACCURACY.md
└── templates/
    ├── agents.yml                   project manifest template
    ├── AGENTS.md                    root AGENTS.md template
    ├── COMPONENT_AGENTS.md          per-component AGENTS.md template
    ├── claude-settings.json         .claude/settings.json template
    ├── hooks/
    │   ├── claude/                  scripts/claude-hooks/ contents
    │   └── git/                     scripts/hooks/ contents
    └── github/
        ├── ISSUE_TEMPLATE/
        ├── PULL_REQUEST_TEMPLATE.md
        └── workflows/
```
