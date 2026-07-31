# Atlas Supabase Schema

Live Atlas Supabase schema. Source of truth: the numbered migrations under
`digiquant/supabase/migrations/`. This document inventories the
17 live tables (12 pre-024 + 5 new in migration 024) and diagrams the
high-value relationships.

> ADRs: [ADR-0008 research schema](../../../docs/adr/0008-atlas-research-schema.md),
> [ADR-0009 Supabase persistence](../../../docs/adr/0009-atlas-supabase-persistence.md),
> [ADR-0010 first-class thesis + deliberation](../../../docs/adr/0010-atlas-first-class-thesis-deliberation.md).

## ERD (primary relationships)

```mermaid
erDiagram
    daily_snapshots  ||--o{ positions             : "date"
    daily_snapshots  ||--o{ theses                : "date"
    daily_snapshots  ||--o{ position_events       : "date"
    daily_snapshots  ||--o{ documents             : "date"
    daily_snapshots  ||--o{ portfolio_metrics     : "date"

    theses           ||--o{ thesis_vehicles       : "(date, thesis_id)"
    theses           ||--o{ positions             : "thesis_id"

    documents        ||..o{ thesis_vehicles       : "source_exploration_key"
    documents        ||..o{ deliberation_rounds   : "deep_dive_document_key"
    documents        ||..o{ analyst_coverage      : "current_recommendation_key"
    documents        ||..o{ deep_dive_triggers    : "deep_dive_document_key"

    deliberation_sessions ||--o{ deliberation_rounds : "session_id"
    deliberation_sessions ||--o{ deep_dive_triggers  : "session_id"

    price_history        ||--o{ price_technicals : "(date, ticker)"
    price_history_tickers ||..|| price_history   : "view"

    macro_series_observations ||..|| daily_snapshots : "obs_date"
```

> Solid lines are FKs; dashed lines are logical pointers (documents.document_key
> strings — not enforced by FK because `documents` is partitioned and the
> pointer target may be in any partition).

## Per-table inventory

### Portfolio core (migration 001, partitioned since 011)

| Table | PK | Purpose |
|-------|----|---------|
| `daily_snapshots` | `(date)` | One consolidated JSON snapshot per calendar day. Root of the daily pipeline. |
| `positions` | `(date, ticker)` | Daily position book; one row per held ticker. |
| `theses` | `(date, thesis_id)` | Active investment theses per day; H1–H3 writers + H9 sync. Migration 025 adds daily thesis fields. Migration 056 adds stable `topic_key` and a partial unique `(date, topic_key)` index so only one nonterminal market opinion exists per topic/date. |
| `position_events` | `(id uuid)` | Every open / close / rebalance against a position with reason tag. |
| `documents` | `(date, document_key)` | JSONB payload store for every narrative / structured artifact. Doc-type CHECK set by migration 023. |
| `nav_history` | `(date)` | Daily portfolio NAV. |
| `portfolio_metrics` | `(date, metric)` | Pre-computed Sharpe, vol, drawdown, exposure metrics. |

> `benchmark_history` was dropped in migration 010 — benchmark close series (SPY / QQQ / IWM …) now live as rows in `price_history`.

### Market data (migrations 005 / 007 / 015 / 018)

| Table | PK | Purpose |
|-------|----|---------|
| `price_history` | `(date, ticker)` | OHLCV history for all watchlist tickers. |
| `price_technicals` | `(date, ticker)` | 35+ pre-computed TA indicators per (date, ticker). |
| `macro_series_observations` | `(source, series_id, obs_date)` | FRED / Frankfurter / crypto FNG time series. |
| `price_history_tickers` | _(view)_ | Distinct tickers currently in `price_history`. |

### Hermes deliberation — new in migration 024

| Table | PK | Purpose |
|-------|----|---------|
| `thesis_vehicles` | `(date, thesis_id, ticker)` | Per-thesis vehicle map; FK → `theses (date, thesis_id)`. |
| `deliberation_sessions` | `(session_id UUID)` | One row per H6 deliberation session; `kind` is legacy (`baseline`, `delta_scoped`, `monthly`) — daily graph uses thesis-first H6 without separate session kinds. |
| `deliberation_rounds` | `(id BIGSERIAL)` | Round-loop persistence; unique on `(session_id, ticker, round_number)`. |
| `analyst_coverage` | `(date, ticker)` | Daily denormalized analyst ↔ ticker index. |
| `deep_dive_triggers` | `(id BIGSERIAL)` | Audit trail of every recess- or delta-watch- or manually- forced deep-dive. |

### Strategy store — new in migration 046 (#1064)

This project is the unified DigiQuant **`core`** backend (Supabase display name `core`;
local alias still `project_id "digiquant-atlas"`). Migration 046 adds the strategy store
(additive only — no existing table touched). See
[`docs/adr/0021-digiquant-supabase-project-topology.md`](../../docs/adr/0021-digiquant-supabase-project-topology.md).

| Table | PK | Purpose |
|-------|----|---------|
| `strategies` | `(id)` | One row per strategy: `symbol`, `label`, `engine`, `config` jsonb, `enabled`, `version`. Public-readable. |
| `strategy_calibrations` | `(strategy_id)` | **Private** 1:1 sidecar; fitted `calibration` jsonb. FK → `strategies (id)`. Service-role-only (see RLS exception). |
| `strategy_trades` | `(id BIGINT)` | Executed trade history; FK → `strategies (id)`. Indexed `(strategy_id, entry_ts DESC)`. |
| `strategy_tearsheets` | `(strategy_id)` | Latest tearsheet payload (`metrics` jsonb, `equity_curve` jsonb, `as_of`). |
| `strategy_signals` | `(strategy_id)` | Current state: `position` (long/flat/short), `last_signal_date`, `last_price`, `as_of`. |

### Public portfolio surface — views only, new in migration 050 (#1461/#1462)

The anon-readable read surface for digiquant.io's live portfolio page (user ruling
2026-07-10, #1462: performance metrics only, never research notes). Curated
security-definer views — the SELECT list is the privacy allowlist; no new tables.
They pair with the `functions/prices-live/` edge function (see [`README.md`](README.md)).

| View | Backed by | Purpose |
|------|-----------|---------|
| `public_portfolio_positions` | `positions` | Latest-date position book, performance columns only. **Excludes** `rationale`, `pm_notes`, `thesis_id`, `conviction`, `stop_loss_pct`, `target_pct_gain`, `horizon_days`. |
| `public_nav_history` | `nav_history` | NAV series + cash/invested % + derived `day_return_pct`. |
| `public_price_latest` | `price_history` | Latest daily close per ticker — valuation fallback while `prices-live` is dormant / market closed. |

## RLS (consistent across all tables above)

- Every table has `ENABLE ROW LEVEL SECURITY`.
- Reads: per-table `{table}_anon_select` (or legacy `anon_read` on the
  001-era tables) policy granting `SELECT TO anon USING (true)`.
- Writes: require the Supabase `service_role` key. Supabase grants
  service_role bypass at the GRANT layer, so there is no explicit
  `service_role` policy on any Atlas table.
- **Exception — `strategy_calibrations` (migration 046):** RLS enabled with **no**
  anon policy, so anon reads return an empty set (not an error) while the service
  role keeps full access. The fitted calibration is private; mirrors the
  `atlas_run_diagnostics` idiom (migration 033).
- **Exception — strategy store lockdown (migration 051, #1462):** `strategies`,
  `strategy_signals`, and `strategy_trades` had their anon policies dropped AND their
  anon/authenticated grants revoked — anon access to live signals would bypass the
  3-day public signal delay (PR #1479). `strategy_tearsheets` keeps its anon policy
  (the pipeline writes the delayed view there). The Atlas research tables
  (`documents`, `theses`, `decision_log`, `deliberation_*`, `positions` incl.
  `rationale`/`pm_notes`) stay anon-readable **by design** — see
  [`README.md`](README.md), "What is public on purpose".
- **Views (migrations 041, 050):** RLS does not apply to views; the curated public
  views are intentionally security-DEFINER (`security_invoker = false`) so the column
  projection — not base-table policy — decides what anon sees, with explicit
  `REVOKE ALL` + `GRANT SELECT TO anon, authenticated`. Supabase's advisor flags
  `security_definer_view`; expected and accepted for this pattern.

## Dead / deprecated

- `sec_recent_filings` — dropped in migration 017.
- `'Portfolio Recommendation'` doc_type — removed by migration 021.
- Partitioned children (`daily_snapshots_y2025`, `documents_y2026`, …) are
  implementation details of the partition strategy and are not inventoried
  here. See migration 004 and 006.

## How to extend

1. Create a new migration under `supabase/migrations/NNN_description.sql`.
2. Follow the RLS pattern above.
3. If the new table holds a structured projection of a `documents` payload,
   add a reference to it in this file under the "Hermes deliberation"
   section pattern and cite the source ADR.
4. Add a test under `tests/dq/atlas/test_migration_NNN.py`
   following the pattern in `test_migration_024.py` — pure-SQL parse check
   for offline unit tests, or `psycopg` round-trip for integration.
