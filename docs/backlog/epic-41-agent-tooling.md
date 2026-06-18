# Epic #41 — Phase 0b: Agent-coding tooling depth

**Status:** in progress
**Tracking issue:** [#41](https://github.com/digithings-ai/digithings/issues/41)
**Last reviewed:** 2026-04-18

## Summary

Phase 0 (epic #34) locked down issue-linkage and cross-tool agent config sync. Phase 0b extends that foundation so multi-agent parallel development is safe, fast, and self-correcting before feature work begins. Scope is limited to agent tooling — no DigiGraph, DigiQuant, or other component feature work lands under this epic.

The epic is a scoping container; each acceptance-criteria bullet on #41 becomes its own small sub-task issue.

## Shipped

- **#48** — `create_issue.sh --project-fields` flag. Auto-appends a TSV row and sets live Project fields at issue-creation time. Covers acceptance bullet 4 and removes the manual TSV backfill pain point.
- **.claude/ surface baseline** — `dictation-normalizer`, `component-router`, `spec-writer`, `pr-reviewer`, `test-first-implementer` subagents plus `write-acceptance-criteria`, `worktree-task-start`, `score-and-fix` skills and `/normalize`, `/spec`, `/score`, `/task` commands are committed and regenerated via `make agents-init` from `agents/sources/`. Covers acceptance bullet 7 (sync pipeline). Extension points for the new skills below are already wired.

## Remaining sub-tasks

Each item below should be filed as its own `agent-task` issue on [Project #1](https://github.com/orgs/digithings-ai/projects/1) and closed via a PR that references #41.

- [ ] **Failing-CI triage skill** — add `agents/sources/skills/ci-triage/` that reads `gh pr checks <N> --log-failed`, buckets failures (lint / doc-links / test / compose / other), and proposes minimal fixes. Expose as `/triage <pr-number>`. Regenerate `.claude/` via `make agents-init`. (~3h)
- [ ] **Component-router PreToolUse hook** — add a hook under `scripts/claude-hooks/` that fires on Edit/Write, checks the target path against components opened in the session, and prompts the agent to re-read the target `{component}/AGENTS.md` on mismatch. Wire it into `.claude/settings.json`. (~3h)
- [ ] **Parallel-worktree conflict detector** — extend `scripts/worktree-task-start` (and the matching skill) to diff the requested task's likely file globs against other `.worktrees/*` branches' staged/uncommitted paths and warn on overlap before `make task ISSUE=N` runs. (~3h)
- [ ] **Auto-stub TSV on issue-open** — GitHub Action triggered on `issues.opened` with label `agent-task`; if `scripts/project_fields.tsv` has no row for the new issue, append a stub row with defaults and commit via a bot PR. Complements #48 for issues filed through the UI. (~2h)
- [ ] **Score-delta reporter** — extend `make score` (or add `make score-delta`) to compute current vs. `origin/develop` baseline per dimension and flag any regression, not just sub-threshold scores. Surface the delta in the `score-and-fix` skill output. (~3h)
- [ ] **Documentation refresh** — update `agents/sources/README.md` with one section per new skill/subagent, add an "Agent Capabilities" pointer in [`AGENTS.md`](../../AGENTS.md) and [`CLAUDE.md`](../../CLAUDE.md), and refresh the diagram in [`docs/agents/AGENT_WORKFLOW.md`](../agents/AGENT_WORKFLOW.md) to include the auto-triage and component-router checkpoints. Do this after the skills above land so the docs match reality. (~2h)

## Out of scope

- Feature or refactor work on any DigiThings component.
- Replacing or rewriting existing subagents/skills — extend only.
