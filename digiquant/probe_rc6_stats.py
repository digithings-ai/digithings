#!/usr/bin/env python3
"""Probe nautilus_trader 2.0.0rc6 portfolio statistics keys."""
import sys
sys.path.insert(0, '/tmp/nt_rc6')

from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig, BacktestVenueConfig
from nautilus_trader.model import InstrumentId, Venue, CryptoPerpetual, Currency, Money, Quantity, Price, OmsType, AccountType, Symbol
from nautilus_trader.execution import FixedFeeModel
from nautilus_trader.model import QuoteTick
from nautilus_trader.common import init_logging

# Create engine
config = BacktestEngineConfig()
engine = BacktestEngine(config=config)
print("Engine created")

# Add venue
engine.add_venue(
    venue=Venue("BINANCE"),
    oms_type=OmsType.NETTING,
    account_type=AccountType.MARGIN,
    base_currency=Currency.from_str("USD"),
    starting_balances=[Money(100000, Currency.from_str("USD"))],
    fee_model=FixedFeeModel(commission=Money(0, Currency.from_str("USD"))),
)
print("Venue added")

# Create a crypto perpetual instrument
btc_usdt = CryptoPerpetual(
    instrument_id=InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
    raw_symbol=Symbol("BTCUSDT"),
    base_currency=Currency.from_str("BTC"),
    quote_currency=Currency.from_str("USDT"),
    settlement_currency=Currency.from_str("USDT"),
    is_inverse=False,
    price_precision=2,
    size_precision=6,
    price_increment=Price.from_str("0.01"),
    size_increment=Quantity.from_str("0.000001"),
    max_quantity=None,
    min_quantity=None,
    max_notional=None,
    min_notional=None,
    max_price=None,
    min_price=None,
    margin_init=0.01,
    margin_maint=0.005,
    ts_event=0,
    ts_init=0,
)
engine.add_instrument(btc_usdt)
print("Instrument added")

# Create some quote ticks
ticks = []
base_price = 50000.0
for i in range(100):
    price = base_price + (i * 10)
    tick = QuoteTick(
        instrument_id=btc_usdt.id,
        bid_price=Price.from_str(f"{price:.2f}"),
        ask_price=Price.from_str(f"{price + 1:.2f}"),
        bid_size=Quantity.from_str("1.0"),
        ask_size=Quantity.from_str("1.0"),
        ts_event=i * 1000,
        ts_init=i * 1000,
    )
    ticks.append(tick)

engine.add_data(ticks)
print(f"Added {len(ticks)} ticks")

# Run backtest
engine.run()
print("Backtest completed")

# Probe portfolio statistics
print("\n=== PORTFOLIO STATISTICS PROBE ===")
portfolio = engine.portfolio
print(f"Portfolio type: {type(portfolio)}")
print(f"Portfolio attributes: {[x for x in dir(portfolio) if not x.startswith('_')]}")

# Check if statistics method exists
if hasattr(portfolio, 'statistics'):
    stats = portfolio.statistics()
    print(f"\nPortfolioStatistics type: {type(stats)}")
    print(f"PortfolioStatistics attributes: {[x for x in dir(stats) if not x.startswith('_')]}")

    # Probe the statistics - in rc6 these are dict properties, not methods!
    if hasattr(stats, 'general'):
        general = stats.general
        print(f"\nGeneral stats type: {type(general)}")
        print(f"General stats: {general}")
        if isinstance(general, dict) and general:
            print(f"General stats keys: {list(general.keys())}")

    if hasattr(stats, 'pnls'):
        pnls = stats.pnls
        print(f"\nPnL stats type: {type(pnls)}")
        print(f"PnL stats: {pnls}")
        if isinstance(pnls, dict) and pnls:
            print(f"PnL stats keys: {list(pnls.keys())}")

    if hasattr(stats, 'returns'):
        returns = stats.returns
        print(f"\nReturn stats type: {type(returns)}")
        print(f"Return stats: {returns}")
        if isinstance(returns, dict) and returns:
            print(f"Return stats keys: {list(returns.keys())}")

    if hasattr(stats, 'returns_series'):
        returns_series = stats.returns_series
        print(f"\nReturns series type: {type(returns_series)}")
        print(f"Returns series: {returns_series}")
else:
    print("No statistics method on portfolio")

# Also check the result
result = engine.get_result()
print(f"\n=== BACKTEST RESULT ===")
print(f"Result type: {type(result)}")
print(f"Result attributes: {[x for x in dir(result) if not x.startswith('_')]}")

# Check for max_drawdown_pct
if hasattr(result, 'max_drawdown_pct'):
    print(f"max_drawdown_pct: {result.max_drawdown_pct}")

engine.dispose()
print("\nDone")
