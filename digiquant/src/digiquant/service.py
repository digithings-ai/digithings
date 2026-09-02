"""Shared entrypoints for HTTP, CLI, and MCP (single implementation path)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from digiquant.backtest import run_backtest
from digiquant.dashboard.replay.comparison import (
    PolicyComparisonReport as RichPolicyComparisonReport,
)
from digiquant.dashboard.replay.exposure import (
    PolicyComparisonSummary,
    PolicyGateEvaluationSummary,
    PolicyReplayFacade,
    PolicyReplayRunSummary,
)
from digiquant.dashboard.replay.governance import (
    AuthenticatedPrincipal,
    HumanAuthoredGateCriteria,
)
from digiquant.dashboard.replay.governance_models import (
    GovernanceDecisionKind,
    PolicyGovernanceDecision,
)
from digiquant.dashboard.replay.store import PolicyReplayStore
from digiquant.export import run_export
from digiquant.models import BacktestResult, ExportResult, OptimizationConstraints, OptimizeResult
from digiquant.optimize import run_optimize
from digiquant.paths import validate_data_paths
from digiquant.strategies.registry import list_strategies

_policy_replay_facade: PolicyReplayFacade | None = None


def get_policy_replay_store() -> PolicyReplayStore:
    """Return the process-local policy replay store."""
    return get_policy_replay_facade().store


def get_policy_replay_facade() -> PolicyReplayFacade:
    """Return (and lazily create) the process-local policy replay facade."""
    global _policy_replay_facade
    if _policy_replay_facade is None:
        _policy_replay_facade = PolicyReplayFacade()
    return _policy_replay_facade


def set_policy_replay_store(store: PolicyReplayStore | None) -> None:
    """Replace or clear the process-local store (tests / CLI isolation)."""
    global _policy_replay_facade
    if store is None:
        _policy_replay_facade = None
        return
    _policy_replay_facade = PolicyReplayFacade(store)


def service_run_backtest(
    *,
    strategy_name: str,
    symbols: list[str],
    data_path: str | None,
    data_dir: str | None,
    strategy_params: dict[str, float | int | str] | None = None,
    tearsheet_path: str | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult:
    validate_data_paths(data_path=data_path, data_dir=data_dir)
    return run_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        strategy_params=strategy_params,
        tearsheet_path=tearsheet_path,
        full_tearsheet=full_tearsheet,
    )


def service_run_optimize(
    *,
    strategy_name: str,
    symbols: list[str],
    data_path: str | None,
    data_dir: str | None,
    param_grid: list[dict[str, float | int | str]] | None = None,
    method: str = "grid",
    n_trials: int = 50,
    objective: str = "sharpe",
    constraints: OptimizationConstraints | None = None,
    base_params: dict[str, float | int | str] | None = None,
) -> OptimizeResult:
    validate_data_paths(data_path=data_path, data_dir=data_dir)
    return run_optimize(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        param_grid=param_grid,
        method=method,
        n_trials=n_trials,
        objective=objective,
        constraints=constraints,
        base_params=base_params,
    )


def service_run_export(
    *,
    strategy_name: str,
    params: dict[str, float | int | str] | None,
    target: str,
    output_dir: str | None = None,
) -> ExportResult:
    return run_export(
        strategy_name=strategy_name,
        params=params,
        target=target,
        output_dir=output_dir,
    )


def service_list_strategies() -> list[dict]:
    return list_strategies()


def service_run_policy_replay(
    *,
    pair_content_hash: str,
    run_id: str | None = None,
    recorded_at: datetime | None = None,
) -> PolicyReplayRunSummary:
    """Register a policy replay run (recommendation/read only — no activation)."""
    return get_policy_replay_facade().run_policy_replay(
        pair_content_hash=pair_content_hash,
        run_id=run_id,
        recorded_at=recorded_at,
    )


def service_get_policy_replay(run_id: str) -> PolicyReplayRunSummary:
    """Fetch a replay-run summary by id (fail closed if unknown)."""
    return get_policy_replay_facade().get_policy_replay(run_id)


def service_get_policy_comparison(comparison_id: str | UUID) -> PolicyComparisonSummary:
    """Fetch a comparison summary (IDs/status only — no confidential evidence)."""
    return get_policy_replay_facade().get_policy_comparison(comparison_id)


def service_evaluate_policy_gate(
    *,
    comparison_id: str | UUID,
    criteria_version_id: str | UUID,
    recorded_at: datetime | None = None,
) -> PolicyGateEvaluationSummary:
    """Evaluate immutable gate criteria (eligibility only — never activates)."""
    return get_policy_replay_facade().evaluate_policy_gate(
        comparison_id=comparison_id,
        criteria_version_id=criteria_version_id,
        recorded_at=recorded_at,
    )


def service_get_policy_gate_evaluation(
    evaluation_id: str | UUID,
) -> PolicyGateEvaluationSummary:
    """Fetch a gate-evaluation summary by id (fail closed if unknown)."""
    return get_policy_replay_facade().get_policy_gate_evaluation(evaluation_id)


def service_ingest_policy_comparison(
    report: RichPolicyComparisonReport,
) -> PolicyComparisonSummary:
    """CLI/test helper: persist comparison envelope + cache rich report."""
    return get_policy_replay_facade().ingest_comparison(report)


def service_ingest_gate_criteria(criteria: HumanAuthoredGateCriteria) -> UUID:
    """CLI/test helper: persist criteria version + cache rich package."""
    return get_policy_replay_facade().ingest_criteria(criteria)


def service_record_policy_governance_decision(
    *,
    principal: AuthenticatedPrincipal,
    evaluation_id: str | UUID,
    decision_kind: GovernanceDecisionKind | str,
    rationale: str,
    recorded_at: datetime | None = None,
    current_policy_version_id: str | None = None,
    supersedes_decision_id: str | UUID | None = None,
) -> PolicyGovernanceDecision:
    """Authenticated decision write — DigiAuth principal only (not MCP)."""
    return get_policy_replay_facade().record_decision(
        principal=principal,
        evaluation_id=evaluation_id,
        decision_kind=decision_kind,
        rationale=rationale,
        recorded_at=recorded_at,
        current_policy_version_id=current_policy_version_id,
        supersedes_decision_id=supersedes_decision_id,
    )
