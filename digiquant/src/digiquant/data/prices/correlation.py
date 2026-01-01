"""Pairwise return correlations from close-price history (pure, no I/O).

Consumed by the risk sizer (Phase 7E) to correct the conservative ρ=1.0
full-correlation default in ``_portfolio_vol`` and to allow ``_corr_dedup``
to drop the lower-conviction leg of a highly correlated pair.

The output is a long frame ``{a, b, corr}`` — one unordered pair per row —
that ``sizing.size_portfolio(corr=...)`` consumes directly. Both ``(a,b)``
and ``(b,a)`` orders are looked up by the sizer, so returning one order per
pair is fine and avoids row-count confusion.

Polars only (no pandas, no numpy). HTTP-free; the Supabase read lives in
``queries.get_return_correlations``.
"""

from __future__ import annotations

import polars as pl


def pairwise_return_correlations(
    closes: pl.DataFrame,
    *,
    min_overlap: int = 30,
) -> pl.DataFrame:
    """Compute pairwise Pearson return correlations from long close-price history.

    Args:
        closes: long frame with columns ``ticker``, ``date``, ``close``.
            ``date`` may be ISO string or ``pl.Date``; ``close`` must be numeric.
        min_overlap: minimum number of shared trading days with *both* tickers
            having a return to include the pair. Pairs with fewer common return
            dates are omitted so a newly-listed ticker doesn't produce spurious
            near-1.0 correlations from a handful of coincidental days.

    Returns:
        Long frame ``{a: Utf8, b: Utf8, corr: Float64}``.  One row per
        unordered pair (a < b lexicographically).  Empty when fewer than two
        tickers survive the overlap threshold.
    """
    if closes.is_empty():
        return pl.DataFrame({"a": [], "b": [], "corr": []}).cast(
            {"a": pl.Utf8, "b": pl.Utf8, "corr": pl.Float64}
        )

    # Normalise date column to pl.Date so sorting and joining are unambiguous.
    schema = closes.schema
    df = closes.select(
        pl.col("ticker").cast(pl.Utf8),
        pl.col("date").cast(pl.Date) if schema.get("date") != pl.Date else pl.col("date"),
        pl.col("close").cast(pl.Float64),
    )

    # Compute daily simple returns (r_t = close_t / close_{t-1} - 1) per ticker,
    # sorted ascending so shift(1) is the previous trading day for that ticker.
    df = df.sort(["ticker", "date"])
    df = df.with_columns(
        (pl.col("close") / pl.col("close").shift(1).over("ticker") - 1.0).alias("ret")
    ).filter(pl.col("ret").is_not_null() & pl.col("ret").is_finite())

    tickers: list[str] = df["ticker"].unique().sort().to_list()
    if len(tickers) < 2:
        return pl.DataFrame({"a": [], "b": [], "corr": []}).cast(
            {"a": pl.Utf8, "b": pl.Utf8, "corr": pl.Float64}
        )

    # Pivot to wide form: date × ticker.  Missing dates for a ticker → null.
    wide = df.pivot(values="ret", index="date", on="ticker", aggregate_function="first")

    rows_a: list[str] = []
    rows_b: list[str] = []
    rows_corr: list[float] = []

    for i, ta in enumerate(tickers):
        for tb in tickers[i + 1 :]:
            # Both columns must exist in the wide frame (they do — every ticker that
            # survived the filter above is a column).  Select the pair, drop rows
            # where either is null (non-overlapping trading days, e.g. ETF closed).
            if ta not in wide.columns or tb not in wide.columns:
                continue  # defensive: should never happen, but skip rather than crash
            pair = wide.select([ta, tb]).drop_nulls()
            if len(pair) < min_overlap:
                # Not enough overlapping history to estimate a reliable correlation.
                continue
            # Pearson r via the pl.corr expression — .item() extracts the scalar float.
            # pl.corr requires Polars ≥ 0.15 (present in any supported install).
            rho = pair.select(pl.corr(ta, tb)).item()
            if rho is None or not isinstance(rho, float):
                continue
            rows_a.append(ta)
            rows_b.append(tb)
            rows_corr.append(rho)

    return pl.DataFrame({"a": rows_a, "b": rows_b, "corr": rows_corr}).cast(
        {"a": pl.Utf8, "b": pl.Utf8, "corr": pl.Float64}
    )


__all__ = ["pairwise_return_correlations"]
