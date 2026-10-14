# Review: PR #4750 — fix(occ): teach zammad_-prefixed tool names in tenant prompt

- Reviewer: subagent (fresh-context review, per task brief; no subagents, no push/merge)
- Subject: PR #4750, `task/4749-occ-prompt-tool-prefix` → `develop`, single commit `55a1dc7d`
- Verdict: **APPROVE** (diff correct; do NOT merge until in-flight CI goes green — mergeState is BLOCKED at review time)
- Severity counts: 0 errors · 0 warnings · 1 info (count correction vs. ticket brief, not a defect)

## Scope

3 files, +3/−3 (one long-line change per file — the OCC `researchSystemPrompt` inside the `DIGI_TENANT_CORPUS_MAP` blob in each of its 3 homes). Single-issue scope, no drive-bys. All three per-file diffs are byte-identical in their differing segments (verified via SequenceMatcher opcode comparison).

## Checks (all pass)

1. Only intended substitutions, nothing else touched — each file's old→new delta is exactly 9 opcode segments, all inside the ticket-recipe paragraph: (a) prefix-rule insert `; exposed as zammad_<name> -- always use the full prefixed name`; (b) 4 renames `aggregate_tickets`→`zammad_aggregate_tickets`, `get_ticket`→`zammad_get_ticket` (×2), `ticket_report`→`zammad_ticket_report`; (c) 2 made-explicit `zammad_search_tickets` calls where the old text only implied the tool in prose (`title:<term> / article.body:<term> search per question term` → `zammad_search_tickets call per question term (… queries)`; `customer.email:<addr> finds the latest ticket, get_ticket…` → `zammad_search_tickets with customer.email:<addr> finds the latest ticket; zammad_get_ticket…`).
2. No bare ticket-tool mentions remain — regex `(?<!zammad_)(?<!\w)(aggregate_tickets|search_tickets|get_ticket|ticket_report|list_tickets)` over all ADDED lines: 0 hits in all 3 files. Leftover non-prefixed tokens (`title:<term>`, `article.body:<term>`, `state_category`, `group_by`, `state.name:open`, `customer.email:<addr>`, `since_days`, `created_at`) are Zammad query/parameter language, not tool names — correctly out of scope. `list_tickets` appears in neither old nor new text (no such recipe step); not a defect.
3. Prefix-rule sentence present in all 3 files (`exposed as zammad_<name>` count = 3, one per added line).
4. Rationale grounded: `digigraph/src/digigraph/orchestration/mcp_client.py:492` (`prefixed_tool_name`) + `:505` (`split_prefixed_tool_name`), with `{"error": f"Unknown tool: {name}"}` runners (e.g. `digigraph/src/digigraph/agents/analysis/runner.py:157`) — bare names fail, so the rename is load-bearing, not cosmetic.

## Findings

- INFO — Brief said "5 call sites + 1 rule sentence"; the diff actually carries 6 tool-call mentions (4 renames + 2 newly-explicit `zammad_search_tickets`) + 1 rule sentence = 7 `zammad_` strings per file. Count correction only; every instance is correct.

## Evidence (PR new-side line numbers from hunk headers)

- `apps/digithings-stack-cloudflare/src/index.ts:128` (hunk `@@ -125,7 +125,7 @@`)
- `apps/digithings-stack-cloudflare/wrangler.toml:289` (hunk `@@ -286,4 +286,4 @@`)
- `infra/digichat-release/compose.profile-a-bundle.override.yml:6` (hunk `@@ -3,7 +3,7 @@`)

## CI / merge readiness at review time

`mergeable: MERGEABLE`, but `mergeStateStatus: BLOCKED` — `Analyze (javascript-typescript)`, `Analyze (python)`, and `web / lint` still IN_PROGRESS; completed checks SUCCESS. Merge only after required CI is green per repo policy.
