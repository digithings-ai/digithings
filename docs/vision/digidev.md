---
title: DigiDev
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - devtools
---
# DigiDev
> A drop-in agentic-coding workflow kit — structured tasks, a quality gate, guardrails, and connectors to the tools you already use.

## What it is

DigiDev is a drop-in kit that turns any codebase — fresh or existing — into one where AI coding agents (Claude Code, Copilot, Cursor) work safely and consistently. Install it and your agents get a structured task backlog, a 4-dimension self-scoring quality gate, PreToolUse guardrails that block unsafe operations, per-component onboarding docs, and generated MCP configuration for the tools a team already uses (Jira, Linear, Slack, Notion, Supabase, GitLab, and more).

DigiDev does not replace your tools — it layers on top of them. The core workflow (tasks → code → score → commit → PR) runs with zero integrations; connectors are additive.

## The problem it solves

Agentic coding fails in predictable ways: agents don't know what to work on, there's no quality bar before PRs, they write to the wrong files, they re-discover the codebase every session, and they have no connection to the team's existing issue tracker or chat. Teams paper over this with ad-hoc prompts that don't compound. DigiDev packages the hard-won conventions — backlog, scoring rubric, guardrail hooks, worktree-per-task isolation, conventional commits — into something installable in minutes.

## How it fits in the ecosystem

DigiDev is the developer-infrastructure product line of DigiThings, distinct from the agentic-stack services. This monorepo dogfoods it: the `.claude/` agent surface, the `make score` gate, the task pipeline, and the guardrail hooks here *are* DigiDev. It is also the most directly portable component — it installs onto repositories that use none of the other DigiThings modules, which makes it a low-friction front door to the ecosystem.

## Capabilities — Current

Shipped and in active use:

- Structured agent-task backlog with execution-tier dispatch (Copilot / Cursor / Claude)
- 4-dimension self-scoring gate (Security / Quality / Optimization / Accuracy) with rubrics
- Claude Code PreToolUse guardrails — hook scripts that block unsafe operations
- Per-component `AGENTS.md` plus a root onboarding doc
- Generated `.mcp.json` for the team's existing tools (Jira, Linear, Slack, Notion, Supabase, GitLab, GitHub Issues)
- Conventional-commit enforcement and worktree-per-task isolation
- Bundled subagents and skills (spec-writer, pr-reviewer, finish-task, triage, and more)
- An install wizard plus an interactive `AI_SETUP.md` walkthrough

## Capabilities — 12-month roadmap

- Broader connector coverage as new MCP servers stabilise
- A curated marketplace of premium agents and skills as paid add-ons
- Tighter feedback loop between the scoring gate and CI triage
- Versioned, upgradable installs so adopting repos can pull kit improvements cleanly

## Open source vs. proprietary

**Open (MIT/Apache):** the DigiDev kit core — task backlog, scoring gate, guardrail hooks, onboarding docs, connector generation, and the base subagents/skills.

**Proprietary (commercial):** premium agents and skills offered as paid add-ons, and any managed/hosted DigiDev offering. The kit is the open front door; the premium agent library is the upsell.
