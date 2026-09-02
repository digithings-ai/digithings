"""WP8.5 — lock H8 allocation invariants after calibrated cutover (#2738).

Permanent property/golden suite for the post-WP8.4 control shell. Changing forecasts
may change raw weights; reordering ``INCUMBENT_CONTROL_ORDER``, redistributing cap
excess into survivors, collapsing controls into an optimizer, or regressing
calibrated mode stamps must fail these tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import polars as pl
import pytest
from digiquant.portfolio.allocation_contracts import (
    AllocationCadence,
    AllocationInputBundle,
    AllocationRunContext,
    AssetInputStatus,
    CalibratedReturnSlice,
    ControlSettingsFingerprint,
    MandateReference,
    PriorBookSnapshot,
    build_source_hashes,
)
from digiquant.portfolio.allocation_hashes import allocation_bundle_content_hash
from digiquant.portfolio.phases import phase7e_risk_sizing
from digiquant.portfolio.risk_controls import BreakerConfig, compute_breaker_scale
from digiquant.portfolio.risk_policy import INCUMBENT_CONTROL_ORDER
from digiquant.portfolio.sizing import SizingCaps, TickerRisk, size_portfolio
from digiquant.portfolio.sizing_events import SizingAdjustment, SizingAdjustmentType
from digiquant.portfolio.turnover import (
    apply_rebalancing_cadence,
    apply_turnover_to_sized_book,
    should_rebalance_today,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 26, 20, 0, tzinfo=UTC)
_SESSION = date(2026, 8, 26)
_POLICY_ID = UUID("22222222-2222-4222-8222-222222222222")
_POLICY_HASH = "d" * 64
_CAL_HASH = "e" * 64
_H7_HASH = "f" * 64

# Explicit post-cutover control sequence — must match RiskPolicy.control_order.
_POST_CUTOVER_CONTROL_SEQUENCE: tuple[str, ...] = (
    "select",
    "raw_weights",
    "position_caps",
    "sector_caps",
    "corr_dedup",
    "vol_target",
    "drawdown_breaker",
    "grid_rounding",
)

# Phase7e outer shell after size_portfolio (continuity → cadence/turnover → final cap).
_POST_SIZING_OUTER_SEQUENCE: tuple[str, ...] = (
    "held_continuity_backstop",
    "rebalancing_cadence_or_turnover",
    "final_total_invested_cap",
)


def _permissive(**over: float | str) -> SizingCaps:
    base: dict[str, float | str] = {
        "min_position_pct": 0.0,
        "max_position_pct": 100.0,
        "max_sector_pct": 100.0,
        "weight_increment_pct": 0.0,
        "target_portfolio_vol": 1.0e6,
        "max_gross_pct": 100.0,
        "min_conviction": 0.0,
    }
    base.update(over)
    return SizingCaps(**base)


def _risk(mapping: dict[str, tuple[float, str]]) -> dict[str, TickerRisk]:
    return {
        t: TickerRisk(ticker=t, hist_vol_21=vol, sector=sector)
        for t, (vol, sector) in mapping.items()
    }


def _targets(result) -> dict[str, float]:
    return {p.ticker: p.target_pct for p in result.positions}


def _bundle(
    *,
    returns: dict[str, tuple[str, str, str]],
    ranks: dict[str, int] | None = None,
    statuses: dict[str, AssetInputStatus] | None = None,
) -> AllocationInputBundle:
    tickers = tuple(sorted(returns))
    rank_map = ranks or {t: i + 1 for i, t in enumerate(tickers)}
    status_map = statuses or {t: AssetInputStatus.AVAILABLE for t in tickers}
    mandates = tuple(
        MandateReference(ticker=t, direction="long", conviction_rank=rank_map[t]) for t in tickers
    )
    calibrated = []
    cal_hashes: list[tuple[str, str]] = []
    for t in tickers:
        status = status_map[t]
        if status is AssetInputStatus.AVAILABLE:
            digest = _CAL_HASH if t == tickers[0] else "c" * 64
            cal_hashes.append((t, digest))
            calibrated.append(
                CalibratedReturnSlice(
                    ticker=t,
                    horizon_sessions=21,
                    expected_gross_return=Decimal(returns[t][0]),
                    forecast_error_std=Decimal(returns[t][1]),
                    reliability_weight=Decimal(returns[t][2]),
                    calibrated_forecast_content_hash=digest,
                    status=AssetInputStatus.AVAILABLE,
                )
            )
        else:
            calibrated.append(
                CalibratedReturnSlice(
                    ticker=t,
                    horizon_sessions=21,
                    expected_gross_return=None,
                    forecast_error_std=None,
                    reliability_weight=Decimal("0"),
                    calibrated_forecast_content_hash=None,
                    status=status,
                    unavailable_reason="degraded_for_invariant_suite",
                )
            )
    prior = PriorBookSnapshot(entries=(), cash_weight_pct=100.0)
    control = ControlSettingsFingerprint(
        risk_policy_content_hash=_POLICY_HASH,
        risk_policy_id=_POLICY_ID,
    )
    source = build_source_hashes(
        h7_memo_hash=_H7_HASH,
        risk_policy_hash=_POLICY_HASH,
        prior_entries=(),
        calibrated_hashes=tuple(cal_hashes),
    )
    run = AllocationRunContext(
        run_id="run-2738",
        session_date=_SESSION,
        cutoff_at=_TS,
        cadence=AllocationCadence.DAILY,
    )
    draft = AllocationInputBundle.model_construct(
        schema_version="1.0",
        run=run,
        canonical_asset_order=tickers,
        mandates=mandates,
        calibrated_returns=tuple(calibrated),
        prior_book=prior,
        control_settings=control,
        covariance=None,
        cost_liquidity=None,
        source_hashes=source,
        bundle_content_hash="",
    )
    digest = allocation_bundle_content_hash(payload=draft._hash_payload())
    return AllocationInputBundle.model_validate(
        {**draft.model_dump(mode="json"), "bundle_content_hash": digest}
    )


def _calibrated_size(
    scores: dict[str, float],
    *,
    risk: dict[str, TickerRisk] | None = None,
    caps: SizingCaps | None = None,
    corr: pl.DataFrame | None = None,
    breaker_scale: float = 1.0,
    stances: dict[str, str] | None = None,
    convictions: dict[str, float] | None = None,
):
    tickers = tuple(scores)
    return size_portfolio(
        convictions=convictions or scores,
        stances=stances or {t: "buy" for t in tickers},
        risk=risk or _risk({t: (20.0, t) for t in tickers}),
        corr=corr,
        caps=caps or _permissive(),
        breaker_scale=breaker_scale,
        calibrated_scores=scores,
    )


# --------------------------------------------------------------------------- control sequence identity


def test_incumbent_control_order_is_explicit_and_frozen() -> None:
    assert INCUMBENT_CONTROL_ORDER == _POST_CUTOVER_CONTROL_SEQUENCE
    assert list(INCUMBENT_CONTROL_ORDER) == [
        "select",
        "raw_weights",
        "position_caps",
        "sector_caps",
        "corr_dedup",
        "vol_target",
        "drawdown_breaker",
        "grid_rounding",
    ]
    # Outer shell after size_portfolio remains a fixed sequence (not an optimizer).
    assert _POST_SIZING_OUTER_SEQUENCE == (
        "held_continuity_backstop",
        "rebalancing_cadence_or_turnover",
        "final_total_invested_cap",
    )


def test_control_order_docs_match_source_signature_order() -> None:
    """Fail if someone reorders the reduce-only shell inside size_portfolio."""
    import inspect

    from digiquant.portfolio import sizing as sizing_mod

    src = inspect.getsource(sizing_mod.size_portfolio)
    # Skip the docstring — early narrative mentions breaker before the live calls.
    body = src.split('"""', 2)[-1]
    markers = [
        "_select(",
        "_raw_weights(",
        "_apply_position_caps(",
        "_apply_sector_caps(",
        "_corr_dedup(",
        "port_vol = _portfolio_vol(",
        "gross_scale = pre_breaker_scale * breaker",
        "_round_to_grid(",
    ]
    positions = [body.index(m) for m in markers]
    assert positions == sorted(positions), "size_portfolio control stages reordered"


# --------------------------------------------------------------------------- cash-first / no redistribute


def test_calibrated_position_cap_is_cash_first_not_redistributed() -> None:
    # Equal calibrated scores → 50/50 raw; 30% position cap → each 30, cash 40.
    # Cap excess must NOT inflate the other leg past the cap.
    result = _calibrated_size(
        {"A": 2.0, "B": 2.0},
        caps=_permissive(max_position_pct=30.0),
    )
    t = _targets(result)
    assert t["A"] == pytest.approx(30.0, abs=0.05)
    assert t["B"] == pytest.approx(30.0, abs=0.05)
    assert result.cash_pct == pytest.approx(40.0, abs=0.1)
    assert all(p.target_pct <= 30.0 + 1e-6 for p in result.positions)


def test_calibrated_sector_cap_does_not_gift_excess_to_other_sectors() -> None:
    result = _calibrated_size(
        {"T1": 3.0, "T2": 3.0, "EN": 3.0},
        risk=_risk({"T1": (20.0, "TECH"), "T2": (20.0, "TECH"), "EN": (20.0, "ENERGY")}),
        caps=_permissive(max_sector_pct=40.0),
    )
    t = _targets(result)
    tech = t["T1"] + t["T2"]
    assert tech == pytest.approx(40.0, abs=0.5)
    # ENERGY keeps its pre-sector-cap share (~33%); does not absorb TECH excess.
    assert t["EN"] == pytest.approx(100.0 / 3.0, abs=0.5)
    assert result.cash_pct == pytest.approx(100.0 - tech - t["EN"], abs=0.5)


def test_calibrated_corr_dedup_drops_lower_score_leg_cash_first() -> None:
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]})
    # Convictions deliberately inverted vs calibrated scores — dedup must use scores.
    result = _calibrated_size(
        {"A": 5.0, "B": 1.0},
        risk=_risk({"A": (20.0, "X"), "B": (20.0, "Y")}),
        caps=_permissive(),
        corr=corr,
        convictions={"A": 1.0, "B": 5.0},
    )
    t = _targets(result)
    assert "B" not in t
    assert t == {"A": pytest.approx(100.0, abs=0.5)}


# --------------------------------------------------------------------------- vol / breaker / grid


def test_calibrated_vol_target_and_breaker_and_grid() -> None:
    hot = _calibrated_size(
        {"HOT": 4.0},
        risk=_risk({"HOT": (40.0, "X")}),
        caps=_permissive(target_portfolio_vol=12.0),
    )
    assert hot.gross_pct == pytest.approx(30.0, abs=0.5)  # 12/40 of 100%

    broken = _calibrated_size(
        {"A": 2.0, "B": 2.0},
        caps=_permissive(max_position_pct=40.0),
        breaker_scale=0.5,
    )
    assert broken.gross_pct == pytest.approx(40.0, abs=0.5)  # 80 * 0.5
    assert broken.cash_pct == pytest.approx(60.0, abs=0.5)
    assert broken.applied_scales["breaker_scale"] == pytest.approx(0.5)

    grid = _calibrated_size(
        {"A": 2.0, "B": 1.0},
        caps=_permissive(weight_increment_pct=5.0),
    )
    assert all(p.target_pct % 5 == pytest.approx(0.0) for p in grid.positions)
    assert grid.cash_pct >= 0.0


def test_breaker_never_levers_up() -> None:
    cfg = BreakerConfig()
    for navs in ([100.0, 130.0], [100.0, 75.0], [100.0, 86.0]):
        assert compute_breaker_scale(navs, config=cfg).scale <= 1.0


# --------------------------------------------------------------------------- edge cases


def test_all_cash_when_calibrated_scores_nonpositive() -> None:
    result = _calibrated_size({"A": 0.0, "B": 0.0})
    assert result.positions == []
    assert result.cash_pct == 100.0


def test_one_asset_calibrated_book_respects_position_cap() -> None:
    result = _calibrated_size(
        {"ONLY": 3.0},
        caps=_permissive(max_position_pct=25.0),
    )
    assert _targets(result) == {"ONLY": pytest.approx(25.0)}
    assert result.cash_pct == pytest.approx(75.0)


def test_cap_saturated_book_stays_within_all_caps() -> None:
    result = _calibrated_size(
        {"T1": 5.0, "T2": 4.0, "T3": 3.0},
        risk=_risk({"T1": (15.0, "TECH"), "T2": (15.0, "TECH"), "T3": (15.0, "TECH")}),
        caps=_permissive(max_position_pct=20.0, max_sector_pct=40.0, max_gross_pct=50.0),
    )
    t = _targets(result)
    assert all(w <= 20.0 + 1e-6 for w in t.values())
    assert sum(t.values()) <= 40.0 + 1e-6  # sector + gross both bind ≤40/50
    assert result.gross_pct <= 50.0 + 1e-6
    assert result.cash_pct == pytest.approx(100.0 - result.gross_pct, abs=1e-3)


def test_degraded_calibrated_inputs_get_no_new_risk() -> None:
    bundle = _bundle(
        returns={"AAPL": ("0.05", "0.02", "1.0"), "MSFT": ("0.04", "0.02", "1.0")},
        statuses={
            "AAPL": AssetInputStatus.AVAILABLE,
            "MSFT": AssetInputStatus.DEGRADED,
        },
    )
    scores = phase7e_risk_sizing.calibrated_scores_from_bundle(
        bundle, long_tickers=["AAPL", "MSFT"]
    )
    assert "AAPL" in scores
    assert "MSFT" not in scores
    result = _calibrated_size(scores, risk=_risk({"AAPL": (20.0, "X")}))
    assert set(_targets(result)) == {"AAPL"}


# --------------------------------------------------------------------------- rank/eligibility decoupling + hash/mode stamps


def test_rank_gap_does_not_change_calibrated_magnitude() -> None:
    returns = {"AAPL": ("0.06", "0.03", "0.9"), "MSFT": ("0.03", "0.03", "0.9")}
    dense = _bundle(returns=returns, ranks={"AAPL": 1, "MSFT": 2})
    gapped = _bundle(returns=returns, ranks={"AAPL": 1, "MSFT": 99})
    a = phase7e_risk_sizing.calibrated_scores_from_bundle(dense, long_tickers=["AAPL", "MSFT"])
    b = phase7e_risk_sizing.calibrated_scores_from_bundle(gapped, long_tickers=["AAPL", "MSFT"])
    assert a == b
    book_a = _calibrated_size(a)
    book_b = _calibrated_size(b, convictions={"AAPL": 5.0, "MSFT": 1.0})
    assert book_a.requested_pct == book_b.requested_pct
    assert _targets(book_a) == _targets(book_b)


def test_identical_calibrated_raw_mix_yields_identical_post_control_book() -> None:
    scores = {"A": 3.0, "B": 1.0}
    caps = _permissive(max_position_pct=40.0)
    first = _calibrated_size(scores, caps=caps)
    second = _calibrated_size(dict(scores), caps=caps)
    assert first.requested_pct == second.requested_pct
    assert _targets(first) == _targets(second)
    assert first.cash_pct == pytest.approx(second.cash_pct)


def test_calibrated_mode_stamps_and_fallback_when_coverage_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digiquant.portfolio.h8_risk_snapshots import H8RiskArtifacts
    from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection
    from digiquant.portfolio.phases.phase7e_risk_sizing import (
        RiskSizingDeps,
        build_risk_sizing_node,
    )
    from digiquant.research.state import (
        PhasePortfolioState,
        ResearchConfigBundle,
        ResearchState,
    )

    from tests.dq.portfolio.test_allocation_inputs import _covariance, _risk_policy
    from tests.dq.research.test_supabase_io import FakeSupabaseClient

    bundle = _bundle(returns={"AAPL": ("0.06", "0.02", "1.0")})
    policy = _risk_policy()
    cov = _covariance(("AAPL",))
    artifacts = H8RiskArtifacts(policy=policy, covariance_snapshot=cov)
    monkeypatch.setattr(
        "digiquant.portfolio.h8_risk_snapshots.resolve_h8_risk_artifacts",
        lambda **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        "digiquant.portfolio.allocation_inputs.assemble_allocation_input_bundle_from_state",
        lambda *_a, **_k: bundle,
    )

    memo = PMDirectionMemo(
        date=date(2026, 6, 12),
        roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
        memo="m",
    )
    prefs = {
        "max_single_etf_pct": 100,
        "max_sector_pct": 100,
        "target_portfolio_vol": 1.0e6,
        "weight_increment_pct": 0,
        "h8_sizing_input_mode": "calibrated",
    }
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 6, 12),
        baseline_date=date(2026, 6, 9),
        config=ResearchConfigBundle(preferences=prefs),
        phase_portfolio=PhasePortfolioState(pm_direction_memo=memo),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": "AAPL", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
            ]
        }
    )
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    book = out["phase_portfolio"].sized_book
    assert book is not None
    assert book["h8_sizing_input_mode"] == "calibrated"
    assert book["allocation_input_bundle_hash"] == bundle.bundle_content_hash

    monkeypatch.setattr(
        phase7e_risk_sizing,
        "calibrated_scores_from_bundle",
        lambda *_a, **_k: {},
    )
    out_fb = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    book_fb = out_fb["phase_portfolio"].sized_book
    assert book_fb is not None
    assert book_fb["h8_sizing_input_mode"] == "incumbent_fallback"
    assert book_fb["allocation_input_bundle_hash"] == bundle.bundle_content_hash


# --------------------------------------------------------------------------- continuity / cadence / turnover / final caps


def test_continuity_backstop_and_final_cap_invariants() -> None:
    from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection
    from digiquant.research.state import (
        PhasePortfolioState,
        PriorContext,
        ResearchConfigBundle,
        ResearchState,
    )

    run_date = date(2026, 6, 12)
    state = ResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=date(2026, 6, 9),
        config=ResearchConfigBundle(preferences={}),
        prior_context=PriorContext(prior_book=[{"ticker": "DBO", "weight_pct": 7.5}]),
        phase_portfolio=PhasePortfolioState(
            pm_direction_memo=PMDirectionMemo(
                date=run_date,
                roster=[
                    TickerDirection(ticker="SPY", direction="long", conviction_rank=1),
                    TickerDirection(ticker="DBO", direction="long", conviction_rank=2),
                ],
                memo="m",
            )
        ),
    )
    events: list[SizingAdjustment] = []
    restored = phase7e_risk_sizing._apply_held_continuity_backstop(
        {"SPY": 60.0}, state, events=events
    )
    assert restored["DBO"] == pytest.approx(7.5)
    assert any(e.adjustment_type == SizingAdjustmentType.CONTINUITY_CARRY for e in events)

    overshoot = phase7e_risk_sizing._cap_total_invested({"A": 70.0, "B": 50.0})
    assert sum(overshoot.values()) == pytest.approx(100.0)
    assert overshoot["A"] / overshoot["B"] == pytest.approx(70.0 / 50.0)


def test_cadence_and_turnover_shell_unchanged_post_cutover() -> None:
    assert should_rebalance_today("daily", date(2026, 8, 26)) is True
    assert should_rebalance_today("none", date(2026, 8, 26)) is False

    held = apply_turnover_to_sized_book(
        {"SPY": 18.0},
        current_weights={"SPY": 20.0},
        prior_book=[{"ticker": "SPY", "weight_pct": 20, "entry_date": "2026-06-01"}],
        preferences={"rebalance_threshold_pct": 3, "holding_days": 5},
        run_date=date(2026, 6, 19),
    )
    assert held["SPY"] == 20.0

    off = apply_rebalancing_cadence(
        {"SPY": 50.0},
        current_weights={"SPY": 40.0, "CASH": 60.0},
        prior_book=[{"ticker": "SPY", "entry_date": "2026-01-01"}],
        preferences={"rebalancing_cadence": "none", "rebalance_threshold_pct": 3},
        run_date=date(2026, 6, 19),
    )
    # Off-cadence holds drifted continuing weight, not the new target.
    assert off["SPY"] == pytest.approx(40.0)


def test_policy_invariants_hold_on_calibrated_multi_control_book() -> None:
    """Single pass exercising cap + sector + corr + breaker + grid under calibrated scores."""
    corr = pl.DataFrame(
        {
            "a": ["A", "A", "B"],
            "b": ["B", "C", "C"],
            "corr": [0.95, 0.1, 0.1],
        }
    )
    result = _calibrated_size(
        {"A": 5.0, "B": 2.0, "C": 3.0},
        risk=_risk({"A": (20.0, "TECH"), "B": (20.0, "TECH"), "C": (20.0, "ENERGY")}),
        caps=_permissive(
            max_position_pct=35.0,
            max_sector_pct=45.0,
            weight_increment_pct=5.0,
            target_portfolio_vol=12.0,
            max_gross_pct=80.0,
        ),
        corr=corr,
        breaker_scale=0.8,
    )
    t = _targets(result)
    assert "B" not in t  # corr-dedup drops lower calibrated score vs A
    assert all(w <= 35.0 + 1e-6 for w in t.values())
    if "A" in t and "C" not in t:
        pass
    tech = sum(w for k, w in t.items() if k in {"A", "B"})
    assert tech <= 45.0 + 1e-6
    assert result.gross_pct <= 80.0 + 1e-6
    assert result.cash_pct == pytest.approx(100.0 - result.gross_pct, abs=0.1)
    assert all(p.target_pct % 5 == pytest.approx(0.0) for p in result.positions)
    assert result.applied_scales["breaker_scale"] == pytest.approx(0.8)
