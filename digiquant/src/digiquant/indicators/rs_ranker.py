"""Relative-strength ranker for multi-asset rotation (#1084).

Produces per-asset **absolute** strength and **cross-sectional** RS rank over a
daily multi-asset pool. Dual-momentum style (Antonacci): risk-adjusted trailing
momentum with a skip window, plus an absolute-return gate so the rotator can
move to cash when no name qualifies.

Pure Polars + Pydantic — no Nautilus dependency. Downstream consumers:

- Phase-1 RS rotation strategy / CI backtest (`strategies/rotation/`)
- SDCA RS-driven risk hook (#1082) and composition (#1078)
- Optional macro-liquidity ``risk_on`` overlay (#1085) applied at allocation time
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator

_EPS = 1e-8


class RsRankerConfig(BaseModel):
    """Lookback / skip / absolute-gate knobs for ``RsRanker``."""

    model_config = ConfigDict(strict=True, frozen=True)

    lookback_days: int = Field(default=90, ge=2, description="Return window length (trading rows).")
    skip_days: int = Field(
        default=7,
        ge=1,
        description="Rows skipped after the lookback end (short-term reversal + same-bar look-ahead buffer).",
    )
    absolute_threshold: float = Field(
        default=0.0,
        description="Asset qualifies when abs trailing return exceeds this (dual momentum).",
    )
    vol_floor: float = Field(default=_EPS, gt=0.0)

    @field_validator("lookback_days", "skip_days")
    @classmethod
    def _non_neg_int(cls, value: int) -> int:
        if value < 0:
            raise ValueError("windows must be non-negative")
        return value


class RsRanker:
    """Rank a multi-asset daily close pool by risk-adjusted relative strength."""

    def __init__(self, config: RsRankerConfig | None = None) -> None:
        self.config = config or RsRankerConfig()

    @property
    def min_rows(self) -> int:
        """Minimum rows per asset before a score can appear."""
        return self.config.lookback_days + self.config.skip_days + 1

    def rank(
        self,
        closes: Mapping[str, pl.DataFrame] | pl.DataFrame,
        *,
        symbols: Sequence[str] | None = None,
    ) -> pl.DataFrame:
        """Return a long frame of absolute + relative rankings.

        Accepts either ``{symbol: DataFrame[date, close]}`` or a long
        ``DataFrame[date, symbol, close]``. Output columns:

        ``date, symbol, abs_return, vol, risk_adj, rs_rank, qualifies``

        ``rs_rank`` is 1 = strongest among assets with a finite ``risk_adj`` that
        day. ``qualifies`` is True when ``abs_return > absolute_threshold``.
        """
        panel = self.to_long_panel(closes, symbols=symbols)
        if panel.is_empty():
            return self._empty()

        cfg = self.config
        parts: list[pl.DataFrame] = []
        for symbol, group in panel.partition_by("symbol", as_dict=True).items():
            sym = symbol[0] if isinstance(symbol, tuple) else symbol
            scored = self._score_symbol(group.sort("date"), str(sym), cfg)
            if scored is not None and not scored.is_empty():
                parts.append(scored)

        if not parts:
            return self._empty()

        long = pl.concat(parts, how="vertical").sort(["date", "symbol"])
        return self._attach_cross_sectional_rank(long)

    def to_long_panel(
        self,
        closes: Mapping[str, pl.DataFrame] | pl.DataFrame,
        *,
        symbols: Sequence[str] | None = None,
    ) -> pl.DataFrame:
        """Normalize mapping or long frame to ``date, symbol, close``."""
        return self._to_long(closes, symbols=symbols)

    def select_top_n(
        self,
        ranked: pl.DataFrame,
        *,
        top_n: int = 1,
        qualifying_only: bool = True,
    ) -> pl.DataFrame:
        """Per-date top-N symbols (equal-weight candidates).

        When ``qualifying_only`` is True, only rows with ``qualifies=True`` are
        eligible — dates with no qualifiers emit **no rows** (cash signal).
        """
        if top_n < 1:
            raise ValueError(f"top_n must be >= 1, got {top_n}")
        if ranked.is_empty():
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "symbol": pl.Utf8,
                    "rs_rank": pl.Int64,
                    "weight": pl.Float64,
                }
            )

        eligible = ranked.filter(pl.col("qualifies")) if qualifying_only else ranked
        eligible = eligible.filter(pl.col("rs_rank").is_not_null())
        if eligible.is_empty():
            return pl.DataFrame(
                schema={
                    "date": pl.Date,
                    "symbol": pl.Utf8,
                    "rs_rank": pl.Int64,
                    "weight": pl.Float64,
                }
            )

        picked = (
            eligible.sort(["date", "rs_rank"])
            .group_by("date", maintain_order=True)
            .head(top_n)
            .with_columns((pl.lit(1.0) / pl.len().over("date")).alias("weight"))
            .select(["date", "symbol", "rs_rank", "weight"])
        )
        return picked

    def write_rankings(self, df: pl.DataFrame, path: str | Path) -> Path:
        """Persist ranking columns for Nautilus / other consumers."""
        out = Path(path)
        cols = ["date", "symbol", "abs_return", "vol", "risk_adj", "rs_rank", "qualifies"]
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"ranking frame missing columns: {missing}")
        out.parent.mkdir(parents=True, exist_ok=True)
        df.select(cols).write_parquet(out)
        return out

    @staticmethod
    def load_rankings(path: str | Path) -> pl.DataFrame:
        """Load a ranking parquet written by ``write_rankings``."""
        df = pl.read_parquet(path)
        required = {"date", "symbol", "abs_return", "rs_rank", "qualifies"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"ranking series missing columns: {sorted(missing)}")
        return df

    @staticmethod
    def ranking_index_by_date(
        df: pl.DataFrame,
    ) -> dict[date, list[tuple[str, int | None, bool]]]:
        """Map ``date → [(symbol, rs_rank, qualifies), ...]`` sorted by rank."""
        rows = df.select(["date", "symbol", "rs_rank", "qualifies"]).to_dicts()
        out: dict[date, list[tuple[str, int | None, bool]]] = {}
        for row in rows:
            d = row["date"]
            key = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            rank = row["rs_rank"]
            out.setdefault(key, []).append(
                (
                    str(row["symbol"]),
                    None if rank is None else int(rank),
                    bool(row["qualifies"]),
                )
            )
        for key in out:
            out[key].sort(
                key=lambda item: (item[1] is None, item[1] if item[1] is not None else 10**9)
            )
        return out

    # ── internals ────────────────────────────────────────────────────────────

    @staticmethod
    def _empty() -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "symbol": pl.Utf8,
                "abs_return": pl.Float64,
                "vol": pl.Float64,
                "risk_adj": pl.Float64,
                "rs_rank": pl.Int64,
                "qualifies": pl.Boolean,
            }
        )

    def _to_long(
        self,
        closes: Mapping[str, pl.DataFrame] | pl.DataFrame,
        *,
        symbols: Sequence[str] | None,
    ) -> pl.DataFrame:
        if isinstance(closes, pl.DataFrame):
            required = {"date", "symbol", "close"}
            missing = required - set(closes.columns)
            if missing:
                raise ValueError(f"long close frame missing columns: {sorted(missing)}")
            df = closes.select(
                pl.col("date").cast(pl.Date),
                pl.col("symbol").cast(pl.Utf8),
                pl.col("close").cast(pl.Float64),
            )
            if symbols is not None:
                wanted = {str(s) for s in symbols}
                df = df.filter(pl.col("symbol").is_in(list(wanted)))
            return df.drop_nulls(subset=["close"]).sort(["symbol", "date"])

        frames: list[pl.DataFrame] = []
        keys = list(symbols) if symbols is not None else list(closes.keys())
        for sym in keys:
            if sym not in closes:
                raise KeyError(f"missing close frame for symbol {sym!r}")
            frame = closes[sym]
            if "date" not in frame.columns or "close" not in frame.columns:
                raise ValueError(f"{sym}: expected columns date, close")
            frames.append(
                frame.select(
                    pl.col("date").cast(pl.Date),
                    pl.lit(str(sym)).alias("symbol"),
                    pl.col("close").cast(pl.Float64),
                ).drop_nulls(subset=["close"])
            )
        if not frames:
            return pl.DataFrame(schema={"date": pl.Date, "symbol": pl.Utf8, "close": pl.Float64})
        return pl.concat(frames, how="vertical").sort(["symbol", "date"])

    @staticmethod
    def _score_symbol(group: pl.DataFrame, symbol: str, cfg: RsRankerConfig) -> pl.DataFrame | None:
        closes = group["close"].to_list()
        dates = group["date"].to_list()
        n = len(closes)
        need = cfg.lookback_days + cfg.skip_days + 1
        if n < need:
            return None

        abs_returns: list[float | None] = [None] * n
        vols: list[float | None] = [None] * n
        risk_adjs: list[float | None] = [None] * n
        qualifies: list[bool] = [False] * n

        for i in range(need - 1, n):
            end = i - cfg.skip_days
            start = end - cfg.lookback_days
            if start < 0 or end <= start:
                continue
            p0 = closes[start]
            p1 = closes[end]
            if p0 is None or p1 is None or not math.isfinite(float(p0)) or float(p0) <= 0:
                continue
            if not math.isfinite(float(p1)) or float(p1) <= 0:
                continue
            abs_ret = float(p1) / float(p0) - 1.0
            # Daily simple returns inside [start+1, end].
            rets: list[float] = []
            for j in range(start + 1, end + 1):
                prev = closes[j - 1]
                cur = closes[j]
                if prev is None or cur is None or float(prev) <= 0:
                    continue
                rets.append(float(cur) / float(prev) - 1.0)
            if len(rets) < 2:
                continue
            mean = sum(rets) / len(rets)
            var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
            vol = math.sqrt(var) if var > 0 else 0.0
            score = abs_ret / max(vol, cfg.vol_floor)
            abs_returns[i] = abs_ret
            vols[i] = vol
            risk_adjs[i] = score
            qualifies[i] = abs_ret > cfg.absolute_threshold

        return pl.DataFrame(
            {
                "date": dates,
                "symbol": [symbol] * n,
                "abs_return": abs_returns,
                "vol": vols,
                "risk_adj": risk_adjs,
                "qualifies": qualifies,
            }
        ).with_columns(pl.lit(None).cast(pl.Int64).alias("rs_rank"))

    @staticmethod
    def _attach_cross_sectional_rank(long: pl.DataFrame) -> pl.DataFrame:
        scored = long.filter(pl.col("risk_adj").is_not_null())
        if scored.is_empty():
            return long.with_columns(pl.lit(None).cast(pl.Int64).alias("rs_rank"))

        ranked = scored.with_columns(
            pl.col("risk_adj")
            .rank(method="ordinal", descending=True)
            .over("date")
            .cast(pl.Int64)
            .alias("rs_rank")
        )
        unscored = long.filter(pl.col("risk_adj").is_null()).with_columns(
            pl.lit(None).cast(pl.Int64).alias("rs_rank")
        )
        return pl.concat([ranked, unscored], how="vertical").sort(["date", "symbol"])


__all__ = [
    "RsRanker",
    "RsRankerConfig",
]
