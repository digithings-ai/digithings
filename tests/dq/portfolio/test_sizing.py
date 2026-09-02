"""Deterministic sizer (Pillar 2) — pure-function contract.

``size_portfolio`` is the code half of the direction/sizing split: it turns per-ticker
conviction + stance into final target weights via select → raw weights → position caps →
sector caps → correlation de-dup → vol-target → breaker → round-to-grid → cash residual.
Every reduction step is **reduce-only / cash-first**: weight freed by a cap or a drop
becomes CASH, never redistributed up (which would re-breach the cap it just enforced).

WP8.5 (#2738): post-cutover calibrated-path control-shell locks live in
``test_allocation_invariants.py``; this module remains the incumbent-leaf suite.
"""

from __future__ import annotations

import polars as pl
import pytest
from digiquant.portfolio.sizing import (
    SizingCaps,
    TickerRisk,
    size_portfolio,
)
from digiquant.portfolio.sizing_events import SizingAdjustmentType, validate_sizing_lineage

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


def _adjustments(result) -> dict[str, list]:
    """{ticker: [SizingAdjustment, ...]} grouping, preserving emission order."""
    out: dict[str, list] = {}
    for a in result.adjustments:
        out.setdefault(a.ticker, []).append(a)
    return out


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


def test_sub_min_position_is_dropped() -> None:
    # The tiny leg falls below the 10% floor → dropped. The min-position step itself does
    # not redistribute its weight to the survivor (reduce-only); but with the vol budget
    # left unfilled the downstream vol-target step scales the survivor up toward the budget
    # (#943), so an otherwise-unconstrained book ends fully invested. Cash residual from a
    # dropped leg is exercised under a *binding* cap by the position/sector/grid tests.
    result = size_portfolio(
        convictions={"TINY": 2.0, "BIG": 5.0},
        stances={"TINY": "buy", "BIG": "buy"},
        risk=_risk({"TINY": (40.0, "A"), "BIG": (10.0, "B")}),
        caps=_permissive(min_position_pct=10.0),
    )
    t = _targets(result)
    assert "TINY" not in t
    assert t == {"BIG": pytest.approx(100.0, abs=0.5)}


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
    # A and B are 0.9 correlated (> 0.8 default); the lower-conviction leg (B) is dropped.
    # The de-dup step does not redistribute B's weight to A (reduce-only); the unfilled vol
    # budget then lets the vol-target step scale A up toward the budget (#943).
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
    assert t == {"A": pytest.approx(100.0, abs=0.5)}


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


def test_vol_target_scales_up_an_underrisked_book_toward_budget() -> None:
    # #943: an under-risked book must deploy toward the vol budget instead of parking the
    # freed weight in cash. B (conviction 2.5) is dropped below the 40% floor, leaving A
    # alone at its raw ~66.7%. The old reduce-only vol step capped scaling at 1.0, so the
    # book sat at 66.7% invested / 33% cash with ex-ante vol ~6.7% — far under the 12%
    # budget. Scale-up lifts A toward the budget, bounded by the 80% position cap.
    result = size_portfolio(
        convictions={"A": 5.0, "B": 2.5},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (10.0, "X"), "B": (10.0, "Y")}),
        caps=_permissive(min_position_pct=40.0, max_position_pct=80.0, target_portfolio_vol=12.0),
    )
    t = _targets(result)
    assert "B" not in t  # dropped below the 40% floor → its weight becomes cash
    assert t["A"] == pytest.approx(80.0, abs=0.5)  # scaled up to the cap, not left at 66.7%
    assert result.cash_pct == pytest.approx(20.0, abs=0.5)
    assert result.realized_portfolio_vol > 6.7  # moved toward the 12% budget


def test_vol_scale_up_never_breaches_a_sector_cap() -> None:
    # Scaling the book up toward the vol budget must not lift a capped sector bucket past
    # its cap. Two low-vol TECH names + one ENERGY name; TECH is sector-capped to 40%, then
    # the (very-under-budget) book tries to scale up — TECH must stay pinned at 40%.
    result = size_portfolio(
        convictions={"T1": 4.0, "T2": 4.0, "EN": 4.0},
        stances={"T1": "buy", "T2": "buy", "EN": "buy"},
        risk=_risk({"T1": (6.0, "TECH"), "T2": (6.0, "TECH"), "EN": (6.0, "ENERGY")}),
        caps=_permissive(max_position_pct=100.0, max_sector_pct=40.0, target_portfolio_vol=12.0),
    )
    t = _targets(result)
    assert t["T1"] + t["T2"] == pytest.approx(40.0, abs=0.6)  # sector cap holds under scale-up


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


# --------------------------------------------------------------------------- adjustment events


def test_single_name_cap_emits_adjustment_for_capped_leg() -> None:
    # Same scenario as test_max_position_cap_leaves_cash_residual: ONE wants 100%, capped
    # to 30% → one SINGLE_NAME_CAP event, 100.0 -> 30.0.
    result = size_portfolio(
        convictions={"ONE": 5.0},
        stances={"ONE": "buy"},
        risk=_risk({"ONE": (20.0, "TECH")}),
        caps=SizingCaps(max_position_pct=30.0),
    )
    events = _adjustments(result)["ONE"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.SINGLE_NAME_CAP
    assert events[0].original_pct == pytest.approx(100.0)
    assert events[0].adjusted_pct == pytest.approx(30.0)


def test_single_name_cap_emits_adjustment_for_dropped_leg() -> None:
    # Same scenario as test_sub_min_position_is_dropped: TINY's raw ~9.09% falls below the
    # 10% floor → dropped to 0, still tagged SINGLE_NAME_CAP (same control, opposite branch).
    result = size_portfolio(
        convictions={"TINY": 2.0, "BIG": 5.0},
        stances={"TINY": "buy", "BIG": "buy"},
        risk=_risk({"TINY": (40.0, "A"), "BIG": (10.0, "B")}),
        caps=_permissive(min_position_pct=10.0),
    )
    events = _adjustments(result)["TINY"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.SINGLE_NAME_CAP
    assert events[0].original_pct == pytest.approx(9.0909, abs=0.01)
    assert events[0].adjusted_pct == 0.0


def test_sector_cap_emits_one_adjustment_per_capped_ticker() -> None:
    # Same scenario as test_sector_cap_scales_down_overweight_bucket: T1/T2 scaled from
    # ~33.33% to ~20% each (66.67% TECH bucket capped to 40%); EN is untouched → no event.
    result = size_portfolio(
        convictions={"T1": 4.0, "T2": 4.0, "EN": 4.0},
        stances={"T1": "buy", "T2": "buy", "EN": "buy"},
        risk=_risk({"T1": (20.0, "TECH"), "T2": (20.0, "TECH"), "EN": (20.0, "ENERGY")}),
        caps=_permissive(max_position_pct=100.0, max_sector_pct=40.0),
    )
    by_ticker = _adjustments(result)
    for t in ("T1", "T2"):
        assert len(by_ticker[t]) == 1
        assert by_ticker[t][0].adjustment_type == SizingAdjustmentType.SECTOR_CAP
        assert by_ticker[t][0].original_pct == pytest.approx(100.0 / 3.0, abs=0.01)
        assert by_ticker[t][0].adjusted_pct == pytest.approx(20.0, abs=0.5)
    assert "EN" not in by_ticker


def test_corr_dedup_emits_adjustment_for_dropped_leg() -> None:
    # Same scenario as test_corr_dedup_drops_lower_conviction_leg: B's raw 37.5% is dropped
    # to 0, reason string carries over verbatim from the existing note.
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]})
    result = size_portfolio(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        corr=corr,
        caps=_permissive(),
    )
    events = _adjustments(result)["B"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.CORRELATION_DEDUP
    assert events[0].original_pct == pytest.approx(37.5)
    assert events[0].adjusted_pct == 0.0
    assert "corr-dedup" in events[0].reason


def test_vol_target_scale_emits_adjustment_when_vol_is_the_binding_factor() -> None:
    # Same scenario as test_vol_target_scales_a_high_vol_book_to_budget: single ticker, no
    # cap binds (all cap-scales are 1.0), so vol_scale (~0.30) is the binding factor and a
    # VOLATILITY_SCALE event fires: 100.0 -> ~30.0.
    result = size_portfolio(
        convictions={"V": 5.0},
        stances={"V": "buy"},
        risk=_risk({"V": (40.0, "X")}),
        caps=_permissive(max_position_pct=100.0, target_portfolio_vol=12.0),
    )
    events = _adjustments(result)["V"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.VOLATILITY_SCALE
    assert events[0].original_pct == pytest.approx(100.0)
    assert events[0].adjusted_pct == pytest.approx(30.0, abs=0.5)


def test_scale_up_bound_by_a_cap_emits_final_gross_scale_not_volatility_scale() -> None:
    # Same scenario as test_vol_target_scales_up_an_underrisked_book_toward_budget: the
    # scale-up is bound by the 80% position cap (binding factor = "pos"), not vol. That is
    # the FINAL_GROSS_SCALE case (#2417 site (a)): the binding factor is a cap, not the
    # vol target, so the event is tagged FINAL_GROSS_SCALE, never VOLATILITY_SCALE — and
    # weight math is unaffected either way (explanation-only).
    result = size_portfolio(
        convictions={"A": 5.0, "B": 2.5},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (10.0, "X"), "B": (10.0, "Y")}),
        caps=_permissive(min_position_pct=40.0, max_position_pct=80.0, target_portfolio_vol=12.0),
    )
    assert _targets(result)["A"] == pytest.approx(80.0, abs=0.5)  # weight math unaffected
    kinds = {a.adjustment_type for a in result.adjustments}
    assert SizingAdjustmentType.VOLATILITY_SCALE not in kinds
    assert SizingAdjustmentType.FINAL_GROSS_SCALE in kinds


def test_breaker_emits_drawdown_breaker_adjustment() -> None:
    # Same scenario as test_breaker_raises_cash: halving the breaker halves B's weight,
    # tagged DRAWDOWN_BREAKER; the unhalved (breaker=1.0) run emits no such event.
    risk = _risk({"B": (12.0, "X")})
    caps = _permissive(max_position_pct=100.0, target_portfolio_vol=1.0e6)
    full = size_portfolio(
        convictions={"B": 5.0}, stances={"B": "buy"}, risk=risk, caps=caps, breaker_scale=1.0
    )
    halved = size_portfolio(
        convictions={"B": 5.0}, stances={"B": "buy"}, risk=risk, caps=caps, breaker_scale=0.5
    )
    assert full.adjustments == []
    events = _adjustments(halved)["B"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.DRAWDOWN_BREAKER
    assert events[0].original_pct == pytest.approx(100.0)
    assert events[0].adjusted_pct == pytest.approx(50.0)


def test_grid_rounding_emits_adjustment_for_snapped_weights() -> None:
    # Same scenario as test_round_to_grid_snaps_weights_down: 66.67 -> 65 and 33.33 -> 30.
    result = size_portfolio(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk=_risk({"HI": (20.0, "X"), "LO": (20.0, "Y")}),
        caps=_permissive(weight_increment_pct=5.0),
    )
    by_ticker = _adjustments(result)
    assert by_ticker["HI"][0].adjustment_type == SizingAdjustmentType.GRID_ROUNDING
    assert by_ticker["HI"][0].original_pct == pytest.approx(66.6667, abs=0.01)
    assert by_ticker["HI"][0].adjusted_pct == pytest.approx(65.0)
    assert by_ticker["LO"][0].original_pct == pytest.approx(33.3333, abs=0.01)
    assert by_ticker["LO"][0].adjusted_pct == pytest.approx(30.0)


def test_grid_rounding_emits_adjustment_when_snapped_to_zero() -> None:
    # B's raw ~3.85% is below the 10% grid increment and rounds DOWN to 0 — previously
    # silent (B just never appeared in ``positions``); now explained by a GRID_ROUNDING
    # event with adjusted_pct == 0.0, distinct from a cap/dedup drop.
    result = size_portfolio(
        convictions={"A": 5.0, "B": 2.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (10.0, "X"), "B": (100.0, "Y")}),
        caps=_permissive(weight_increment_pct=10.0),
    )
    assert "B" not in _targets(result)
    events = _adjustments(result)["B"]
    assert len(events) == 1
    assert events[0].adjustment_type == SizingAdjustmentType.GRID_ROUNDING
    assert events[0].original_pct == pytest.approx(3.846, abs=0.01)
    assert events[0].adjusted_pct == 0.0
    assert "rounded to zero" in events[0].reason


def test_requested_pct_covers_both_kept_and_dropped_tickers() -> None:
    # Same scenario as test_corr_dedup_drops_lower_conviction_leg: requested_pct is the
    # pre-cap/pre-dedup raw request, so it still carries B (37.5%) even though B never
    # makes it into ``positions``.
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]})
    result = size_portfolio(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        corr=corr,
        caps=_permissive(),
    )
    assert result.requested_pct["A"] == pytest.approx(62.5)
    assert result.requested_pct["B"] == pytest.approx(37.5)


def test_flat_reason_distinguishes_no_conviction_from_all_dropped() -> None:
    no_conviction = size_portfolio(
        convictions={"AAA": 1.0, "BBB": 1.9},
        stances={"AAA": "buy", "BBB": "buy"},
        risk=_risk({"AAA": (20.0, "TECH"), "BBB": (20.0, "TECH")}),
    )
    assert no_conviction.flat_reason == "no_conviction_cleared_bar"

    all_dropped = size_portfolio(
        convictions={"A": 4.0, "B": 4.0, "C": 4.0},
        stances={"A": "buy", "B": "buy", "C": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y"), "C": (20.0, "Z")}),
        caps=_permissive(min_position_pct=60.0),
    )
    assert all_dropped.flat_reason == "all_candidates_dropped"
    assert len(all_dropped.adjustments) == 3  # each leg dropped by the 60% floor
    assert all(
        a.adjustment_type == SizingAdjustmentType.SINGLE_NAME_CAP for a in all_dropped.adjustments
    )


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


# --------------------------------------------------------------------------- lineage battery
# (#2417 §5/§8 — "zero unexplained deltas" closed without a hypothesis dependency)


def _assert_zero_unexplained_deltas(result, *, materiality_pct: float = 1e-6) -> None:
    """requested->approved reconciles for every ticker, using the real per-pass output."""
    approved = {p.ticker: p.target_pct for p in result.positions}
    validate_sizing_lineage(
        result.requested_pct,
        approved,
        result.adjustments,
        materiality_pct=materiality_pct,
    )  # must not raise


# Each scenario is a proven configuration lifted from (or a light variant of) an existing
# single-purpose test above, so the battery's job is purely to check the *lineage*
# invariant across combinations already known to size correctly — not to re-derive new
# sizing behavior.
_LINEAGE_SCENARIOS: dict[str, dict] = {
    "baseline_no_binding_constraints": dict(
        convictions={"LOW": 4.0, "HIGH": 4.0},
        stances={"LOW": "buy", "HIGH": "buy"},
        risk=_risk({"LOW": (10.0, "L"), "HIGH": (40.0, "H")}),
        caps=_permissive(),
    ),
    "position_cap_binds_one_leg": dict(
        convictions={"ONE": 5.0},
        stances={"ONE": "buy"},
        risk=_risk({"ONE": (20.0, "TECH")}),
        caps=SizingCaps(max_position_pct=30.0),
    ),
    "sector_cap_binds_a_bucket": dict(
        convictions={"T1": 4.0, "T2": 4.0, "EN": 4.0},
        stances={"T1": "buy", "T2": "buy", "EN": "buy"},
        risk=_risk({"T1": (20.0, "TECH"), "T2": (20.0, "TECH"), "EN": (20.0, "ENERGY")}),
        caps=_permissive(max_position_pct=100.0, max_sector_pct=40.0),
    ),
    "correlation_dedup_drops_a_leg": dict(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        corr=pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]}),
        caps=_permissive(),
    ),
    "vol_target_scales_down_a_hot_book": dict(
        convictions={"V": 5.0},
        stances={"V": "buy"},
        risk=_risk({"V": (40.0, "X")}),
        caps=_permissive(max_position_pct=100.0, target_portfolio_vol=12.0),
    ),
    "vol_target_scales_up_an_underrisked_book": dict(
        convictions={"A": 5.0, "B": 2.5},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (10.0, "X"), "B": (10.0, "Y")}),
        caps=_permissive(min_position_pct=40.0, max_position_pct=80.0, target_portfolio_vol=12.0),
    ),
    "drawdown_breaker_reduces_gross": dict(
        convictions={"B": 5.0},
        stances={"B": "buy"},
        risk=_risk({"B": (12.0, "X")}),
        caps=_permissive(max_position_pct=100.0, target_portfolio_vol=1.0e6),
        breaker_scale=0.5,
    ),
    "grid_rounding_leaves_a_remainder": dict(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk=_risk({"HI": (20.0, "X"), "LO": (20.0, "Y")}),
        caps=_permissive(weight_increment_pct=5.0),
    ),
    "grid_rounding_snaps_a_leg_to_zero": dict(
        convictions={"A": 5.0, "B": 2.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (10.0, "X"), "B": (100.0, "Y")}),
        caps=_permissive(weight_increment_pct=10.0),
    ),
    "min_position_floor_drops_the_tiny_leg": dict(
        convictions={"TINY": 2.0, "BIG": 5.0},
        stances={"TINY": "buy", "BIG": "buy"},
        risk=_risk({"TINY": (40.0, "A"), "BIG": (10.0, "B")}),
        caps=_permissive(min_position_pct=10.0),
    ),
    "all_candidates_dropped_by_the_floor": dict(
        convictions={"A": 4.0, "B": 4.0, "C": 4.0},
        stances={"A": "buy", "B": "buy", "C": "buy"},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y"), "C": (20.0, "Z")}),
        caps=_permissive(min_position_pct=60.0),
    ),
    "no_conviction_clears_the_bar": dict(
        convictions={"AAA": 1.0, "BBB": 1.9},
        stances={"AAA": "buy", "BBB": "buy"},
        risk=_risk({"AAA": (20.0, "TECH"), "BBB": (20.0, "TECH")}),
    ),
    "kelly_mode": dict(
        convictions={"A": 5.0, "B": 3.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk({"A": (15.0, "X"), "B": (25.0, "Y")}),
        caps=_permissive(sizing_mode="kelly"),
    ),
    "default_caps_multiple_pressures_at_once": dict(
        convictions={"AAPL": 5.0, "MSFT": 4.5, "NVDA": 4.0, "GLD": 2.0},
        stances={"AAPL": "buy", "MSFT": "buy", "NVDA": "buy", "GLD": "hold"},
        risk=_risk(
            {
                "AAPL": (25.0, "TECH"),
                "MSFT": (22.0, "TECH"),
                "NVDA": (55.0, "TECH"),
                "GLD": (12.0, "COMMODITY"),
            }
        ),
        # SizingCaps() defaults (30% position / 40% sector / 12% vol target / 5pp grid)
        # binds several controls in the same pass at once.
    ),
}


# --------------------------------------------------------------------------- WP6.1 incumbent golden leaves (#2687)


def test_incumbent_default_caps_match_golden_fixture() -> None:
    from tests.dq.hermes.incumbent_risk_fixtures import (
        dataclass_matches_fixture,
        load_incumbent_risk_fixture,
    )

    golden = load_incumbent_risk_fixture()["policy_defaults"]["sizing_caps"]
    assert dataclass_matches_fixture(SizingCaps(), golden)


@pytest.mark.parametrize("scenario", _LINEAGE_SCENARIOS.values(), ids=list(_LINEAGE_SCENARIOS))
def test_zero_unexplained_deltas_across_scenario_battery(scenario: dict) -> None:
    """Deterministic battery covering every control combination the pipeline can hit in a
    single pass (position cap, sector cap, corr-dedup, vol-scale up/down, breaker,
    grid-rounding both mid-value and snap-to-zero, min-floor drop, full-drop, a
    no-conviction-clears-the-bar flat book, kelly mode, and a multi-pressure default-caps
    case). No ``hypothesis`` dependency: this repo has none, so the acceptance-criteria
    property ("every material requested->approved delta is accounted for by its ticker's
    adjustment chain, zero unexplained") is pinned by an explicit, deterministic scenario
    matrix run through ``validate_sizing_lineage`` against real ``size_portfolio`` output,
    instead of by generated/random inputs. "Accounted for" means the chain *ends* at the
    approved value — see ``validate_sizing_lineage``'s docstring for why the chain's start
    is deliberately not checked here.
    """
    result = size_portfolio(**scenario)
    _assert_zero_unexplained_deltas(result)
