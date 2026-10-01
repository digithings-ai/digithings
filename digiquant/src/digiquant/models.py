"""Structured outputs for digiquant (Pydantic). All data exchange uses these models."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class BacktestResult(BaseModel):
    """Result of a single backtest run. Used by digigraph and MCP."""

    run_id: str = Field(..., description="Unique run identifier")
    strategy_name: str = Field(..., description="Strategy or idea label")
    symbols: list[str] = Field(default_factory=list, description="Instruments used")
    start_time: str = Field(..., description="Backtest start (ISO)")
    end_time: str = Field(..., description="Backtest end (ISO)")
    total_pnl: float = Field(0.0, description="Total PnL (account currency)")
    total_return_pct: float = Field(0.0, description="Total return %")
    sharpe_ratio: float | None = Field(None, description="Sharpe ratio if computable")
    max_drawdown_pct: float | None = Field(
        None,
        description="Max drawdown as negative percent, e.g. -15 for -15%",
    )
    num_trades: int = Field(0, description="Number of trades")
    per_symbol_pnl: dict[str, float] = Field(
        default_factory=dict,
        description="Per-symbol PnL breakdown for multi-symbol backtests",
    )
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message or error")

    @computed_field
    @property
    def success(self) -> bool:
        """A completed backtest. ``partial`` (valid PnL, missing optional metric) is still success."""
        return self.status != "error"


class OptimizationConstraints(BaseModel):
    """Hard limits for optimization; candidates violating these are rejected."""

    min_trades: int | None = Field(None, description="Minimum number of trades required")
    max_drawdown_pct: float | None = Field(
        None,
        description="Max drawdown as negative percent, e.g. -15 for -15%",
    )
    min_sharpe: float | None = Field(None, description="Minimum Sharpe ratio")
    min_return_pct: float | None = Field(None, description="Minimum total return %")
    max_trades_per_year: float | None = Field(None, description="Cap trade frequency")
    min_trades_per_year: float | None = Field(None, description="Ensure minimum activity")


class OptimizeResult(BaseModel):
    """Result of parameter optimization. Phase 2: grid over backtest runs."""

    run_id: str = Field(..., description="Optimization run identifier")
    strategy_name: str = Field(..., description="Strategy label")
    symbols: list[str] = Field(default_factory=list, description="Instruments")
    best_params: dict[str, float | int | str] = Field(
        default_factory=dict, description="Best parameter set"
    )
    best_backtest: BacktestResult | None = Field(
        None, description="Backtest result for best params"
    )
    num_evaluations: int = Field(0, description="Number of param sets evaluated")
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message")


class ExportResult(BaseModel):
    """Result of strategy export to a target platform."""

    run_id: str = Field(..., description="Export run identifier")
    target: str = Field(..., description="nautilus | tradingview | alpaca | quantconnect")
    strategy_name: str = Field(..., description="Strategy label")
    artifact_path: str | None = Field(None, description="Path to exported artifact if written")
    status: str = Field("ok", description="ok | partial | error")
    message: str = Field("", description="Optional message")


class BarsBar(BaseModel):
    """One OHLCV bar for dashboard charts (display only — never a backtest input)."""

    timestamp: str = Field(..., description="Bar timestamp (ISO date or datetime from upstream)")
    open: float | None = Field(None, description="Opening price")
    high: float | None = Field(None, description="High price")
    low: float | None = Field(None, description="Low price")
    close: float = Field(..., description="Closing price")
    volume: float | None = Field(None, description="Volume (if reported upstream)")


class BarsResponse(BaseModel):
    """Keyless OHLCV bars for dashboard charts (GET /bars).

    Display-only read over the anonymous Gloomberb price-history path:
    free-tier data may be delayed (see ``delay_note``) and must never feed
    the validate → backtest → optimize → export pipeline. Carries no Sharpe,
    PnL, or drawdown — no performance claims originate here.
    """

    symbol: str = Field(..., description="Requested symbol (as normalized upstream)")
    timeframe: str = Field(..., description="Requested timeframe (Gloomberb resolution)")
    limit: int = Field(..., description="Requested max bars")
    count: int = Field(..., description="Bars actually returned (<= limit)")
    bars: list[BarsBar] = Field(default_factory=list, description="Newest-last OHLCV bars")
    source: str = Field("gloomberb", description="Upstream family (Sourced from Gloomberb)")
    stale: bool = Field(False, description="Upstream cache-stale signal")
    delay_note: str | None = Field(
        None, description="Free-tier delay notice (up to 15 minutes on equities)"
    )
