#!/usr/bin/env python3
"""Gold HY/IG keep-one duel — relative comparison of the two credit legs (#4804).

hy_oas and ig_oas correlate at |r| ~ 0.86, so at most one survives. Candidates
are `seed` (valuation 1.0/m2 0.5/dxy 0.5), `hy_only` (seed + hy_oas 0.5), and
`ig_only` (seed + ig_oas 0.5), scored on index stats only (coverage, buy-zone
share, mean risk) plus pairwise |r| of each single leg vs dxy/nfci/valuation
on the overlapping window. No backtest, no gate run.

RELATIVE comparison on truncated data only: both staged credit CSVs start
2023-09-30 (~785 rows), so coverage and buy-zone shares are window artifacts.
The winner still waits on full-depth staging (Task 2) before any gate weight.

Decision criterion (in code, printed): keep the leg with the higher buy-zone
share; tie-break: lower max |r| vs (dxy, nfci, valuation). Exact tie on both
keeps neither.

Sanity gate: the `seed` candidate must reproduce `.scratch/gold_seed.json`
risk byte-identically (max abs diff == 0.0); anything else means the loader
or blend changed under the published seed.

Research-only; writes `.scratch/gold_hy_ig_duel.json`. Touches nothing
outside `.scratch/`.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src python3 \\
        digiquant/scripts/run_gold_hy_ig_duel.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_hy_ig_duel.json"

FULL = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    dxy=0.5,
    hy_oas=0.5,
    ig_oas=0.5,
    nfci=0.5,
)
CANDIDATES: dict[str, SdcaCompositeWeights] = {
    "seed": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5),
    "hy_only": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, hy_oas=0.5),
    "ig_only": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, ig_oas=0.5),
}
REF_LEGS = ("dxy", "nfci", "valuation")


def _stats(risk: list[float | None]) -> dict[str, float]:
    valid = [v for v in risk if v is not None]
    buy_zone = sum(1 for v in valid if v < 25.0)
    return {
        "coverage": len(valid),
        "buy_zone_share": buy_zone / max(len(valid), 1),
        "mean_risk": sum(valid) / max(len(valid), 1),
    }


def _decide(
    hy_share: float,
    ig_share: float,
    hy_max_r: float,
    ig_max_r: float,
) -> dict[str, object]:
    """Keep the leg with the higher buy-zone share; tie-break: lower max |r|."""
    if hy_share > ig_share:
        keep, reason = "hy_oas", (f"hy_only buy-zone share {hy_share:.6f} > ig_only {ig_share:.6f}")
    elif ig_share > hy_share:
        keep, reason = "ig_oas", (f"ig_only buy-zone share {ig_share:.6f} > hy_only {hy_share:.6f}")
    elif hy_max_r < ig_max_r:
        keep, reason = (
            "hy_oas",
            (
                f"tied buy-zone share {hy_share:.6f}; "
                f"hy max|r| {hy_max_r:.3f} < ig max|r| {ig_max_r:.3f}"
            ),
        )
    elif ig_max_r < hy_max_r:
        keep, reason = (
            "ig_oas",
            (
                f"tied buy-zone share {ig_share:.6f}; "
                f"ig max|r| {ig_max_r:.3f} < hy max|r| {hy_max_r:.3f}"
            ),
        )
    else:
        keep, reason = (
            "neither",
            (f"tied buy-zone share {hy_share:.6f} and tied max|r| {hy_max_r:.3f}"),
        )
    return {
        "keep": keep,
        "reason": reason,
        "hy_buy_zone_share": hy_share,
        "ig_buy_zone_share": ig_share,
        "hy_max_abs_r": hy_max_r,
        "ig_max_abs_r": ig_max_r,
    }


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    present = [
        k
        for k in ("hy_oas", "ig_oas", "m2", "dxy", "nfci")
        if getattr(sources, f"{k}_dates") is not None
    ]
    print(f"duel legs present: {present}")
    missing = set(FULL.enabled_extras()) - {"valuation"} - set(present)
    if missing:
        raise SystemExit(f"missing staged series for {sorted(missing)} — rerun staging")

    vectors = extra_z_vectors(date_s, price_s, FULL, sources)
    print(f"materialized: {sorted(vectors)}")

    seed_risk = json.loads(SEED_PATH.read_text())["risk"]
    report: dict[str, object] = {"candidates": {}, "correlations": {}}
    valuation_z: list[float | None] | None = None
    for name, weights in CANDIDATES.items():
        extras = extra_indicators_for_window(dates, dates, vectors, weights)
        index = build_risk_index(date_s, price_s, model, extras, valuation_weight=weights.valuation)
        risk = index["risk"].to_list()
        entry = _stats(risk)
        entry["legs"] = sorted(weights.enabled_extras())
        report["candidates"][name] = entry  # type: ignore[index]
        print(f"{name}: {entry}")
        if name == "seed":
            valuation_z = index["valuation_z"].to_list()
            diff = max(
                abs(a - b)
                for a, b in zip(risk, seed_risk, strict=True)
                if a is not None and b is not None
            )
            report["seed_repro_max_abs_diff"] = diff
            print(f"seed repro max abs diff: {diff}")
            if diff != 0.0:
                raise SystemExit("seed no longer reproduces gold_seed.json — stop and investigate")

    assert valuation_z is not None
    frame = pl.DataFrame(
        {
            "hy_oas": vectors["hy_oas"],
            "ig_oas": vectors["ig_oas"],
            "dxy": vectors["dxy"],
            "nfci": vectors["nfci"],
            "valuation": valuation_z,
        }
    ).drop_nulls()
    corr = frame.corr()
    matrix = {
        row: {col: round(val, 3) for col, val in zip(corr.columns, corr.row(i), strict=True)}
        for i, row in enumerate(corr.columns)
    }
    report["correlations"] = matrix
    print(json.dumps(matrix, indent=2))

    hy_max_r = max(abs(matrix["hy_oas"][leg]) for leg in REF_LEGS)
    ig_max_r = max(abs(matrix["ig_oas"][leg]) for leg in REF_LEGS)
    print(f"hy max|r| vs {REF_LEGS}: {hy_max_r:.3f}")
    print(f"ig max|r| vs {REF_LEGS}: {ig_max_r:.3f}")
    candidates = report["candidates"]
    assert isinstance(candidates, dict)
    hy_share = candidates["hy_only"]["buy_zone_share"]  # type: ignore[index]
    ig_share = candidates["ig_only"]["buy_zone_share"]  # type: ignore[index]
    decision = _decide(hy_share, ig_share, hy_max_r, ig_max_r)
    report["decision"] = decision
    print(f"decision: {decision}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
