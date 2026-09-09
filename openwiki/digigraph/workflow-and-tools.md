---
type: behavior-guide
title: digigraph Workflow and Tools
description: digigraph workflow behavior — graph nodes and routing, tool allowlist, digistore datasets, two-tier compaction, and checkpoints.
tags: [digigraph, workflow, langgraph, tools]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-f7a337c6ddca8aa6af23ce93
    resource: repo://digigraph/src/digigraph/compaction.py
  - id: openwiki-source-8100027abb34a8983e244d2e
    resource: repo://digigraph/src/digigraph/digistore.py
  - id: openwiki-source-c371fe6b6859586069a9e24e
    resource: repo://digigraph/src/digigraph/graph/graph.py
  - id: openwiki-source-1c79b8709f0405a71bcef2fd
    resource: repo://digigraph/src/digigraph/graph/nodes.py
  - id: openwiki-source-90658d6266af009ade56ec79
    resource: repo://digigraph/src/digigraph/orchestration/registry.py
  - id: openwiki-source-b8ce71e484c565ab6667e332
    resource: repo://digigraph/src/digigraph/tool_policy.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digigraph Workflow and Tools

A digigraph run is a LangGraph traversal over lean state, with tools
dispatched through the registry allowlist, large data parked in
digistore, and long transcripts compacted in two tiers. Every behavior
below traces to the node, registry, store, or compaction module — new
capabilities belong in those seams, never inline in a node.

## Nodes and routing

`graph/nodes.py` implements `supervisor_node` (opt-in),
`strategy_validator_node`, `backtest_node` (digiquant jobs + fallback),
and `optimize_node`, wired in `graph/graph.py` with conditional edges
(`_route_after_research`, `_route_after_validate`, `_route_after_backtest`)
that skip or repeat stages by profile and result. `tool_policy.py`
computes the per-workflow allowlist (`allowed_tool_names_for_workflow`,
web-search opt-in) consumed as `ToolContext.allowed_tool_names`.

## digistore

`digistore_put/get/list/profile` manage session-scoped named datasets
under a session directory: `put` writes rows and returns a `dataset_ref`,
`get` resolves a ref to a path on disk, `profile` reports schema, row
count, and samples. Paths assert under the session dir (no traversal).
Multi-turn context prepends a `[Current session datasets: …]` block so the
LLM references prior results by ref; cross-restart persistence needs a
non-memory `DIGI_CHECKPOINTER`.

## Two-tier compaction

Long research transcripts compact without losing evidence: tier 1
truncates tool results (`apply_tier1_truncation`, capped by digillm's
`DIGI_TOOL_MESSAGE_MAX_CHARS`), tier 2 summarizes tagged messages, and
originals offload to the session workspace (`offload_tool_result`,
`offload_evicted_messages`) with only a lean `_compaction_event` kept on
`WorkflowState`. Tuned via `CompactionConfig` / `DIGI_COMPACTION_*`.
Never stub same-turn `execute_tool` results before digillm injects them.

## Planning executor

`planning/executor.py` runs multi-step plans with topological sort and
parallel steps — the seam for decomposing work the linear node chain
cannot express.

## Checkpoints

`DIGI_CHECKPOINTER=memory|sqlite|postgres` selects LangGraph checkpoint
persistence explicitly in production; `memory` is dev-only and does not
survive restarts. Never use `MemorySaver` unwittingly in production.
