# NautilusTrader Quick Reference

One-page cheat sheet for agents. Full guide: [NAUTILUS_NAVIGATION.md](NAUTILUS_NAVIGATION.md).

## Common Imports

```python
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import PositiveInt, PositiveFloat, StrategyConfig
from nautilus_trader.indicators import RelativeStrengthIndex, BollingerBands, MovingAverageConvergenceDivergence, ExponentialMovingAverage
from nautilus_trader.model import BarType, Venue
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Money
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.trading.strategy import Strategy
```

## BarType Format

```
{symbol}.{venue}-{period}-LAST-EXTERNAL
```

Example: `AAPL.SIM-1-DAY-LAST-EXTERNAL`

## Config Base

```python
class MyStrategyConfig(StrategyConfig, frozen=True):
    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # add strategy-specific params with PositiveInt, PositiveFloat, etc.
```

## Registry

```python
from digiquant.strategies.registry import register

register(
    "my_strategy",
    MyStrategy,
    MyStrategyConfig,
    {"trade_size": Decimal(1000), "param": 14},
    aliases=["alias1", "alias2"],
    description="Short description",
)
```

## Adding a New Strategy (4 Steps)

1. Create `digiquant/src/digiquant/strategies/my_strategy.py` with Strategy + Config classes.
2. Call `register()` at module bottom.
3. Add `from digiquant.strategies import my_strategy` in `strategies/__init__.py`.
4. Add smoke test in `tests/dq/test_strategies.py`.
