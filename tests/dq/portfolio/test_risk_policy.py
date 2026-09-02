"""WP6.2 — resolve incumbent RiskPolicy and CovarianceSnapshot (#2692)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime

import polars as pl
import pytest
from digiquant.portfolio.models.risk_policy import (
    PolicyArtifactStatus,
    ProvenanceSource,
    risk_policy_content_hash,
    risk_policy_id,
)
from digiquant.portfolio.phases.phase7e_risk_sizing import (
    _effective_inputs,
    _memo_effective_inputs,
)
from digiquant.portfolio.risk_controls import BreakerConfig
from digiquant.portfolio.risk_policy import (
    INCUMBENT_CONTROL_ORDER,
    METHOD_VERSION,
    breaker_config_from_policy,
    resolve_covariance_snapshot,
    resolve_risk_policy,
    sizing_caps_from_policy,
)
from digiquant.portfolio.sizing import SizingCaps, size_portfolio
from pydantic import ValidationError

from tests.dq.hermes.incumbent_risk_fixtures import (
    assert_book_matches_golden,
    load_incumbent_risk_fixture,
    sizing_result_snapshot,
)
from tests.dq.hermes.test_incumbent_risk_characterization import (
    _LEAF_SCENARIOS,
    _REP_BOOK_SCENARIOS,
)

pytestmark = pytest.mark.unit

_GOLDEN = load_incumbent_risk_fixture()
_TS = datetime(2026, 8, 25, 20, 0, tzinfo=UTC)
_AS_OF = date(2026, 8, 25)


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


def test_default_policy_matches_incumbent_fixture_defaults() -> None:
    resolution = resolve_risk_policy(effective_at=_TS)
    policy = resolution.policy
    assert policy.status is PolicyArtifactStatus.AVAILABLE
    assert policy.method_version == METHOD_VERSION
    assert list(policy.control_order) == _GOLDEN["policy_defaults"]["control_order"]
    assert list(policy.control_order) == list(INCUMBENT_CONTROL_ORDER)

    for field, expected in _GOLDEN["policy_defaults"]["sizing_caps"].items():
        assert policy.sizing_caps[field].value == expected
        assert policy.sizing_caps[field].source is ProvenanceSource.CODE_DEFAULT

    for field, expected in _GOLDEN["policy_defaults"]["breaker_config"].items():
        assert policy.breaker[field].value == expected

    assert policy.annualize_factor.value == _GOLDEN["policy_defaults"]["annualize_factor"]
    assert policy.vol_lookback_days.value == _GOLDEN["policy_defaults"]["vol_lookback_days"]
    assert policy.corr_lookback_days.value == _GOLDEN["policy_defaults"]["corr_lookback_days"]

    for field, expected in _GOLDEN["policy_defaults"]["turnover_preferences"].items():
        assert policy.turnover[field].value == expected


def test_policy_leaves_carry_provenance_and_deterministic_hash() -> None:
    first = resolve_risk_policy(effective_at=_TS).policy
    second = resolve_risk_policy(effective_at=_TS).policy
    assert first.content_hash == second.content_hash
    assert first.policy_id == second.policy_id
    assert first.policy_id == risk_policy_id(
        method_version=METHOD_VERSION,
        content_hash=first.content_hash,
    )
    assert len(first.content_hash) == 64
    assert all(leaf.source is not None for leaf in first.sizing_caps.values())
    assert all(leaf.source is not None for leaf in first.breaker.values())


def test_policy_bridge_matches_incumbent_dataclass_defaults() -> None:
    resolution = resolve_risk_policy(effective_at=_TS)
    assert asdict(resolution.sizing_caps) == _GOLDEN["policy_defaults"]["sizing_caps"]
    assert asdict(resolution.breaker_config) == _GOLDEN["policy_defaults"]["breaker_config"]
    assert asdict(sizing_caps_from_policy(resolution.policy)) == asdict(SizingCaps())
    assert asdict(breaker_config_from_policy(resolution.policy)) == asdict(BreakerConfig())


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
def test_correlation_bucket_map_matches_golden(label: str, class_a: str, class_b: str) -> None:
    policy = resolve_risk_policy(effective_at=_TS).policy
    expected = _GOLDEN["bucket_correlations"][label]
    match = next(
        (
            entry
            for entry in policy.correlation_buckets
            if {entry.class_a, entry.class_b} == {class_a, class_b}
        ),
        None,
    )
    assert match is not None
    assert match.rho == expected


def test_vol_fallback_chain_matches_golden() -> None:
    policy = resolve_risk_policy(effective_at=_TS).policy
    expected = _GOLDEN["vol_fallback"]
    chain = {entry.key: entry.annualized_pct for entry in policy.vol_fallback_chain}
    assert chain == expected


@pytest.mark.parametrize("n_key", ["n_long_1", "n_long_2", "n_long_3", "n_long_5"])
def test_rank_to_conviction_matches_golden(n_key: str) -> None:
    n = int(n_key.split("_")[-1])
    policy = resolve_risk_policy(effective_at=_TS).policy
    entry = next(item for item in policy.rank_to_conviction if item.n_long == n)
    expected = _GOLDEN["rank_to_conviction"][n_key]
    assert {str(k): v for k, v in entry.mapping.items()} == {str(k): v for k, v in expected.items()}


def test_phase1_advanced_capabilities_explicitly_unavailable() -> None:
    policy = resolve_risk_policy(effective_at=_TS).policy
    for cap in (
        policy.factor_limits,
        policy.stress_limits,
        policy.tail_limits,
    ):
        assert cap.available is False
        assert cap.enforced is False
        assert cap.limit is None
        assert cap.reason == "phase1_not_implemented"
    assert policy.liquidity_limits.available is True
    assert policy.liquidity_limits.enforced is False
    assert policy.cost_policy.available is True
    assert policy.cost_policy.enforced is False


def test_contradictory_policy_is_typed_degraded() -> None:
    resolution = resolve_risk_policy(
        {"min_position_pct": 50.0, "max_position_pct": 10.0},
        effective_at=_TS,
    )
    assert resolution.policy.status is PolicyArtifactStatus.DEGRADED
    assert resolution.policy.unavailable_reason == "min_position_exceeds_max_position"


def test_degraded_policy_still_derives_bridge_caps_for_tests_only() -> None:
    resolution = resolve_risk_policy(
        {"min_position_pct": 50.0, "max_position_pct": 10.0},
        effective_at=_TS,
    )
    caps = sizing_caps_from_policy(resolution.policy)
    assert caps.min_position_pct == 50.0
    assert caps.max_position_pct == 10.0


@pytest.mark.parametrize("leaf", _LEAF_SCENARIOS.keys())
def test_resolved_policy_sizing_leaves_match_golden(leaf: str) -> None:
    scenario = dict(_LEAF_SCENARIOS[leaf])
    caps = scenario.pop("caps", SizingCaps())
    prefs = {k: v for k, v in asdict(caps).items()}
    resolution = resolve_risk_policy(prefs, effective_at=_TS)
    result = size_portfolio(**scenario, caps=resolution.sizing_caps)
    assert_book_matches_golden(sizing_result_snapshot(result), _GOLDEN["sizing_caps_leaves"][leaf])


@pytest.mark.parametrize("book", _REP_BOOK_SCENARIOS.keys())
def test_resolved_policy_representative_books_match_golden(book: str) -> None:
    scenario = dict(_REP_BOOK_SCENARIOS[book])
    caps = scenario.pop("caps", SizingCaps())
    prefs = {k: v for k, v in asdict(caps).items()}
    resolution = resolve_risk_policy(prefs, effective_at=_TS)
    result = size_portfolio(**scenario, caps=resolution.sizing_caps)
    assert_book_matches_golden(
        sizing_result_snapshot(result), _GOLDEN["representative_books"][book]
    )


def test_covariance_snapshot_complete_matrix_is_symmetric_and_canonical_order() -> None:
    corr = pl.DataFrame({"a": ["A", "B"], "b": ["B", "A"], "corr": [0.9, 0.9]})
    snap = resolve_covariance_snapshot(
        tickers=["b", "a"],
        corr=corr,
        as_of_session=_AS_OF,
        resolved_at=_TS,
        observation_count=42,
    )
    assert snap.status is PolicyArtifactStatus.AVAILABLE
    assert snap.tickers == ("A", "B")
    assert snap.lookback_days == 63
    assert snap.estimator == "pearson_daily_return"
    assert snap.matrix[0][1] == pytest.approx(0.9)
    assert snap.matrix[1][0] == pytest.approx(0.9)
    assert snap.observation_count == 42


def test_covariance_snapshot_missing_frame_is_unavailable() -> None:
    snap = resolve_covariance_snapshot(
        tickers=["A", "B"],
        corr=None,
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    assert snap.status is PolicyArtifactStatus.UNAVAILABLE
    assert snap.unavailable_reason == "missing_correlation_frame"


def test_covariance_snapshot_incomplete_pairs_is_unavailable_not_repaired() -> None:
    """Incomplete Pearson frames fail closed — no silent identity labeled degraded (#2803)."""
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]})
    snap = resolve_covariance_snapshot(
        tickers=["A", "B", "C"],
        corr=corr,
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    assert snap.status is PolicyArtifactStatus.UNAVAILABLE
    assert snap.unavailable_reason == "incomplete_pairs:A/C,B/C"
    # Placeholder identity only — observed A/B=0.9 must not be claimed as matrix content.
    assert snap.matrix == (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )


def test_incomplete_pair_reasons_do_not_collide_on_snapshot_id() -> None:
    """Distinct incomplete patterns must not share content_hash / snapshot_id (#2803)."""
    snap_ab = resolve_covariance_snapshot(
        tickers=["A", "B", "C"],
        corr=pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.9]}),
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    snap_ac = resolve_covariance_snapshot(
        tickers=["A", "B", "C"],
        corr=pl.DataFrame({"a": ["A"], "b": ["C"], "corr": [0.1]}),
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    assert snap_ab.status is PolicyArtifactStatus.UNAVAILABLE
    assert snap_ac.status is PolicyArtifactStatus.UNAVAILABLE
    assert snap_ab.unavailable_reason != snap_ac.unavailable_reason
    assert snap_ab.content_hash != snap_ac.content_hash
    assert snap_ab.snapshot_id != snap_ac.snapshot_id


def test_covariance_snapshot_hash_is_deterministic() -> None:
    corr = pl.DataFrame({"a": ["A"], "b": ["B"], "corr": [0.75]})
    first = resolve_covariance_snapshot(
        tickers=["A", "B"],
        corr=corr,
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    second = resolve_covariance_snapshot(
        tickers=["A", "B"],
        corr=corr,
        as_of_session=_AS_OF,
        resolved_at=_TS,
    )
    assert first.content_hash == second.content_hash
    assert first.snapshot_id == second.snapshot_id


def test_invalid_policy_hash_rejected() -> None:
    policy = resolve_risk_policy(effective_at=_TS).policy
    with pytest.raises(ValidationError, match="content_hash"):
        type(policy).model_validate({**policy.model_dump(), "content_hash": "deadbeef" * 8})


def test_memo_and_effective_inputs_unchanged_under_resolver() -> None:
    from datetime import date as date_cls

    from digiquant.portfolio.models.pm_direction import PMDirectionMemo, TickerDirection

    memo = PMDirectionMemo(
        date=date_cls(2026, 6, 12),
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

    conv2, stances2 = _effective_inputs(
        ["AAA", "BBB", "CCC"],
        {
            "AAA": {"conviction_score": 5, "stance": "buy"},
            "BBB": {"conviction_score": 3, "stance": "hold"},
        },
        {"AAA": {"conviction_delta": 1.0}, "BBB": {"conviction_delta": -0.5}},
        2.0,
    )
    expected2 = _GOLDEN["effective_inputs"]["analyst_debate_blend"]
    assert {k: round(v, 4) for k, v in conv2.items()} == expected2["convictions"]
    assert stances2 == expected2["stances"]

    # Resolver presence must not alter helper semantics.
    _ = resolve_risk_policy(effective_at=_TS).policy.content_hash
    assert (
        risk_policy_content_hash(payload={"probe": 1})
        != resolve_risk_policy(effective_at=_TS).policy.content_hash
    )
