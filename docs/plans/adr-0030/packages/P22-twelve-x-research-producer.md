# P2.2 — Confirm twelve-x research publish matches the stage-1 board

**Lane:** Needs a GitHub token that can read `digithings-ai/twelve-x`, then stronger review. OpenCode free is the wrong lane until step 0 passes.

**Parent:** #4762.

## Goal

The twelve-x producer still publishes `fx_daily_digest`, `fx_research_history`, `fx_relevance_ledger`, `fx_events_snapshot`, and `fx_consensus_snapshot` with the columns the hub reads. A producer-side test locks those column names. Recommendation policy (relevance weights, what gets ingested, strategist text) does not change.

## Non-goals

- Do not change ranking, freshness weights, or which notes are ingested.
- Do not wire scrapers onto `digifetch`.
- Do not add a Python dependency from twelve-x onto this monorepo.
- Do not merge Supabase projects.
- Do not edit digiquant in the twelve-x PR. If a column is missing, comment on this issue and stop. Do not "fix" the hub types in digithings from the twelve-x agent.

## Step 0 — access gate

```bash
gh api repos/digithings-ai/twelve-x --jq .full_name
```

Expected on success: `"digithings-ai/twelve-x"`.

If the response is HTTP 404 or 403: comment on this issue with the status code and stop. Do not create files. Do not guess paths from the upload names (`graph.py`, `nodes/trade_ideas.py`, `nodes/digest.py`, `timeframe.py`). Those names were not verified in the planning session.

## Files this monorepo already names (open these first; do not create them)

| Path | Where this repo mentions it |
|------|------------------------------|
| `twelve_x/nodes/scrape.py` | `digifetch/ARCHITECTURE.md` |
| `twelve_x/fx_calendar/scraper.py` | `digifetch/ARCHITECTURE.md` |
| `config.py` (Prime Market and Trading Economics constants) | `digifetch/ARCHITECTURE.md` |
| `.github/workflows/daily_run_asia.yml` | `apps/digithings-cron/src/jobs.ts` |
| `.github/workflows/daily_run_london.yml` | same |
| `.github/workflows/daily_run_new_york.yml` | same |
| `.github/workflows/market_context_ingest.yml` | same |
| `.github/workflows/primemarket_session_heartbeat.yml` | same |
| `.github/workflows/session_catchup.yml` | same |
| `.github/workflows/performance_eval.yml` | same |
| `.github/workflows/archive_maintenance.yml` | same, not a stage |

If a listed file is absent, record that in the PR and keep going only for files that exist. Do not recreate a missing scraper.

## Column contract to lock (from `apps/dashboard/lib/twelve-x/types.ts`)

Digest `fx_daily_digest`: `run_date`, `summary`, `key_themes`, `doc_count`, `broker_count`.

Brief `fx_research_history`: `run_date`, `source_file`, `broker_name`, `analyst_names`, `central_thesis`, `brief_markdown`, `trader_relevance`, `currency_views`.

Currency view element: `currency`, `direction`, `conviction`. Optional on the reader: `signal`, `rationale`, `key_facts`. Leave `targets` as the producer already stores them. Do not change their shape.

Ledger `fx_relevance_ledger`: `run_date`, `source_file`, `view_index`, `broker_name`, `currency`, `direction`, `conviction`, `relevance`, `classification`, `reason`.

Event `fx_events_snapshot`: `run_date`, `event_key`, `event_name`, `event_date`, `category`, `mentions`.

Consensus `fx_consensus_snapshot`: `run_date`, `currency`, `timeframe`, `weighted`, `score`. `timeframe` values the hub types as the contract are `medium` and `long`. Do not add a third consensus value. If the producer already writes only those two, add a test that asserts the writer’s literal set is `{"medium", "long"}`. If you cannot find a closed set in source, stop and comment. Do not invent a mapping from free strings.

## Steps after the access gate

1. Search the producer for the table names above (`rg -n "fx_daily_digest|fx_research_history|fx_relevance_ledger|fx_events_snapshot|fx_consensus_snapshot"`).
2. Add one unit test beside the publisher you found. Build a row dict with the required keys and assert each key is present. Use the producer’s existing test style and fixtures. Do not call the network.
3. Do not change function bodies that decide scores, weights, or which documents are kept. A test-only diff is the success case.
4. Map the seven hub copy steps onto stages in a comment in the test module, not in new runtime code:
   - 01 Calendar, 02 Ingest desk research, 03 Score relevance, 04 Digest → stage 1 research.
   - 05 Synthesize ideas and 06 Attach levels → stage 2 (out of scope here; see P3.2).
   - 07 Daily board → publish, not a stage.
5. Open the PR on `digithings-ai/twelve-x` into that repo’s default branch. Title: `test(twelve-x): lock research publish columns for the stage-1 board`. Body links this digithings issue and #4762. If you cannot open a twelve-x PR, push nothing to digithings and comment the column findings on this issue instead.

## Acceptance checklist

- [ ] Step 0 returned the repo full name. The PR description quotes it.
- [ ] Tests assert required column names for the five tables.
- [ ] Diff does not change relevance math, ingest filters, or scraper selectors.
- [ ] No `digifetch` dependency was added.
- [ ] No digiquant import was added.
- [ ] Workflow schedules were not edited.
- [ ] Secrets and `config.py` credential constants were not moved or logged.

## Dependencies

- Blocked by: P2.1 (so the column list is the one the board model validates) and by repo read access.
- Unblocks: nothing in digithings. Producer confirmation only.

## Out of scope / do not touch

- `digiquant/brokers/**`, execution routing, live venues.
- House GitHub Actions schedules and #4761 container moves.
- Trade-idea ranking and level attachment (P3.2).
- Supabase project merge, new secrets, Prime Market passwords.
