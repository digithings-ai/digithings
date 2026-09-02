"""WP9.3 — attach PreTradeRiskReport after the final H8 control shell (#2750)."""

from __future__ import annotations

from datetime import date
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import pytest
from digiquant.olympus.hermes.allocation_contracts import PreTradeRiskReport
from digiquant.olympus.hermes.allocation_hashes import weights_fingerprint
from digiquant.olympus.hermes.phases import phase7e_risk_sizing
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_pretrade_risk_report_for_final_book,
    build_risk_sizing_node,
)
from digiquant.olympus.hermes.sizing_events import SizingAdjustment, SizingAdjustmentType

pytestmark = pytest.mark.unit


def _final_weights(book: dict[str, Any]) -> dict[str, float]:
    """Match H9 commit extraction — report fingerprint must equal this map."""
    from digiquant.olympus.hermes.writers.commit_io import weights_from_sized_book

    return weights_from_sized_book(book)


def _run_h8(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tickers: tuple[str, ...] = ("AAPL", "MSFT"),
    preferences: dict[str, Any] | None = None,
    prior_book: list[dict[str, Any]] | None = None,
    current_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    from digiquant.olympus.atlas.state import (
        AtlasConfigBundle,
        AtlasResearchState,
        PhaseHermesState,
        PriorContext,
    )
    from digiquant.olympus.hermes.h8_risk_snapshots import H8RiskArtifacts
    from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection

    from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
    from tests.dq.hermes.test_allocation_inputs import _covariance, _risk_policy
    from tests.dq.hermes.test_calibrated_sizing import _bundle

    returns = {t: ("0.06", "0.02", "1.0") for t in tickers}
    bundle = _bundle(returns=returns)
    policy = _risk_policy()
    cov = _covariance(tickers)
    artifacts = H8RiskArtifacts(policy=policy, covariance_snapshot=cov)
    monkeypatch.setattr(
        "digiquant.olympus.hermes.h8_risk_snapshots.resolve_h8_risk_artifacts",
        lambda **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        "digiquant.olympus.hermes.allocation_inputs.assemble_allocation_input_bundle_from_state",
        lambda *_a, **_k: bundle,
    )

    run_date = date(2026, 6, 12)
    memo = PMDirectionMemo(
        date=run_date,
        roster=[
            TickerDirection(ticker=t, direction="long", conviction_rank=i)
            for i, t in enumerate(tickers, start=1)
        ],
        memo="m",
    )
    prefs = {
        "max_single_etf_pct": 100,
        "max_sector_pct": 100,
        "target_portfolio_vol": 1.0e6,
        "weight_increment_pct": 0,
        "h8_sizing_input_mode": "calibrated",
        **(preferences or {}),
    }
    if current_weights is not None:
        prefs["current_weights"] = current_weights
    state = AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences=prefs),
        prior_context=PriorContext(prior_book=prior_book or []),
        phase_hermes=PhaseHermesState(pm_direction_memo=memo),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": t, "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None}
                for t in tickers
            ]
        }
    )
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    hermes = out["phase_hermes"]
    book = hermes.sized_book
    assert book is not None
    report_raw = hermes.pre_trade_risk_report
    assert report_raw is not None, "WP9.3 must attach pre_trade_risk_report after final H8"
    report = PreTradeRiskReport.model_validate(report_raw)
    return {"book": book, "report": report, "hermes": hermes, "bundle": bundle}


def test_report_fingerprint_matches_final_book_after_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_h8(monkeypatch)
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)
    assert report.final_weights.weights_fingerprint == weights_fingerprint(final)
    assert book["pre_trade_risk_report_hash"] == report.report_content_hash
    assert report.allocation_input_bundle_hash == result["bundle"].bundle_content_hash


def test_final_book_weights_matches_h9_extractor_on_divergent_shapes() -> None:
    """H8 report binding and H9 validation must share one weight extractor (#2824)."""
    from digiquant.olympus.hermes.phases.phase7e_risk_sizing import _final_book_weights
    from digiquant.olympus.hermes.writers.commit_io import weights_from_sized_book

    gross_gt_100 = {
        "recommended_portfolio": [
            {"ticker": "SPY", "target_pct": 80.0},
            {"ticker": "TLT", "target_pct": 40.0},
        ]
    }
    dup_rows = {
        "recommended_portfolio": [
            {"ticker": "SPY", "target_pct": 30.0},
            {"ticker": "SPY", "target_pct": 30.0},
            {"ticker": "TLT", "target_pct": 40.0},
        ]
    }
    for book in (gross_gt_100, dup_rows):
        h8_risky, _cash = _final_book_weights(book)
        h9_risky = weights_from_sized_book(book)
        assert h8_risky == h9_risky
        assert weights_fingerprint(h8_risky) == weights_fingerprint(h9_risky)


def test_continuity_carry_case_report_matches_final_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Held continuity carry enters the final book; report must hash that book."""
    result = _run_h8(
        monkeypatch,
        tickers=("SPY",),
        prior_book=[{"ticker": "DBO", "weight_pct": 7.5}],
        current_weights={"SPY": 40.0, "DBO": 7.5, "CASH": 52.5},
        preferences={"max_single_etf_pct": 100, "weight_increment_pct": 0},
    )
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    # Continuity may restore DBO depending on memo addressing; fingerprint must
    # equal whatever landed in the final book either way.
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)
    assert "DBO" in final or "SPY" in final


def test_cadence_hold_case_report_matches_final_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_h8(
        monkeypatch,
        tickers=("SPY",),
        prior_book=[{"ticker": "SPY", "weight_pct": 40.0, "entry_date": "2026-01-01"}],
        current_weights={"SPY": 40.0, "CASH": 60.0},
        preferences={
            "rebalancing_cadence": "none",
            "rebalance_threshold_pct": 3,
            "max_single_etf_pct": 100,
            "weight_increment_pct": 0,
        },
    )
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)


def test_grid_rounding_case_report_matches_final_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_h8(
        monkeypatch,
        preferences={"weight_increment_pct": 5, "max_single_etf_pct": 40},
    )
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)
    assert any(
        e.get("adjustment_type") == SizingAdjustmentType.GRID_ROUNDING.value
        for e in book.get("adjustments") or []
    ) or all(w % 5 == 0 or abs(w % 5) < 1e-9 for w in final.values())


def test_final_cap_case_report_matches_final_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force an overshoot through the final invested cap; report uses post-cap book."""
    # Extremely permissive vol/sector so size_portfolio can ask for >100%, then
    # _cap_total_invested (or gross scale) brings it back — report must match.
    result = _run_h8(
        monkeypatch,
        tickers=("AAPL", "MSFT", "GOOG"),
        preferences={
            "max_single_etf_pct": 80,
            "max_sector_pct": 100,
            "target_portfolio_vol": 1.0e6,
            "weight_increment_pct": 0,
            "max_gross_pct": 100,
        },
    )
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    assert sum(final.values()) <= 100.0 + 1e-6
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)


def test_builder_path_does_not_mutate_final_book_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_h8(monkeypatch)
    book = result["book"]
    before = [dict(row) for row in book["recommended_portfolio"]]
    # Re-run attach helper against a mutable copy of the book payload.
    from digiquant.olympus.atlas.state import (
        AtlasConfigBundle,
        AtlasResearchState,
        PhaseHermesState,
    )
    from digiquant.olympus.hermes.h8_risk_snapshots import H8RiskArtifacts
    from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection

    from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
    from tests.dq.hermes.test_allocation_inputs import _covariance, _risk_policy

    run_date = date(2026, 6, 12)
    memo = PMDirectionMemo(
        date=run_date,
        roster=[
            TickerDirection(ticker="AAPL", direction="long", conviction_rank=1),
            TickerDirection(ticker="MSFT", direction="long", conviction_rank=2),
        ],
        memo="m",
    )
    state = AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences={}),
        phase_hermes=PhaseHermesState(pm_direction_memo=memo),
    )
    mutable_book = {
        **book,
        "recommended_portfolio": [dict(row) for row in book["recommended_portfolio"]],
    }
    artifacts = H8RiskArtifacts(
        policy=_risk_policy(),
        covariance_snapshot=_covariance(("AAPL", "MSFT")),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": "AAPL", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
                {"ticker": "MSFT", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
            ]
        }
    )
    again = build_pretrade_risk_report_for_final_book(
        state=state,
        sized_book=mutable_book,
        allocation_bundle=result["bundle"],
        risk_artifacts=artifacts,
        deps=RiskSizingDeps(client=client),
    )
    assert again is not None
    assert mutable_book["recommended_portfolio"] == before


def test_report_failure_omits_report_without_changing_book(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typed report failure blocks only report promotion (pre-H9 enforcement)."""
    monkeypatch.setattr(
        phase7e_risk_sizing,
        "build_pretrade_risk_report_for_final_book",
        lambda **_k: None,
    )
    from digiquant.olympus.atlas.state import (
        AtlasConfigBundle,
        AtlasResearchState,
        PhaseHermesState,
    )
    from digiquant.olympus.hermes.h8_risk_snapshots import H8RiskArtifacts
    from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection

    from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
    from tests.dq.hermes.test_allocation_inputs import _covariance, _risk_policy
    from tests.dq.hermes.test_calibrated_sizing import _bundle

    bundle = _bundle(returns={"AAPL": ("0.06", "0.02", "1.0")})
    artifacts = H8RiskArtifacts(policy=_risk_policy(), covariance_snapshot=_covariance(("AAPL",)))
    monkeypatch.setattr(
        "digiquant.olympus.hermes.h8_risk_snapshots.resolve_h8_risk_artifacts",
        lambda **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        "digiquant.olympus.hermes.allocation_inputs.assemble_allocation_input_bundle_from_state",
        lambda *_a, **_k: bundle,
    )
    run_date = date(2026, 6, 12)
    state = AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "h8_sizing_input_mode": "calibrated",
            }
        ),
        phase_hermes=PhaseHermesState(
            pm_direction_memo=PMDirectionMemo(
                date=run_date,
                roster=[TickerDirection(ticker="AAPL", direction="long", conviction_rank=1)],
                memo="m",
            )
        ),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": "AAPL", "date": "2026-06-12", "hist_vol_21": 20, "atr_pct": None},
            ]
        }
    )
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    hermes = out["phase_hermes"]
    assert hermes.sized_book is not None
    assert hermes.pre_trade_risk_report is None
    assert "pre_trade_risk_report_hash" not in hermes.sized_book


def test_controls_from_adjustments_maps_caps_and_exits() -> None:
    sized_book = {
        "recommended_portfolio": [{"ticker": "AAPL", "target_pct": 30.0}],
        "adjustments": [
            SizingAdjustment(
                ticker="AAPL",
                adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
                original_pct=48.0,
                adjusted_pct=30.0,
                reason="single-name cap applied",
            ).model_dump(),
            SizingAdjustment(
                ticker="TSLA",
                adjustment_type=SizingAdjustmentType.FLAT_EXIT,
                original_pct=5.0,
                adjusted_pct=0.0,
                reason="flat exit",
            ).model_dump(),
            SizingAdjustment(
                ticker="MSFT",
                adjustment_type=SizingAdjustmentType.CONTINUITY_CARRY,
                original_pct=0.0,
                adjusted_pct=7.5,
                reason="carried",
            ).model_dump(),
        ],
    }
    binding, altered, rejected = phase7e_risk_sizing._controls_from_adjustments(sized_book)
    assert any(c.constraint_kind == "single_name_cap" for c in binding)
    assert any(a.ticker == "AAPL" and a.final_weight_pct == 30.0 for a in altered)
    assert any(a.ticker == "MSFT" for a in altered)
    assert any(r.ticker == "TSLA" for r in rejected)
