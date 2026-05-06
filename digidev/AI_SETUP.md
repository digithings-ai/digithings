# digidev — AI-assisted setup prompt

Copy the block below and paste it into Claude Code (or any coding agent) in your project. The agent will walk through the setup interactively, ask for your project details, and complete the installation.

---

## Paste this into Claude Code

```
I want to set up digidev in this repository. digidev is a drop-in agentic
workflow kit that installs Claude Code guardrails, structured GitHub issue
management, three-tier agent dispatch (Copilot/Cursor/Claude Code), a
four-dimension quality gate, and a worktree-based task runner.

Please:

1. Read `digidev/AGENT_GUIDE.md` to understand what gets installed and why.

2. Ask me for the following required configuration values:
   - Project name (short slug, e.g. "myapp")
   - GitHub org or username
   - GitHub repository name
   - Integration branch name (usually "develop" or "main")
   - Production branch name (usually "main")
   - My GitHub handle (for the branch allowlist)
   - The components/services in this repo (name + description + test command each)
   - Tech stack: python, node, or python+node

3. Run the installer interactively:
      bash digidev/install.sh
   It will prompt for the values above if digidev/digidev.yml doesn't exist yet.

4. After the installer finishes, complete the remaining steps:
   - Add `include Makefile.digidev` to the Makefile (create one if needed)
   - Run `make hooks-install` to install the git pre-push hook
   - Create the GitHub labels (the installer prints the exact commands)
   - Commit everything with `git commit -m "chore: install digidev agentic workflow kit"`
   - Push to the repo

5. Verify with `make status` — it should run without error.

Ask me for each required value before proceeding. Do not guess the org name,
repo name, or component list — these must come from me.
```

---

## Alternative: run the wizard directly

If you have a terminal (not using an AI agent), just run:

```bash
bash digidev/install.sh
```

When `digidev/digidev.yml` doesn't exist, the installer asks for your project details interactively and creates the config file before proceeding.

---

## What happens next

After setup, the workflow is:

```bash
make new-task        # create a backlog issue (opens GitHub issue form)
make task ISSUE=42   # start work — creates branch + worktree
# ... implement and test ...
make score           # four-dimension quality gate
make commit MSG="feat(api): add /healthz"
make pr              # open PR with pre-filled template
```

Your agents (Copilot, Cursor, Claude Code) will see the structured issues, know which tier to execute at, and score themselves before every PR.

Read `digidev/AGENT_GUIDE.md` for the full workflow reference.
