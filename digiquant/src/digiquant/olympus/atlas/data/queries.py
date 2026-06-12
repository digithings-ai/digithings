"""Read structured price/technical + macro values from Supabase for the research agent.

These return compact, token-budgeted JSON (latest snapshot + a short recent window),
not full history. Selected technical columns only — the model gets signal, not noise.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any  # noqa  # scored-lint suppression: duck-typed Supabase client + rows

# Indicator columns surfaced to the agent (trend / momentum / regime). Not all 30+.
TECHNICAL_COLUMNS: tuple[str, ...] = (
    "date",
    "sma_50",
    "sma_200",
    "pct_vs_sma50",
    "pct_vs_sma200",
    "rsi_14",
    "macd_hist",
    "roc_21",
    "adx_14",
    "atr_pct",
    "bb_pct_b",
    "zscore_200",
)


def get_price_technicals(*, client: Any, ticker: str, lookback: int = 20) -> dict[str, Any]:
    """Return {ticker, latest, window[]} of selected technicals for one ticker.

    ``window`` is newest-first, length <= lookback. ``latest`` is window[0] or {}.
    """
    resp = (
        client.table("price_technicals")
        .select(",".join(TECHNICAL_COLUMNS))
        .eq("ticker", ticker)
        .order("date", desc=True)
        .limit(lookback)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    return {"ticker": ticker, "latest": rows[0] if rows else {}, "window": rows}


def get_macro_series(*, client: Any, series_ids: list[str], lookback: int = 6) -> dict[str, Any]:
    """Return {series_id: {latest, window[]}} for each requested FRED series id."""
    out: dict[str, Any] = {}
    for sid in series_ids:
        resp = (
            client.table("macro_series_observations")
            .select("series_id,obs_date,value,unit")
            .eq("series_id", sid)
            .order("obs_date", desc=True)
            .limit(lookback)
            .execute()
        )
        rows = getattr(resp, "data", None) or []
        out[sid] = {"latest": rows[0] if rows else {}, "window": rows}
    return out


def get_market_context(
    *,
    client: Any,
    tickers: list[str] | tuple[str, ...],
    series_ids: list[str] | tuple[str, ...],
    run_date: date,
    price_window_days: int = 7,
) -> dict[str, Any]:
    """Compact latest-values block for the run-wide shared context (#694).

    Returns ``{"as_of", "price_technicals": {ticker: {…latest row…}},
    "macro_series": {series_id: {date, value, prev_value, unit}}}``.

    - Technicals: one bulk query over ``tickers`` for the trailing
      ``price_window_days``; the newest row per ticker wins. Tickers absent
      from ``price_technicals`` are simply omitted.
    - Macro: re-uses :func:`get_macro_series` (per-series latest two
      observations — series cadences are mixed, so a bulk newest-first query
      would starve monthly series behind daily ones).
    """
    out: dict[str, Any] = {
        "as_of": run_date.isoformat(),
        "price_technicals": {},
        "macro_series": {},
    }
    if tickers:
        since = (run_date - timedelta(days=price_window_days)).isoformat()
        resp = (
            client.table("price_technicals")
            .select(",".join(("ticker", *TECHNICAL_COLUMNS)))
            .in_("ticker", list(tickers))
            .gte("date", since)
            .order("date", desc=True)
            .limit(len(tickers) * price_window_days)
            .execute()
        )
        for row in getattr(resp, "data", None) or []:
            ticker = row.get("ticker")
            if ticker and ticker not in out["price_technicals"]:
                out["price_technicals"][ticker] = {k: row.get(k) for k in TECHNICAL_COLUMNS}
    if series_ids:
        macro = get_macro_series(client=client, series_ids=list(series_ids), lookback=2)
        for sid, payload in macro.items():
            window = payload.get("window") or []
            if not window:
                continue
            latest = window[0]
            prev = window[1] if len(window) > 1 else {}
            out["macro_series"][sid] = {
                "date": latest.get("obs_date"),
                "value": latest.get("value"),
                "prev_value": prev.get("value"),
                "unit": latest.get("unit"),
            }
    return out
