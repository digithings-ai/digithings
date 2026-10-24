---
type: behavior-guide
title: digigraph Workflow and Tools
description: digigraph workflow behavior — graph nodes and routing, tool allowlist and web-search opt-in, digistore datasets, two-tier compaction, and checkpoints.
tags: [digigraph, workflow, langgraph, tools]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
sources:
  - id: openwiki-source-f7a337c6ddca8aa6af23ce93
    resource: repo://digigraph/src/digigraph/compaction.py
  - id: openwiki-source-8100027abb34a8983e244d2e
    resource: repo://digigraph/src/digigraph/digistore.py
  - id: openwiki-source-c371fe6b6859586069a9e24e
    resource: repo://digigraph/src/digigraph/graph/graph.py
  - id: openwiki-source-1c79b8709f0405a71bcef2fd
    resource: repo://digigraph/src/digigraph/graph/nodes.py
  - id: openwiki-source-58789704b727014fe015169c
    resource: repo://digigraph/src/digigraph/graph/research.py
  - id: openwiki-source-94ec0d8621cfa2689f75a43d
    resource: repo://digigraph/src/digigraph/graph/state.py
  - id: openwiki-source-90658d6266af009ade56ec79
    resource: repo://digigraph/src/digigraph/orchestration/registry.py
  - id: openwiki-source-b8ce71e484c565ab6667e332
    resource: repo://digigraph/src/digigraph/tool_policy.py
  - id: openwiki-source-8f587e40d690edc498fbff40
    resource: repo://digigraph/src/digigraph/workflow.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
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
that skip or repeat stages by profile and result. The research step is a
compiled subgraph (`build_research_subgraph`), and an optional supervisor
is inserted ahead of it when `DIGI_SUPERVISOR=1`. `backtest_node` prefers
digiquant's `POST /v1/jobs/backtest` + status polling, then the SSE
`/backtest/start` path, then synchronous `POST /run_backtest`; it catches
transient client errors internally and returns an error-state dict rather
than raising, so node-level LangGraph `RetryPolicy` would be dead code.

## Tool allowlist and policy

`tool_policy.py` resolves the per-workflow tool allowlist and the
deployment-grain `tool_choice` mandate. `allowed_tool_names_for_workflow`
uses **most-specific-wins** precedence: an explicit request
`allowed_tools` (including an empty list, which means *no tools*) wins;
otherwise project `agents.allowed_tools`, then env `DIGI_ALLOWED_TOOLS`
(comma-separated); if none apply it returns `None` (all registered tools
allowed). The result is then passed through the web-search opt-in
(`apply_web_search_opt_in`), the disabled-token subtraction
(`apply_disabled_tools`), and a `force_tool` re-add that injects only the
locate tool (never its `fetch_all`/`get_note` siblings).

`None` (unrestricted) and `frozenset()` (deny-all) are distinct and must
never be conflated: `frozen_from_state_list` deliberately avoids a falsy
check because `frozenset([]) if [] else None` would silently reopen every
tool. The allowlist is serialized to `WorkflowState.allowed_tool_names`
(sorted, for stable checkpoints) and enforced in two places: `get_tools`
filters tool exposure, and `execute` denies out-of-allowlist calls with a
`tool_not_allowed` error plus a `tool_denied` audit event.

Web search (`web_search`) is opt-in (#3420) and never in the default
corpus allowlist. `is_web_search_tool` matches both the native name and
the MCP-proxied `{server_id}_web_search` form, which is the same
capability exposed by a digisearch MCP server and must obey the same
request opt-in. Opt-in can never escalate past the operator/project
allowlist: if web search is not already permitted, enabling the flag does
nothing; if it is permitted but the request opts out (the default), both
forms are stripped so the model cannot reach the public web through
either path. `apply_mcp_extra_tools` folds discovered remote-MCP tool
names into the allowlist and is the single policy point for the MCP-extra
union in `research_node`; because the MCP proxy has no handler-side
availability check, it materializes a concrete allowlist (registry minus
disabled, plus live extras) for an otherwise-unrestricted session when a
proxied `{id}_web_search` would otherwise be admitted. `execute` adds a
second, discovery-independent gate (`is_proxied_web_search_tool`) so a
model-guessed proxied name cannot reach the remote tool even when an MCP
list failure left the session unrestricted.

Disabled tools map client catalog ids and slash aliases onto registered
tool names (`expand_disabled_tool_tokens`): `digisearch`/`search` strip
`digisearch` + `digisearch_fetch_all`; `digivault`/`vault`/`docs` strip
`digivault_search_notes` + `digivault_get_note`; unknown tokens are
ignored. `require_tool_calls_for_workflow` resolves the
`tool_choice="required"` mandate as a **floor**, not an override: project
`agents.require_tool_calls` and env `DIGI_REQUIRE_TOOL_CALLS` can only
add the requirement, never be lowered by a request-level `False`, because
the bare bool has no registry ceiling to bound it (unlike the allowlist)
and digigraph's `/v1/chat/completions` is reachable by clients outside
digichat's control.

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
