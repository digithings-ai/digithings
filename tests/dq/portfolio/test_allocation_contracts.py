"""WP8.2 — AllocationInputBundle contracts and stable hashes (#2727)."""

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
    CostLiquidityBinding,
    CovarianceBinding,
    MandateReference,
    PriorBookSnapshot,
    PriorWeightEntry,
    build_source_hashes,
)
from digiquant.portfolio.allocation_hashes import (
    allocation_bundle_content_hash,
    allocation_bundle_hash_payload,
    canonical_json,
    weights_fingerprint,
)
from digiquant.portfolio.writers.commit_io import weights_fingerprint as commit_io_weights_fp
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_TS = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_SESSION = date(2026, 8, 25)
_POLICY_ID = UUID("11111111-1111-4111-8111-111111111111")
_SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
_FORECAST_ID = UUID("33333333-3333-4333-8333-333333333333")
_POLICY_HASH = "a" * 64
_CAL_HASH_A = "b" * 64
_CAL_HASH_B = "c" * 64
_COST_HASH_A = "d" * 64
_H7_HASH = "e" * 64
_COV_HASH = "f" * 64


def _run_context() -> AllocationRunContext:
    return AllocationRunContext(
        run_id="run-2727",
        session_date=_SESSION,
        cutoff_at=_TS,
        cadence=AllocationCadence.DAILY,
    )


def _sample_bundle(**overrides: object) -> AllocationInputBundle:
    tickers = ("AAPL", "MSFT")
    mandates = tuple(
        MandateReference(
            ticker=ticker,
            direction="long",
            conviction_rank=idx,
            effective_forecast_id=_FORECAST_ID,
        )
        for idx, ticker in enumerate(tickers, start=1)
    )
    calibrated = tuple(
        CalibratedReturnSlice(
            ticker=ticker,
            horizon_sessions=21,
            expected_gross_return=Decimal("0.05"),
            forecast_error_std=Decimal("0.02"),
            reliability_weight=Decimal("0.8"),
            calibrated_forecast_content_hash=_CAL_HASH_A if ticker == "AAPL" else _CAL_HASH_B,
            status=AssetInputStatus.AVAILABLE,
        )
        for ticker in tickers
    )
    prior = PriorBookSnapshot(
        entries=(
            PriorWeightEntry(ticker="AAPL", weight_pct=30.0),
            PriorWeightEntry(ticker="MSFT", weight_pct=20.0),
        ),
        cash_weight_pct=50.0,
    )
    control = ControlSettingsFingerprint(
        risk_policy_content_hash=_POLICY_HASH,
        risk_policy_id=_POLICY_ID,
    )
    covariance = CovarianceBinding(
        snapshot_id=_SNAPSHOT_ID,
        content_hash=_COV_HASH,
        tickers=tickers,
    )
    cost = CostLiquidityBinding(entries=(("AAPL", _COST_HASH_A),))
    source = build_source_hashes(
        h7_memo_hash=_H7_HASH,
        risk_policy_hash=_POLICY_HASH,
        prior_entries=tuple((entry.ticker, entry.weight_pct) for entry in prior.entries),
        calibrated_hashes=(("AAPL", _CAL_HASH_A), ("MSFT", _CAL_HASH_B)),
        covariance_hash=_COV_HASH,
        cost_hashes=cost.entries,
    )
    payload = {
        "schema_version": "1.0",
        "run": _run_context(),
        "canonical_asset_order": tickers,
        "mandates": mandates,
        "calibrated_returns": calibrated,
        "prior_book": prior,
        "control_settings": control,
        "covariance": covariance,
        "cost_liquidity": cost,
        "source_hashes": source,
    }
    payload.update(overrides)
    draft = AllocationInputBundle.model_construct(
        schema_version="1.0",
        run=payload["run"],
        canonical_asset_order=payload["canonical_asset_order"],
        mandates=payload["mandates"],
        calibrated_returns=payload["calibrated_returns"],
        prior_book=payload["prior_book"],
        control_settings=payload["control_settings"],
        covariance=payload.get("covariance"),
        cost_liquidity=payload.get("cost_liquidity"),
        source_hashes=payload["source_hashes"],
        bundle_content_hash="",
    )
    bundle_hash = allocation_bundle_content_hash(payload=draft._hash_payload())
    return AllocationInputBundle.model_validate({**payload, "bundle_content_hash": bundle_hash})


def test_weights_fingerprint_matches_commit_io_delegate() -> None:
    weights = {"MSFT": 20.3333, "AAPL": 10.5}
    direct = weights_fingerprint(weights)
    delegated = commit_io_weights_fp(weights)
    assert direct == delegated
    assert len(direct) == 64


def test_weights_fingerprint_golden_bytes() -> None:
    """Byte-stable incumbent idempotency digest (WP8.2 must not drift H9)."""
    fp = weights_fingerprint({"ZZZ": 12.5, "AAA": 3.3333})
    assert fp == "39e67aed0e43743b8b8f3c58b52f8c07187ec69333c9549764c36d327a43c99b"


def test_bundle_hash_stable_and_order_independent_in_payload() -> None:
    bundle = _sample_bundle()
    again = _sample_bundle()
    assert bundle.bundle_content_hash == again.bundle_content_hash

    reversed_order_payload = allocation_bundle_hash_payload(
        schema_version="1.0",
        run={
            "run_id": "run-2727",
            "session_date": _SESSION.isoformat(),
            "cutoff_at": _TS.isoformat(),
            "cadence": "daily",
            "profile_config_version_id": None,
        },
        canonical_asset_order=("MSFT", "AAPL"),
        mandates=(
            {
                "ticker": "MSFT",
                "direction": "long",
                "conviction_rank": 2,
                "effective_forecast_id": str(_FORECAST_ID),
                "forecast_reference_hash": None,
                "degradation_reason": None,
            },
            {
                "ticker": "AAPL",
                "direction": "long",
                "conviction_rank": 1,
                "effective_forecast_id": str(_FORECAST_ID),
                "forecast_reference_hash": None,
                "degradation_reason": None,
            },
        ),
        calibrated_returns=(
            {
                "ticker": "MSFT",
                "horizon_sessions": 21,
                "expected_gross_return": "0.05",
                "forecast_error_std": "0.02",
                "reliability_weight": "0.8",
                "calibrated_forecast_content_hash": _CAL_HASH_B,
                "status": "available",
                "unavailable_reason": None,
            },
            {
                "ticker": "AAPL",
                "horizon_sessions": 21,
                "expected_gross_return": "0.05",
                "forecast_error_std": "0.02",
                "reliability_weight": "0.8",
                "calibrated_forecast_content_hash": _CAL_HASH_A,
                "status": "available",
                "unavailable_reason": None,
            },
        ),
        prior_book={
            "entries": [
                {"ticker": "AAPL", "weight_pct": 30.0},
                {"ticker": "MSFT", "weight_pct": 20.0},
            ],
            "cash_weight_pct": 50.0,
        },
        control_settings={
            "risk_policy_content_hash": _POLICY_HASH,
            "risk_policy_id": str(_POLICY_ID),
        },
        covariance={
            "snapshot_id": str(_SNAPSHOT_ID),
            "content_hash": _COV_HASH,
            "tickers": ["MSFT", "AAPL"],
        },
        cost_liquidity={"entries": [["AAPL", _COST_HASH_A]]},
        source_hashes={
            "h7_memo_hash": _H7_HASH,
            "risk_policy_hash": _POLICY_HASH,
            "prior_weights_fingerprint": weights_fingerprint({"AAPL": 30.0, "MSFT": 20.0}),
            "covariance_hash": _COV_HASH,
            "calibrated_hashes": [["AAPL", _CAL_HASH_A], ["MSFT", _CAL_HASH_B]],
            "cost_hashes": [["AAPL", _COST_HASH_A]],
        },
    )
    assert (
        allocation_bundle_content_hash(payload=reversed_order_payload) == bundle.bundle_content_hash
    )


def test_source_change_changes_bundle_hash() -> None:
    base = _sample_bundle()
    mutated = _sample_bundle(
        calibrated_returns=tuple(
            CalibratedReturnSlice(
                ticker=ticker,
                horizon_sessions=21,
                expected_gross_return=Decimal("0.06"),
                forecast_error_std=Decimal("0.02"),
                reliability_weight=Decimal("0.8"),
                calibrated_forecast_content_hash=_CAL_HASH_A if ticker == "AAPL" else _CAL_HASH_B,
                status=AssetInputStatus.AVAILABLE,
            )
            for ticker in ("AAPL", "MSFT")
        ),
    )
    assert base.bundle_content_hash != mutated.bundle_content_hash


def test_rejects_extra_fields_and_nan() -> None:
    with pytest.raises(ValidationError, match="extra"):
        MandateReference(
            ticker="AAPL",
            direction="long",
            conviction_rank=1,
            surprise="nope",
        )
    with pytest.raises(ValidationError):
        PriorWeightEntry(ticker="AAPL", weight_pct=float("nan"))


def test_rejects_horizon_mismatch_and_matrix_order_mismatch() -> None:
    with pytest.raises(ValidationError, match="horizon_sessions"):
        _sample_bundle(
            calibrated_returns=(
                CalibratedReturnSlice(
                    ticker="AAPL",
                    horizon_sessions=21,
                    expected_gross_return=Decimal("0.05"),
                    forecast_error_std=Decimal("0.02"),
                    reliability_weight=Decimal("0.8"),
                    calibrated_forecast_content_hash=_CAL_HASH_A,
                    status=AssetInputStatus.AVAILABLE,
                ),
                CalibratedReturnSlice(
                    ticker="MSFT",
                    horizon_sessions=42,
                    expected_gross_return=Decimal("0.05"),
                    forecast_error_std=Decimal("0.02"),
                    reliability_weight=Decimal("0.8"),
                    calibrated_forecast_content_hash=_CAL_HASH_B,
                    status=AssetInputStatus.AVAILABLE,
                ),
            ),
        )

    with pytest.raises(ValidationError, match="covariance tickers"):
        _sample_bundle(
            covariance=CovarianceBinding(
                snapshot_id=_SNAPSHOT_ID,
                content_hash=_COV_HASH,
                tickers=("MSFT", "AAPL"),
            ),
        )


def test_rejects_non_utc_cutoff() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        AllocationRunContext(
            run_id="run",
            session_date=_SESSION,
            cutoff_at=datetime(2026, 8, 25, 20, 0, tzinfo=UTC).replace(tzinfo=None),
        )


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
