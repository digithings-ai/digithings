"""WP10.5 — paired incumbent/challenger shadow comparison evidence (#2799).

Compares two isolated WP10.4 shared-cash replay arms under an identical observed
manifest. Evidence only — never production H8/H9 booking, auto-promotion, or
config write. Challenger remains unreachable from the production graph.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.dashboard.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_request,
    execution_policy_hash,
)
from digiquant.dashboard.replay.models import (
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    TargetWeight,
    max_drawdown_from_nav_path,
)
from digiquant.portfolio.allocation_hashes import sha256_hex

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
FiniteDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
FiniteNonNegDec: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]

# Static import fence — AST tests + isolation checker assert these never appear.
FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "digiquant.brokers",
        "digiquant.portfolio.writers",
        "digiquant.portfolio.phases.h9_commit_run",
        "digiquant.portfolio.phases.phase7e_risk_sizing",
        "digiquant.research.supabase_io",
        "digiquant.nautilus_runner",
        "supabase",
        "httpx",
        "requests",
    }
)

# Criteria must never declare production activation.
_FORBIDDEN_CRITERIA_KEYS: frozenset[str] = frozenset(
    {
        "activation_hook",
        "activate",
        "auto_promote",
        "auto_promotion",
        "production_config_write",
        "set_live",
        "promote_to_production",
        "h8_booking",
        "h9_commit",
    }
)

_CRITERIA_PACKAGE = Path(__file__).resolve().parent / "shadow_criteria"
DEFAULT_CRITERIA_PATH = _CRITERIA_PACKAGE / "v1.json"

_MONEY = Decimal("0.00000001")


class ComparisonContractModel(BaseModel):
    """Strict immutable base for shadow comparison contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ComparisonArm(StrEnum):
    """Paired policy arm label."""

    INCUMBENT = "incumbent"
    CHALLENGER = "challenger"


class ComparisonStatus(StrEnum):
    """Typed outcome of one paired comparison."""

    OK = "ok"
    ABSTAINED = "abstained"
    INCONCLUSIVE = "inconclusive"


class MetricAvailability(StrEnum):
    """Availability of one absolute or paired metric leaf."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCONCLUSIVE = "inconclusive"


class SharedReplayManifest(ComparisonContractModel):
    """Hashes that must be identical across paired arms."""

    data_hash: NonEmptyId
    cost_hash: NonEmptyId
    execution_hash: NonEmptyId
    starting_cash: FiniteNonNegDec
    artifact_content_hash: NonEmptyId | None = None
    covariance_hash: NonEmptyId | None = None
    policy_hash: NonEmptyId | None = None

    def content_hash(self) -> str:
        return sha256_hex(self.model_dump(mode="json"))


class ArmIdentity(ComparisonContractModel):
    """Arm label plus book/replay identity for the report."""

    arm: ComparisonArm
    weights_fingerprint: NonEmptyId
    request_content_hash: NonEmptyId
    result_content_hash: NonEmptyId | None = None
    replay_status: PortfolioReplayStatus
    hard_constraint_breaches: tuple[NonEmptyId, ...] = ()

    @field_validator("hard_constraint_breaches", mode="before")
    @classmethod
    def _coerce_breaches(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class ScalarEvidence(ComparisonContractModel):
    """One numeric leaf with explicit availability."""

    status: MetricAvailability
    value: FiniteDec | None = None
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_leaf(self) -> ScalarEvidence:
        if self.status is MetricAvailability.AVAILABLE:
            if self.value is None:
                raise ValueError("available metric requires value")
            if self.unavailable_reason is not None:
                raise ValueError("available metric cannot carry unavailable_reason")
        else:
            if self.value is not None:
                raise ValueError("non-available metric cannot carry value")
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("non-available metric requires unavailable_reason")
        return self


class AbsoluteArmMetrics(ComparisonContractModel):
    """Absolute portfolio metrics for one arm."""

    total_return: ScalarEvidence
    ending_nav: ScalarEvidence
    total_commission: ScalarEvidence
    turnover: ScalarEvidence
    max_drawdown: ScalarEvidence
    benchmark_return: ScalarEvidence
    tail_loss: ScalarEvidence
    scenario_pnl: ScalarEvidence


class PairedMetricDelta(ComparisonContractModel):
    """Challenger minus incumbent for one named metric."""

    metric: NonEmptyId
    status: MetricAvailability
    incumbent: FiniteDec | None = None
    challenger: FiniteDec | None = None
    delta: FiniteDec | None = None
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_delta(self) -> PairedMetricDelta:
        if self.status is MetricAvailability.AVAILABLE:
            if self.incumbent is None or self.challenger is None or self.delta is None:
                raise ValueError("available paired metric requires incumbent/challenger/delta")
            if self.unavailable_reason is not None:
                raise ValueError("available paired metric cannot carry unavailable_reason")
            expected = self.challenger - self.incumbent
            if abs(expected - self.delta) > _MONEY:
                raise ValueError("delta must equal challenger - incumbent")
        else:
            if self.delta is not None:
                raise ValueError("non-available paired metric cannot carry delta")
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("non-available paired metric requires unavailable_reason")
        return self


class ShadowCriteria(ComparisonContractModel):
    """Versioned shadow evidence criteria — no production activation hook."""

    schema_version: str = "1.0"
    criteria_version: NonEmptyId
    author: NonEmptyId
    rationale: NonEmptyId
    effective_date: date
    evidence_mode: NonEmptyId
    require_identical_manifest: bool = True
    require_hard_constraints_visible: bool = True
    min_sample_periods: Annotated[int, Field(ge=1)] = 1
    notes: tuple[str, ...] = ()
    criteria_content_hash: NonEmptyId

    @field_validator("notes", mode="before")
    @classmethod
    def _coerce_notes(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_criteria(self) -> ShadowCriteria:
        expected = shadow_criteria_content_hash(self._hash_payload())
        if self.criteria_content_hash != expected:
            raise ValueError("criteria_content_hash must match canonical digest")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "criteria_version": self.criteria_version,
            "author": self.author,
            "rationale": self.rationale,
            "effective_date": self.effective_date.isoformat(),
            "evidence_mode": self.evidence_mode,
            "require_identical_manifest": self.require_identical_manifest,
            "require_hard_constraints_visible": self.require_hard_constraints_visible,
            "min_sample_periods": self.min_sample_periods,
            "notes": list(self.notes),
        }


class AllocationComparisonReport(ComparisonContractModel):
    """Immutable paired shadow comparison report (file-only evidence)."""

    schema_version: str = "1.0"
    status: ComparisonStatus
    abstain_reason: NonEmptyId | None = None
    criteria_version: NonEmptyId
    criteria_content_hash: NonEmptyId
    shared_manifest: SharedReplayManifest
    incumbent: ArmIdentity
    challenger: ArmIdentity
    incumbent_metrics: AbsoluteArmMetrics
    challenger_metrics: AbsoluteArmMetrics
    paired_deltas: tuple[PairedMetricDelta, ...]
    hard_constraint_hidden_by_return: bool = False
    report_content_hash: NonEmptyId

    @field_validator("paired_deltas", mode="before")
    @classmethod
    def _coerce_deltas(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_report(self) -> AllocationComparisonReport:
        if self.status is ComparisonStatus.OK:
            if self.abstain_reason is not None:
                raise ValueError("ok report cannot carry abstain_reason")
        else:
            if self.abstain_reason is None or not self.abstain_reason.strip():
                raise ValueError("non-ok report requires abstain_reason")
        expected = sha256_hex(self._hash_payload())
        if self.report_content_hash != expected:
            raise ValueError("report_content_hash must match canonical digest")
        return self

    def _hash_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "abstain_reason": self.abstain_reason,
            "criteria_version": self.criteria_version,
            "criteria_content_hash": self.criteria_content_hash,
            "shared_manifest": self.shared_manifest.model_dump(mode="json"),
            "incumbent": self.incumbent.model_dump(mode="json"),
            "challenger": self.challenger.model_dump(mode="json"),
            "incumbent_metrics": self.incumbent_metrics.model_dump(mode="json"),
            "challenger_metrics": self.challenger_metrics.model_dump(mode="json"),
            "paired_deltas": [d.model_dump(mode="json") for d in self.paired_deltas],
            "hard_constraint_hidden_by_return": self.hard_constraint_hidden_by_return,
        }


class ComparisonArmInput(ComparisonContractModel):
    """One paired arm: request + result + optional hard-constraint breaches."""

    arm: ComparisonArm
    weights_fingerprint: NonEmptyId
    request: PortfolioReplayRequest
    result: PortfolioReplayResult
    hard_constraint_breaches: tuple[NonEmptyId, ...] = ()

    @field_validator("hard_constraint_breaches", mode="before")
    @classmethod
    def _coerce_breaches(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_arm(self) -> ComparisonArmInput:
        if self.result.request_id != self.request.request_id:
            raise ValueError("result.request_id must match request.request_id")
        if self.result.request_content_hash != self.request.content_hash():
            raise ValueError("result.request_content_hash must match request digest")
        return self


class OptionalScenarioInputs(ComparisonContractModel):
    """Optional observed scenario/tail inputs (absent → typed unavailable)."""

    benchmark_return: FiniteDec | None = None
    tail_loss: FiniteDec | None = None
    scenario_pnl: FiniteDec | None = None


def shadow_criteria_content_hash(payload: dict[str, object]) -> str:
    """SHA-256 of criteria fields excluding the hash itself."""
    return sha256_hex(payload)


def load_shadow_criteria(path: Path | str | None = None) -> ShadowCriteria:
    """Load and validate a versioned criteria file (frozen before results).

    Rejects any production activation hook key. Hash is computed after load so
    the on-disk file may omit ``criteria_content_hash``; callers freeze the
    returned object before inspecting arm results.
    """
    criteria_path = Path(path) if path is not None else DEFAULT_CRITERIA_PATH
    raw = json.loads(criteria_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("criteria file must be a JSON object")
    _assert_no_activation_hooks(raw)
    payload = {
        "schema_version": str(raw.get("schema_version", "1.0")),
        "criteria_version": raw["criteria_version"],
        "author": raw["author"],
        "rationale": raw["rationale"],
        "effective_date": raw["effective_date"],
        "evidence_mode": raw["evidence_mode"],
        "require_identical_manifest": bool(raw.get("require_identical_manifest", True)),
        "require_hard_constraints_visible": bool(raw.get("require_hard_constraints_visible", True)),
        "min_sample_periods": int(raw.get("min_sample_periods", 1)),
        "notes": list(raw.get("notes") or ()),
    }
    digest = shadow_criteria_content_hash(payload)
    return ShadowCriteria.model_validate({**payload, "criteria_content_hash": digest})


def build_shared_manifest(
    incumbent: PortfolioReplayRequest,
    challenger: PortfolioReplayRequest,
    *,
    artifact_content_hash: str | None = None,
    covariance_hash: str | None = None,
    policy_hash: str | None = None,
) -> SharedReplayManifest:
    """Build a shared manifest or raise when arm identities diverge."""
    inc_data = data_hash_from_request(incumbent)
    ch_data = data_hash_from_request(challenger)
    if inc_data != ch_data:
        raise ValueError("paired arms require identical data_hash")

    inc_exec = execution_policy_hash(incumbent.execution)
    ch_exec = execution_policy_hash(challenger.execution)
    if inc_exec != ch_exec:
        raise ValueError("paired arms require identical execution_hash")

    inc_cost = cost_hash_from_execution(incumbent.execution)
    ch_cost = cost_hash_from_execution(challenger.execution)
    if inc_cost != ch_cost:
        raise ValueError("paired arms require identical cost_hash")

    if incumbent.starting_cash != challenger.starting_cash:
        raise ValueError("paired arms require identical starting_cash")

    # Target weights may differ (policy under test); everything else must match.
    if incumbent.series != challenger.series:
        raise ValueError("paired arms require identical bar series")
    if incumbent.initial_holdings != challenger.initial_holdings:
        raise ValueError("paired arms require identical initial_holdings")
    if incumbent.execution != challenger.execution:
        raise ValueError("paired arms require identical execution policy")

    return SharedReplayManifest(
        data_hash=inc_data,
        cost_hash=inc_cost,
        execution_hash=inc_exec,
        starting_cash=incumbent.starting_cash,
        artifact_content_hash=artifact_content_hash,
        covariance_hash=covariance_hash,
        policy_hash=policy_hash,
    )


def weights_pct_to_targets(risky_pct: dict[str, float]) -> tuple[TargetWeight, ...]:
    """Convert percent book weights to unit-interval target weights."""
    return tuple(
        TargetWeight(ticker=ticker, weight=Decimal(str(weight)) / Decimal("100"))
        for ticker, weight in sorted(risky_pct.items())
        if abs(weight) > 1e-12
    )


def compute_absolute_metrics(
    result: PortfolioReplayResult,
    *,
    scenarios: OptionalScenarioInputs | None = None,
) -> AbsoluteArmMetrics:
    """Derive absolute metrics from one replay result (typed unavailability)."""
    scenarios = scenarios or OptionalScenarioInputs()
    if result.status != PortfolioReplayStatus.OK:
        reason = f"replay_{result.status.value}"
        unavailable = ScalarEvidence(
            status=MetricAvailability.INCONCLUSIVE,
            unavailable_reason=reason,
        )
        return AbsoluteArmMetrics(
            total_return=unavailable,
            ending_nav=unavailable,
            total_commission=unavailable,
            turnover=unavailable,
            max_drawdown=ScalarEvidence(
                status=MetricAvailability.UNAVAILABLE,
                unavailable_reason="path_nav_unavailable",
            ),
            benchmark_return=_optional_scalar(scenarios.benchmark_return, "benchmark_not_provided"),
            tail_loss=_optional_scalar(scenarios.tail_loss, "tail_not_provided"),
            scenario_pnl=_optional_scalar(scenarios.scenario_pnl, "scenario_not_provided"),
        )

    assert result.ending_nav is not None
    assert result.total_commission is not None
    starting = result.starting_cash
    if starting == 0:
        total_return = ScalarEvidence(
            status=MetricAvailability.UNAVAILABLE,
            unavailable_reason="zero_starting_cash",
        )
    else:
        total_return = ScalarEvidence(
            status=MetricAvailability.AVAILABLE,
            value=(result.ending_nav - starting) / starting,
        )

    turnover_value = _turnover_from_fills(result)
    drawdown_value = max_drawdown_from_nav_path(result.nav_path)
    if drawdown_value is None:
        max_drawdown = ScalarEvidence(
            status=MetricAvailability.UNAVAILABLE,
            unavailable_reason="path_nav_unavailable",
        )
    else:
        max_drawdown = ScalarEvidence(
            status=MetricAvailability.AVAILABLE,
            value=drawdown_value,
        )
    return AbsoluteArmMetrics(
        total_return=total_return,
        ending_nav=ScalarEvidence(status=MetricAvailability.AVAILABLE, value=result.ending_nav),
        total_commission=ScalarEvidence(
            status=MetricAvailability.AVAILABLE,
            value=result.total_commission,
        ),
        turnover=ScalarEvidence(status=MetricAvailability.AVAILABLE, value=turnover_value),
        max_drawdown=max_drawdown,
        benchmark_return=_optional_scalar(scenarios.benchmark_return, "benchmark_not_provided"),
        tail_loss=_optional_scalar(scenarios.tail_loss, "tail_not_provided"),
        scenario_pnl=_optional_scalar(scenarios.scenario_pnl, "scenario_not_provided"),
    )


def compare_allocation_arms(
    *,
    criteria: ShadowCriteria,
    incumbent: ComparisonArmInput,
    challenger: ComparisonArmInput,
    artifact_content_hash: str | None = None,
    covariance_hash: str | None = None,
    policy_hash: str | None = None,
    incumbent_scenarios: OptionalScenarioInputs | None = None,
    challenger_scenarios: OptionalScenarioInputs | None = None,
) -> AllocationComparisonReport:
    """Produce a paired report or typed abstention/inconclusive outcome.

    Criteria must already be loaded (frozen) before arm results are inspected.
    Hard-constraint breaches on the challenger remain visible even when return
    is stronger — never hidden.
    """
    if incumbent.arm is not ComparisonArm.INCUMBENT:
        raise ValueError("incumbent input arm must be incumbent")
    if challenger.arm is not ComparisonArm.CHALLENGER:
        raise ValueError("challenger input arm must be challenger")

    try:
        manifest = build_shared_manifest(
            incumbent.request,
            challenger.request,
            artifact_content_hash=artifact_content_hash,
            covariance_hash=covariance_hash,
            policy_hash=policy_hash,
        )
    except ValueError as exc:
        return _abstained_manifest_mismatch(
            criteria=criteria,
            incumbent=incumbent,
            challenger=challenger,
            reason=str(exc),
        )

    inc_metrics = compute_absolute_metrics(incumbent.result, scenarios=incumbent_scenarios)
    ch_metrics = compute_absolute_metrics(challenger.result, scenarios=challenger_scenarios)
    paired = _build_paired_deltas(inc_metrics, ch_metrics)

    inc_id = _arm_identity(incumbent)
    ch_id = _arm_identity(challenger)

    if (
        incumbent.result.status != PortfolioReplayStatus.OK
        or challenger.result.status != PortfolioReplayStatus.OK
    ):
        return _finalize_report(
            status=ComparisonStatus.INCONCLUSIVE,
            abstain_reason="arm_replay_not_ok",
            criteria=criteria,
            manifest=manifest,
            incumbent=inc_id,
            challenger=ch_id,
            incumbent_metrics=inc_metrics,
            challenger_metrics=ch_metrics,
            paired_deltas=paired,
            hard_constraint_hidden_by_return=False,
        )

    ch_breaches = challenger.hard_constraint_breaches
    if ch_breaches and criteria.require_hard_constraints_visible:
        return _finalize_report(
            status=ComparisonStatus.ABSTAINED,
            abstain_reason="challenger_hard_constraint_breach",
            criteria=criteria,
            manifest=manifest,
            incumbent=inc_id,
            challenger=ch_id,
            incumbent_metrics=inc_metrics,
            challenger_metrics=ch_metrics,
            paired_deltas=paired,
            hard_constraint_hidden_by_return=False,
        )

    return _finalize_report(
        status=ComparisonStatus.OK,
        abstain_reason=None,
        criteria=criteria,
        manifest=manifest,
        incumbent=inc_id,
        challenger=ch_id,
        incumbent_metrics=inc_metrics,
        challenger_metrics=ch_metrics,
        paired_deltas=paired,
        hard_constraint_hidden_by_return=False,
    )


def write_comparison_report(
    report: AllocationComparisonReport,
    path: Path | str,
) -> Path:
    """Atomically write the immutable report as canonical JSON (file-only sink)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{out.name}.", suffix=".tmp", dir=out.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, out)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return out


def _assert_no_activation_hooks(raw: dict[str, object]) -> None:
    lowered = {str(key).lower() for key in raw}
    banned = lowered & _FORBIDDEN_CRITERIA_KEYS
    if banned:
        raise ValueError(
            f"criteria file must not contain production activation keys: {sorted(banned)}"
        )
    for key, value in raw.items():
        if str(key).lower() in _FORBIDDEN_CRITERIA_KEYS:
            raise ValueError(f"forbidden criteria key: {key}")
        if isinstance(value, dict):
            _assert_no_activation_hooks(value)  # type: ignore[arg-type]


def _optional_scalar(value: Decimal | None, missing_reason: str) -> ScalarEvidence:
    if value is None:
        return ScalarEvidence(
            status=MetricAvailability.UNAVAILABLE,
            unavailable_reason=missing_reason,
        )
    return ScalarEvidence(status=MetricAvailability.AVAILABLE, value=value)


def _turnover_from_fills(result: PortfolioReplayResult) -> Decimal:
    notional = Decimal("0")
    for fill in result.fills:
        if fill.is_seed:
            continue
        notional += fill.quantity * fill.price
    if result.starting_cash == 0:
        return Decimal("0")
    return notional / result.starting_cash


def _arm_identity(arm: ComparisonArmInput) -> ArmIdentity:
    return ArmIdentity(
        arm=arm.arm,
        weights_fingerprint=arm.weights_fingerprint,
        request_content_hash=arm.request.content_hash(),
        result_content_hash=arm.result.result_content_hash,
        replay_status=arm.result.status,
        hard_constraint_breaches=arm.hard_constraint_breaches,
    )


def _build_paired_deltas(
    incumbent: AbsoluteArmMetrics,
    challenger: AbsoluteArmMetrics,
) -> tuple[PairedMetricDelta, ...]:
    names = (
        "total_return",
        "ending_nav",
        "total_commission",
        "turnover",
        "max_drawdown",
        "benchmark_return",
        "tail_loss",
        "scenario_pnl",
    )
    deltas: list[PairedMetricDelta] = []
    for name in names:
        inc_leaf: ScalarEvidence = getattr(incumbent, name)
        ch_leaf: ScalarEvidence = getattr(challenger, name)
        if (
            inc_leaf.status is MetricAvailability.AVAILABLE
            and ch_leaf.status is MetricAvailability.AVAILABLE
            and inc_leaf.value is not None
            and ch_leaf.value is not None
        ):
            deltas.append(
                PairedMetricDelta(
                    metric=name,
                    status=MetricAvailability.AVAILABLE,
                    incumbent=inc_leaf.value,
                    challenger=ch_leaf.value,
                    delta=ch_leaf.value - inc_leaf.value,
                )
            )
            continue
        if (
            inc_leaf.status is MetricAvailability.INCONCLUSIVE
            or ch_leaf.status is MetricAvailability.INCONCLUSIVE
        ):
            reason = inc_leaf.unavailable_reason or ch_leaf.unavailable_reason or "arm_inconclusive"
            deltas.append(
                PairedMetricDelta(
                    metric=name,
                    status=MetricAvailability.INCONCLUSIVE,
                    incumbent=inc_leaf.value,
                    challenger=ch_leaf.value,
                    unavailable_reason=reason,
                )
            )
            continue
        reason = inc_leaf.unavailable_reason or ch_leaf.unavailable_reason or "metric_unavailable"
        deltas.append(
            PairedMetricDelta(
                metric=name,
                status=MetricAvailability.UNAVAILABLE,
                incumbent=inc_leaf.value,
                challenger=ch_leaf.value,
                unavailable_reason=reason,
            )
        )
    return tuple(deltas)


def _finalize_report(
    *,
    status: ComparisonStatus,
    abstain_reason: str | None,
    criteria: ShadowCriteria,
    manifest: SharedReplayManifest,
    incumbent: ArmIdentity,
    challenger: ArmIdentity,
    incumbent_metrics: AbsoluteArmMetrics,
    challenger_metrics: AbsoluteArmMetrics,
    paired_deltas: tuple[PairedMetricDelta, ...],
    hard_constraint_hidden_by_return: bool,
) -> AllocationComparisonReport:
    draft = AllocationComparisonReport.model_construct(
        schema_version="1.0",
        status=status,
        abstain_reason=abstain_reason,
        criteria_version=criteria.criteria_version,
        criteria_content_hash=criteria.criteria_content_hash,
        shared_manifest=manifest,
        incumbent=incumbent,
        challenger=challenger,
        incumbent_metrics=incumbent_metrics,
        challenger_metrics=challenger_metrics,
        paired_deltas=paired_deltas,
        hard_constraint_hidden_by_return=hard_constraint_hidden_by_return,
        report_content_hash="",
    )
    digest = sha256_hex(draft._hash_payload())
    return AllocationComparisonReport.model_validate(
        {
            **draft.model_dump(mode="python"),
            "report_content_hash": digest,
        }
    )


def _abstained_manifest_mismatch(
    *,
    criteria: ShadowCriteria,
    incumbent: ComparisonArmInput,
    challenger: ComparisonArmInput,
    reason: str,
) -> AllocationComparisonReport:
    """Typed abstention when arms do not share an identical observed manifest."""
    placeholder = SharedReplayManifest(
        data_hash=data_hash_from_request(incumbent.request),
        cost_hash=cost_hash_from_execution(incumbent.request.execution),
        execution_hash=execution_policy_hash(incumbent.request.execution),
        starting_cash=incumbent.request.starting_cash,
    )
    unavailable = ScalarEvidence(
        status=MetricAvailability.UNAVAILABLE,
        unavailable_reason="manifest_mismatch",
    )
    empty_metrics = AbsoluteArmMetrics(
        total_return=unavailable,
        ending_nav=unavailable,
        total_commission=unavailable,
        turnover=unavailable,
        max_drawdown=unavailable,
        benchmark_return=unavailable,
        tail_loss=unavailable,
        scenario_pnl=unavailable,
    )
    paired = tuple(
        PairedMetricDelta(
            metric=name,
            status=MetricAvailability.UNAVAILABLE,
            unavailable_reason="manifest_mismatch",
        )
        for name in (
            "total_return",
            "ending_nav",
            "total_commission",
            "turnover",
            "max_drawdown",
            "benchmark_return",
            "tail_loss",
            "scenario_pnl",
        )
    )
    return _finalize_report(
        status=ComparisonStatus.ABSTAINED,
        abstain_reason=reason,
        criteria=criteria,
        manifest=placeholder,
        incumbent=_arm_identity(incumbent),
        challenger=_arm_identity(challenger),
        incumbent_metrics=empty_metrics,
        challenger_metrics=empty_metrics,
        paired_deltas=paired,
        hard_constraint_hidden_by_return=False,
    )


__all__ = [
    "FORBIDDEN_IMPORT_PREFIXES",
    "DEFAULT_CRITERIA_PATH",
    "AbsoluteArmMetrics",
    "AllocationComparisonReport",
    "ArmIdentity",
    "ComparisonArm",
    "ComparisonArmInput",
    "ComparisonStatus",
    "MetricAvailability",
    "OptionalScenarioInputs",
    "PairedMetricDelta",
    "ScalarEvidence",
    "ShadowCriteria",
    "SharedReplayManifest",
    "build_shared_manifest",
    "compare_allocation_arms",
    "compute_absolute_metrics",
    "cost_hash_from_execution",
    "data_hash_from_request",
    "execution_policy_hash",
    "load_shadow_criteria",
    "shadow_criteria_content_hash",
    "weights_pct_to_targets",
    "write_comparison_report",
]
