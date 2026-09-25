"""Per-indicator roughness diagnostic across the full 17 SURVIVING_INDICATORS
(SDCA index smoothing, 2026-09-25). Diagnostic only -- writes to .scratch/,
never settings.json or RESEARCH_STATE.md's validated-candidate section.

Run: uv run python scripts/run_indicator_roughness_diagnostic.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.btc_power_law import BtcPowerLawRiskModel, load_coefficients
from digiquant.strategies.sdca.optimize import load_sdca_extra_z, load_sdca_ohlcv
from digiquant.strategies.sdca.power_law_zscore import power_law_confluence_z
from digiquant.strategies.sdca.roughness import compute_pool_roughness

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "indicator_roughness_diagnostic.json"

# Real Stage 1 per-indicator periods for the macro/on-chain extras (reused from
# run_aggregate_reweight_full17_fixed_index.py's established 17-indicator pattern).
SURVIVING_INDICATORS: tuple[str, ...] = (
    "power_law",
    "m2",
    "rs_eth",
    "dxy",
    "onchain_mvrv",
    "onchain_asopr",
    "onchain_puell",
    "onchain_rhodl",
    "onchain_addr_ratio",
    "fear_greed",
    "weekly_monthly_rsi",
    "weekly_monthly_macd",
    "weekly_rsi",
    "weekly_macd",
    "sma_band",
    "monthly_rsi",
    "monthly_macd",
)

EXTRA_WINDOWS: dict[str, int] = {
    "dxy": 60,
    "onchain_mvrv": 365,
    "onchain_asopr": 365,
    "onchain_puell": 365,
    "onchain_rhodl": 365,
    "onchain_addr_ratio": 365,
    "fear_greed": 270,
}


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["BTC-USD"], data_path=DEFAULT_DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)

    risk_model = BtcPowerLawRiskModel(load_coefficients())
    rails = risk_model.rails(date_s)
    power_law_z = power_law_confluence_z(
        date_s, price_s, rails["low"], rails["median"], rails["high"], trend_window=180
    )

    extra_z = load_sdca_extra_z(
        dates, prices, data_path=DEFAULT_DATA_PATH, data_dir=None, extra_windows=EXTRA_WINDOWS
    )
    missing = [n for n in SURVIVING_INDICATORS if n != "power_law" and n not in extra_z]
    if missing:
        raise SystemExit(f"missing extra_z for: {missing} -- have {sorted(extra_z)}")

    # Convert extra_z lists to pl.Series, maintaining SURVIVING_INDICATORS order
    pool = {"power_law": power_law_z}
    for name in SURVIVING_INDICATORS:
        if name != "power_law":
            if name not in extra_z:
                raise SystemExit(f"missing extra_z for {name}")
            pool[name] = pl.Series(name, extra_z[name], dtype=pl.Float64)

    results = compute_pool_roughness(pool)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps([r.model_dump() for r in results], indent=2))

    print(f"{'name':<22}{'mean':>8}{'p95':>8}{'p99':>8}{'max':>8}{'>2pt':>6}{'>5pt':>6}{'>10pt':>6}")
    for r in sorted(results, key=lambda r: r.max_abs_delta_risk, reverse=True):
        print(
            f"{r.name:<22}{r.mean_abs_delta_risk:>8.2f}{r.p95_abs_delta_risk:>8.2f}"
            f"{r.p99_abs_delta_risk:>8.2f}{r.max_abs_delta_risk:>8.2f}"
            f"{r.spike_days_gt_2:>6}{r.spike_days_gt_5:>6}{r.spike_days_gt_10:>6}"
        )
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
