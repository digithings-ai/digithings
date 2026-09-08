"""WP6.1 — golden characterization of incumbent H8 risk policy (#2687).

Freezes distributed defaults (``SizingCaps``, ``BreakerConfig``, control order,
correlation buckets, vol fallbacks, rank→conviction mapping, effective-input
helpers, and representative final books) before WP6.2 models a versioned
``RiskPolicy``. No production formula changes — tests only.
"""

from __future__ import annotations

from datetime import date
from inspect import signature

import polars as pl
import pytest
from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.portfolio.phases.phase7e_risk_sizing import (
    _VOL_LOOKBACK_DAYS,
    _effective_inputs,
    _memo_effective_inputs,
    _rank_to_conviction,
)
from digiquant.portfolio.risk_controls import BreakerConfig, compute_breaker_scale
from digiquant.portfolio.sizing import (
    _ANNUALIZE,
    SizingCaps,
    TickerRisk,
    _bucket_corr,
    _vol_fraction,
    size_portfolio,
)
from digiquant.research.data.queries import get_return_correlations

from tests.dq.portfolio.incumbent_risk_fixtures import (
    assert_book_matches_golden,
    dataclass_matches_fixture,
    load_incumbent_risk_fixture,
    sizing_result_snapshot,
)

pytestmark = pytest.mark.unit

_GOLDEN = load_incumbent_risk_fixture()


def _permissive(**over: float | str) -> SizingCaps:
    base: dict[str, float | str] = {
        "min_position_pct": 0.0,
        "max_position_pct": 100.0,
        "max_sector_pct": 100.0,
        "weight_increment_pct": 0.0,
        "target_portfolio_vol": 1.0e6,
        "max_gross_pct": 100.0,
        "min_conviction": 2.0,
    }
    base.update(over)
    return SizingCaps(**base)


# --------------------------------------------------------------------------- policy defaults


def test_incumbent_sizing_caps_defaults_match_fixture() -> None:
    assert dataclass_matches_fixture(SizingCaps(), _GOLDEN["policy_defaults"]["sizing_caps"])


def test_incumbent_breaker_config_defaults_match_fixture() -> None:
    assert dataclass_matches_fixture(BreakerConfig(), _GOLDEN["policy_defaults"]["breaker_config"])


def test_incumbent_horizon_and_control_order_frozen() -> None:
    defaults = _GOLDEN["policy_defaults"]
    assert _ANNUALIZE == defaults["annualize_factor"]
    assert _VOL_LOOKBACK_DAYS == defaults["vol_lookback_days"]
    assert (
        signature(get_return_correlations).parameters["lookback_days"].default
        == (defaults["corr_lookback_days"])
    )
    assert defaults["control_order"] == [
        "select",
        "raw_weights",
        "position_caps",
        "sector_caps",
        "corr_dedup",
        "vol_target",
        "drawdown_breaker",
        "grid_rounding",
    ]


# --------------------------------------------------------------------------- vol fallback + buckets


@pytest.mark.parametrize(
    ("label", "class_a", "class_b"),
    [
        ("equity_bond", "EQUITY", "FIXED_INCOME"),
        ("equity_equity", "EQUITY", "EQUITY"),
        ("equity_cash", "EQUITY", "CASH"),
        ("equity_unknown", "EQUITY", "UNKNOWN"),
        ("equity_commodity", "EQUITY", "COMMODITY"),
        ("equity_crypto", "EQUITY", "CRYPTO"),
        ("fixed_income_fixed_income", "FIXED_INCOME", "FIXED_INCOME"),
    ],
)
def test_incumbent_bucket_correlation_golden(label: str, class_a: str, class_b: str) -> None:
    assert _bucket_corr(class_a, class_b) == _GOLDEN["bucket_correlations"][label]


def test_incumbent_vol_fallback_chain_golden() -> None:
    caps = SizingCaps()
    expected = _GOLDEN["vol_fallback"]
    assert (
        round(_vol_fraction(TickerRisk("X", hist_vol_21=25.0), caps) * 100, 4)
        == expected["hist_vol_21"]
    )
    assert round(_vol_fraction(TickerRisk("X", atr_pct=1.5), caps) * 100, 4) == expected["atr_pct"]
    assert round(_vol_fraction(TickerRisk("X"), caps) * 100, 4) == expected["default_annual_vol"]


# --------------------------------------------------------------------------- rank → conviction + effective inputs


@pytest.mark.parametrize("n_key", ["n_long_1", "n_long_2", "n_long_3", "n_long_5"])
def test_incumbent_rank_to_conviction_golden(n_key: str) -> None:
    n = int(n_key.split("_")[-1])
    expected = _GOLDEN["rank_to_conviction"][n_key]
    for rank_str, want in expected.items():
        got = round(_rank_to_conviction(int(rank_str), n, floor=2.0), 4)
        assert got == want


def test_incumbent_memo_effective_inputs_golden() -> None:
    memo = PMDirectionMemo(
        date=date(2026, 6, 12),
        roster=[
            TickerDirection(ticker="AAA", direction="long", conviction_rank=1),
            TickerDirection(ticker="BBB", direction="long", conviction_rank=2),
            TickerDirection(ticker="CCC", direction="long", conviction_rank=3),
        ],
        memo="test",
    )
    conv, stances = _memo_effective_inputs(
        memo,
        {"AAA": {"stance": "buy"}, "BBB": {"stance": "hold"}, "CCC": {"stance": "sell"}},
        2.0,
    )
    expected = _GOLDEN["memo_effective_inputs"]["three_long_mixed_stances"]
    assert {k: round(v, 4) for k, v in conv.items()} == expected["convictions"]
    assert stances == expected["stances"]


def test_incumbent_effective_inputs_golden() -> None:
    conv, stances = _effective_inputs(
        ["AAA", "BBB", "CCC"],
        {
            "AAA": {"conviction_score": 5, "stance": "buy"},
            "BBB": {"conviction_score": 3, "stance": "hold"},
        },
        {"AAA": {"conviction_delta": 1.0}, "BBB": {"conviction_delta": -0.5}},
        2.0,
    )
    expected = _GOLDEN["effective_inputs"]["analyst_debate_blend"]
    assert {k: round(v, 4) for k, v in conv.items()} == expected["convictions"]
    assert stances == expected["stances"]


# --------------------------------------------------------------------------- breaker scales


@pytest.mark.parametrize(
    ("label", "navs"),
    [
        ("fresh_book", [100.0]),
        ("shallow_dd", [100.0, 95.0]),
        ("soft_boundary", [100.0, 92.0]),
        ("mid_ramp", [100.0, 86.0]),
        ("hard_dd", [100.0, 75.0]),
    ],
)
def test_incumbent_breaker_scale_golden(label: str, navs: list[float]) -> None:
    state = compute_breaker_scale(navs)
    expected = _GOLDEN["breaker_scales"][label]
    assert state.scale == expected["scale"]
    assert state.drawdown_pct == expected["drawdown_pct"]


# --------------------------------------------------------------------------- SizingCaps leaves + representative books


_LEAF_SCENARIOS: dict[str, dict] = {
    "min_position_pct": dict(
        convictions={"TINY": 2.0, "BIG": 5.0},
        stances={"TINY": "buy", "BIG": "buy"},
        risk={
            "TINY": TickerRisk("TINY", hist_vol_21=40.0),
            "BIG": TickerRisk("BIG", hist_vol_21=10.0),
        },
        caps=_permissive(min_position_pct=10.0),
    ),
    "max_position_pct": dict(
        convictions={"ONE": 5.0},
        stances={"ONE": "buy"},
        risk={"ONE": TickerRisk("ONE", hist_vol_21=20.0)},
        caps=SizingCaps(max_position_pct=30.0),
    ),
    "max_sector_pct": dict(
        convictions={"T1": 4.0, "T2": 4.0, "EN": 4.0},
        stances={"T1": "buy", "T2": "buy", "EN": "buy"},
        risk={
            "T1": TickerRisk("T1", hist_vol_21=20.0, sector="TECH"),
            "T2": TickerRisk("T2", hist_vol_21=20.0, sector="TECH"),
            "EN": TickerRisk("EN", hist_vol_21=20.0, sector="ENERGY"),
        },
        caps=_permissive(max_sector_pct=40.0),
    ),
    "weight_increment_pct": dict(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk={"HI": TickerRisk("HI", hist_vol_21=20.0), "LO": TickerRisk("LO", hist_vol_21=20.0)},
        caps=_permissive(weight_increment_pct=5.0),
    ),
    "target_portfolio_vol": dict(
        convictions={"V": 5.0},
        stances={"V": "buy"},
        risk={"V": TickerRisk("V", hist_vol_21=40.0)},
        caps=_permissive(target_portfolio_vol=12.0),
    ),
    "corr_dedup_threshold": dict(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk={"A": TickerRisk("A", hist_vol_21=20.0), "B": TickerRisk("B", hist_vol_21=20.0)},
        corr=pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]}),
        caps=_permissive(corr_dedup_threshold=0.80),
    ),
    "min_conviction": dict(
        convictions={"AAA": 1.0, "BBB": 1.9},
        stances={"AAA": "buy", "BBB": "buy"},
        risk={
            "AAA": TickerRisk("AAA", hist_vol_21=20.0),
            "BBB": TickerRisk("BBB", hist_vol_21=20.0),
        },
    ),
    "drawdown_breaker": dict(
        convictions={"B": 5.0},
        stances={"B": "buy"},
        risk={"B": TickerRisk("B", hist_vol_21=12.0)},
        caps=_permissive(),
        breaker_scale=0.5,
    ),
    "kelly_fraction": dict(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk={"A": TickerRisk("A", hist_vol_21=15.0), "B": TickerRisk("B", hist_vol_21=25.0)},
        caps=_permissive(sizing_mode="kelly", kelly_fraction=0.5),
    ),
}

_REP_BOOK_SCENARIOS: dict[str, dict] = {
    "default_caps_equity_bond": dict(
        convictions={"SPY": 4.0, "TLT": 4.0},
        stances={"SPY": "buy", "TLT": "buy"},
        risk={
            "SPY": TickerRisk("SPY", hist_vol_21=20.0, sector="broad", asset_class="EQUITY"),
            "TLT": TickerRisk("TLT", hist_vol_21=8.0, sector="bonds", asset_class="FIXED_INCOME"),
        },
    ),
    "default_caps_single_name": dict(
        convictions={"ONE": 5.0},
        stances={"ONE": "buy"},
        risk={"ONE": TickerRisk("ONE", hist_vol_21=20.0, sector="TECH")},
    ),
    "kelly_mode_pair": dict(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk={
            "A": TickerRisk("A", hist_vol_21=15.0, sector="X"),
            "B": TickerRisk("B", hist_vol_21=25.0, sector="Y"),
        },
        caps=_permissive(sizing_mode="kelly", kelly_fraction=0.25),
    ),
    "multi_pressure_default_caps": dict(
        convictions={"AAPL": 5.0, "MSFT": 4.5, "NVDA": 4.0, "GLD": 2.0},
        stances={"AAPL": "buy", "MSFT": "buy", "NVDA": "buy", "GLD": "hold"},
        risk={
            "AAPL": TickerRisk("AAPL", hist_vol_21=25.0, sector="TECH"),
            "MSFT": TickerRisk("MSFT", hist_vol_21=22.0, sector="TECH"),
            "NVDA": TickerRisk("NVDA", hist_vol_21=55.0, sector="TECH"),
            "GLD": TickerRisk("GLD", hist_vol_21=12.0, sector="COMMODITY"),
        },
    ),
}


@pytest.mark.parametrize("leaf", _LEAF_SCENARIOS.keys())
def test_incumbent_sizing_caps_leaf_golden(leaf: str) -> None:
    result = size_portfolio(**_LEAF_SCENARIOS[leaf])
    assert_book_matches_golden(sizing_result_snapshot(result), _GOLDEN["sizing_caps_leaves"][leaf])


@pytest.mark.parametrize("book", _REP_BOOK_SCENARIOS.keys())
def test_incumbent_representative_book_golden(book: str) -> None:
    result = size_portfolio(**_REP_BOOK_SCENARIOS[book])
    assert_book_matches_golden(
        sizing_result_snapshot(result), _GOLDEN["representative_books"][book]
    )


def test_incumbent_sizing_caps_field_coverage() -> None:
    """Every ``SizingCaps`` dataclass field has a named golden leaf or default entry."""
    defaults = set(_GOLDEN["policy_defaults"]["sizing_caps"])
    leaves = set(_GOLDEN["sizing_caps_leaves"])
    covered = defaults.copy()
    # max_gross_pct and kelly_annual_premium bind only under multi-pressure books.
    for field in ("max_gross_pct", "kelly_annual_premium", "sizing_mode", "default_annual_vol"):
        covered.discard(field)
    assert leaves >= {
        "min_position_pct",
        "max_position_pct",
        "max_sector_pct",
        "weight_increment_pct",
        "target_portfolio_vol",
        "corr_dedup_threshold",
        "min_conviction",
        "drawdown_breaker",
        "kelly_fraction",
    }
    assert "multi_pressure_default_caps" in _GOLDEN["representative_books"]
