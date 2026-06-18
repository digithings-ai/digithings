# Epic #14 — SITAAS Phase 2: POC improvements

## Recap

SITAAS (Stock-Idea-To-Actionable-Strategy, per the user's flagship-pilot framing) is the
first vertical pilot on DigiThings. As described in [docs/VISION.md](../VISION.md), the
SITAAS deployment runs DigiGraph orchestration over DigiSearch's unified content index
(emails, Teams, SharePoint) via LiteLLM — no DigiQuant in the SITAAS data path. Phase 2's
goal is to turn the working POC into a demo-ready multi-turn research assistant by
unblocking multi-turn flows (exposing stored-dataset state to the LLM and orchestrator
tools), improving search quality, and polishing the frontend + configuration story.
The authoritative backlog lives in `projects/sitaas/IMPROVEMENT_IDEAS.md` (confidential;
not in this repo).

## Remaining sub-tasks

Derived from the epic body on GitHub issue #14 plus obvious gaps for a PM-ready pilot.
Items marked `(inferred — confirm with PM)` are not in the issue body but follow from
the architecture and the POC-to-pilot transition.

### High-priority — unblock multi-turn flows

- [ ] Surface `stored_datasets` to the LLM in the research-node prompt so follow-up turns
      can reference previously fetched data without re-ingestion.
- [ ] Expose `digistore_list` and `digistore_profile` as first-class orchestrator tools
      in the DigiGraph MCP registry (`digigraph/orchestration/registry.py`).
- [ ] Refresh `projects/sitaas/README.md` and config samples so they match current
      behavior (tool names, env vars, checkpointer defaults).

### Medium

- [ ] Frontend ECharts rendering — either an Open WebUI plugin or a SITAAS-specific
      client — so chart payloads render inline instead of as raw JSON.
- [ ] Enable the LangGraph checkpointer by default for SITAAS (pick `sqlite` or
      `postgres` based on deployment target; document `DIGI_CHECKPOINTER`).
- [ ] Search-quality improvements: facets inside the agent loop, Azure semantic search,
      and an optional speller stage.

### Lower

- [ ] Configurable limits: max rows per `fetch_all`, dataset size caps, and a
      `data_engineer` node timeout — all surfaced via env/config rather than hard-coded.
- [ ] Natural-language → filter hints (let the LLM propose DigiSearch filters from
      free-text user intent).

### Gaps not in the issue body (inferred — confirm with PM)

- [ ] Latency budget + profiling pass across the research loop (DigiGraph node timings,
      DigiSearch query latency, LiteLLM round-trips) with a target p95 per turn.
- [ ] User-feedback capture (thumbs-up/down per answer, free-text comment) wired into
      the audit JSONL so we can iterate on prompt + ranking.
- [ ] Demo polish: recorded walkthrough, screenshot set, and a scripted happy-path
      prompt sequence for pilot stakeholders.
- [ ] Integration-test suite covering the SITAAS workflow end-to-end (DigiGraph →
      DigiSearch → LiteLLM), runnable under `make test-e2e`.
- [ ] Cost-per-request tracking — token + vector-query counters attached to each
      `workflow_id` via DigiSmith spans, surfaced on `/v1/status` or an internal
      dashboard.

## Done-criteria for the epic

- Each sub-task above is a separate GitHub issue on Project #1, labelled `sitaas` and
  linked back to #14.
- High-priority items ship before any external SITAAS demo.
- `projects/sitaas/IMPROVEMENT_IDEAS.md` is reconciled with the issue tracker — items
  either migrated to issues or explicitly dropped with a note.
