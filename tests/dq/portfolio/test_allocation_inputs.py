"""WP8.3 — assemble canonical H8 AllocationInputBundle (#2730)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from digiquant.portfolio.allocation_contracts import (
    AssetInputStatus,
)
from digiquant.portfolio.allocation_hashes import (
    h7_memo_hash_payload,
    sha256_hex,
    weights_fingerprint,
)
from digiquant.portfolio.allocation_inputs import (
    AllocationInputAssemblyError,
    assemble_allocation_input_bundle,
)
from digiquant.portfolio.models.forecast_calibration import (
    CalibratedForecast,
    CalibrationArtifactStatus,
    calibrated_forecast_content_hash,
    calibrated_forecast_id,
)
from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.portfolio.models.risk_policy import (
    CapabilityLimit,
    CovarianceSnapshot,
    PolicyArtifactStatus,
    ProvenanceSource,
    ResolvedLeaf,
    RiskPolicy,
    covariance_snapshot_content_hash,
    covariance_snapshot_id,
    policy_hash_payload,
    risk_policy_content_hash,
    risk_policy_id,
    snapshot_hash_payload,
)

pytestmark = pytest.mark.unit

_SESSION = date(2026, 8, 25)
_CUTOFF = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_BASE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_EFF_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_CAL_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
_PHASE1_UNAVAILABLE = "phase1_not_implemented"


def _leaf(value: float | int | str) -> ResolvedLeaf:
    return ResolvedLeaf(value=value, source=ProvenanceSource.CODE_DEFAULT)


def _unavailable_cap() -> CapabilityLimit:
    return CapabilityLimit(
        available=False,
        enforced=False,
        limit=None,
        reason=_PHASE1_UNAVAILABLE,
    )


def _risk_policy() -> RiskPolicy:
    draft = RiskPolicy.model_construct(
        policy_id=risk_policy_id(method_version="incumbent-risk-policy@v1", content_hash="0" * 64),
        method_version="incumbent-risk-policy@v1",
        effective_at=_CUTOFF,
        source_run_id="run-2730",
        status=PolicyArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        content_hash="0" * 64,
        sizing_caps={"max_position_pct": _leaf(30.0)},
        breaker={"soft_dd_pct": _leaf(8.0)},
        turnover={"cadence": _leaf("daily")},
        horizons={"forecast_horizon_sessions": _leaf(21)},
        control_order=("select", "raw_weights"),
        correlation_buckets=(),
        vol_fallback_chain=(),
        rank_to_conviction=(),
        annualize_factor=_leaf(252.0),
        vol_lookback_days=_leaf(40),
        corr_lookback_days=_leaf(63),
        factor_limits=_unavailable_cap(),
        stress_limits=_unavailable_cap(),
        tail_limits=_unavailable_cap(),
        liquidity_limits=_unavailable_cap(),
        cost_policy=_unavailable_cap(),
        cost_coefficients={},
    )
    content_hash = risk_policy_content_hash(payload=policy_hash_payload(draft))
    return RiskPolicy.model_validate(
        {
            **draft.model_dump(mode="json"),
            "content_hash": content_hash,
            "policy_id": str(
                risk_policy_id(method_version=draft.method_version, content_hash=content_hash)
            ),
        }
    )


def _covariance(tickers: tuple[str, ...]) -> CovarianceSnapshot:
    n = len(tickers)
    matrix = tuple(tuple(1.0 if i == j else 0.2 for j in range(n)) for i in range(n))
    draft = CovarianceSnapshot.model_construct(
        snapshot_id=covariance_snapshot_id(
            as_of_session=_SESSION, tickers=tickers, content_hash="0" * 64
        ),
        method_version="incumbent-covariance@v1",
        as_of_session=_SESSION,
        lookback_days=63,
        estimator="pearson_daily_return",
        shrinkage="none",
        fallback_policy="asset_class_bucket@v1",
        tickers=tickers,
        matrix=matrix,
        observation_count=40,
        source_table=None,
        resolved_at=_CUTOFF,
        status=PolicyArtifactStatus.AVAILABLE,
        unavailable_reason=None,
        content_hash="0" * 64,
    )
    content_hash = covariance_snapshot_content_hash(payload=snapshot_hash_payload(draft))
    return CovarianceSnapshot.model_validate(
        {
            **draft.model_dump(mode="json"),
            "content_hash": content_hash,
            "snapshot_id": str(
                covariance_snapshot_id(
                    as_of_session=_SESSION, tickers=tickers, content_hash=content_hash
                )
            ),
        }
    )


def _calibrated(
    ticker: str,
    *,
    content_suffix: str = "1",
    status: CalibrationArtifactStatus = CalibrationArtifactStatus.AVAILABLE,
    known_at: datetime | None = None,
) -> CalibratedForecast:
    known = known_at or _CUTOFF
    if status is CalibrationArtifactStatus.AVAILABLE:
        payload = {
            "base_forecast_id": str(_BASE_ID),
            "effective_forecast_id": str(_EFF_ID),
            "calibration_id": str(_CAL_ID),
            "ticker": ticker,
            "expected_gross_return": "0.05",
            "forecast_error_std": "0.02",
            "downside_quantiles": ["-0.1", "0.0"],
            "calibrated_positive_probability": "0.6",
            "reliability_weight": "0.8",
            "effective_until": (known + timedelta(days=30)).isoformat(),
            "status": "available",
            "unavailable_reason": None,
            "effective_at": known.isoformat(),
            "known_at": known.isoformat(),
        }
        # Distinct hashes per ticker via reliability tweak when needed
        if content_suffix != "1":
            payload["reliability_weight"] = f"0.8{content_suffix}"
        content_hash = calibrated_forecast_content_hash(payload=payload)
        cf_id = calibrated_forecast_id(
            effective_forecast_id=_EFF_ID,
            calibration_id=_CAL_ID,
            content_hash=content_hash,
        )
        return CalibratedForecast.model_validate(
            {
                **payload,
                "calibrated_forecast_id": str(cf_id),
                "content_hash": content_hash,
            }
        )
    payload = {
        "base_forecast_id": str(_BASE_ID),
        "effective_forecast_id": str(_EFF_ID),
        "calibration_id": None,
        "ticker": ticker,
        "expected_gross_return": None,
        "forecast_error_std": None,
        "downside_quantiles": None,
        "calibrated_positive_probability": None,
        "reliability_weight": "0.1",
        "effective_until": None,
        "status": "unavailable",
        "unavailable_reason": "insufficient_cohort",
        "effective_at": known.isoformat(),
        "known_at": known.isoformat(),
    }
    content_hash = calibrated_forecast_content_hash(payload=payload)
    cf_id = calibrated_forecast_id(
        effective_forecast_id=_EFF_ID,
        calibration_id=None,
        content_hash=content_hash,
    )
    return CalibratedForecast.model_validate(
        {
            **payload,
            "calibrated_forecast_id": str(cf_id),
            "content_hash": content_hash,
        }
    )


def _memo(*tickers: str, directions: dict[str, str] | None = None) -> PMDirectionMemo:
    dirs = directions or {}
    roster = [
        TickerDirection(
            ticker=ticker,
            direction=dirs.get(ticker, "long"),  # type: ignore[arg-type]
            conviction_rank=idx,
            forecast_reference=None,
        )
        for idx, ticker in enumerate(tickers, start=1)
    ]
    # Attach degraded forecast refs so memo validates without inventing IDs
    from digiquant.portfolio.models.pm_direction import ForecastReference

    roster = [
        entry.model_copy(
            update={
                "forecast_reference": ForecastReference(
                    ticker=entry.ticker,
                    effective_forecast_id=_EFF_ID,
                    base_forecast_id=_BASE_ID,
                )
            }
        )
        for entry in roster
    ]
    return PMDirectionMemo(date=_SESSION, roster=roster, memo="test memo")


def _assemble(
    *,
    memo: PMDirectionMemo | None = None,
    calibrated: dict[str, CalibratedForecast] | None = None,
    horizons: dict[str, int] | None = None,
    prior: dict[str, float] | None = None,
    cash: float = 50.0,
    covariance: CovarianceSnapshot | None | object = ...,
    cost_hashes: dict[str, str] | None = None,
    expected_horizon: int | None = 21,
    cutoff: datetime | None = None,
    analysts: dict[str, dict] | None = None,
):
    tickers = ("AAPL", "MSFT")
    memo = memo or _memo(*tickers)
    calibrated = calibrated or {
        "AAPL": _calibrated("AAPL", content_suffix="1"),
        "MSFT": _calibrated("MSFT", content_suffix="2"),
    }
    horizons = horizons or {t: 21 for t in tickers}
    prior = prior or {"AAPL": 30.0, "MSFT": 20.0}
    cov: CovarianceSnapshot | None
    if covariance is ...:
        order = tuple(sorted({e.ticker for e in memo.roster}))
        cov = _covariance(order)
    else:
        cov = covariance  # type: ignore[assignment]
    return assemble_allocation_input_bundle(
        memo=memo,
        run_id="run-2730",
        session_date=_SESSION,
        cutoff_at=cutoff or _CUTOFF,
        calibrated_by_ticker=calibrated,
        horizon_by_ticker=horizons,
        risk_policy=_risk_policy(),
        covariance=cov,
        prior_risky_weights=prior,
        cash_weight_pct=cash,
        cost_hashes_by_ticker=cost_hashes,
        expected_horizon_sessions=expected_horizon,
        analyst_stances=analysts,
    )


def test_h7_authorization_only_ignores_extra_calibrated_tickers() -> None:
    """Only H7 roster tickers enter the bundle — extras in calibration map are ignored."""
    memo = _memo("AAPL")
    calibrated = {
        "AAPL": _calibrated("AAPL"),
        "TSLA": _calibrated("TSLA", content_suffix="9"),
    }
    bundle = _assemble(
        memo=memo,
        calibrated=calibrated,
        horizons={"AAPL": 21, "TSLA": 21},
        prior={"AAPL": 40.0},
        cash=60.0,
        covariance=_covariance(("AAPL",)),
    )
    assert bundle.canonical_asset_order == ("AAPL",)
    assert all(m.ticker == "AAPL" for m in bundle.mandates)
    assert "TSLA" not in {c.ticker for c in bundle.calibrated_returns}


def test_exact_forecast_policy_covariance_cost_versions() -> None:
    cost_a = "d" * 64
    bundle = _assemble(cost_hashes={"AAPL": cost_a})
    policy = _risk_policy()
    assert bundle.control_settings.risk_policy_content_hash == policy.content_hash
    assert bundle.control_settings.risk_policy_id == policy.policy_id
    assert bundle.source_hashes.risk_policy_hash == policy.content_hash

    assert bundle.covariance is not None
    assert bundle.source_hashes.covariance_hash == bundle.covariance.content_hash

    cal_hashes = {
        t: c.calibrated_forecast_content_hash
        for t, c in zip(
            ("AAPL", "MSFT"),
            bundle.calibrated_returns,
            strict=True,
        )
    }
    assert cal_hashes["AAPL"] == _calibrated("AAPL", content_suffix="1").content_hash
    assert cal_hashes["MSFT"] == _calibrated("MSFT", content_suffix="2").content_hash
    assert bundle.source_hashes.calibrated_hashes == (
        ("AAPL", cal_hashes["AAPL"]),
        ("MSFT", cal_hashes["MSFT"]),
    )
    assert bundle.cost_liquidity is not None
    assert bundle.cost_liquidity.entries == (("AAPL", cost_a),)
    assert bundle.source_hashes.cost_hashes == (("AAPL", cost_a),)

    expected_h7 = sha256_hex(
        h7_memo_hash_payload(
            session_date=_SESSION.isoformat(),
            roster=[
                {
                    "ticker": e.ticker,
                    "direction": e.direction,
                    "conviction_rank": e.conviction_rank,
                    "effective_forecast_id": (
                        None
                        if e.forecast_reference is None
                        else (
                            None
                            if e.forecast_reference.effective_forecast_id is None
                            else str(e.forecast_reference.effective_forecast_id)
                        )
                    ),
                    "forecast_reference_hash": None,
                    "degradation_reason": (
                        None
                        if e.forecast_reference is None
                        else e.forecast_reference.degradation_reason
                    ),
                }
                for e in _memo("AAPL", "MSFT").roster
            ],
        )
    )
    assert bundle.source_hashes.h7_memo_hash == expected_h7


def test_prior_weights_fingerprint_matches_book() -> None:
    prior = {"MSFT": 15.5, "AAPL": 25.25}
    bundle = _assemble(prior=prior, cash=59.25)
    assert bundle.prior_book.risky_weights() == {"AAPL": 25.25, "MSFT": 15.5}
    assert bundle.source_hashes.prior_weights_fingerprint == weights_fingerprint(prior)


def test_rejects_wrong_horizon_and_mixed_horizons() -> None:
    with pytest.raises(AllocationInputAssemblyError, match="horizon"):
        _assemble(expected_horizon=42)

    with pytest.raises(AllocationInputAssemblyError, match="horizon"):
        _assemble(horizons={"AAPL": 21, "MSFT": 63})


def test_rejects_future_known_at_past_cutoff() -> None:
    future = _CUTOFF + timedelta(hours=1)
    with pytest.raises(AllocationInputAssemblyError, match="future|cutoff|known_at"):
        _assemble(
            calibrated={
                "AAPL": _calibrated("AAPL", known_at=future),
                "MSFT": _calibrated("MSFT", content_suffix="2"),
            }
        )


def test_h5_stance_mutation_does_not_change_authorization() -> None:
    """Analyst sell/buy cannot add, drop, or reverse H7-authorized instruments."""
    memo = _memo("AAPL", "MSFT", directions={"AAPL": "long", "MSFT": "flat"})
    base = _assemble(
        memo=memo,
        covariance=_covariance(("AAPL", "MSFT")),
        analysts={"AAPL": {"stance": "buy"}, "MSFT": {"stance": "hold"}},
    )
    mutated = _assemble(
        memo=memo,
        covariance=_covariance(("AAPL", "MSFT")),
        analysts={
            "AAPL": {"stance": "sell"},
            "MSFT": {"stance": "buy"},
            "NVDA": {"stance": "buy"},
        },
    )
    assert base.canonical_asset_order == mutated.canonical_asset_order == ("AAPL", "MSFT")
    assert [m.direction for m in base.mandates] == [m.direction for m in mutated.mandates]
    assert base.bundle_content_hash == mutated.bundle_content_hash


def test_deterministic_asset_order_independent_of_roster_input_order() -> None:
    forward = _assemble(memo=_memo("MSFT", "AAPL"), covariance=_covariance(("AAPL", "MSFT")))
    reverse = _assemble(memo=_memo("AAPL", "MSFT"), covariance=_covariance(("AAPL", "MSFT")))
    assert forward.canonical_asset_order == ("AAPL", "MSFT")
    assert reverse.canonical_asset_order == ("AAPL", "MSFT")
    # Mandate ranks still follow H7 values; order of rows is canonical
    assert [m.ticker for m in forward.mandates] == ["AAPL", "MSFT"]
    assert [m.ticker for m in reverse.mandates] == ["AAPL", "MSFT"]


def test_missing_calibration_yields_typed_degraded_slice() -> None:
    bundle = _assemble(
        calibrated={"AAPL": _calibrated("AAPL")},
        horizons={"AAPL": 21, "MSFT": 21},
        cost_hashes=None,
    )
    by_ticker = {c.ticker: c for c in bundle.calibrated_returns}
    assert by_ticker["AAPL"].status is AssetInputStatus.AVAILABLE
    assert by_ticker["MSFT"].status is AssetInputStatus.DEGRADED
    assert by_ticker["MSFT"].unavailable_reason is not None
    assert by_ticker["MSFT"].calibrated_forecast_content_hash is None


def test_long_plus_flat_roster_pins_matching_covariance() -> None:
    """Full H7 roster (including flat) must keep covariance when tickers match order."""
    memo = _memo("AAPL", "MSFT", directions={"AAPL": "long", "MSFT": "flat"})
    cov = _covariance(("AAPL", "MSFT"))
    bundle = _assemble(memo=memo, covariance=cov, prior={"AAPL": 40.0}, cash=60.0)
    assert bundle.canonical_asset_order == ("AAPL", "MSFT")
    assert bundle.covariance is not None
    assert bundle.covariance.content_hash == cov.content_hash
    assert bundle.source_hashes.covariance_hash == cov.content_hash


def test_from_state_fills_missing_horizons_with_default() -> None:
    from digiquant.research.state import (
        AtlasConfigBundle,
        AtlasResearchState,
        PhaseHermesState,
    )
    from digiquant.portfolio.allocation_inputs import (
        DEFAULT_FORECAST_HORIZON_SESSIONS,
        assemble_allocation_input_bundle_from_state,
    )

    policy = _risk_policy()
    cov = _covariance(("AAPL",))
    memo = _memo("AAPL")
    state = AtlasResearchState(
        run_type="delta",
        run_date=_SESSION,
        knowledge_cutoff_at=_CUTOFF,
        config=AtlasConfigBundle(preferences={"current_weights": {"AAPL": 40.0, "CASH": 60.0}}),
        phase_hermes=PhaseHermesState(
            pm_direction_memo=memo,
            calibrated_forecasts={"AAPL": _calibrated("AAPL").model_dump(mode="json")},
            # No deliberation_summaries → no H6 horizons
        ),
    )
    # from_state derives DEFAULT when horizons are absent (phase7e no longer forces 21).
    bundle = assemble_allocation_input_bundle_from_state(
        state,
        risk_policy=policy,
        covariance=cov,
    )
    assert bundle is not None
    assert bundle.calibrated_returns[0].horizon_sessions == DEFAULT_FORECAST_HORIZON_SESSIONS
    assert bundle.covariance is not None


def test_from_state_derives_coherent_non_default_horizon() -> None:
    """#2814: coherent H6 horizon ≠ 21 must assemble — not reject via expected=21."""
    from digiquant.research.state import (
        AtlasConfigBundle,
        AtlasResearchState,
        PhaseHermesState,
    )
    from digiquant.portfolio.allocation_inputs import (
        DEFAULT_FORECAST_HORIZON_SESSIONS,
        assemble_allocation_input_bundle_from_state,
    )

    policy = _risk_policy()
    cov = _covariance(("AAPL",))
    memo = _memo("AAPL")
    # Horizon extraction only needs terms.horizon_sessions (not a full EffectiveForecast).
    deliberation = {
        "AAPL": {
            "effective_forecast": {
                "terms": {"horizon_sessions": 63},
            }
        }
    }
    state = AtlasResearchState(
        run_type="delta",
        run_date=_SESSION,
        knowledge_cutoff_at=_CUTOFF,
        config=AtlasConfigBundle(preferences={"current_weights": {"AAPL": 40.0, "CASH": 60.0}}),
        phase_hermes=PhaseHermesState(
            pm_direction_memo=memo,
            calibrated_forecasts={"AAPL": _calibrated("AAPL").model_dump(mode="json")},
            deliberation_summaries=deliberation,
        ),
    )
    hard_expected = assemble_allocation_input_bundle_from_state(
        state,
        risk_policy=policy,
        covariance=cov,
        expected_horizon_sessions=DEFAULT_FORECAST_HORIZON_SESSIONS,
    )
    assert hard_expected is None  # old phase7e contract — must not be reintroduced

    derived = assemble_allocation_input_bundle_from_state(
        state,
        risk_policy=policy,
        covariance=cov,
    )
    assert derived is not None
    assert derived.calibrated_returns[0].horizon_sessions == 63
    assert derived.calibrated_returns[0].status is AssetInputStatus.AVAILABLE
