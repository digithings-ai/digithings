-- 007_price_technicals.sql — Computed TA indicators for all watchlist tickers.
-- One row per (date, ticker) containing pre-computed indicators across multiple
-- timeframes. Populated by scripts/compute-technicals.py after each price update.
--
-- Coverage:
--   Trend           : SMA 20/50/200, EMA 12/26/50, price-vs-MA %
--   Trend Strength  : ADX 14 + ±DI (directional movement)
--   Momentum        : RSI 7/14/21, MACD 12-26-9, ROC 5/10/21
--   Volatility      : ATR 14, Bollinger Bands 20/2, realized vol 21d
--   Mean Reversion  : BB %B, BB bandwidth, Z-scores vs SMA50/200, Stochastics
--
-- All numeric values are rounded to 4 decimal places in the ETL.
-- NULL = not enough history to compute (e.g. SMA_200 needs 200 bars).

CREATE TABLE IF NOT EXISTS price_technicals (
  date           date NOT NULL,
  ticker         text NOT NULL,

  -- ── Moving Averages ──────────────────────────────────────────────────────
  sma_20         numeric,
  sma_50         numeric,
  sma_200        numeric,
  ema_12         numeric,
  ema_26         numeric,
  ema_50         numeric,

  -- Price deviation from key MAs (%, positive = above MA)
  pct_vs_sma20   numeric,
  pct_vs_sma50   numeric,
  pct_vs_sma200  numeric,

  -- ── Trend Strength (ADX / DMI) ───────────────────────────────────────────
  adx_14         numeric,   -- ADX: 0-25 weak, 25-50 strong, 50+ very strong
  dmi_plus       numeric,   -- +DI (bullish pressure)
  dmi_minus      numeric,   -- -DI (bearish pressure)

  -- ── Momentum ─────────────────────────────────────────────────────────────
  rsi_7          numeric,   -- short-term overbought/oversold
  rsi_14         numeric,   -- standard RSI
  rsi_21         numeric,   -- longer-term RSI (less noise)

  macd           numeric,   -- MACD line (12-26 EMA diff)
  macd_signal    numeric,   -- signal line (9-day EMA of MACD)
  macd_hist      numeric,   -- histogram (macd - signal, momentum direction)

  roc_5          numeric,   -- 1-week rate of change (%)
  roc_10         numeric,   -- 2-week rate of change (%)
  roc_21         numeric,   -- 1-month rate of change (%)

  -- ── Volatility ───────────────────────────────────────────────────────────
  atr_14         numeric,   -- Average True Range (absolute)
  atr_pct        numeric,   -- ATR / close * 100 (normalized volatility %)

  bb_upper       numeric,   -- Bollinger upper band (20, 2σ)
  bb_middle      numeric,   -- Bollinger middle (SMA 20)
  bb_lower       numeric,   -- Bollinger lower band
  bb_pct_b       numeric,   -- %B: 0=at lower band, 0.5=middle, 1=upper band
  bb_bandwidth   numeric,   -- (upper-lower)/middle * 100 (volatility squeeze indicator)

  hist_vol_21    numeric,   -- 21-day realized volatility, annualized (%)

  -- ── Mean Reversion / Oscillators ─────────────────────────────────────────
  stoch_k        numeric,   -- Stochastic %K (fast)
  stoch_d        numeric,   -- Stochastic %D (signal, 3-day SMA of %K)

  zscore_50      numeric,   -- (close - sma50) / rolling_50_std  (standard deviations)
  zscore_200     numeric,   -- (close - sma200) / rolling_200_std

  PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_tech_ticker_date
  ON price_technicals (ticker, date DESC);

CREATE INDEX IF NOT EXISTS idx_tech_date
  ON price_technicals (date DESC);

ALTER TABLE price_technicals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "price_technicals_anon_select" ON price_technicals;
CREATE POLICY "price_technicals_anon_select"
  ON price_technicals FOR SELECT
  TO anon USING (true);

COMMENT ON TABLE price_technicals IS
  'Pre-computed TA indicators (trend, momentum, volatility, mean-reversion) '
  'for all watchlist tickers. Populated daily by compute-technicals.py.';
