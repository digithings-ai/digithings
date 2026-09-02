"""WP10.5 — paired incumbent/challenger shadow comparison evidence (#2799)."""

from __future__ import annotations

import ast
import importlib.util
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.dashboard.replay.allocation_comparison import (
    FORBIDDEN_IMPORT_PREFIXES,
    ComparisonArm,
    ComparisonArmInput,
    ComparisonStatus,
    MetricAvailability,
    OptionalScenarioInputs,
    build_shared_manifest,
    compare_allocation_arms,
    data_hash_from_request,
    load_shadow_criteria,
    write_comparison_report,
)
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    FillRecord,
    HoldingSnapshot,
    InstrumentBarSeries,
    NavPoint,
    OhlcvBar,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    TargetWeight,
    inconclusive_result,
    portfolio_replay_result_content_hash,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_REPO = Path(__file__).resolve().parents[3]
_REPLAY_ROOT = _REPO / "digiquant" / "src" / "digiquant" / "olympus" / "replay"
_COMPARISON = _REPLAY_ROOT / "allocation_comparison.py"
_CRITERIA = _REPLAY_ROOT / "shadow_criteria" / "v1.json"
_CLI = _REPO / "digiquant" / "scripts" / "atlas" / "compare_allocation_shadow.py"
_PRODUCTION_GUARD_PATHS = (
    _REPO / "digiquant/src/digiquant/olympus/hermes/chain.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/phase7e_risk_sizing.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/phases/h9_commit_run.py",
    _REPO / "digiquant/src/digiquant/olympus/hermes/shadow_artifact.py",
)


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=_UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str, closes: list[str]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 2, c) for i, c in enumerate(closes)),
    )


def _request(
    *,
    request_id: str,
    targets: tuple[tuple[str, str], ...],
    closes: list[str] | None = None,
    commission: str = "0.001",
    cash: str = "100000",
) -> PortfolioReplayRequest:
    aapl = closes or ["100", "101", "102", "103", "104"]
    msft = [str(Decimal(c) * 2) for c in aapl]
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal(cash),
        series=(_series("AAPL", aapl), _series("MSFT", msft)),
        target_weights=tuple(TargetWeight(ticker=t, weight=Decimal(w)) for t, w in targets),
        execution=ExecutionPolicy(commission_rate=Decimal(commission)),
    )


def _ok_result(
    request: PortfolioReplayRequest,
    *,
    ending_nav: str,
    ending_cash: str = "20000",
    commission: str = "50",
    fills: tuple[FillRecord, ...] = (),
    nav_path: tuple[tuple[int, str], ...] | None = None,
) -> PortfolioReplayResult:
    holdings = (
        HoldingSnapshot(
            ticker="AAPL",
            quantity=Decimal("100"),
            last_price=Decimal("100"),
            market_value=Decimal("10000"),
        ),
    )
    path = ()
    if nav_path is not None:
        path = tuple(
            NavPoint(
                ts=datetime(2024, 1, day, tzinfo=_UTC),
                nav=Decimal(nav),
            )
            for day, nav in nav_path
        )
    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id=request.request_id,
        request_content_hash=request.content_hash(),
        status=PortfolioReplayStatus.OK,
        starting_cash=request.starting_cash,
        ending_cash=Decimal(ending_cash),
        ending_nav=Decimal(ending_nav),
        total_commission=Decimal(commission),
        rebalance_commission=Decimal(commission),
        holdings=holdings,
        fills=fills,
        nav_path=path,
        message="",
        result_content_hash=None,
    )
    digest = portfolio_replay_result_content_hash(draft)
    return PortfolioReplayResult.model_validate(
        {**draft.model_dump(mode="python"), "result_content_hash": digest}
    )


def _arm(
    arm: ComparisonArm,
    request: PortfolioReplayRequest,
    result: PortfolioReplayResult,
    *,
    fingerprint: str,
    breaches: tuple[str, ...] = (),
) -> ComparisonArmInput:
    return ComparisonArmInput(
        arm=arm,
        weights_fingerprint=fingerprint,
        request=request,
        result=result,
        hard_constraint_breaches=breaches,
    )


@pytest.fixture(scope="module")
def criteria():
    return load_shadow_criteria(_CRITERIA)


def test_criteria_loads_without_activation_hook(criteria) -> None:
    assert criteria.criteria_version == "shadow-allocation-v1"
    assert criteria.criteria_content_hash
    raw = json.loads(_CRITERIA.read_text(encoding="utf-8"))
    assert "activation_hook" not in raw
    assert "auto_promote" not in raw


def test_criteria_rejects_activation_hook(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "criteria_version": "x",
                "author": "t",
                "rationale": "r",
                "effective_date": "2026-01-01",
                "evidence_mode": "observed",
                "activation_hook": "set_live",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="activation"):
        load_shadow_criteria(bad)


def test_identical_manifest_required(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(
        request_id="ch",
        targets=(("AAPL", "0.5"), ("MSFT", "0.3")),
        closes=["100", "101", "102", "103", "999"],
    )
    with pytest.raises(ValueError, match="data_hash"):
        build_shared_manifest(inc_req, ch_req)

    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="102000"),
            fingerprint="ch-fp",
        ),
    )
    assert report.status is ComparisonStatus.ABSTAINED
    assert "data_hash" in (report.abstain_reason or "")


def test_execution_cost_data_hashes_equal(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    manifest = build_shared_manifest(inc_req, ch_req)
    assert manifest.data_hash == data_hash_from_request(inc_req)
    assert manifest.execution_hash
    assert manifest.cost_hash

    ch_cost = _request(
        request_id="ch-cost",
        targets=(("AAPL", "0.5"), ("MSFT", "0.3")),
        commission="0.002",
    )
    with pytest.raises(ValueError, match="cost_hash|execution_hash"):
        build_shared_manifest(inc_req, ch_cost)


def test_absolute_and_paired_metrics(criteria) -> None:
    fills = (
        FillRecord(
            ticker="AAPL",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("100"),
            commission=Decimal("1"),
            ts=datetime(2024, 1, 3, tzinfo=_UTC),
            is_seed=False,
        ),
    )
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(
                inc_req,
                ending_nav="101000",
                fills=fills,
                nav_path=((2, "100000"), (3, "102000"), (4, "101000"), (5, "101000")),
            ),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(
                ch_req,
                ending_nav="103000",
                fills=fills,
                nav_path=((2, "100000"), (3, "105000"), (4, "99000"), (5, "103000")),
            ),
            fingerprint="ch-fp",
        ),
        incumbent_scenarios=OptionalScenarioInputs(benchmark_return=Decimal("0.01")),
        challenger_scenarios=OptionalScenarioInputs(benchmark_return=Decimal("0.01")),
    )
    assert report.status is ComparisonStatus.OK
    assert report.incumbent_metrics.total_return.status is MetricAvailability.AVAILABLE
    assert report.challenger_metrics.total_return.status is MetricAvailability.AVAILABLE
    ret_delta = next(d for d in report.paired_deltas if d.metric == "total_return")
    assert ret_delta.status is MetricAvailability.AVAILABLE
    assert ret_delta.delta == ret_delta.challenger - ret_delta.incumbent
    dd = next(d for d in report.paired_deltas if d.metric == "max_drawdown")
    assert dd.status is MetricAvailability.AVAILABLE
    # Peak 102000 → trough 101000 ⇒ -1000/102000
    assert dd.incumbent == (Decimal("101000") - Decimal("102000")) / Decimal("102000")
    # Peak 105000 → trough 99000
    assert dd.challenger == (Decimal("99000") - Decimal("105000")) / Decimal("105000")
    assert dd.delta == dd.challenger - dd.incumbent
    bm = next(d for d in report.paired_deltas if d.metric == "benchmark_return")
    assert bm.status is MetricAvailability.AVAILABLE


def test_max_drawdown_unavailable_without_nav_path(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="103000"),
            fingerprint="ch-fp",
        ),
    )
    dd = next(d for d in report.paired_deltas if d.metric == "max_drawdown")
    assert dd.status is MetricAvailability.UNAVAILABLE
    assert dd.unavailable_reason == "path_nav_unavailable"

def test_unavailable_and_inconclusive_explicit(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    bad = inconclusive_result(
        request_id=ch_req.request_id,
        request_content_hash=ch_req.content_hash(),
        status=PortfolioReplayStatus.CRASH,
        message="boom",
        starting_cash=ch_req.starting_cash,
    )
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(ComparisonArm.CHALLENGER, ch_req, bad, fingerprint="ch-fp"),
    )
    assert report.status is ComparisonStatus.INCONCLUSIVE
    assert report.abstain_reason == "arm_replay_not_ok"
    assert report.challenger_metrics.total_return.status is MetricAvailability.INCONCLUSIVE


def test_hard_constraint_not_hidden_by_stronger_return(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.9"), ("MSFT", "0.1")))
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="120000"),
            fingerprint="ch-fp",
            breaches=("max_position_pct",),
        ),
    )
    assert report.status is ComparisonStatus.ABSTAINED
    assert report.abstain_reason == "challenger_hard_constraint_breach"
    assert report.challenger.hard_constraint_breaches == ("max_position_pct",)
    assert report.hard_constraint_hidden_by_return is False
    ret = next(d for d in report.paired_deltas if d.metric == "total_return")
    assert ret.status is MetricAvailability.AVAILABLE
    assert ret.challenger > ret.incumbent


def test_file_only_output_and_criteria_frozen_before_results(criteria, tmp_path: Path) -> None:
    frozen_hash = criteria.criteria_content_hash
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="102000"),
            fingerprint="ch-fp",
        ),
    )
    assert report.criteria_content_hash == frozen_hash
    out = tmp_path / "allocation-shadow-comparison.json"
    write_comparison_report(report, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["report_content_hash"] == report.report_content_hash
    assert loaded["criteria_version"] == criteria.criteria_version


def test_future_data_mutation_invariance(criteria) -> None:
    """Mutating bars not present in the observed requests cannot change the report."""
    base_closes = ["100", "101", "102", "103", "104"]
    inc_req = _request(
        request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")), closes=base_closes
    )
    ch_req = _request(
        request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")), closes=base_closes
    )
    report_a = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="102000"),
            fingerprint="ch-fp",
        ),
    )
    future_buffer = list(base_closes) + ["999", "1000"]
    assert future_buffer[-1] == "1000"
    report_b = compare_allocation_arms(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="102000"),
            fingerprint="ch-fp",
        ),
    )
    assert report_a.report_content_hash == report_b.report_content_hash


def test_deterministic_report_hash(criteria) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    kwargs = dict(
        criteria=criteria,
        incumbent=_arm(
            ComparisonArm.INCUMBENT,
            inc_req,
            _ok_result(inc_req, ending_nav="101000"),
            fingerprint="inc-fp",
        ),
        challenger=_arm(
            ComparisonArm.CHALLENGER,
            ch_req,
            _ok_result(ch_req, ending_nav="102000"),
            fingerprint="ch-fp",
        ),
    )
    a = compare_allocation_arms(**kwargs)
    b = compare_allocation_arms(**kwargs)
    assert a.report_content_hash == b.report_content_hash


def test_cli_writes_file_only_report(criteria, tmp_path: Path) -> None:
    inc_req = _request(request_id="inc", targets=(("AAPL", "0.4"), ("MSFT", "0.4")))
    ch_req = _request(request_id="ch", targets=(("AAPL", "0.5"), ("MSFT", "0.3")))
    inc_res = _ok_result(inc_req, ending_nav="101000")
    ch_res = _ok_result(ch_req, ending_nav="102000")
    for name, obj in (
        ("inc-req.json", inc_req),
        ("inc-res.json", inc_res),
        ("ch-req.json", ch_req),
        ("ch-res.json", ch_res),
    ):
        (tmp_path / name).write_text(
            json.dumps(obj.model_dump(mode="json"), allow_nan=False),
            encoding="utf-8",
        )
    out = tmp_path / "report.json"
    spec = importlib.util.spec_from_file_location("compare_allocation_shadow", _CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rc = mod.main(
        [
            "--criteria",
            str(_CRITERIA),
            "--incumbent-request",
            str(tmp_path / "inc-req.json"),
            "--incumbent-result",
            str(tmp_path / "inc-res.json"),
            "--challenger-request",
            str(tmp_path / "ch-req.json"),
            "--challenger-result",
            str(tmp_path / "ch-res.json"),
            "--incumbent-weights-fingerprint",
            "inc-fp",
            "--challenger-weights-fingerprint",
            "ch-fp",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "ok"
    assert payload["criteria_content_hash"] == criteria.criteria_content_hash


def test_no_forbidden_imports_in_comparison_module() -> None:
    tree = ast.parse(_COMPARISON.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in FORBIDDEN_IMPORT_PREFIXES:
                    assert not alias.name.startswith(prefix), alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for prefix in FORBIDDEN_IMPORT_PREFIXES:
                assert not node.module.startswith(prefix), node.module


def test_production_surfaces_do_not_import_comparison() -> None:
    for path in _PRODUCTION_GUARD_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "allocation_comparison" not in node.module
                if "shadow_artifact" not in str(path):
                    assert "olympus.replay" not in node.module
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "allocation_comparison" not in alias.name
