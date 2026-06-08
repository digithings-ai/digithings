"""Read structured price/technical + macro values from Supabase for the research agent.

These return compact, token-budgeted JSON (latest snapshot + a short recent window),
not full history. Selected technical columns only — the model gets signal, not noise.
"""

from __future__ import annotations

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
