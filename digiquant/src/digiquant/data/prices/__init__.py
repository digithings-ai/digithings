"""Polars-only price pipeline package.

Migrated from apps/digiquant-atlas/scripts/* per issue #149 (Wave 1 Unit E).

Public surface:
    - fetchers.fetch_quotes / fetch_batch
    - technicals.compute_indicators / TECHNICAL_COLUMNS
    - history_cache.load_cached / save_cached / incremental_update
    - macro_ingest.fetch_fred / fetch_fx_yahoo (default daily pipeline)
    - macro_ingest.fetch_frankfurter / fetch_crypto_fng (legacy, opt-in)
    - supabase_writer.upsert_price_history / upsert_price_technicals / upsert_macro_observations

No pandas anywhere. All DataFrames are `polars.DataFrame`.
"""

from __future__ import annotations

__all__ = [
    "OHLCV_COLUMNS",
    "TECHNICAL_COLUMNS",
]

# Canonical OHLCV column contract (matches digiquant.data.loader.OHLCV_COLUMNS).
OHLCV_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "symbol",
)

# Canonical indicator column list (matches Atlas price_technicals schema).
TECHNICAL_COLUMNS: tuple[str, ...] = (
    "sma_20",
    "sma_50",
    "sma_200",
    "ema_12",
    "ema_26",
    "ema_50",
    "pct_vs_sma20",
    "pct_vs_sma50",
    "pct_vs_sma200",
    "adx_14",
    "dmi_plus",
    "dmi_minus",
    "rsi_7",
    "rsi_14",
    "rsi_21",
    "macd",
    "macd_signal",
    "macd_hist",
    "roc_5",
    "roc_10",
    "roc_21",
    "atr_14",
    "atr_pct",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "bb_pct_b",
    "bb_bandwidth",
    "hist_vol_21",
    "stoch_k",
    "stoch_d",
    "zscore_50",
    "zscore_200",
)
