---
title: DigiClaw
type: module
status: reviewed
created: 2026-04-19
tags:
  - support
  - audit
---
# DigiClaw

> The always-on agent layer — scheduled and continuous AI agents that run the ecosystem autonomously.

**What it is:** DigiClaw is the persistent agent orchestration layer. Where DigiGraph handles on-demand requests triggered by users, DigiClaw handles scheduled, continuous, and autonomously running agents. It is a deployment and scheduling wrapper around OpenClaw that simplifies defining, launching, and monitoring long-running agents — giving them access to DigiGraph sub-graphs, DigiSearch indexes, and DigiQuant tools on a schedule or continuously.

**The problem:** Most agent systems are reactive — they respond to user requests and then stop. But some of the most valuable AI workflows are proactive: monitoring a live strategy around the clock, continuously exploring new research directions, running daily analysis cycles autonomously. DigiClaw is the infrastructure that makes these workflows reliable and auditable.

**Architecture:**
- Agent definitions: what the agent does, which tools and sub-graphs it has access to, what outputs it produces
- Schedule config: cron schedule, continuous (24/7), or event-triggered
- Tool provisioning: controlled access grants to DigiGraph sub-graphs, DigiSearch indexes, DigiQuant tools
- Audit trail: immutable JSONL log of every action taken autonomously — critical accountability layer for agents operating without human supervision
- OpenClaw runtime: the agent execution layer underneath DigiClaw

**Confirmed use cases:**
- Atlas runner: the daily delta research cycle, weekly full generation, and monthly rollup are DigiClaw-scheduled jobs — this is what makes Atlas run reliably without manual execution
- Strategy monitor: watches a deployed live strategy's P&L, flags drift, takes defined actions on threshold breach
- Strategy explorer: runs Kairos autonomously in the background, continuously iterating on strategy ideas and populating the research library
- Code reviewer: scheduled agent that reviews recent commits against quality criteria and files issues on failures

**Why the audit trail matters:** When autonomous agents make decisions — modifying research files, flagging strategy drift, triggering rebalancing recommendations — there must be an immutable record. DigiClaw's audit log is the accountability layer for everything that runs without a human in the loop.

**ADDM (Adaptive Drift Detection Monitor):** Detects when autonomous agent outputs or running strategy behavior deviates from expected patterns — both strategy performance drift (vs. backtest baseline) and agent output quality drift (outputs changing character over time). Flags for human review before automated action.

**Current state:** Heartbeat polling (DigiGraph, DigiQuant health) and JSONL audit logging implemented. OpenClaw integration, agent definition framework, and scheduling system not yet built. Atlas daily cycle still runs manually — migrating to DigiClaw is a near-term priority.

**12-month roadmap:**
- OpenClaw integration
- Agent definition schema and registry
- Cron and continuous scheduling
- Atlas daily cycle running automatically via DigiClaw
- Strategy performance monitor agent
- DigiClaw dashboard (agent status, audit log viewer)

**Open source vs. proprietary:** DigiClaw framework — open. The specific agent definitions (what Atlas does, how the strategy monitor reasons) — proprietary.
