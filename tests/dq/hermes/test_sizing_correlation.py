"""Asset-class correlation fallback for the deterministic sizer (#934).

When ``get_return_correlations`` has no estimated rho for a pair (thin history),
``_portfolio_vol`` previously defaulted that pair to rho=1.0 (full correlation),
which over-stated ex-ante portfolio vol so vol-targeting systematically over-raised
cash (the Jun-19 "BIL 30% only" symptom). These tests pin the asset-class bucket
fallback (Carver "handcrafting" style) that replaces the rho=1.0 default.
"""

from __future__ import annotations

import math

from digiquant.olympus.hermes.sizing import (
    SizingCaps,
    TickerRisk,
    _bucket_corr,
    _portfolio_vol,
    size_portfolio,
)


def test_bucket_corr_equity_bond_is_diversifying() -> None:
    assert _bucket_corr("EQUITY", "FIXED_INCOME") == 0.0
    assert _bucket_corr("FIXED_INCOME", "EQUITY") == 0.0  # symmetric


def test_bucket_corr_same_equity_high_but_below_one() -> None:
    assert _bucket_corr("EQUITY", "EQUITY") == 0.80


def test_bucket_corr_cash_zero_and_unknown_conservative() -> None:
    assert _bucket_corr("EQUITY", "CASH") == 0.0
    # Unknown class stays conservatively full-correlated — credit only for known pairs.
    assert _bucket_corr("EQUITY", "UNKNOWN") == 1.0


def test_missing_pair_uses_buckets_not_full_correlation() -> None:
    # 50/50 equity (20% vol) + bond (5% vol), no correlation frame.
    # rho=1.0 (old): 0.5*20 + 0.5*5 = 12.5%. bucket rho=0: sqrt(0.25*400 + 0.25*25) = 10.31%.
    risk = {
        "SPY": TickerRisk("SPY", hist_vol_21=20.0, sector="broad", asset_class="EQUITY"),
        "TLT": TickerRisk("TLT", hist_vol_21=5.0, sector="bonds", asset_class="FIXED_INCOME"),
    }
    vol = _portfolio_vol({"SPY": 0.5, "TLT": 0.5}, risk, None, SizingCaps())
    assert math.isclose(vol, math.sqrt(0.25 * 400 + 0.25 * 25), rel_tol=1e-6)
    assert vol < 12.5  # strictly less than the old full-correlation default


def test_equity_bond_book_invests_rather_than_over_cashing() -> None:
    risk = {
        "SPY": TickerRisk("SPY", hist_vol_21=20.0, sector="broad", asset_class="EQUITY"),
        "TLT": TickerRisk("TLT", hist_vol_21=8.0, sector="bonds", asset_class="FIXED_INCOME"),
    }
    res = size_portfolio(
        convictions={"SPY": 4.0, "TLT": 4.0},
        stances={"SPY": "buy", "TLT": "buy"},
        risk=risk,
        corr=None,
        caps=SizingCaps(),
    )
    assert res.gross_pct > 0.0  # diversified book invests instead of dumping to cash
