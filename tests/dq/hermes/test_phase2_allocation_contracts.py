"""Integration Task 2.1 — lock Phase 2 allocation contracts (#2820).

End-to-end composition gate across WP8–WP10: calibrated H8 path, PreTradeRiskReport
bind/persist identity, shadow isolation + challenger comparison. Challenger stays
disabled in production; graph topology unchanged.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import date
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import pytest
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    PhaseHermesState,
)
from digiquant.olympus.hermes.allocation_contracts import PreTradeRiskReport
from digiquant.olympus.hermes.allocation_hashes import weights_fingerprint
from digiquant.olympus.hermes.graph import (
    HermesGraphDeps,
    ThesisGraphDeps,
    build_hermes_graph,
    build_hermes_phases_thesis,
)
from digiquant.olympus.hermes.models.pm_direction import PMDirectionMemo, TickerDirection
from digiquant.olympus.hermes.phases import phase7e_risk_sizing
from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps
from digiquant.olympus.hermes.risk_policy import INCUMBENT_CONTROL_ORDER
from digiquant.olympus.hermes.shadow_optimizer import ShadowOptimizerStatus, book_to_weight_map
from digiquant.olympus.hermes.writers.commit_io import (
    PreTradeRiskMode,
    validate_pretrade_risk_report,
)
from digiquant.olympus.replay.allocation_comparison import ComparisonStatus
from digiquant.olympus.replay.models import PortfolioReplayStatus
from digiquant.olympus.replay.worker import run_portfolio_replay_isolated

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.hermes.phase2_e2e_fixtures import (
    FORBIDDEN_PHASE2_NODES,
    HERMES_COMPILED_NODES,
    PHASE2_RUN_ID,
    PRODUCTION_GUARD_PATHS,
    load_isolation_checker,
    phase2_comparison_report,
    phase2_replay_request,
    phase2_shadow_artifact,
    production_imports_challenger,
    run_phase2_composition,
)

pytestmark = pytest.mark.unit


def _graph_node_names(graph) -> set[str]:
    return set(graph.get_graph().nodes.keys())


def _final_weights(book: dict[str, Any]) -> dict[str, float]:
    return {
        str(row["ticker"]): float(row["target_pct"])
        for row in book.get("recommended_portfolio") or []
        if float(row.get("target_pct") or 0) > 0
        and str(row.get("ticker", "")).strip().upper() != "CASH"
    }


def _run_calibrated_h8(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """H8 calibrated cutover with PreTradeRiskReport attach (WP8.4 + WP9.3)."""
    from digiquant.olympus.hermes.h8_risk_snapshots import H8RiskArtifacts
    from digiquant.olympus.hermes.phases.phase7e_risk_sizing import build_risk_sizing_node

    from tests.dq.hermes.test_allocation_inputs import _covariance, _risk_policy
    from tests.dq.hermes.test_calibrated_sizing import _bundle

    tickers = ("AAPL", "MSFT")
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
        memo="phase2-lock",
    )
    prefs = {
        "max_single_etf_pct": 100,
        "max_sector_pct": 100,
        "target_portfolio_vol": 1.0e6,
        "weight_increment_pct": 0,
        "h8_sizing_input_mode": "calibrated",
    }
    state = AtlasResearchState(
        run_type="delta",
        run_date=run_date,
        baseline_date=date(2026, 6, 9),
        config=AtlasConfigBundle(preferences=prefs),
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
    assert report_raw is not None
    report = PreTradeRiskReport.model_validate(report_raw)
    return {"book": book, "report": report, "bundle": bundle, "hermes": hermes}


# --------------------------------------------------------------------------- topology / ownership


def test_hermes_graph_topology_unchanged_by_phase2() -> None:
    client = FakeSupabaseClient()
    deps = HermesGraphDeps(
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client),
    )
    graph = build_hermes_graph(watchlist=["AAPL"], deps=deps)
    nodes = _graph_node_names(graph)
    assert FORBIDDEN_PHASE2_NODES.isdisjoint(nodes)
    assert HERMES_COMPILED_NODES.issubset(nodes)
    phase_names = {p.name for p in build_hermes_phases_thesis(watchlist=["AAPL"], held=set())}
    for expected in (
        "hermes_h7_pm_direction",
        "hermes_h8_risk_sizing",
        "hermes_h9_commit_run",
    ):
        assert expected in phase_names


def test_h7_owns_eligibility_h5_stance_cannot_reverse() -> None:
    """H7 long roster → buy stances; H5 sell cannot reverse authorization."""
    roster = [
        TickerDirection(ticker="AAA", direction="long", conviction_rank=1),
        TickerDirection(ticker="BBB", direction="long", conviction_rank=2),
        TickerDirection(ticker="CCC", direction="long", conviction_rank=3),
    ]
    memo = PMDirectionMemo(date=date(2026, 8, 26), roster=roster, memo="m")
    analysts = {
        "AAA": {"stance": "buy"},
        "BBB": {"stance": "hold"},
        "CCC": {"stance": "sell"},
    }
    _conv, stances = phase7e_risk_sizing._memo_effective_inputs(memo, analysts, 2.0)
    assert stances == {"AAA": "buy", "BBB": "buy", "CCC": "buy"}


def test_rank_gap_does_not_change_calibrated_magnitude() -> None:
    returns = {"AAPL": ("0.06", "0.03", "0.9"), "MSFT": ("0.03", "0.03", "0.9")}
    from tests.dq.hermes.test_allocation_invariants import _bundle, _calibrated_size, _targets

    dense = _bundle(returns=returns, ranks={"AAPL": 1, "MSFT": 2})
    gapped = _bundle(returns=returns, ranks={"AAPL": 1, "MSFT": 99})
    a = phase7e_risk_sizing.calibrated_scores_from_bundle(dense, long_tickers=["AAPL", "MSFT"])
    b = phase7e_risk_sizing.calibrated_scores_from_bundle(gapped, long_tickers=["AAPL", "MSFT"])
    assert a == b
    assert _targets(_calibrated_size(a)) == _targets(
        _calibrated_size(b, convictions={"AAPL": 5.0, "MSFT": 1.0})
    )


def test_incumbent_control_order_preserved() -> None:
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
    from digiquant.olympus.hermes import sizing as sizing_mod

    src = inspect.getsource(sizing_mod.size_portfolio)
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
    assert positions == sorted(positions)


# --------------------------------------------------------------------------- H8 → report → H9 identity


def test_calibrated_h8_report_binds_final_book(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run_calibrated_h8(monkeypatch)
    book = result["book"]
    report: PreTradeRiskReport = result["report"]
    final = _final_weights(book)
    assert book["h8_sizing_input_mode"] == "calibrated"
    assert book["allocation_input_bundle_hash"] == result["bundle"].bundle_content_hash
    assert report.final_book_weights_fingerprint == weights_fingerprint(final)
    assert book["pre_trade_risk_report_hash"] == report.report_content_hash
    assert report.allocation_input_bundle_hash == result["bundle"].bundle_content_hash


def test_h9_validates_hashes_never_recomputes_report() -> None:
    import digiquant.olympus.hermes.phases.h9_commit_run as h9
    import digiquant.olympus.hermes.writers.commit_io as commit_io

    for module in (h9, commit_io):
        src = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "build_pretrade_risk_report" not in src
        tree_imports = {
            node.module for node in ast.walk(ast.parse(src)) if getattr(node, "module", None)
        }
        assert not any(
            m == "digiquant.olympus.hermes.pretrade_risk"
            or (m or "").startswith("digiquant.olympus.hermes.pretrade_risk.")
            for m in tree_imports
        )

    artifact = phase2_shadow_artifact()
    final = {
        e.ticker: e.weight_pct for e in artifact.incumbent_final_weights.entries if e.weight_pct > 0
    }
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 26),
        phase_hermes=PhaseHermesState(
            sized_book={
                "recommended_portfolio": [{"ticker": t, "target_pct": w} for t, w in final.items()]
                + [
                    {
                        "ticker": "CASH",
                        "target_pct": artifact.incumbent_final_weights.cash_weight_pct,
                    }
                ],
                "pre_trade_risk_report_hash": artifact.pre_trade_risk_report.report_content_hash,
                "allocation_input_bundle_hash": artifact.allocation_input_bundle.bundle_content_hash,
            },
            pre_trade_risk_report=artifact.pre_trade_risk_report.model_dump(mode="json"),
            allocation_input_bundle=artifact.allocation_input_bundle.model_dump(mode="json"),
        ),
    )
    validation = validate_pretrade_risk_report(state, final, mode=PreTradeRiskMode.ENFORCE)
    assert validation.ok is True
    assert validation.report is not None
    assert (
        validation.report.report_content_hash == artifact.pre_trade_risk_report.report_content_hash
    )

    bad = validate_pretrade_risk_report(state, {"AAPL": 99.0}, mode=PreTradeRiskMode.ENFORCE)
    assert bad.ok is False
    assert bad.reason == "final_book_weights_fingerprint_mismatch"


# --------------------------------------------------------------------------- shadow / challenger / comparison


def test_phase2_full_fixture_byte_stable_artifacts() -> None:
    composed = run_phase2_composition()
    artifact = composed["artifact"]
    assert artifact.artifact_content_hash == composed["artifact_again"].artifact_content_hash
    assert len(artifact.artifact_content_hash) == 64
    assert artifact.run_id == PHASE2_RUN_ID
    assert (
        artifact.pre_trade_risk_report.allocation_input_bundle_hash
        == artifact.allocation_input_bundle.bundle_content_hash
    )
    assert (
        artifact.pre_trade_risk_report.final_book_weights_fingerprint
        == artifact.incumbent_final_weights.weights_fingerprint
    )

    from digiquant.olympus.hermes import shadow_artifact as sa

    sa._assert_no_forbidden_payload_keys(artifact.model_dump(mode="json"))

    challenger = composed["challenger"]
    assert challenger.status in (
        ShadowOptimizerStatus.IDENTITY,
        ShadowOptimizerStatus.IMPROVED,
        ShadowOptimizerStatus.ABSTAINED,
    )
    if challenger.challenger_weights is not None:
        weights = book_to_weight_map(challenger.challenger_weights)
        assert all(w >= 0 for w in weights.values())

    comparison = composed["comparison"]
    assert comparison.status is ComparisonStatus.OK
    assert comparison.report_content_hash
    criteria = composed["criteria"]
    assert criteria.criteria_content_hash == comparison.criteria_content_hash


def test_artifact_binds_report_to_final_book_under_rank_gap() -> None:
    dense = phase2_shadow_artifact(ranks={"AAPL": 1, "MSFT": 2})
    gapped = phase2_shadow_artifact(ranks={"AAPL": 1, "MSFT": 99})
    assert (
        dense.pre_trade_risk_report.final_book_weights_fingerprint
        == dense.incumbent_final_weights.weights_fingerprint
    )
    assert (
        gapped.pre_trade_risk_report.final_book_weights_fingerprint
        == gapped.incumbent_final_weights.weights_fingerprint
    )


def test_hard_constraint_breach_visible_even_when_return_stronger() -> None:
    _criteria, report = phase2_comparison_report(
        challenger_breaches=("max_position_pct",),
        challenger_nav="150000",
    )
    assert report.status is ComparisonStatus.ABSTAINED
    assert report.abstain_reason == "challenger_hard_constraint_breach"
    assert report.challenger.hard_constraint_breaches == ("max_position_pct",)
    ret = next(d for d in report.paired_deltas if d.metric == "total_return")
    assert ret.challenger > ret.incumbent


def test_production_surfaces_do_not_import_challenger() -> None:
    for path in PRODUCTION_GUARD_PATHS:
        hits = production_imports_challenger(path)
        assert hits == [], f"{path.name} imports challenger modules: {hits}"


def test_shadow_isolation_checks_pass() -> None:
    iso = load_isolation_checker()
    report = iso.run_isolation_checks(repo_root=iso.REPO_ROOT, artifact_paths=[])
    assert report.ok is True, [f.message for f in report.findings]


def test_replay_hard_failure_is_visible(tmp_path: pathlib.Path, monkeypatch) -> None:
    class _CrashProcess:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.exitcode: int | None = None

        def start(self) -> None:
            self.exitcode = -6

        def join(self, timeout: float | None = None) -> None:
            return None

        def is_alive(self) -> bool:
            return False

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

    monkeypatch.setattr(
        "digiquant.olympus.replay.worker._SPAWN_CTX.Process",
        _CrashProcess,
    )
    result = run_portfolio_replay_isolated(
        phase2_replay_request(request_id="phase2-crash"),
        timeout_s=5,
        work_dir=tmp_path,
    )
    assert result.status is PortfolioReplayStatus.CRASH
    assert result.ending_nav is None
    assert "SIGABRT" in result.message


def test_h9_validate_rejects_bundle_hash_mismatch() -> None:
    artifact = phase2_shadow_artifact()
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 26),
        phase_hermes=PhaseHermesState(
            sized_book={
                "recommended_portfolio": [
                    {"ticker": "AAPL", "target_pct": 25.0},
                    {"ticker": "MSFT", "target_pct": 25.0},
                    {"ticker": "CASH", "target_pct": 50.0},
                ],
                "pre_trade_risk_report_hash": artifact.pre_trade_risk_report.report_content_hash,
                "allocation_input_bundle_hash": "0" * 64,
            },
            pre_trade_risk_report=artifact.pre_trade_risk_report.model_dump(mode="json"),
            allocation_input_bundle=artifact.allocation_input_bundle.model_dump(mode="json"),
        ),
    )
    validation = validate_pretrade_risk_report(
        state, {"AAPL": 25.0, "MSFT": 25.0}, mode=PreTradeRiskMode.ENFORCE
    )
    assert validation.ok is False
    assert validation.reason == "allocation_input_bundle_hash_mismatch"
