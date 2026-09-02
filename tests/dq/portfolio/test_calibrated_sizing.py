"""WP8.4 — feed calibrated forecasts into incumbent H8 raw sizing (#2734).

Control shell (caps / corr / vol / breaker / grid) stays unchanged; only the raw-weight
stage switches from rank→conviction / fixed-premium Kelly to calibrated μ/σ/reliability.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

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
from digiquant.portfolio.sizing import (
    SizingCaps,
    TickerRisk,
    calibrated_raw_score,
    size_portfolio,
)

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_SESSION = date(2026, 8, 25)
_POLICY_ID = UUID("11111111-1111-4111-8111-111111111111")
_POLICY_HASH = "a" * 64
_CAL_HASH_A = "b" * 64
_CAL_HASH_B = "c" * 64
_H7_HASH = "e" * 64


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


def _risk(tickers: tuple[str, ...]) -> dict[str, TickerRisk]:
    return {t: TickerRisk(ticker=t, hist_vol_21=20.0, sector=t) for t in tickers}


def _bundle(
    *,
    returns: dict[str, tuple[str, str, str]],
    ranks: dict[str, int] | None = None,
) -> AllocationInputBundle:
    """returns: ticker → (expected_gross_return, forecast_error_std, reliability_weight)."""
    tickers = tuple(sorted(returns))
    rank_map = ranks or {t: i + 1 for i, t in enumerate(tickers)}
    cal_hashes = {
        tickers[0]: _CAL_HASH_A,
        **{t: _CAL_HASH_B for t in tickers[1:]},
    }
    mandates = tuple(
        MandateReference(
            ticker=t,
            direction="long",
            conviction_rank=rank_map[t],
        )
        for t in tickers
    )
    calibrated = tuple(
        CalibratedReturnSlice(
            ticker=t,
            horizon_sessions=21,
            expected_gross_return=Decimal(returns[t][0]),
            forecast_error_std=Decimal(returns[t][1]),
            reliability_weight=Decimal(returns[t][2]),
            calibrated_forecast_content_hash=cal_hashes[t],
            status=AssetInputStatus.AVAILABLE,
        )
        for t in tickers
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
        calibrated_hashes=tuple((t, cal_hashes[t]) for t in tickers),
    )
    run = AllocationRunContext(
        run_id="run-2734",
        session_date=_SESSION,
        cutoff_at=_TS,
        cadence=AllocationCadence.DAILY,
    )
    draft = AllocationInputBundle.model_construct(
        schema_version="1.0",
        run=run,
        canonical_asset_order=tickers,
        mandates=mandates,
        calibrated_returns=calibrated,
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


def test_calibrated_raw_score_applies_reliability_and_uncertainty() -> None:
    # Approved policy: score = reliability * max(0, μ) / σ_ε
    base = calibrated_raw_score(
        expected_gross_return=0.10,
        forecast_error_std=0.05,
        reliability_weight=1.0,
    )
    half_rel = calibrated_raw_score(
        expected_gross_return=0.10,
        forecast_error_std=0.05,
        reliability_weight=0.5,
    )
    double_unc = calibrated_raw_score(
        expected_gross_return=0.10,
        forecast_error_std=0.10,
        reliability_weight=1.0,
    )
    assert base == pytest.approx(2.0)
    assert half_rel == pytest.approx(base * 0.5)
    assert double_unc == pytest.approx(base * 0.5)


def test_negative_alpha_cannot_create_contrary_risk() -> None:
    assert (
        calibrated_raw_score(
            expected_gross_return=-0.08,
            forecast_error_std=0.05,
            reliability_weight=1.0,
        )
        == 0.0
    )
    result = size_portfolio(
        convictions={"A": 5.0, "B": 5.0},
        stances={"A": "buy", "B": "buy"},
        risk=_risk(("A", "B")),
        caps=_permissive(),
        calibrated_scores={"A": 0.0, "B": 1.5},
    )
    assert set(result.requested_pct) == {"B"}
    assert "A" not in {p.ticker for p in result.positions}


def test_forecast_change_with_fixed_ranks_changes_raw_weights() -> None:
    scores_lo = phase7e_risk_sizing.calibrated_scores_from_bundle(
        _bundle(returns={"AAPL": ("0.02", "0.02", "1.0"), "MSFT": ("0.04", "0.02", "1.0")}),
        long_tickers=["AAPL", "MSFT"],
    )
    scores_hi = phase7e_risk_sizing.calibrated_scores_from_bundle(
        _bundle(returns={"AAPL": ("0.08", "0.02", "1.0"), "MSFT": ("0.04", "0.02", "1.0")}),
        long_tickers=["AAPL", "MSFT"],
    )
    # Synthetic convictions equal — ranks irrelevant to magnitude.
    convictions = {"AAPL": 5.0, "MSFT": 5.0}
    stances = {"AAPL": "buy", "MSFT": "buy"}
    risk = _risk(("AAPL", "MSFT"))
    caps = _permissive()
    lo = size_portfolio(
        convictions=convictions,
        stances=stances,
        risk=risk,
        caps=caps,
        calibrated_scores=scores_lo,
    )
    hi = size_portfolio(
        convictions=convictions,
        stances=stances,
        risk=risk,
        caps=caps,
        calibrated_scores=scores_hi,
    )
    assert lo.requested_pct != hi.requested_pct
    assert hi.requested_pct["AAPL"] > lo.requested_pct["AAPL"]


def test_rank_gap_change_with_fixed_forecasts_does_not_change_raw_weights() -> None:
    returns = {"AAPL": ("0.06", "0.03", "0.9"), "MSFT": ("0.03", "0.03", "0.9")}
    dense = _bundle(returns=returns, ranks={"AAPL": 1, "MSFT": 2})
    gapped = _bundle(returns=returns, ranks={"AAPL": 2, "MSFT": 11})
    scores_a = phase7e_risk_sizing.calibrated_scores_from_bundle(
        dense, long_tickers=["AAPL", "MSFT"]
    )
    scores_b = phase7e_risk_sizing.calibrated_scores_from_bundle(
        gapped, long_tickers=["AAPL", "MSFT"]
    )
    assert scores_a == scores_b
    # Even if caller still passes rank-derived convictions, calibrated_scores own magnitude.
    a = size_portfolio(
        convictions={"AAPL": 5.0, "MSFT": 2.0},
        stances={"AAPL": "buy", "MSFT": "buy"},
        risk=_risk(("AAPL", "MSFT")),
        caps=_permissive(),
        calibrated_scores=scores_a,
    )
    b = size_portfolio(
        convictions={"AAPL": 5.0, "MSFT": 3.5},
        stances={"AAPL": "buy", "MSFT": "buy"},
        risk=_risk(("AAPL", "MSFT")),
        caps=_permissive(),
        calibrated_scores=scores_b,
    )
    assert a.requested_pct == b.requested_pct


def test_h5_stance_does_not_affect_calibrated_eligibility() -> None:
    """H7 memo path stamps buy even when H5 says sell; calibrated sizing uses that map."""
    from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection

    memo = PMDirectionMemo(
        date=_SESSION,
        roster=[TickerDirection(ticker="AAA", direction="long", conviction_rank=1)],
        memo="m",
    )
    _conv, stances = phase7e_risk_sizing._memo_effective_inputs(
        memo,
        {"AAA": {"stance": "sell", "conviction_score": 1}},
        2.0,
    )
    assert stances == {"AAA": "buy"}
    scores = {"AAA": 2.0}
    result = size_portfolio(
        convictions=scores,
        stances=stances,
        risk=_risk(("AAA",)),
        caps=_permissive(),
        calibrated_scores=scores,
    )
    assert result.requested_pct["AAA"] == pytest.approx(100.0)


def test_degraded_or_missing_slice_gets_no_new_risk() -> None:
    scores = phase7e_risk_sizing.calibrated_scores_from_bundle(
        _bundle(returns={"AAPL": ("0.05", "0.02", "1.0")}),
        long_tickers=["AAPL", "MSFT"],
    )
    assert "AAPL" in scores
    assert "MSFT" not in scores


def test_zero_uncertainty_rejected() -> None:
    with pytest.raises(ValueError, match="forecast_error_std"):
        calibrated_raw_score(
            expected_gross_return=0.05,
            forecast_error_std=0.0,
            reliability_weight=1.0,
        )


def test_resolve_sizing_input_mode_versioned() -> None:
    assert (
        phase7e_risk_sizing.resolve_h8_sizing_input_mode({})
        == phase7e_risk_sizing.H8_SIZING_INPUT_MODE_CALIBRATED
    )
    assert (
        phase7e_risk_sizing.resolve_h8_sizing_input_mode({"h8_sizing_input_mode": "incumbent"})
        == phase7e_risk_sizing.H8_SIZING_INPUT_MODE_INCUMBENT
    )
    assert (
        phase7e_risk_sizing.resolve_h8_sizing_input_mode({"h8_sizing_input_mode": "nope"})
        == phase7e_risk_sizing.H8_SIZING_INPUT_MODE_CALIBRATED
    )


def test_calibrated_path_does_not_use_rank_to_conviction_for_raw_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []
    original = phase7e_risk_sizing._rank_to_conviction

    def tracked(rank: int, n_long: int, *, floor: float) -> float:
        calls.append((rank, n_long))
        return original(rank, n_long, floor=floor)

    monkeypatch.setattr(phase7e_risk_sizing, "_rank_to_conviction", tracked)
    bundle = _bundle(returns={"AAPL": ("0.05", "0.02", "1.0"), "MSFT": ("0.03", "0.02", "1.0")})
    scores = phase7e_risk_sizing.calibrated_scores_from_bundle(
        bundle, long_tickers=["AAPL", "MSFT"]
    )
    result = size_portfolio(
        convictions=scores,
        stances={"AAPL": "buy", "MSFT": "buy"},
        risk=_risk(("AAPL", "MSFT")),
        caps=_permissive(),
        calibrated_scores=scores,
    )
    assert result.requested_pct
    assert calls == []


def test_incumbent_mode_still_uses_rank_path() -> None:
    # Smoke: without calibrated_scores, equal-vol books still tilt by conviction.
    result = size_portfolio(
        convictions={"HI": 5.0, "LO": 2.5},
        stances={"HI": "buy", "LO": "buy"},
        risk=_risk(("HI", "LO")),
        caps=_permissive(),
    )
    assert result.requested_pct["HI"] / result.requested_pct["LO"] == pytest.approx(2.0, rel=0.05)


def test_identical_raw_weights_yield_identical_post_control_book() -> None:
    """Control shell invariance: same raw mix → same finals under a binding position cap."""
    scores = {"A": 3.0, "B": 1.0}  # 75/25 raw
    caps = SizingCaps(
        min_position_pct=0.0,
        max_position_pct=40.0,
        max_sector_pct=100.0,
        weight_increment_pct=0.0,
        target_portfolio_vol=1.0e6,
        max_gross_pct=100.0,
        min_conviction=0.0,
    )
    risk = _risk(("A", "B"))
    stances = {"A": "buy", "B": "buy"}
    calibrated = size_portfolio(
        convictions=scores,
        stances=stances,
        risk=risk,
        caps=caps,
        calibrated_scores=scores,
    )
    # Equal vol → incumbent conviction_vol raw ∝ conviction; 3:1 matches calibrated scores.
    incumbent = size_portfolio(
        convictions={"A": 3.0, "B": 1.0},
        stances=stances,
        risk=risk,
        caps=caps,
    )
    assert calibrated.requested_pct == incumbent.requested_pct
    assert {p.ticker: p.target_pct for p in calibrated.positions} == {
        p.ticker: p.target_pct for p in incumbent.positions
    }
    assert calibrated.cash_pct == pytest.approx(incumbent.cash_pct)


def test_calibrated_book_stamps_bundle_hash(
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

    bundle = _bundle(returns={"AAPL": ("0.06", "0.02", "1.0"), "MSFT": ("0.03", "0.02", "1.0")})
    policy = _risk_policy()
    cov = _covariance(("AAPL", "MSFT"))
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
        roster=[
            TickerDirection(ticker="AAPL", direction="long", conviction_rank=1),
            TickerDirection(ticker="MSFT", direction="long", conviction_rank=2),
        ],
        memo="m",
    )
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 6, 12),
        baseline_date=date(2026, 6, 9),
        config=ResearchConfigBundle(
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "h8_sizing_input_mode": "calibrated",
            }
        ),
        phase_portfolio=PhasePortfolioState(pm_direction_memo=memo),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": "AAPL", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
                {"ticker": "MSFT", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
            ]
        }
    )
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    book = out["phase_portfolio"].sized_book
    assert book is not None
    assert book["h8_sizing_input_mode"] == "calibrated"
    assert book["allocation_input_bundle_hash"] == bundle.bundle_content_hash
    assert "allocation_input_bundle_hash=" in book["notes"]
    weights = {row["ticker"]: row["target_pct"] for row in book["recommended_portfolio"]}
    assert weights["AAPL"] > weights["MSFT"]


def test_empty_calibrated_coverage_falls_back_to_incumbent(
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

    # Bundle present but no usable calibrated scores → characterized incumbent_fallback.
    base = _bundle(returns={"AAPL": ("0.05", "0.02", "1.0")})
    policy = _risk_policy()
    cov = _covariance(("AAPL",))
    artifacts = H8RiskArtifacts(policy=policy, covariance_snapshot=cov)
    monkeypatch.setattr(
        "digiquant.portfolio.h8_risk_snapshots.resolve_h8_risk_artifacts",
        lambda **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        "digiquant.portfolio.allocation_inputs.assemble_allocation_input_bundle_from_state",
        lambda *_a, **_k: base,
    )
    monkeypatch.setattr(
        phase7e_risk_sizing,
        "calibrated_scores_from_bundle",
        lambda *_a, **_k: {},
    )

    memo = PMDirectionMemo(
        date=date(2026, 6, 12),
        roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
        memo="m",
    )
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 6, 12),
        baseline_date=date(2026, 6, 9),
        config=ResearchConfigBundle(
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "h8_sizing_input_mode": "calibrated",
            }
        ),
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
    assert book["h8_sizing_input_mode"] == "incumbent_fallback"
    assert book["allocation_input_bundle_hash"] == base.bundle_content_hash
    assert any(row["ticker"] == "AAPL" for row in book["recommended_portfolio"])
