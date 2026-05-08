# AGENTS.md

Canonical rules for all agents in this repo are in **[CLAUDE.md](CLAUDE.md)** — read that first.

Claude Code loads `CLAUDE.md` at session start. Cursor agents use `.cursor/rules/digithings.mdc`; Copilot uses `.github/copilot-instructions.md` — both generated from `agents.yml` by `make agents-init`.
