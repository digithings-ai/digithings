"""WP-H — H8 scales calibrated size by PM confidence; rank is order, not size.

Cash-first: a confidence haircut must not be renormalized into other names.
Missing confidence uses the documented conservative default (not 1.0).
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.portfolio.h8_risk_snapshots import H8RiskArtifacts
from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.portfolio.phases import phase7e_risk_sizing
from digiquant.portfolio.phases.phase7e_risk_sizing import (
    RiskSizingDeps,
    build_risk_sizing_node,
)
from digiquant.portfolio.sizing import SizingCaps, TickerRisk, size_portfolio
from digiquant.portfolio.skills import load_skill_full
from digiquant.research.state import (
    PhasePortfolioState,
    ResearchConfigBundle,
    ResearchState,
)

from tests.dq.portfolio.test_allocation_inputs import _covariance, _risk_policy
from tests.dq.portfolio.test_calibrated_sizing import _bundle
from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SESSION = date(2026, 8, 31)


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


def _risk(tickers: tuple[str, ...], *, vol: float = 20.0) -> dict[str, TickerRisk]:
    return {t: TickerRisk(ticker=t, hist_vol_21=vol, sector=t) for t in tickers}


def _weights(result: object) -> dict[str, float]:
    return {p.ticker: p.target_pct for p in result.positions}


def test_all_missing_confidence_skips_haircut() -> None:
    """Pre-WP-G memos omit confidence on every long — do not shrink the book."""
    memo = PMDirectionMemo(
        date=_SESSION,
        roster=[
            TickerDirection(ticker="IAU", direction="long", conviction_rank=1),
            TickerDirection(ticker="GLD", direction="long", conviction_rank=2),
        ],
        memo="m",
    )
    assert phase7e_risk_sizing.confidence_scales_from_memo(memo) is None


def test_missing_confidence_uses_conservative_default_not_one() -> None:
    assert phase7e_risk_sizing.H8_MISSING_CONFIDENCE_DEFAULT == pytest.approx(0.5)
    assert phase7e_risk_sizing.pm_confidence_scale(None) == pytest.approx(0.5)
    assert phase7e_risk_sizing.pm_confidence_scale(None) != pytest.approx(1.0)
    assert phase7e_risk_sizing.pm_confidence_scale(0.9) == pytest.approx(0.9)
    assert phase7e_risk_sizing.pm_confidence_scale(0.0) == pytest.approx(0.0)


def test_higher_confidence_gets_more_weight_same_forecast() -> None:
    scores = {"IAU": 2.0, "GLD": 2.0}
    result = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 0.9, "GLD": 0.5},
    )
    weights = _weights(result)
    assert weights["IAU"] > weights["GLD"]
    assert weights["IAU"] / weights["GLD"] == pytest.approx(0.9 / 0.5)


def test_both_low_confidence_raises_cash() -> None:
    scores = {"IAU": 2.0, "GLD": 2.0}
    full = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 1.0, "GLD": 1.0},
    )
    low = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 0.4, "GLD": 0.4},
    )
    assert low.cash_pct > full.cash_pct
    assert low.gross_pct < full.gross_pct
    assert low.gross_pct == pytest.approx(full.gross_pct * 0.4)


def test_confidence_haircut_is_cash_first_does_not_boost_peer() -> None:
    """Vol-target must not redistribute a confidence haircut into the other name."""
    scores = {"IAU": 2.0, "GLD": 2.0}
    # Permissive vol budget would otherwise upscale leftover risk into the peer.
    full = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 1.0, "GLD": 1.0},
    )
    haircut = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 1.0, "GLD": 0.5},
    )
    full_w = _weights(full)
    hair_w = _weights(haircut)
    assert hair_w["IAU"] == pytest.approx(full_w["IAU"])
    assert hair_w["GLD"] == pytest.approx(full_w["GLD"] * 0.5)
    assert haircut.cash_pct == pytest.approx(full.cash_pct + full_w["GLD"] * 0.5)


def test_rank_swap_does_not_change_calibrated_size_with_confidence() -> None:
    returns = {"IAU": ("0.06", "0.03", "1.0"), "GLD": ("0.06", "0.03", "1.0")}
    dense = _bundle(returns=returns, ranks={"IAU": 1, "GLD": 2})
    swapped = _bundle(returns=returns, ranks={"IAU": 2, "GLD": 1})
    scores_a = phase7e_risk_sizing.calibrated_scores_from_bundle(dense, long_tickers=["IAU", "GLD"])
    scores_b = phase7e_risk_sizing.calibrated_scores_from_bundle(
        swapped, long_tickers=["IAU", "GLD"]
    )
    assert scores_a == scores_b
    scales = {"IAU": 0.8, "GLD": 0.8}
    a = size_portfolio(
        convictions={"IAU": 5.0, "GLD": 2.0},
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores_a,
        confidence_scales=scales,
    )
    b = size_portfolio(
        convictions={"IAU": 2.0, "GLD": 5.0},
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores_b,
        confidence_scales=scales,
    )
    assert _weights(a) == _weights(b)


def test_vol_budget_and_grid_can_pin_ten_pct_without_using_rank() -> None:
    """Operator: 2026-08-31 rank-1 gold ~10%. No in-repo pm-rebalance fixture exists.

    On the calibrated path rank is unused. A six-name equal-forecast book at 20%
    name vol, 12% portfolio vol budget, and 5% grid lands each name at 10% — the
    same pin a rank-1 name can hit without rank driving size.
    """
    names = ("IAU", "GLD", "SLV", "GDX", "TLT", "IEF")
    scores = {t: 1.0 for t in names}
    result = size_portfolio(
        convictions={t: 5.0 - i * 0.5 for i, t in enumerate(names)},
        stances={t: "buy" for t in names},
        risk=_risk(names, vol=20.0),
        caps=SizingCaps(
            min_position_pct=0.0,
            max_position_pct=30.0,
            max_sector_pct=100.0,
            weight_increment_pct=5.0,
            target_portfolio_vol=12.0,
            max_gross_pct=100.0,
            min_conviction=0.0,
        ),
        calibrated_scores=scores,
        confidence_scales={t: 1.0 for t in names},
    )
    weights = _weights(result)
    assert set(weights) == set(names)
    assert all(w == pytest.approx(10.0) for w in weights.values())
    # Rank-shaped convictions did not break the equal calibrated mix.
    assert weights["IAU"] == pytest.approx(weights["IEF"])


def test_missing_confidence_scale_matches_half_not_full() -> None:
    memo = PMDirectionMemo(
        date=_SESSION,
        roster=[
            TickerDirection(ticker="IAU", direction="long", conviction_rank=1),
            TickerDirection(ticker="GLD", direction="long", conviction_rank=2, confidence=1.0),
        ],
        memo="m",
    )
    scales = phase7e_risk_sizing.confidence_scales_from_memo(memo)
    assert scales["IAU"] == pytest.approx(phase7e_risk_sizing.H8_MISSING_CONFIDENCE_DEFAULT)
    assert scales["GLD"] == pytest.approx(1.0)
    scores = {"IAU": 2.0, "GLD": 2.0}
    result = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy", "GLD": "buy"},
        risk=_risk(("IAU", "GLD")),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales=scales,
    )
    weights = _weights(result)
    assert weights["GLD"] == pytest.approx(weights["IAU"] * 2.0)


def _run_h8_with_memo(
    monkeypatch: pytest.MonkeyPatch,
    *,
    roster: list[TickerDirection],
    returns: dict[str, tuple[str, str, str]],
) -> dict[str, float]:
    bundle = _bundle(returns=returns, ranks={row.ticker: row.conviction_rank for row in roster})
    tickers = tuple(row.ticker for row in roster if row.direction == "long")
    artifacts = H8RiskArtifacts(policy=_risk_policy(), covariance_snapshot=_covariance(tickers))
    monkeypatch.setattr(
        "digiquant.portfolio.h8_risk_snapshots.resolve_h8_risk_artifacts",
        lambda **_kwargs: artifacts,
    )
    monkeypatch.setattr(
        "digiquant.portfolio.allocation_inputs.assemble_allocation_input_bundle_from_state",
        lambda *_a, **_k: bundle,
    )
    state = ResearchState(
        run_type="delta",
        run_date=_SESSION,
        baseline_date=date(2026, 8, 28),
        config=ResearchConfigBundle(
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "h8_sizing_input_mode": "calibrated",
            }
        ),
        phase_portfolio=PhasePortfolioState(
            pm_direction_memo=PMDirectionMemo(date=_SESSION, roster=roster, memo="m")
        ),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "price_technicals": [
                {"ticker": t, "date": "2026-08-31", "hist_vol_21": 20, "atr_pct": None}
                for t in tickers
            ]
        }
    )
    out = build_risk_sizing_node(RiskSizingDeps(client=client))(state)
    book = out["phase_portfolio"].sized_book
    assert book is not None
    return {row["ticker"]: row["target_pct"] for row in book["recommended_portfolio"]}


def test_phase7e_applies_memo_confidence_cash_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    returns = {"IAU": ("0.06", "0.02", "1.0"), "GLD": ("0.06", "0.02", "1.0")}
    high = _run_h8_with_memo(
        monkeypatch,
        roster=[
            TickerDirection(ticker="IAU", direction="long", conviction_rank=1, confidence=0.9),
            TickerDirection(ticker="GLD", direction="long", conviction_rank=2, confidence=0.5),
        ],
        returns=returns,
    )
    assert high["IAU"] > high["GLD"]
    invested = sum(high.values())
    assert invested < 100.0
    # Same forecasts: haircuts must not lift IAU above its full-confidence size.
    full = _run_h8_with_memo(
        monkeypatch,
        roster=[
            TickerDirection(ticker="IAU", direction="long", conviction_rank=1, confidence=1.0),
            TickerDirection(ticker="GLD", direction="long", conviction_rank=2, confidence=1.0),
        ],
        returns=returns,
    )
    assert high["IAU"] == pytest.approx(full["IAU"] * 0.9)
    assert high["GLD"] == pytest.approx(full["GLD"] * 0.5)
    assert high["IAU"] <= full["IAU"] + 1e-9


def test_pm_skill_says_h8_sizes_by_confidence_not_rank() -> None:
    body = load_skill_full("pm-direction")
    lowered = body.lower()
    assert "converts your ranks" not in lowered
    assert "h8 may later" not in lowered
    assert "confidence" in lowered
    assert "rank" in lowered and "order" in lowered
    assert "size" in lowered


def test_size_portfolio_records_confidence_scale_in_explanation() -> None:
    scores = {"IAU": 2.0}
    result = size_portfolio(
        convictions=scores,
        stances={"IAU": "buy"},
        risk=_risk(("IAU",)),
        caps=_permissive(),
        calibrated_scores=scores,
        confidence_scales={"IAU": 0.5},
    )
    assert "confidence" in result.explanation.lower()
    # Keep the closed 12-reason ledger vocabulary: reuse FINAL_GROSS_SCALE.
    kinds = {e.adjustment_type.value for e in result.adjustments}
    assert "final_gross_scale" in kinds
    reasons = " ".join(e.reason for e in result.adjustments)
    assert "confidence" in reasons.lower()


def test_confidence_scales_ignore_flat_rows() -> None:
    memo = PMDirectionMemo(
        date=_SESSION,
        roster=[
            TickerDirection(ticker="IAU", direction="long", conviction_rank=1, confidence=0.8),
            TickerDirection(ticker="CASH", direction="flat", conviction_rank=2, confidence=0.1),
        ],
        memo="m",
    )
    scales = phase7e_risk_sizing.confidence_scales_from_memo(memo)
    assert list(scales) == ["IAU"]
    assert scales["IAU"] == pytest.approx(0.8)
