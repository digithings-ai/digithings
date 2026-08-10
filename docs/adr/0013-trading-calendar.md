# ADR 0013: Venue-Aware Trading Calendar Table

**Status:** accepted
**Date:** 2026-04-23

## Context

Epic #335 (point-in-time price history completeness) requires a reliable way to
distinguish trading days from non-trading days across the three venue types in
the core universe: US equity exchanges (NYSE/NASDAQ), continuous crypto markets,
and FX sessions.

Migration `013_calendar_fill.sql` addressed this by adding an `is_trading_day`
boolean column directly to `price_history`. That approach has three problems:

1. **Row bloat.** To mark non-trading days, the pipeline must insert
   forward-filled rows for weekends and holidays — roughly 40% more rows in
   `price_history` for NYSE-listed assets alone.
2. **Indicator corruption.** Technical analysis computations run on the full
   `price_history` series produce incorrect results for volume-weighted signals
   (e.g., OBV, VWAP) because forward-filled rows carry `volume = 0` but a
   non-zero close; filtering after the fact is error-prone and cannot be
   enforced at the schema level.
3. **Multi-venue ambiguity.** A Saturday is a non-trading day for NYSE but a
   valid trading day for CRYPTO. Encoding this in a single boolean per row in a
   table keyed by `(date, ticker)` requires knowing the venue per ticker at
   every read site — information that is absent from the schema today.

The `trading_calendar` table is the standard pattern used by
`exchange_calendars` and `pandas_market_calendars`: a separate venue-keyed
relation that any consumer can join, with no dependency on whether a price row
exists for that date.

## Decision

Create a standalone `trading_calendar` table keyed by `(date, venue)`. The
table is populated by the backfill job (issue #337) using the
`exchange_calendars` library (PyPI: `exchange-calendars`), which provides
authoritative open/close/holiday data for NYSE, NASDAQ, and a broad set of
other exchanges.

**Library choice — `exchange_calendars` over `pandas_market_calendars`:**
Both libraries cover NYSE, NASDAQ, and the crypto/FX special cases. We choose
`exchange_calendars` because it has broader venue coverage, a more active
maintenance record (QuantConnect / Zipline lineage), and a clean API for bulk
date-range generation. `pandas_market_calendars` remains usable but is
considered secondary.

**Venue mapping for the core universe (~80 tickers):**

| Venue | Asset classes | Representative tickers |
|-------|--------------|------------------------|
| NYSE | US equity ETFs — market-cap, sector, international, commodity, fixed-income | SPY, QQQ, DIA, IWM, XLK, GLD, TLT, EFA, EEM |
| CRYPTO | Crypto spot + ETFs (24x7, no closures) | BTC-USD, ETH-USD, SOL-USD, IBIT, FBTC, ETHA, GBTC, BITO |
| FX | FX majors (5.5-day week, pending issue #328) | EUR/USD, GBP/USD, JPY/USD, CAD/USD |
| NASDAQ | Reserved for future individual equity coverage | (none in core universe today) |

Notes:
- All US equity ETFs in the current watchlist are assigned `venue = 'NYSE'`
  regardless of primary listing exchange. NYSE Arca is the dominant listing
  venue; NYSE is used as the canonical US equity calendar for simplicity.
- Crypto assets trade continuously; their `is_trading_day` is always `true` and
  `reason` is always `NULL`.
- FRED macro series stored in `macro_series_observations` are exempt — macro
  observation cadence is independent of exchange calendars.
- The `NASDAQ` venue is defined in the schema to support future expansion (e.g.,
  individual equities in a broader universe) but is not populated for the
  current watchlist.

**`is_trading_day` column on `price_history` (migration 013):** The column is
retained but deprecated. The backfill pipeline (issue #337) will stop writing
forward-filled rows and will no longer set `is_trading_day = false` on
`price_history`. All new consumers must join `trading_calendar` instead. A
follow-up migration to drop the column will be tracked as a separate issue once
all read paths are confirmed migrated.

**`reason` column:** Allowed values are `'weekend'`, `'holiday:<name>'`,
`'early_close'`, and `NULL` (normal trading day). These are enforced by
convention and documented via column comment rather than a CHECK constraint, so
new reason types can be added without a schema change.

**Query patterns:**

TA layer — join price history to calendar to filter real trading days:
```sql
SELECT ph.*
FROM price_history ph
JOIN trading_calendar tc
  ON ph.date = tc.date
 AND tc.venue = 'NYSE'   -- or the venue for ph.ticker
WHERE tc.is_trading_day = true;
```

Frontend — show only real trading days for charting:
```sql
SELECT ph.*
FROM price_history ph
JOIN trading_calendar tc
  ON ph.date = tc.date
 AND tc.venue = 'NYSE'
WHERE tc.is_trading_day = true
ORDER BY ph.date DESC;
```

Backfill iteration — enumerate business days for a venue:
```sql
SELECT date
FROM trading_calendar
WHERE venue = 'NYSE'
  AND is_trading_day = true
  AND date BETWEEN '2020-01-01' AND CURRENT_DATE
ORDER BY date;
```

## Consequences

**Positive:**

- `price_history` stores only real price observations — no forward-filled
  weekend/holiday rows — reducing table size by approximately 40% for
  NYSE-class assets.
- TA indicators computed over the full `price_history` series are correct by
  construction; no per-query `is_trading_day` filter is needed on the price
  table.
- Multi-venue logic is centralised in one table. Adding a new venue (e.g., LSE
  for European ETFs) requires only a new batch of rows in `trading_calendar`,
  not schema changes or pipeline refactors.
- The partial index `(venue, is_trading_day) WHERE is_trading_day = true` keeps
  join cost low for the common case of filtering to open days.
- RLS anon-SELECT policy matches the rest of the schema: public read, service
  role write.

**Negative / tradeoffs:**

- Every TA or backfill query now requires a join. In practice the join is cheap
  (indexed primary key lookup), but it adds query complexity.
- The `is_trading_day` column on `price_history` remains until a follow-up
  migration removes it. During the transition period, the two sources of truth
  can diverge if the old pipeline path is not fully shut down.
- `exchange_calendars` is a new Python dependency for the backfill job. It must
  be added to `apps/digiquant-atlas/pyproject.toml` (or equivalent) before
  issue #337 can ship.

## Alternatives considered

**`pandas_market_calendars`:** Overlapping functionality; `exchange_calendars`
is preferred for broader venue coverage and more active maintenance. Either
could be used; the schema is library-agnostic.

**Inline flag on `price_history` (migration 013 approach):** Rejected. See
Context above — row bloat, indicator corruption, and multi-venue ambiguity are
all structural problems that cannot be solved by adding more columns to a
row-per-day table.

**Synthetic forward-fill filtered at query time:** Rejected. Puts business logic
in every query site with no schema-level guardrail; harder to audit and
maintain.

**Materialised view over `generate_series`:** Rejected. A materialised view
cannot be partially refreshed when holidays change; a plain table with a managed
population job is simpler to operate and backfill.

## Links

- Epic: [#335](https://github.com/digithings-ai/digithings/issues/335)
- This issue: [#336](https://github.com/digithings-ai/digithings/issues/336)
- Child issues: [#337](https://github.com/digithings-ai/digithings/issues/337) (backfill), [#338](https://github.com/digithings-ai/digithings/issues/338) (full-history workflow), [#340](https://github.com/digithings-ai/digithings/issues/340) (frontend view)
- Migration introduced by this ADR: `apps/digiquant-atlas/supabase/migrations/025_trading_calendar.sql`
- Supersedes (in part): migration 013 pattern (`013_calendar_fill.sql`)
