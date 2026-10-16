# OSS web search — effort-normalized spend scoring (R6 follow-up)

**Status:** accepted 2026-09-16 (#4251). Closes the R6 "follow-up spec" clause
and integration-review items 5–6
(`2026-09-14-oss-websearch-integration-review.md`). Companion: #4252 re-measured
the live scaffolding anchors (raw receipt:
`2026-09-16-oss-websearch-exa-remeasure-anchors.json`). **Scope: docs + rules
only — no code changes.**

## Problem

OSS `cost_dollars.total` is structurally `0.0`
(`{total: 0.0, provider: "web-oss", breakdown, note}` —
`web/accounting.py::estimate_cost`): the leg is self-hosted, and its dominant
real spend — synthesis LLM tokens — is metered in **digillm telemetry**, never
folded into the envelope. Any gate of the form `total <= maxCostDollars`, or a
router that minimizes `total`, therefore always prefers OSS — including over a
paid path that recalled better — while EXA-backed paths report real dollars
(`costDollars.total`). The two families are not comparable on `total` at all
(integration review item 6, ruling R6a–c).

## Metric definitions (the scoring triple)

One number cannot describe OSS spend. Score every turn on three axes; every
routing/budget gate MUST use at least two, and none may use `total` alone.

| Axis | Definition | Source | Effort-proportional |
|------|------------|--------|---------------------|
| **stage-ms** | measured stage latencies of one turn: `search_ms`, `fetch_ms`, `rerank_ms`, `synthesis_ms`, `total_ms` | turn `usage` — `TurnUsage` (`{searches, pages_fetched, pages_cited, llm_calls, "<stage>_ms"}`; Phase B §Accounting keys) | yes — the preset scales how many pages are searched/fetched/cited |
| **token-dollars** | metered LLM spend for the turn's synthesis calls | digillm telemetry: `CallPurpose.WEB_SEARCH` (`digillm/src/digillm/telemetry.py:25`), plumbed per call by digigraph (`digigraph/src/digigraph/llm_client.py:295`); aggregate per workspace/session | yes — thorough cites more context |
| **counts** | structural work of one turn: `cost_dollars.breakdown.{searches, pages_fetched, llm_calls}` | `estimate_cost` (self-reported, zero-priced but effort-proportional) | yes |

**Effort-normalized efficiency score.** Report the triple, not a scalar, until
a digillm join key (workspace/session) exists:

- `cited_sources` = `len(results)` = `usage.pages_cited` (output quantity).
- `effort_score` = `cited_sources / (total_ms/1000 + ε)` — **comparisons are
  valid only within one effort preset**: `fast` (live_top_n 8 / fetch 5 /
  cited 5) vs `thorough` (20 / 10 / 8), Phase B §Effort presets. A
  fast-vs-thorough delta is a cost-of-effort question answered by the preset
  table, not by the score.
- `token_dollars` is reported alongside; while it is unavailable the displayed
  number MUST carry the caveat **"OSS total excludes LLM spend"**.
- Paid comparators (EXA `costDollars.total`, per-call `$0.007`-class shallow /
  agent-run class deep — see the re-measure receipt) are real dollars **only on
  EXA-backed paths** and are never mixed into an OSS total.

## Routing & budget rules (normative)

1. No router, budget gate, or backend comparison may branch on
   `cost_dollars.total` alone while any backend reports `0.0` (R6a).
2. Budget gates MUST combine stage-ms with LLM telemetry counts:
   `breakdown.llm_calls > 0 ⇒ consult digillm telemetry` (R6a). When the
   telemetry aggregate is unavailable, the gate treats OSS token spend as
   **UNKNOWN** — fail open and log; never assume `$0`.
3. Backend choice stays explicit (`provider` param / per-watch `backend` label /
   effort preset). Never cheapest-total-wins (R6c).
4. Budgets are declared **per effort preset**. A single absolute dollar cap
   spanning `fast` and `thorough` is invalid by construction (thorough fetches
   and cites strictly more).
5. Every operator-facing cost comparison prints "OSS total excludes LLM spend"
   until token-dollars are joined into the displayed number (R6 close-out).

## Copy audit (landed operator docs)

| Document | Statement | Disposition |
|----------|-----------|-------------|
| `digisearch/ARCHITECTURE.md` §Phase B accounting keys | `cost_dollars` advisory; "`total` MUST NOT drive budget/routing gates alone" | kept, extended with the effort-normalized rule + caveat pointer (#4251) |
| `digisearch/ARCHITECTURE.md` `WebSearchData` interchange table | EXA `{total: 0.012}` vs OSS `{total: 0.0, …}` "advisory-only" | amended: OSS cell now says "excludes LLM spend" |
| Phase A spec §0 / §Interfaces | `total: 0.0` "advisory, not billed" | OK as-is (self-hosted framing is accurate) |
| Phase B spec Goal/R6 (`~$0.007–0.012` shallow, `~$0.26` deep) | live scaffolding anchors | re-measured 2026-09-16 (#4252): shallow unchanged, deep now `$0.0887` — anchors marked provisional with receipt provenance |
| Phase B spec §"live gate is SCAFFOLDING" / §Task 6 Step 4 | single-key, single-day samples | refreshed with the #4252 receipt; environment re-measurement stays mandatory before SLOs |
| Integration review R6 / items 5–6 | ruling source | OK (historical record) |

## Non-goals

- No single scalar score until a digillm join key (workspace/session) exists.
- Monitor runs (Phase C `MonitorRun`) persist `cost_dollars` but not `usage`;
  per-run stage-ms for watches is out of scope here (research-mode digests carry
  the answer; the run keeps the turn's `cost_dollars`).
- Live anchor re-measurement lives in #4252 and its receipt; this spec does not
  restate the numbers as constants.

## References

- Integration review: `2026-09-14-oss-websearch-integration-review.md` (R6, items 5–7)
- Phase B: `2026-09-14-oss-websearch-phaseB-web-research-turn.md` (§Accounting keys,
  §Effort presets, R6)
- Anchor receipt: `2026-09-16-oss-websearch-exa-remeasure-anchors.json`
- digillm telemetry: `digillm/src/digillm/telemetry.py:25` (`CallPurpose.WEB_SEARCH`)
- digigraph plumbing: `digigraph/src/digigraph/llm_client.py:295`
