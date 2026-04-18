# DigiQuant OHLCV Data

## Sample Data (Synthetic)

The default CSVs (`AAPL.csv`, `MSFT.csv`, etc.) are **synthetic** data from `generate_synthetic_ohlcv()`. They use a deterministic oscillator pattern for testing and demos.

**Important:** Synthetic data is adversarial to momentum strategies like EMA crossover—it causes buy-high/sell-low on every cycle (0% win rate). The backtest engine and strategy logic are correct; use real data for meaningful results.

## Real Market Data

Fetch real OHLCV from Yahoo Finance:

```bash
pip install yfinance
python digiquant/scripts/fetch_real_ohlcv.py --symbols AAPL MSFT --start 2024-01-01 --end 2024-12-31
```

Then run backtest with `data_path` or `data_dir`:

```python
run_backtest(strategy_name="ema_cross", data_path="digiquant/data/AAPL_real.csv", ...)
```

**CSV format:** `timestamp, open, high, low, close, volume, symbol`

## DigiClone (Docker Compose)

For **DigiChat → DigiGraph → DigiQuant**, Compose mounts [`digiquant/data`](.) read-only at `/app/data` inside the `digiquant` container and sets `DIGIQUANT_DATA_DIR=/app/data` on **digigraph** so chat-driven backtests resolve `{symbol}.csv` here (e.g. add `XAUUSD.csv` for a gold experiment). See `digichat/ARCHITECTURE.md` (DigiClone quickstart).
