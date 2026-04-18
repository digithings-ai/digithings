# NautilusTrader Built-in Strategies

Catalog of all strategies in `nautilus_trader.examples.strategies`. Use this to avoid duplicating Nautilus functionality in DigiQuant.

## Strategy Catalog

| Strategy | Module | Data Type | Description |
|----------|--------|-----------|-------------|
| EMACross | ema_cross | Bar | EMA crossover, market orders |
| EMACrossLongOnly | ema_cross_long_only | Bar | Long-only EMA crossover (equities, CASH accounts) |
| EMACrossTrailingStop | ema_cross_trailing_stop | Bar | EMA crossover + ATR trailing stop |
| EMACrossStopEntry | ema_cross_stop_entry | Bar | EMA crossover with stop-market entry |
| EMACrossBracket | ema_cross_bracket | Bar | EMA crossover with bracket orders |
| EMACrossBracketAlgo | ema_cross_bracket_algo | Bar | EMA crossover + bracket + exec algo |
| EMACrossHedgeMode | ema_cross_hedge_mode | Bar | EMA crossover, hedge OMS |
| EMACrossTWAP | ema_cross_twap | Tick | EMA crossover + TWAP execution |
| OrderbookImbalance | orderbook_imbalance | Order book | Order book imbalance signals |
| OrderbookImbalanceRust | orderbook_imbalance_rust | Order book | Same, Rust implementation |
| MarketMaker | market_maker | Quote tick | Market making |
| VolatilityMarketMaker | volatility_market_maker | Quote tick | Volatility-based market making |
| SimplerQuoter | simpler_quoter | Quote tick | Simple quoting |
| SignalStrategy | signal_strategy | Tick | Test signal emission |
| blank | blank | - | Template strategy |

## OHLCV/Bar Compatibility

DigiQuant's backtest pipeline uses **bar data** (OHLCV). Bar-compatible strategies:

- EMACross
- EMACrossLongOnly
- EMACrossTrailingStop
- EMACrossStopEntry
- EMACrossBracket
- EMACrossBracketAlgo
- EMACrossHedgeMode

**Not compatible** with our OHLCV pipeline (require tick or L2 data):

- EMACrossTWAP (tick)
- OrderbookImbalance, OrderbookImbalanceRust (order book)
- MarketMaker, VolatilityMarketMaker, SimplerQuoter (quote tick)
- SignalStrategy (tick)

## Nautilus Indicators

For custom strategies, use `nautilus_trader.indicators`:

| Category | Indicators |
|----------|------------|
| Averages | EMA, SMA, WMA, HMA, AMA, DEMA, Wilder |
| Momentum | RSI, Stochastics, CCI, CMO, ROC, RVI, PsychologicalLine |
| Trend | MACD, Aroon, Ichimoku, LinearRegression, Bias, DirectionalMovement |
| Volatility | BollingerBands, ATR, DonchianChannel, KeltnerChannel, VolatilityRatio |
| Volume | OBV, VWAP, KlingerVolumeOscillator, Pressure |

### Indicator Notes

- **MACD:** `MovingAverageConvergenceDivergence(fast, slow)` takes only 2 params. A third int is interpreted as `ma_type`; invalid values (e.g. 9) cause `MovingAverageFactory.create` to return None and `update_raw` to raise. For signal line, use `EMA(signal_period)` on MACD values manually.
- **BollingerBands:** `update_raw(high, low, close)` — three args.
- **RSI, MACD:** `update_raw(value)` — single close price.

### Adding a New Strategy

1. Create strategy module in `digiquant/src/digiquant/strategies/` with Strategy + Config.
2. Call `register(name, strategy_cls, config_cls, default_params, ...)` at module bottom.
3. Import module in `strategies/__init__.py` to trigger registration.
4. Add smoke test in `tests/dq/test_strategies.py`. See [NAUTILUS_QUICK_REF.md](NAUTILUS_QUICK_REF.md).

## When to Use Each

| Use Case | Nautilus Strategy | DigiQuant Custom |
|----------|-------------------|------------------|
| Crossover | EMACross | - |
| Long-only equities | EMACrossLongOnly | - |
| Trailing stop | EMACrossTrailingStop | - |
| Momentum (RSI) | - | rsi_momentum |
| Mean reversion | - | bollinger_mr |
| Trend (MACD) | - | macd_trend |
