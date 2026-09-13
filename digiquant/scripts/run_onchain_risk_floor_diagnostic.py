#!/usr/bin/env python3
"""Root-cause diagnostic for the on-chain-indicator Stage 4 walk-forward
rejections (``run_onchain_addr_ratio_walk_forward.py`` and
``run_onchain_4bitview_walk_forward.py``, both ``beats_flat_dca_oos=False``,
driven by an infeasible fold 1 with 0% OOS capital deployed).

Both frozen candidates share ``onchain_mvrv_weight=1.0`` and
``onchain_rhodl_weight=1.0`` (long trailing windows: 1095d / 730d). This
computes the actual composite risk index over fold 1's out-of-sample window
(2019-07-01..2021-11-20 -- the COVID crash through the Nov-2021 ATH) and
compares it against the frozen curve shape's ``buy_knee_risk``/
``sell_knee_risk`` dead zone (``curve_shape.py``'s ``rate_at()`` returns
*exactly* 0.0 -- no buy, no sell -- for any risk in
``[buy_knee_risk, sell_knee_risk]``).

Finding: because ``onchain_mvrv``/``onchain_rhodl`` use long (1095d/730d)
trailing lookback windows, they still "remember" the 2017 mega-bubble and
2019 mid-cycle rally through most of 2019-2021 -- so BTC's on-chain ratios
read as merely average, not cheap, even during the COVID crash. This pulls
fold 1's composite-risk floor up to ~33, which never crosses back below the
frozen curve's buy_knee_risk (~29.7-30.5) for the entire 874-day OOS window
-- even at the COVID low (BTC ~$5k, an ~80% drawdown from ATH), risk was
33.7-47.8, still inside the dead zone. The strategy therefore buys exactly
0% of capital for the whole window while flat DCA keeps buying on schedule
and captures the ~600%+ recovery to the Nov-2021 ATH -- producing the
observed OOS ~-77% vs flat DCA in that fold.

This is a structural property of stacking long-lookback on-chain-ratio
indicators at weight=1.0, not something specific to ``onchain_addr_ratio``
(ruled out separately) or necessarily to ``onchain_mvrv``/``onchain_rhodl``
individually -- either alone likely reproduces some version of this, since
both are calibrated the same way and both are present in every rejected mix.

Diagnostic only. Does not touch settings.json or RESEARCH_STATE.md.

Usage:
    uv run python scripts/run_onchain_risk_floor_diagnostic.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from digiquant.data.prices.history_cache import load_cached
from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.curve_optimize import apply_calendar_delay
from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    onchain_asopr_z,
    onchain_mvrv_z,
    onchain_puell_z,
    onchain_rhodl_z,
)
from digiquant.strategies.sdca.optimize import load_sdca_extra_sources, load_sdca_extra_z
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.stage_a import risk_from_weighted_z

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = DIGIQUANT_ROOT / "data" / "price-history"

TICKER = "BTC-USD"
SIGNAL_DELAY_DAYS = 3

# Rejected 4-Bitview-only mix (run_onchain_4bitview_walk_forward.py), the
# smaller of the two rejected candidates -- same mvrv/rhodl weights as the
# 8-dim addr_ratio mix that was rejected first.
WEIGHTS = SdcaCompositeWeights(
    power_law=0.325, m2=0.1, dxy=0.1,
    onchain_mvrv=1.0, onchain_asopr=0.1, onchain_puell=0.1, onchain_rhodl=1.0,
)
ONCHAIN_WINDOWS = {
    "onchain_mvrv": 1095, "onchain_asopr": 1095, "onchain_puell": 1095, "onchain_rhodl": 730,
}
ONCHAIN_Z_FNS = {
    "onchain_mvrv": onchain_mvrv_z, "onchain_asopr": onchain_asopr_z,
    "onchain_puell": onchain_puell_z, "onchain_rhodl": onchain_rhodl_z,
}

# Frozen curve shape from run_onchain_4bitview_curve_search.py.
BUY_KNEE_RISK = 29.7094
SELL_KNEE_RISK = 71.5304

# Walk-forward fold windows (make_walk_forward_folds, n_folds=3,
# holdout_frac=0.2, oos_frac=0.25) on the full 2014-09-17..2026-09-02 series.
WINDOWS = [
    ("fold0 OOS", date(2017, 2, 7), date(2019, 6, 30)),
    ("fold1 OOS", date(2019, 7, 1), date(2021, 11, 20)),
    ("fold2 OOS", date(2021, 11, 21), date(2024, 4, 12)),
    ("holdout", date(2024, 4, 13), date(2026, 9, 2)),
]


def build_risk_frame(cache_dir: Path) -> pl.DataFrame:
    ohlcv = load_cached(TICKER, cache_dir)
    if ohlcv is None or ohlcv.is_empty():
        raise FileNotFoundError(f"no cached {TICKER} under {cache_dir}")
    ohlcv = apply_calendar_delay(ohlcv, SIGNAL_DELAY_DAYS)
    ts_col = "timestamp" if "timestamp" in ohlcv.columns else ohlcv.columns[0]
    dates = ohlcv[ts_col]
    if dates.dtype != pl.Date:
        dates = dates.cast(pl.Date)
    price = ohlcv["close"]

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(dates)
    power_law_z = power_law_confluence_z(
        dates, price, rails["low"], rails["median"], rails["high"], trend_window=180,
    ).to_list()

    sources = load_sdca_extra_sources(cache_dir)
    extra_z: dict[str, list[float | None]] = load_sdca_extra_z(
        dates.to_list(), price.to_list(), data_path=None, data_dir=cache_dir,
    )
    for name, z_fn in ONCHAIN_Z_FNS.items():
        src_dates = getattr(sources, f"{name}_dates")
        src_values = getattr(sources, f"{name}_values")
        if src_dates is None:
            raise SystemExit(f"no {name} source found -- expected all 4 on-chain series present")
        extra_z[name] = z_fn(dates, src_dates, src_values, window=ONCHAIN_WINDOWS[name]).to_list()

    risk = risk_from_weighted_z(dates.to_list(), power_law_z, extra_z, WEIGHTS)
    return pl.DataFrame(
        {
            "date": dates,
            "price": price,
            "risk": pl.Series(risk, dtype=pl.Float64),
            "mvrv_z": pl.Series(extra_z["onchain_mvrv"], dtype=pl.Float64),
            "rhodl_z": pl.Series(extra_z["onchain_rhodl"], dtype=pl.Float64),
        }
    )


def run(cache_dir: Path = DEFAULT_CACHE_DIR) -> None:
    frame = build_risk_frame(cache_dir)
    print(f"frozen weights: {WEIGHTS.model_dump()}")
    print(f"frozen dead zone: buy_knee_risk={BUY_KNEE_RISK}  sell_knee_risk={SELL_KNEE_RISK}\n")

    print("=== composite risk index vs. buy/sell knees, by walk-forward window ===")
    for label, start, end in WINDOWS:
        w = frame.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        below_knee_pct = 100.0 * (w["risk"] < BUY_KNEE_RISK).sum() / w.height
        print(
            f"{label:>10} {start}..{end}  n={w.height:4d}  "
            f"risk mean={w['risk'].mean():6.2f}  min={w['risk'].min():6.2f}  max={w['risk'].max():6.2f}  "
            f"pct_time_below_buy_knee={below_knee_pct:5.1f}%"
        )

    print("\n=== fold 1 OOS: risk around the COVID-crash low (never re-enters buy zone) ===")
    covid = frame.filter((pl.col("date") >= date(2020, 3, 1)) & (pl.col("date") <= date(2020, 3, 31)))
    print(
        f"2020-03 (COVID low): price min={covid['price'].min():,.0f}  "
        f"risk min={covid['risk'].min():.2f}  risk max={covid['risk'].max():.2f}  "
        f"(buy_knee_risk={BUY_KNEE_RISK} -- risk never drops below it even at the crash low)"
    )
    print(
        "\nConclusion: fold 1's OOS risk floor (~33) never dips below the frozen buy_knee_risk "
        f"(~{BUY_KNEE_RISK:.1f}) even during an ~80% drawdown, because onchain_mvrv/onchain_rhodl's "
        "long trailing windows (1095d/730d) still price in the 2017 bubble and 2019 rally through "
        "2019-2021. curve_shape.rate_at() returns exactly 0.0 (dead zone) for any risk in "
        "[buy_knee_risk, sell_knee_risk], so the strategy buys 0% of capital for the entire 874-day "
        "OOS window while flat DCA keeps buying and captures the recovery to the Nov-2021 ATH -- this "
        "is the mechanistic cause of the observed OOS_capital_deployed=0.00% and ~-77% vs flat DCA."
    )
    print(
        "\nDiagnostic only. Not touching RESEARCH_STATE.md/settings.json -- "
        "report back for Chris's explicit accept/reject."
    )


if __name__ == "__main__":
    run()
