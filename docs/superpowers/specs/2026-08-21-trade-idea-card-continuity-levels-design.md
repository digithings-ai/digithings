# Trade idea cards — continuity, levels ladder, rounding, binding fix

- **Date:** 2026-08-21
- **Status:** Locked product change (implement as specified)
- **Surfaces:** Olympus `TradeIdeasPanel` (digithings) + twelve-x `trade_intelligence` / `levels` write path

## Goal

Make Olympus trade idea cards honest about **when** an idea thread started, **how** levels are shown (ladder + precision), and stop stamping **opposite-direction** broker targets onto ideas.

## Continuity (no stable idea ID)

Ideas are keyed by `(run_date, rank)` only. Continuity is **pair+direction streak**:

- Normalize: pair uppercased/trimmed; direction lowercased.
- Boards = unique `run_date`s that have any ideas (sorted).
- For an idea on board D, walk prior boards while the same key is present; streak breaks on a missing board or direction flip.
- `firstSuggested` = first `run_date` of the unbroken streak; `lastUpdated` = this row’s `as_of`.
- UI: muted mono line in the **top-right of each card header** (not under body). Debut: `Suggested {date} · Updated {as_of}`; streak: `First suggested … · Updated …`.

Fetch: `getTradeIdeaHistory(lookbackDays≈45)` → `run_date, pair, direction, as_of`.

## Rounding / display

| Kind | Rule |
|------|------|
| Broker-quoted (and similar presented strings) | Keep presented precision; trim junk trailing zeros only |
| Computed | Round to pair-reasonable decimals: JPY crosses ~3; most majors ~5 |
| R:R | One decimal |

Prefer also rounding **computed** levels on the twelve-x attach/publish path so stored jsonb matches display.

## Card layout

1. Header: rank · pair · direction · **continuity timestamps (top-right)**.
2. Title.
3. Expanded: thesis + catalyst **full width** above.
4. Detail grid: **levels ladder left**, **evidence list right**.
5. Levels ladder (price descending): Entry boxed in the middle. Semantic colors fixed — Target `accent`, Stop `warn`. Long: Target above / Stop below. Short: reverse price order (Stop above / Target below) with the same colors.
6. Contributing desks remain below.

## twelve-x binding fix (root cause)

`_levels_for_pair` currently pools **all** `CurrencyView.targets` for a pair axis across briefs, ignoring view direction. That stamped KBC’s bullish GBP/USD `1.3560` onto a Crédit Agricole **short** idea.

**Fix:** only bind targets from views whose **directional legs** agree with the idea (`long`↔`bullish`, `short`↔`bearish`, compared via G10 legs so a GBP/USD bullish view does not match a USD/GBP long idea). Skip `neutral` / `watch` / opposite. Prefer per-level `source_ref` from the originating brief when attaching structured levels (avoid one citation_ref for a pooled mix). Side-guard remains a safety net, not the primary filter.

Regression test: CA short GBP/USD must not pick up KBC bullish `1.3560`.

## Out of scope

- No `consensus.py` scoring or trade-idea LLM prompt changes.
- No Olympus visual redesign (keep accent/warn, mono, glass cards).
- No develop→main promotion.
