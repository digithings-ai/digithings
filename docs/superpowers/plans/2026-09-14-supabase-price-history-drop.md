# Drop retired Supabase market-data tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the last Supabase `price_history` stragglers to R2/live sources, then drop `price_history`, `price_technicals`, and their two dependent views in a new numbered migration.

**Architecture:** Remove (not branch): same-day opens come from a live fetch instead of the intraday Supabase writer; browser surfaces lose their Supabase fallbacks and read only the Worker market API; backfill scripts and `get_price_technicals` go R2-only; migration 127 drops the two views first, then the two tables.

**Tech Stack:** Python (Polars only, ruff line 100), Supabase Postgres (migration chain + RLS/grants), Cloudflare Worker market API (`GET /v1/market/tickers`, `GET /v1/market/closes`), Next.js static-export dashboard + digiquant-web, yfinance (already in the digiquant `prices` extra).

**Spec:** Issue #4053 (this workstream). Prior art: #4013 (R2 cutover, closed; plan `docs/superpowers/plans/2026-09-14-supabase-r2-market-data-migration.md`), #3951 (deferred DROPs), migration `124_drop_market_data_tables.sql` (deliberate no-op — never un-comment or re-edit it).

## Global Constraints

- Polars only — never pandas. Ruff line length 100.
- Every task PR body carries `Refs #4053` (Task 5 carries `Fixes #4053`, which closes the issue on merge to develop — develop is the default branch).
- Branch base is `origin/develop`; task PRs merge into `develop` with a merge commit when green (autopilot per AGENTS.md).
- Review coverage per task: `reviewed:agent` label + a comment opening with the `<!-- in-session-review -->` marker before merge.
- Do NOT merge `main` (human gate). Do not touch `digikey/` auth, brokers, or live-trading paths.
- Never run DDL against production. The 127 migration is applied by a human via the db-migrate path; agents ship the file + tests + PR only.
- Python tests: `PYTHONPATH=$PWD/digiquant/src /Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest <paths> -q -o pythonpath=$PWD/digiquant/src` from the worktree root.
- Dashboard JS tests: `/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run` from `cloudflare/dashboard`; digiquant-web from `cloudflare/digiquant-web`. Dashboard has eslint (`npm run lint`); `cloudflare/digiweb/web` has no eslint config.
- `yaml.safe_load` parses the workflow `on:` key as boolean `True` in pin tests.
- No production writes or network in tests. Commit style `... (#4053)`.
- One worktree per task or task cluster: `git worktree add -b task/4053-<slug> .worktrees/task-4053-<slug> origin/develop`. Do not disturb other `.worktrees/*`.

## Decisions

| ID | Decision | Status |
|----|----------|--------|
| D1 | Same-day opens come from a live fetch at execution time (yfinance), replacing the intraday `fetch-quotes --supabase` writer. `prices_live` cannot serve opens (columns are only ticker/price/change/change_pct/quoted_at/updated_at). | DEFAULT — confirm with owner (alternative: R2 intraday generation) |
| D2 | Both dependent views are dropped in 127, not repointed: `price_history_tickers` (replaced by Worker `/v1/market/tickers` via `fetchMarketTickers`) and `public_price_latest` (replaced by the Worker closes seed in `useLivePrices` Lane 1). A Postgres view cannot read R2, and a replacement latest-close table would contradict the drop. | DEFAULT — confirm with owner |
| D3 | Browser fallbacks are removed outright (env var becomes required), not kept. Keeping a fallback to a dropped table is a crash, not a fallback. | decided (forced by the drop) |
| D4 | Migration number is `127` (`126_product_invite_plan_floor.sql` is the current max on develop; `tests/dq/test_migration_prefix_uniqueness.py` guards prefixes). | decided |
| D5 | Enablement gate: `NEXT_PUBLIC_MARKET_DATA_URL` must be live in prod (dashboard + digiquant-web Pages env) and the Worker CORS allowlist must cover prod origins BEFORE the T2/T3 removal PRs merge. Local dev needs `localhost:3000` in `MARKET_DATA_ALLOWED_ORIGINS` (Phase C follow-up). | decided |
| D6 | Subagent-driven execution, one PR per task. | decided |

## Straggler inventory (verified on origin/develop)

- `execute_at_open.py`: `_fetch_open` (L237) / `_open_marks` (L488) fall back to Supabase when `d > seal`; fed by the intraday `fetch-quotes --supabase` writer (`.github/workflows/pipeline-digiquant-prices.yml` intraday step; calendar-sync step in the same workflow writes `trading_calendar` and STAYS).
- Dashboard: `fetchComparablePriceHistory` (`cloudflare/dashboard/lib/queries.ts:1577-1613`), position price fill (`:1116-1137`), holding marks (`lib/observability-queries.ts:981-993`), universe (`:760-775` reads `price_history_tickers`).
- digiquant-web: benchmark block (`lib/live/useLivePortfolio.ts:98-118`), Lane 1 seed (`lib/live/useLivePrices.ts:81-91` reads `public_price_latest`; seed contract in `lib/live/quote-transforms.ts:140`, `lib/live/types.ts:7,49,59`; `components/landing/LiveTickerRow.tsx:50`).
- Nine scripts keep Supabase bodies as the flag-off path (see #4013 plan §D): `verify_nav_replay.py:510-521`, `refresh_performance_metrics.py:119/255/471`, `refresh_attribution.py:85`, `execute_at_open.py:233/479`, `finalize_period_accounting.py:154`, `backfill_execution_prices.py:51`, `position_entry_from_events.py:56`, `fill-entry-prices.py:53`, `backfill_context.py:67/82/96/105`; plus `get_price_technicals` Supabase body (`digiquant/src/digiquant/research/data/queries.py:261`).
- Live dependents in prod: views `price_history_tickers` (migration 018; anon/authenticated SELECT) and `public_price_latest` (migration 052).Fees, slippage, and fills are unaffected — this plan touches market-data reads and the two retired tables only.

---

### Task 1: Same-day opens from a live fetch; retire the intraday Supabase writer

**Files:**
- Create: `digiquant/src/digiquant/data/prices/live_opens.py`
- Modify: `digiquant/scripts/research/execute_at_open.py` (`_fetch_open`, `_open_marks`, D3 seal-gate comments)
- Modify: `.github/workflows/pipeline-digiquant-prices.yml` (delete the intraday `fetch-quotes --supabase` step; keep calendar sync; update header comments)
- Test: `tests/dq/data/test_live_opens.py` (new); extend `tests/scripts/test_digiquant_prices_workflow.py` (or the prices-workflow pin file) to assert no `fetch-quotes --supabase` step remains

**Interfaces:**
- Consumes: R2 seal via `r2_manifest_seal()` (tuple[date, int]); existing D3 gate shape (`seal, _ = r2_manifest_seal()`; R2 when `d <= seal.isoformat()`).
- Produces: `fetch_live_open(ticker: str, d: str) -> float | None` — today's open via yfinance (single-ticker, `period="1d"`, first open; `None` on any failure, never raises); `fetch_live_opens(tickers: list[str], d: str) -> dict[str, float]` batch wrapper skipping failures. Later tasks rely on the `| None` / skip-failure contract.

- [ ] **Step 1: Write the failing test**

```python
def test_live_open_returns_none_on_fetch_failure(monkeypatch):
    monkeypatch.setattr("yfinance.download", _raise)
    assert fetch_live_open("AAA", "2026-09-14") is None


def test_live_open_reads_first_open(monkeypatch):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: _frame(open=101.5))
    assert fetch_live_open("AAA", "2026-09-14") == 101.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD/digiquant/src /Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/data/test_live_opens.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL with "No module named 'digiquant.data.prices.live_opens'" (or ImportError)

- [ ] **Step 3: Write minimal implementation**

```python
def fetch_live_open(ticker: str, d: str) -> float | None:
    """Today's open for ticker via a live fetch (same-day opens have no sealed R2 bar, D1)."""
    import yfinance as yf

    try:
        frame = yf.download(ticker, start=d, end=d, period="1d", progress=False)
        o = frame["Open"].iloc[0]
    except Exception:
        return None
    return float(o) if o is not None and math.isfinite(float(o)) else None
```

- [ ] **Step 4: Rewire `_fetch_open` / `_open_marks` same-day branch to `fetch_live_open(s)`; delete the intraday writer step; update the workflow pin test**

Run: same pytest + `actionlint .github/workflows/pipeline-digiquant-prices.yml`
Expected: PASS, exit 0

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/prices/live_opens.py digiquant/scripts/research/execute_at_open.py .github/workflows/pipeline-digiquant-prices.yml tests/dq/data/test_live_opens.py tests/scripts/test_digiquant_prices_workflow.py
git commit -m "feat(digiquant): same-day opens from a live fetch; retire intraday Supabase writer (#4053)"
```

### Task 2: Dashboard off Supabase (remove fallbacks; wire the universe)

**Files:**
- Modify: `cloudflare/dashboard/lib/market-data.ts` (add `fetchMarketTickers() -> string[]`, fail-soft `[]`)
- Modify: `cloudflare/dashboard/lib/queries.ts` (`fetchComparablePriceHistory`, position price fill, universe site `:760-775` — market API only, delete Supabase branches)
- Modify: `cloudflare/dashboard/lib/observability-queries.ts` (holding marks — market API only)
- Test: `cloudflare/dashboard/lib/market-data.test.ts` (extend: tickers + no-network-when-unset pins stay)

**Interfaces:**
- Consumes: Task 8 Worker contract (`GET /v1/market/tickers -> {as_of, tickers[]}`; `/v1/market/closes?tickers=&from=&to= -> {as_of, rows[]}`); `isMarketDataConfigured()` gate is DELETED — the env var is required (D3, D5 enablement gate must be live first).
- Produces: dashboard market reads with no `supabase` import for market paths; `fetchMarketTickers` for Task 5's universe grep.

- [ ] **Step 1: Write the failing test**

```ts
it("fetches the ticker universe from the market API", async () => {
  mockFetch({ as_of: "2026-09-13", tickers: ["AAA", "BBB"] });
  expect(await fetchMarketTickers()).toEqual(["AAA", "BBB"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run lib/market-data.test.ts` from `cloudflare/dashboard`
Expected: FAIL with "fetchMarketTickers is not a function"

- [ ] **Step 3: Implement `fetchMarketTickers`; delete the three Supabase fallback branches; point the universe site at it**

- [ ] **Step 4: Run tests + lint**

Run: same vitest + `npm run lint`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(dashboard): market reads R2-API-only; universe from /v1/market/tickers (#4053)"
```

### Task 3: digiquant-web off Supabase (benchmark + Lane 1 seed)

**Files:**
- Modify: `cloudflare/digiquant-web/lib/live/useLivePortfolio.ts` (benchmark block — market API only, delete Supabase fallback)
- Modify: `cloudflare/digiquant-web/lib/live/useLivePrices.ts` (Lane 1 seed reads Worker closes for the book universe instead of `public_price_latest`)
- Test: `cloudflare/digiquant-web/lib/live/market-data.test.ts` (extend: seed mapping test)

**Interfaces:**
- Consumes: Task 8 Worker `/v1/market/closes` (+ `fetchBenchmarkHistory` from Task 10); `isMarketDataConfigured()` gate DELETED (D3, D5 gate live first).
- Produces: no `price_history` / `public_price_latest` reads in `cloudflare/digiquant-web`.

- [ ] **Step 1: Write the failing test**

```ts
it("seeds live prices from Worker closes", async () => {
  mockFetchCloses([{ date: "2026-09-13", ticker: "AAA", close: 100 }]);
  expect(await seedFromWorker(["AAA"], "2026-09-13")).toHaveLength(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run lib/live/market-data.test.ts` from `cloudflare/digiquant-web`
Expected: FAIL

- [ ] **Step 3: Implement the seed + benchmark swap; delete both Supabase branches**

- [ ] **Step 4: Run tests + lint + build**

Run: same vitest + `npm run lint`
Expected: PASS, 0 errors

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(digiquant-web): live prices seeded from the R2 market API (#4053)"
```

### Task 4: Scripts + `get_price_technicals` R2-only

**Files:**
- Modify (delete Supabase market-data bodies, keep R2 branches unconditional): `digiquant/scripts/research/verify_nav_replay.py`, `refresh_performance_metrics.py`, `refresh_attribution.py`, `execute_at_open.py`, `finalize_period_accounting.py`, `backfill_execution_prices.py`, `position_entry_from_events.py`, `fill-entry-prices.py`, `backfill_context.py`, `digiquant/src/digiquant/research/data/queries.py` (`get_price_technicals` only; macro helpers stay)
- Test: update `tests/dq/research/test_*_r2_reads.py`, `test_backfill_context_r2.py`, `test_verify_nav_r2.py`, `tests/dq/test_market_data_parity.py` fixtures as needed (Supabase-path tests for market reads are deleted; R2 tests stay)

**Interfaces:**
- Consumes: Tasks 1–3 (no remaining runtime Supabase market reader outside these bodies).
- Produces: `r2_backend_enabled()` no longer gates market reads in these files (flag may remain as a no-op default for one release; the bodies are R2-only). Rollback after this task is restore-from-generation + replay, not a flag flip.

- [ ] **Step 1: Write the failing test (R2-only assertion)**

```python
def test_no_supabase_market_body():
    src = Path("digiquant/scripts/research/refresh_attribution.py").read_text()
    assert 'table("price_history")' not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD/digiquant/src /Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/research/test_r2_only.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL (bodies still present)

- [ ] **Step 3: Delete the Supabase market bodies file by file; convert tests**

- [ ] **Step 4: Run tests + ruff**

Run: same pytest + `ruff check` + `ruff format --check`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(digiquant): market reads R2-only; remove Supabase bodies (#4053)"
```

### Task 5: Migration 127 drops the tables + views; cleanup

**Files:**
- Create: `digiquant/supabase/migrations/127_drop_market_data_tables.sql`
- Modify: `digiquant/src/digiquant/dashboard/database.types.ts` (remove `price_history`, `price_technicals`, `price_history_tickers`, `public_price_latest` entries — or regenerate via `supabase gen types`)
- Modify: docs/digiquant ARCHITECTURE + RUNBOOK close-out lines naming the tables as live (short note: dropped in 127; macro tables stay)
- Test: `scripts/check-types-sync.sh` if it covers these entries; `tests/dq/test_migration_prefix_uniqueness.py` must pass (127 is free)

**Interfaces:**
- Consumes: Tasks 1–4 (zero runtime readers).
- Produces: the applied migration (human db-migrate path) + a merged PR that `Fixes #4053`.

Migration content (exact):

```sql
-- 127_drop_market_data_tables.sql
-- Requires: every market-data reader on R2/live sources (#4053 Tasks 1-4);
-- NEXT_PUBLIC_MARKET_DATA_URL live in prod (D5). Rollback =
-- restore-from-generation + replay (no flag rollback; tables are gone).
-- macro_series_observations is NOT dropped (FEDPROB/* has no R2 home).
-- trading_calendar is NOT dropped (calendar sync still writes it).
DROP VIEW IF EXISTS public.price_history_tickers;
DROP VIEW IF EXISTS public.public_price_latest;
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS price_technicals;
```

- [ ] **Step 1: Write the migration + a grep pin test asserting no runtime `price_history`/`price_technicals` reader remains outside historical migrations**

- [ ] **Step 2: Run the pin test to verify it fails (stragglers still present)**

- [ ] **Step 3: Land Tasks 1–4 first; then verify the pin passes; run prefix-uniqueness + check-types-sync**

- [ ] **Step 4: Commit (with the Task 4 code already merged)**

```bash
git commit -m "chore(digiquant): drop retired Supabase market-data tables (#4053)"
```

- [ ] **Step 5: Open the final PR with `Fixes #4053`**

## Rollout & Rollback

| Step | Rollout | Rollback |
|------|---------|----------|
| T1 live opens | Merge; at-open job uses live fetch for `d > seal` | Revert PR (intraday writer already deleted — re-add step to restore) |
| T2/T3 browser | Merge AFTER D5 gate live; no fallback remains | Revert PRs (requires tables still present — merge before T5) |
| T4 R2-only | Merge; flag becomes a no-op for market reads | Revert PR (code only; tables still present until T5) |
| T5 migration | Merge file; HUMAN applies via db-migrate | Restore-from-generation + replay (tables gone; no flag rollback) |

Order is load-bearing: D5 enablement → T1 → T2+T3 → T4 → T5 file → human db-migrate apply. Never apply 127 before T1–T4 are merged AND the env var is live in prod.

## Self-Review

1. Spec coverage: #4053 straggler list (D3 opens, fallbacks, tickers view, Lane 1 seed, nine script bodies, `get_price_technicals` body, intraday writer, two views, two tables) — each has a task above. `trading_calendar`, `macro_series_observations`, `prices_live` are explicitly not dropped.
2. Placeholder scan: no TBD/TODO; error handling specified (`| None` / skip-failure / fail-soft `[]`); test commands exact.
3. Type consistency: `fetch_live_open -> float | None`; Worker shapes match Phase C (`{as_of, tickers[]}`, `{as_of, rows[]}`); migration drops views before tables (dependency order).
