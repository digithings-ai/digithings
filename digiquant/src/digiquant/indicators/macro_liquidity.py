"""Macro-liquidity regime gauge (#1085).

Expands the M2-only vote in ``m2_signals.M2SignalComputer`` into a pluggable
composite of macro series (M2 + dollar + labor + manufacturing activity). Each
enabled series becomes a causal rolling z-score (liquidity-positive = +z), then:

1. **Continuous blend** — weight-normalized ``composite_z`` ∈ [-3, 3] maps to
   ``regime_score`` ∈ [0, 100] (100 = max expansion / risk-on).
2. **Equal-weight vote** — per-day 0/1 state from ``z > 0`` (latch-free; unlike
   ``M2SignalComputer``'s crossover latch), averaged into ``avg_vote``.
   ``avg_vote`` ignores ``MacroSeriesSpec.weight``; weighted consumers should
   read ``regime_score`` / ``composite_z``.
3. **Discrete state** — ``expansion`` / ``neutral`` / ``contraction`` from
   score thresholds; ``risk_on`` is true only in expansion (gate open).

Series are expected as ``{name: DataFrame[date, value]}`` already sourced from
the macro pipeline (``macro_series_observations`` / FRED via
``digiquant prices fetch-macro``). This module never fetches and never holds
secrets. Default YoY specs need roughly ``roc_days + min_samples`` calendar
days (~395) before ``regime_score`` is non-null.

The gate backtest (``backtest_regime_gate``) is a CI-only long-vs-cash harness
for documenting whether the gate helps vs always-invested — **not** a
published ``BacktestResult`` and not a Nautilus path (same CI-parity exception
as ``strategies/sdca/backtest.py``).
"""

from __future__ import annotations

import math
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Literal, Mapping, Sequence

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Defaults match SDCA macro extras (#1080 family) and FRED ids in
# ``research/config/macro_series.yaml``.
DEFAULT_ROLLING_WINDOW = 90
_MIN_SAMPLES = 30
_SIGMA_FLOOR = 1e-8

Transform = Literal["level", "yoy", "roc"]


class RegimeState(str, Enum):
    """Discrete liquidity regime for downstream gates (#1084 rotation, books)."""

    EXPANSION = "expansion"
    NEUTRAL = "neutral"
    CONTRACTION = "contraction"


class MacroSeriesSpec(BaseModel):
    """One pluggable macro vote: FRED/Yahoo series id + transform + sign."""

    model_config = ConfigDict(strict=True, frozen=True)

    name: str = Field(min_length=1)
    series_id: str = Field(
        min_length=1,
        description="FRED (or Yahoo FX) series id in macro_series_observations.",
    )
    weight: float = Field(default=1.0, gt=0.0)
    sign: Literal[-1, 1] = 1
    transform: Transform = "level"
    roc_days: int = Field(default=365, ge=2)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name_token(cls, value: str) -> str:
        token = value.strip()
        if not token or any(ch.isspace() for ch in token):
            raise ValueError("name must be a non-empty token without whitespace")
        return token


# Published default blend: M2 + ≥2 new macros (DXY, UNRATE) + manufacturing
# activity proxy (MANEMP YoY — FRED does not carry live ISM PMI).
DEFAULT_MACRO_SPECS: tuple[MacroSeriesSpec, ...] = (
    MacroSeriesSpec(name="m2", series_id="M2SL", transform="yoy", sign=1, weight=1.0),
    MacroSeriesSpec(name="dxy", series_id="DTWEXBGS", transform="level", sign=-1, weight=1.0),
    MacroSeriesSpec(name="unrate", series_id="UNRATE", transform="level", sign=-1, weight=1.0),
    MacroSeriesSpec(name="pmi", series_id="MANEMP", transform="yoy", sign=1, weight=1.0),
)


class MacroLiquidityConfig(BaseModel):
    """Thresholds and rolling window for ``MacroLiquidityModel``."""

    model_config = ConfigDict(strict=True, frozen=True)

    window: int = Field(default=DEFAULT_ROLLING_WINDOW, ge=2)
    min_samples: int = Field(default=_MIN_SAMPLES, ge=2)
    expansion_threshold: float = Field(default=60.0, ge=0.0, le=100.0)
    contraction_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
    specs: tuple[MacroSeriesSpec, ...] = DEFAULT_MACRO_SPECS

    @field_validator("specs")
    @classmethod
    def _at_least_one_enabled(
        cls, specs: tuple[MacroSeriesSpec, ...]
    ) -> tuple[MacroSeriesSpec, ...]:
        if not any(s.enabled for s in specs):
            raise ValueError("at least one MacroSeriesSpec must be enabled")
        names = [s.name for s in specs if s.enabled]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate enabled indicator names: {names}")
        return specs

    @model_validator(mode="after")
    def _ordered_thresholds(self) -> MacroLiquidityConfig:
        if self.contraction_threshold >= self.expansion_threshold:
            raise ValueError("contraction_threshold must be < expansion_threshold")
        return self


class RegimeGateReport(BaseModel):
    """CI-only long-vs-cash comparison for the regime gate (not a BacktestResult)."""

    model_config = ConfigDict(strict=True, frozen=True)

    always_in_return_pct: float
    gated_return_pct: float
    gated_minus_always_pct: float
    days_total: int
    days_invested: int
    days_cash: int
    final_always_in: float
    final_gated: float
    notes: str = (
        "CI diagnostic only — not a published BacktestResult; "
        "gate invests on expansion, holds cash on neutral/contraction."
    )


def causal_rolling_z(
    values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Rolling z in ``[-3, 3]``. Each day uses only that day and prior window."""
    if window < 2:
        raise ValueError(f"rolling window must be >= 2, got {window}")
    mu = values.rolling_mean(window_size=window, min_samples=min_samples)
    sigma = values.rolling_std(window_size=window, min_samples=min_samples)
    return ((values - mu) / sigma.clip(lower_bound=_SIGMA_FLOOR)).clip(-3.0, 3.0)


def align_to_dates(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    *,
    forward_fill: bool = True,
) -> pl.Series:
    """Left-join ``src`` onto ``dates``. Macro series typically forward-fill."""
    if dates.dtype != pl.Date:
        raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
    src = (
        pl.DataFrame({"date": src_dates, "value": src_values})
        .unique(subset=["date"], keep="last")
        .sort("date")
    )
    joined = pl.DataFrame({"date": dates}).join(src, on="date", how="left")
    if forward_fill:
        joined = joined.with_columns(pl.col("value").forward_fill())
    return joined["value"]


def _apply_transform(aligned: pl.Series, spec: MacroSeriesSpec) -> pl.Series:
    if spec.transform == "level":
        return aligned
    # ``yoy`` and ``roc`` both mean percent change over ``roc_days`` (default 365).
    # Kept as separate tokens so callers can label intent; semantics are identical.
    if spec.transform in ("yoy", "roc"):
        return aligned / aligned.shift(spec.roc_days) - 1.0
    raise ValueError(f"unknown transform: {spec.transform}")


def _require_series_frame(frame: pl.DataFrame, name: str) -> tuple[pl.Series, pl.Series]:
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"series[{name!r}] must have columns date, value")
    return frame["date"], frame["value"]


class MacroLiquidityModel:
    """Blend M2 + pluggable macros into a regime score/state series.

    Parameters
    ----------
    config:
        Thresholds, window, and indicator specs. Defaults enable M2 + DXY +
        UNRATE + MANEMP (manufacturing-activity / PMI proxy).
    """

    def __init__(self, config: MacroLiquidityConfig | None = None) -> None:
        self.config = config or MacroLiquidityConfig()

    @property
    def enabled_specs(self) -> list[MacroSeriesSpec]:
        return [s for s in self.config.specs if s.enabled]

    def compute(
        self,
        dates: pl.Series,
        series: Mapping[str, pl.DataFrame],
    ) -> pl.DataFrame:
        """Return ``date`` + per-indicator z/state + regime columns.

        ``series`` keys are indicator ``name`` values (not FRED ids). Missing
        keys for enabled specs raise ``KeyError``. Null z on any enabled
        indicator nulls the composite that day (no partial blend).
        """
        if dates.dtype != pl.Date:
            raise ValueError(f"dates must be pl.Date, got {dates.dtype}")
        if dates.len() == 0:
            raise ValueError("dates must be non-empty")

        enabled = self.enabled_specs
        z_cols: dict[str, pl.Series] = {}
        state_cols: dict[str, pl.Series] = {}

        for spec in enabled:
            if spec.name not in series:
                raise KeyError(
                    f"enabled indicator {spec.name!r} (series_id={spec.series_id}) "
                    f"missing from series map; have {sorted(series)}"
                )
            src_dates, src_values = _require_series_frame(series[spec.name], spec.name)
            aligned = align_to_dates(dates, src_dates, src_values, forward_fill=True)
            transformed = _apply_transform(aligned, spec)
            z = causal_rolling_z(
                transformed,
                window=self.config.window,
                min_samples=self.config.min_samples,
            )
            # Liquidity-positive orientation: apply sign before vote/blend.
            signed = (z * float(spec.sign)).alias(f"{spec.name}_z")
            z_cols[spec.name] = signed
            # Equal-weight vote (m2_signals pattern): bull when z > 0.
            state_cols[spec.name] = (
                pl.DataFrame({"z": signed})
                .select(
                    pl.when(pl.col("z").is_null())
                    .then(None)
                    .when(pl.col("z") > 0.0)
                    .then(pl.lit(1))
                    .otherwise(pl.lit(0))
                    .cast(pl.Int32)
                    .alias(f"{spec.name}_state")
                )
                .to_series()
            )

        total_weight = sum(s.weight for s in enabled)
        if not math.isfinite(total_weight) or total_weight == 0:
            raise ValueError(f"total weight must be finite and nonzero, got {total_weight}")

        frame = pl.DataFrame({"date": dates, **{f"{n}_z": z for n, z in z_cols.items()}})
        for name, state in state_cols.items():
            frame = frame.with_columns(state.alias(f"{name}_state"))

        weighted_sum = pl.sum_horizontal(
            [pl.col(f"{s.name}_z") * s.weight for s in enabled],
            ignore_nulls=False,
        )
        composite_z = (weighted_sum / total_weight).clip(-3.0, 3.0)
        # 100 = max expansion (z=+3); 0 = max contraction (z=-3).
        regime_score = 50.0 + composite_z * (50.0 / 3.0)

        vote_sum = pl.sum_horizontal(
            [pl.col(f"{s.name}_state") for s in enabled], ignore_nulls=False
        )
        avg_vote = vote_sum.cast(pl.Float64) / float(len(enabled))

        expansion_t = self.config.expansion_threshold
        contraction_t = self.config.contraction_threshold
        regime_state = (
            pl.when(regime_score.is_null())
            .then(None)
            .when(regime_score >= expansion_t)
            .then(pl.lit(RegimeState.EXPANSION.value))
            .when(regime_score <= contraction_t)
            .then(pl.lit(RegimeState.CONTRACTION.value))
            .otherwise(pl.lit(RegimeState.NEUTRAL.value))
        )
        risk_on = (
            pl.when(regime_state.is_null())
            .then(None)
            .otherwise(regime_state == RegimeState.EXPANSION.value)
        )

        return frame.with_columns(
            [
                composite_z.alias("composite_z"),
                regime_score.alias("regime_score"),
                avg_vote.alias("avg_vote"),
                regime_state.alias("regime_state"),
                risk_on.alias("risk_on"),
            ]
        )

    def write_regime_series(self, df: pl.DataFrame, path: str | Path) -> Path:
        """Persist the consumer-facing regime columns for other strategies."""
        out = Path(path)
        cols = ["date", "regime_score", "regime_state", "risk_on", "composite_z", "avg_vote"]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"regime frame missing columns: {missing}")
        out.parent.mkdir(parents=True, exist_ok=True)
        df.select(cols).write_parquet(out)
        return out


def load_regime_series(path: str | Path) -> pl.DataFrame:
    """Load a regime parquet written by ``MacroLiquidityModel.write_regime_series``."""
    df = pl.read_parquet(path)
    required = {"date", "regime_score", "regime_state", "risk_on"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"regime series missing columns: {sorted(missing)}")
    return df


def regime_index_by_date(df: pl.DataFrame) -> dict[date, tuple[str | None, bool | None]]:
    """Map ``date → (regime_state, risk_on)`` for Nautilus / rotation gates."""
    rows = df.select(["date", "regime_state", "risk_on"]).to_dicts()
    out: dict[date, tuple[str | None, bool | None]] = {}
    for row in rows:
        d = row["date"]
        if isinstance(d, date):
            key = d
        else:
            key = date.fromisoformat(str(d)[:10])
        state = row["regime_state"]
        risk = row["risk_on"]
        out[key] = (
            None if state is None else str(state),
            None if risk is None else bool(risk),
        )
    return out


def backtest_regime_gate(
    dates: Sequence[date] | pl.Series,
    price: Sequence[float] | pl.Series,
    risk_on: Sequence[bool | None] | pl.Series,
    *,
    initial_cash: float = 10_000.0,
) -> RegimeGateReport:
    """Compare always-invested buy-&-hold vs invest-only-when-``risk_on``.

    Gated book: 100% invested on ``risk_on=True`` days (mark-to-market), 100%
    cash otherwise (no interest). Always-in stays fully invested every day.
    Null ``risk_on`` days stay in cash for the gated book. CI diagnostic only.
    """
    if initial_cash <= 0 or not math.isfinite(initial_cash):
        raise ValueError(f"initial_cash must be finite and > 0, got {initial_cash}")

    date_list = list(dates) if not isinstance(dates, pl.Series) else dates.to_list()
    price_list = list(price) if not isinstance(price, pl.Series) else price.to_list()
    gate_list = list(risk_on) if not isinstance(risk_on, pl.Series) else risk_on.to_list()
    n = len(date_list)
    if n < 2 or n != len(price_list) or n != len(gate_list):
        raise ValueError("dates, price, and risk_on must be equal length >= 2")
    if any(p is None or not math.isfinite(float(p)) or float(p) <= 0 for p in price_list):
        raise ValueError("price must be finite and > 0 on every day")

    always = float(initial_cash)
    gated = float(initial_cash)
    always_units = always / float(price_list[0])
    gated_units = 0.0
    gated_cash = gated
    invested_days = 0
    cash_days = 0

    # Start of day 0: allocate always-in; gated follows risk_on[0].
    if gate_list[0] is True:
        gated_units = gated_cash / float(price_list[0])
        gated_cash = 0.0
        invested_days += 1
    else:
        cash_days += 1

    for i in range(1, n):
        px = float(price_list[i])
        always = always_units * px

        want_in = gate_list[i] is True
        currently_in = gated_units > 0.0
        if want_in and not currently_in:
            gated_units = gated_cash / px
            gated_cash = 0.0
        elif not want_in and currently_in:
            gated_cash = gated_units * px
            gated_units = 0.0

        gated = gated_cash + gated_units * px
        if want_in:
            invested_days += 1
        else:
            cash_days += 1

    always_ret = (always / initial_cash - 1.0) * 100.0
    gated_ret = (gated / initial_cash - 1.0) * 100.0
    return RegimeGateReport(
        always_in_return_pct=always_ret,
        gated_return_pct=gated_ret,
        gated_minus_always_pct=gated_ret - always_ret,
        days_total=n,
        days_invested=invested_days,
        days_cash=cash_days,
        final_always_in=always,
        final_gated=gated,
    )


__all__ = [
    "DEFAULT_MACRO_SPECS",
    "DEFAULT_ROLLING_WINDOW",
    "MacroLiquidityConfig",
    "MacroLiquidityModel",
    "MacroSeriesSpec",
    "RegimeGateReport",
    "RegimeState",
    "align_to_dates",
    "backtest_regime_gate",
    "causal_rolling_z",
    "load_regime_series",
    "regime_index_by_date",
]
