"""Deterministic sizer (Pillar 2) — pure-function contract.

``size_portfolio`` is the code half of the direction/sizing split: it turns per-ticker
conviction + stance into final target weights via select → raw weights → position caps →
sector caps → correlation de-dup → vol-target → breaker → round-to-grid → cash residual.
Every reduction step is **reduce-only / cash-first**: weight freed by a cap or a drop
becomes CASH, never redistributed up (which would re-breach the cap it just enforced).
"""

from __future__ import annotations

import polars as pl
import pytest

from digiquant.olympus.hermes.sizing import (
    SizingCaps,
    TickerRisk,
    size_portfolio,
)

pytestmark = pytest.mark.unit


def _permissive(**over: float | str) -> SizingCaps:
    """Caps with every binding constraint relaxed; override one to isolate its effect."""
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


def _risk(mapping: dict[str, tuple[float, str]]) -> dict[str, TickerRisk]:
    """{ticker: (annual_vol_pct, sector)} → {ticker: TickerRisk}."""
    return {
        t: TickerRisk(ticker=t, hist_vol_21=vol, sector=sector)
        for t, (vol, sector) in mapping.items()
    }


def _targets(result) -> dict[str, float]:
    return {p.ticker: p.target_pct for p in result.positions}


# --------------------------------------------------------------------------- empty / select


def test_empty_convictions_is_all_cash() -> None:
    result = size_portfolio(convictions={}, stances={}, risk={})
    assert result.positions == []
    assert result.cash_pct == 100.0
    assert result.gross_pct == 0.0
    assert "cash" in result.explanation.lower()


def test_none_clear_conviction_bar_is_all_cash() -> None:
    # All below the default min_conviction (2.0) → defensive 100% cash.
    result = size_portfolio(
        convictions={"AAA": 1.0, "BBB": 1.9},
        stances={"AAA": "buy", "BBB": "buy"},
        risk=_risk({"AAA": (20.0, "TECH"), "BBB": (20.0, "TECH")}),
    )
    assert result.positions == []
    assert result.cash_pct == 100.0


def test_select_gates_conviction_and_stance() -> None:
    # Only buy/hold above the bar enter: A below bar, C sell, D watch are all excluded.
    result = size_portfolio(
        convictions={"A": 1.5, "B": 3.0, "C": 4.0, "D": 4.0, "E": 3.0},
        stances={"A": "buy", "B": "buy", "C": "sell", "D": "watch", "E": "hold"},
        risk=_risk({t: (20.0, str(i)) for i, t in enumerate("ABCDE")}),
        caps=_permissive(),
    )
    assert set(_targets(result)) == {"B", "E"}


# --------------------------------------------------------------------------- raw weighting


def test_inverse_vol_tilt_at_equal_conviction() -> None:
    # Equal conviction, 4x vol gap → the low-vol name gets ~4x the weight (w ∝ conv/vol).
    result = size_portfolio(
        convictions={"LOW": 4.0, "HIGH": 4.0},
        stances={"LOW": "buy", "HIGH": "buy"},
        risk=_risk({"LOW": (10.0, "L"), "HIGH": (40.0, "H")}),
        caps=_permissive(),
    )
    t = _targets(result)
    assert t["LOW"] > t["HIGH"]
    assert t["LOW"] / t["HIGH"] == pytest.approx(4.0, rel=0.05)
    assert t["LOW"] + t["HIGH"] == pytest.approx(100.0, abs=1e-6)


def test_conviction_tilt_at_equal_vol() -> None:
    # Equal vol, 2x conviction gap → ~2x the weight (w ∝ conviction).
    result = size_portfolio(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk=_risk({"HI": (20.0, "X"), "LO": (20.0, "Y")}),
        caps=_permissive(),
    )
    t = _targets(result)
    assert t["HI"] / t["LO"] == pytest.approx(2.0, rel=0.05)


# --------------------------------------------------------------------------- position caps


def test_max_position_cap_leaves_cash_residual() -> None:
    # Single conviction name would want 100%; the 30% cap freed weight becomes CASH,
    # not re-inflated back to 100% (reduce-only).
    result = size_portfolio(
        convictions={"ONE": 5.0},
        stances={"ONE": "buy"},
        risk=_risk({"ONE": (20.0, "TECH")}),
        caps=SizingCaps(max_position_pct=30.0),
    )
    t = _targets(result)
    assert t["ONE"] == pytest.approx(30.0)
    assert result.cash_pct == pytest.approx(70.0)
    assert any("capped" in n for n in result.positions[0].notes)


def test_sub_min_position_is_dropped_to_cash() -> None:
    # The tiny leg falls below the 10% floor → dropped; its weight becomes cash, the
    # surviving leg is NOT scaled up to fill the gap (reduce-only).
    result = size_portfolio(
        convictions={"TINY": 2.0, "BIG": 5.0},
        stances={"TINY": "buy", "BIG": "buy"},
        risk=_risk({"TINY": (40.0, "A"), "BIG": (10.0, "B")}),
        caps=_permissive(min_position_pct=10.0),
    )
    t = _targets(result)
    assert "TINY" not in t
    assert "BIG" in t
    assert result.cash_pct > 0.0  # freed weight is cash, not redistributed


# --------------------------------------------------------------------------- sector caps


def test_sector_cap_scales_down_overweight_bucket() -> None:
    # Two TECH names + one ENERGY name, equal raw weights (~33% each). TECH (66%) is
    # scaled to the 40% cap; the freed 26% becomes cash (reduce-only, not given to ENERGY).
    result = size_portfolio(
        convictions={"T1": 4.0, "T2": 4.0, "EN": 4.0},
        stances={"T1": "buy", "T2": "buy", "EN": "buy"},
        risk=_risk({"T1": (20.0, "TECH"), "T2": (20.0, "TECH"), "EN": (20.0, "ENERGY")}),
        caps=_permissive(max_position_pct=100.0, max_sector_pct=40.0),
    )
    t = _targets(result)
    tech = t["T1"] + t["T2"]
    assert tech == pytest.approx(40.0, abs=0.5)
    assert t["EN"] == pytest.approx(100.0 / 3.0, abs=0.5)  # untouched
    assert result.cash_pct == pytest.approx(100.0 - tech - t["EN"], abs=1e-3)
    assert any("sector-capped" in n for n in result.positions[0].notes + result.positions[1].notes)


# --------------------------------------------------------------------------- correlation de-dup


def test_corr_dedup_drops_lower_conviction_leg() -> None:
    # A and B are 0.9 correlated (> 0.8 default); the lower-conviction leg (B) is dropped
    # and its weight becomes cash — the survivor keeps its own weight (reduce-only).
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]})
    result = size_portfolio(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        corr=corr,
        caps=_permissive(),
    )
    t = _targets(result)
    assert "B" not in t
    assert "A" in t
    assert result.cash_pct > 0.0


def test_corr_dedup_tie_break_is_order_independent() -> None:
    # Equal conviction → the tie is broken by ticker (lexicographically larger dropped),
    # so the survivor is the same whether the frame stores the pair as (A,B) or (B,A).
    risk = _risk({"A": (20.0, "X"), "B": (20.0, "Y")})
    convs = {"A": 4.0, "B": 4.0}
    stances = {"A": "buy", "B": "buy"}
    ab = size_portfolio(
        convictions=convs,
        stances=stances,
        risk=risk,
        corr=pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.95]}),
        caps=_permissive(),
    )
    ba = size_portfolio(
        convictions=convs,
        stances=stances,
        risk=risk,
        corr=pl.DataFrame({"a": ["B"], "b": ["A"], "corr": [0.95]}),
        caps=_permissive(),
    )
    assert set(_targets(ab)) == {"A"}
    assert set(_targets(ba)) == {"A"}


def test_corr_below_threshold_keeps_both() -> None:
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.5]})
    result = size_portfolio(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        corr=corr,
        caps=_permissive(),
    )
    assert set(_targets(result)) == {"A", "B"}


# --------------------------------------------------------------------------- vol target / breaker


def test_vol_target_scales_a_high_vol_book_to_budget() -> None:
    # One 40%-vol name fully invested = 40% portfolio vol; the 12% budget scales gross to
    # ~30% so ex-ante vol lands on target, the rest is cash.
    result = size_portfolio(
        convictions={"V": 5.0},
        stances={"V": "buy"},
        risk=_risk({"V": (40.0, "X")}),
        caps=_permissive(max_position_pct=100.0, target_portfolio_vol=12.0),
    )
    t = _targets(result)
    assert t["V"] == pytest.approx(30.0, abs=0.5)
    assert result.applied_scales["vol_scale"] == pytest.approx(0.30, abs=0.02)
    assert result.realized_portfolio_vol == pytest.approx(12.0, abs=0.5)


def test_missing_correlation_is_conservatively_full() -> None:
    # Two equal 30%-vol names with NO correlation data. Unknown ρ defaults to +1.0 (full
    # correlation), so the un-scaled book's vol is the weighted sum (30%), not the
    # diversified √-sum (~21%). Vol-targeting to 12% therefore scales gross to ~40% and
    # parks the rest in cash — the conservative outcome when correlations are unknown.
    result = size_portfolio(
        convictions={"A": 4.0, "B": 4.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (30.0, "X"), "B": (30.0, "Y")}),
        corr=None,
        caps=_permissive(max_position_pct=100.0, target_portfolio_vol=12.0),
    )
    assert result.gross_pct == pytest.approx(40.0, abs=1.0)
    assert result.realized_portfolio_vol == pytest.approx(12.0, abs=0.5)
    assert result.cash_pct == pytest.approx(60.0, abs=1.0)


def test_breaker_raises_cash() -> None:
    risk = _risk({"B": (12.0, "X")})
    caps = _permissive(max_position_pct=100.0, target_portfolio_vol=1.0e6)
    full = size_portfolio(
        convictions={"B": 5.0}, stances={"B": "buy"}, risk=risk, caps=caps, breaker_scale=1.0
    )
    halved = size_portfolio(
        convictions={"B": 5.0}, stances={"B": "buy"}, risk=risk, caps=caps, breaker_scale=0.5
    )
    assert full.gross_pct == pytest.approx(100.0)
    assert halved.gross_pct == pytest.approx(50.0)
    assert halved.cash_pct == pytest.approx(50.0)
    assert halved.applied_scales["breaker_scale"] == pytest.approx(0.5)


def test_breaker_scale_is_clamped_to_unit_interval() -> None:
    # An out-of-range breaker (e.g. a buggy upstream 2.0) can never lever up past 100%.
    risk = _risk({"B": (12.0, "X")})
    caps = _permissive(max_position_pct=100.0, target_portfolio_vol=1.0e6)
    result = size_portfolio(
        convictions={"B": 5.0}, stances={"B": "buy"}, risk=risk, caps=caps, breaker_scale=2.0
    )
    assert result.gross_pct <= 100.0 + 1e-6
    assert result.applied_scales["breaker_scale"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- rounding / invariants


def test_round_to_grid_snaps_weights_down() -> None:
    # Raw 66.7 / 33.3 floor DOWN to the 5% grid → 65 / 30; the 5% remainder becomes cash
    # (rounding down, never to nearest, can't lift gross past 100% or re-breach a cap).
    result = size_portfolio(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk=_risk({"HI": (20.0, "X"), "LO": (20.0, "Y")}),
        caps=_permissive(weight_increment_pct=5.0),
    )
    t = _targets(result)
    assert t["HI"] == pytest.approx(65.0)
    assert t["LO"] == pytest.approx(30.0)
    assert result.cash_pct == pytest.approx(5.0)
    for p in result.positions:
        assert p.target_pct % 5.0 == pytest.approx(0.0, abs=1e-6)


def test_gross_never_exceeds_full_invested_and_cash_reconciles() -> None:
    result = size_portfolio(
        convictions={"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.5},
        stances={"A": "buy", "B": "hold", "C": "buy", "D": "buy"},
        risk=_risk(
            {"A": (15.0, "TECH"), "B": (22.0, "ENERGY"), "C": (30.0, "BONDS"), "D": (18.0, "GOLD")}
        ),
    )
    assert result.gross_pct <= 100.0 + 1e-6
    assert result.cash_pct >= 0.0
    assert result.gross_pct + result.cash_pct == pytest.approx(100.0, abs=1e-3)
    assert all(p.target_pct > 0 for p in result.positions)


def test_all_candidates_dropped_by_min_is_all_cash() -> None:
    # Three equal names (~33% each) under an absurd 60% floor → every leg dropped → cash.
    result = size_portfolio(
        convictions={"A": 4.0, "B": 4.0, "C": 4.0},
        stances={"A": "buy", "B": "buy", "C": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y"), "C": (20.0, "Z")}),
        caps=_permissive(min_position_pct=60.0),
    )
    assert result.positions == []
    assert result.cash_pct == 100.0
    assert "dropped" in result.explanation.lower()


# --------------------------------------------------------------------------- kelly / preferences


def test_kelly_mode_produces_a_valid_book() -> None:
    result = size_portfolio(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (15.0, "X"), "B": (25.0, "Y")}),
        caps=_permissive(sizing_mode="kelly"),
    )
    t = _targets(result)
    assert t  # non-empty
    assert result.gross_pct <= 100.0 + 1e-6
    # Higher edge (conviction) + lower vol → A outsizes B under fractional-Kelly too.
    assert t["A"] > t["B"]


def test_from_preferences_reads_config_keys() -> None:
    caps = SizingCaps.from_preferences(
        {
            "max_single_etf_pct": 25.0,
            "weight_increment_pct": 10.0,
            "max_sector_pct": 50.0,
            "target_portfolio_vol": 15.0,
            "sizing_mode": "kelly",
            "min_position_pct": 3.0,
            "min_conviction": 1.5,
            "corr_dedup_threshold": 0.7,
            "kelly_fraction": 0.5,
        }
    )
    assert caps.max_position_pct == 25.0
    assert caps.weight_increment_pct == 10.0
    assert caps.max_sector_pct == 50.0
    assert caps.target_portfolio_vol == 15.0
    assert caps.sizing_mode == "kelly"
    assert caps.min_position_pct == 3.0
    assert caps.min_conviction == 1.5
    assert caps.corr_dedup_threshold == 0.7
    assert caps.kelly_fraction == 0.5


def test_from_preferences_keeps_defaults_when_absent() -> None:
    caps = SizingCaps.from_preferences({})
    assert caps == SizingCaps()
