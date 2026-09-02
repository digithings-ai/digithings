"""WP10.3 — solver-free robust challenger (#2770).

Deterministic coordinate-search allocator for write-denied shadow evaluation
only. Consumes a WP10.1 :class:`ShadowAllocationArtifact` plus numeric
covariance/cost schedules supplied by the isolated caller.

Must never be imported by the production H8/H9 graph, commit writers, brokers,
or live-trading surfaces. No SciPy/CVXPY — pure Python grid search only.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.portfolio.allocation_contracts import (
    AssetInputStatus,
    BookWeightsView,
    ReportWeightEntry,
)
from digiquant.portfolio.allocation_hashes import (
    sha256_hex,
    weights_fingerprint,
)
from digiquant.portfolio.shadow_artifact import ShadowAllocationArtifact

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
FiniteNonNeg: TypeAlias = Annotated[float, Field(ge=0, allow_inf_nan=False)]
FiniteFloat: TypeAlias = Annotated[float, Field(allow_inf_nan=False)]
PositiveInt: TypeAlias = Annotated[int, Field(gt=0)]

# Static import fence — AST tests + isolation checker assert these never appear.
FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "scipy",
        "cvxpy",
        "cvxopt",
        "digiquant.brokers",
        "digiquant.portfolio.writers",
        "digiquant.portfolio.phases.h9_commit_run",
        "digiquant.portfolio.phases.phase7e_risk_sizing",
        "digiquant.research.supabase_io",
        "nautilus_trader",
        "supabase",
        "httpx",
        "requests",
    }
)

CASH_TOKEN = "CASH"
OBJECTIVE_EPS = 1e-12
OBJECTIVE_TOLERANCE = 1e-12
_WEIGHT_ROUND = 10


class ShadowOptimizerStatus(StrEnum):
    """Outcome of one shadow challenger evaluation."""

    IMPROVED = "improved"
    IDENTITY = "identity"
    ABSTAINED = "abstained"


class ShadowContractModel(BaseModel):
    """Strict immutable base for shadow optimizer contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ShadowFeasibilityConstraints(ShadowContractModel):
    """Hard book constraints inherited from production policy semantics."""

    max_position_pct: FiniteNonNeg = 30.0
    min_cash_pct: FiniteNonNeg = 0.0
    max_gross_pct: FiniteNonNeg = 100.0
    weight_increment_pct: FiniteNonNeg = 5.0

    @model_validator(mode="after")
    def _validate_caps(self) -> ShadowFeasibilityConstraints:
        if self.max_gross_pct > 100.0 + 1e-9:
            raise ValueError("max_gross_pct cannot exceed 100")
        if self.min_cash_pct > 100.0 + 1e-9:
            raise ValueError("min_cash_pct cannot exceed 100")
        if self.max_position_pct > self.max_gross_pct + 1e-9:
            raise ValueError("max_position_pct cannot exceed max_gross_pct")
        return self


class ShadowObjectiveParams(ShadowContractModel):
    """Hyperparameters for the robust objective J(w)."""

    kappa: FiniteNonNeg = 1.0
    lambda_risk: FiniteNonNeg = 1.0
    gamma: FiniteNonNeg = 0.0
    improvement_epsilon: FiniteNonNeg = OBJECTIVE_EPS
    max_iterations: PositiveInt = 64


class ShadowCostSchedule(ShadowContractModel):
    """Per-asset linear cost rates on absolute weight-fraction changes."""

    rates: tuple[tuple[NonEmptyId, FiniteNonNeg], ...]

    @field_validator("rates", mode="before")
    @classmethod
    def _coerce_rates(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(tuple(pair) for pair in value)
        return value

    @model_validator(mode="after")
    def _validate_rates(self) -> ShadowCostSchedule:
        tickers = [ticker for ticker, _ in self.rates]
        if tickers != sorted(tickers):
            raise ValueError("cost schedule rates must be sorted by ticker")
        if len(tickers) != len(set(tickers)):
            raise ValueError("cost schedule rates must be unique by ticker")
        if CASH_TOKEN in tickers:
            raise ValueError("cost schedule must not include CASH token")
        return self

    def rate_map(self) -> dict[str, float]:
        return {ticker: float(rate) for ticker, rate in self.rates}


class ShadowMove(ShadowContractModel):
    """One accepted grid-quantum transfer in the move trace."""

    iteration: PositiveInt
    donor: NonEmptyId
    receiver: NonEmptyId
    quantum_pct: FiniteNonNeg
    objective_before: FiniteFloat
    objective_after: FiniteFloat


class ShadowChallengerResult(ShadowContractModel):
    """Immutable challenger outcome for isolated replay/comparison."""

    status: ShadowOptimizerStatus
    artifact_content_hash: NonEmptyId
    result_content_hash: NonEmptyId
    abstain_reason: NonEmptyId | None = None
    seed_objective: FiniteFloat | None = None
    challenger_objective: FiniteFloat | None = None
    challenger_weights: BookWeightsView | None = None
    move_trace: tuple[ShadowMove, ...] = ()

    @field_validator("move_trace", mode="before")
    @classmethod
    def _coerce_trace(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_result(self) -> ShadowChallengerResult:
        if self.status is ShadowOptimizerStatus.ABSTAINED:
            if self.abstain_reason is None or not self.abstain_reason.strip():
                raise ValueError("abstained result requires abstain_reason")
            if self.challenger_weights is not None:
                raise ValueError("abstained result cannot carry challenger_weights")
            if self.move_trace:
                raise ValueError("abstained result cannot carry move_trace")
        else:
            if self.abstain_reason is not None:
                raise ValueError("non-abstained result cannot carry abstain_reason")
            if self.seed_objective is None or self.challenger_objective is None:
                raise ValueError("non-abstained result requires objectives")
            if self.challenger_weights is None:
                raise ValueError("non-abstained result requires challenger_weights")
            if self.challenger_objective + OBJECTIVE_TOLERANCE < self.seed_objective:
                raise ValueError("challenger objective must not be worse than seed")
            if self.status is ShadowOptimizerStatus.IDENTITY and self.move_trace:
                raise ValueError("identity result must have empty move_trace")
            if self.status is ShadowOptimizerStatus.IMPROVED and not self.move_trace:
                raise ValueError("improved result requires a non-empty move_trace")
        expected = sha256_hex(self._hash_payload())
        if self.result_content_hash != expected:
            raise ValueError("result_content_hash must match canonical digest")
        return self

    def _hash_payload(self) -> dict[str, object]:
        weights_payload: dict[str, object] | None = None
        if self.challenger_weights is not None:
            weights_payload = {
                "entries": [
                    {"ticker": e.ticker, "weight_pct": e.weight_pct}
                    for e in self.challenger_weights.entries
                ],
                "cash_weight_pct": self.challenger_weights.cash_weight_pct,
                "weights_fingerprint": self.challenger_weights.weights_fingerprint,
            }
        return {
            "status": self.status.value,
            "artifact_content_hash": self.artifact_content_hash,
            "abstain_reason": self.abstain_reason,
            "seed_objective": self.seed_objective,
            "challenger_objective": self.challenger_objective,
            "challenger_weights": weights_payload,
            "move_trace": [
                {
                    "iteration": move.iteration,
                    "donor": move.donor,
                    "receiver": move.receiver,
                    "quantum_pct": move.quantum_pct,
                    "objective_before": move.objective_before,
                    "objective_after": move.objective_after,
                }
                for move in self.move_trace
            ],
        }


class ShadowOptimizerRequest(ShadowContractModel):
    """Isolated evaluation request — artifact in, numeric schedules beside it."""

    artifact: ShadowAllocationArtifact
    covariance_matrix: tuple[tuple[FiniteFloat, ...], ...]
    cost_schedule: ShadowCostSchedule
    constraints: ShadowFeasibilityConstraints = Field(default_factory=ShadowFeasibilityConstraints)
    objective: ShadowObjectiveParams = Field(default_factory=ShadowObjectiveParams)

    @field_validator("covariance_matrix", mode="before")
    @classmethod
    def _coerce_matrix(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(tuple(row) for row in value)
        return value


def book_to_weight_map(book: BookWeightsView) -> dict[str, float]:
    """Risky weight map (%) from a book view."""
    return {entry.ticker: float(entry.weight_pct) for entry in book.entries}


def build_book_weights(risky_pct: dict[str, float], cash_pct: float) -> BookWeightsView:
    """Construct a sorted, fingerprinted book view."""
    cleaned = {
        ticker: _round_pct(weight)
        for ticker, weight in risky_pct.items()
        if abs(weight) > 10 ** (-_WEIGHT_ROUND)
    }
    entries = tuple(
        ReportWeightEntry(ticker=ticker, weight_pct=cleaned[ticker]) for ticker in sorted(cleaned)
    )
    return BookWeightsView(
        entries=entries,
        cash_weight_pct=_round_pct(cash_pct),
        weights_fingerprint=weights_fingerprint(cleaned),
    )


def is_on_grid(weight_pct: float, increment_pct: float, *, tol: float = 1e-9) -> bool:
    """True when ``weight_pct`` sits on the sizing grid (or increment is disabled)."""
    if increment_pct <= 0:
        return True
    steps = weight_pct / increment_pct
    return abs(steps - round(steps)) <= tol


def check_feasibility(
    *,
    risky_pct: dict[str, float],
    cash_pct: float,
    constraints: ShadowFeasibilityConstraints,
    authorized_longs: frozenset[str],
) -> str | None:
    """Return a reason string when the book violates a hard constraint, else None."""
    for ticker, weight in risky_pct.items():
        if not math.isfinite(weight):
            return f"non-finite weight for {ticker}"
        if weight < -1e-9:
            return f"negative weight for {ticker}"
        if weight > constraints.max_position_pct + 1e-9:
            return f"position cap breached for {ticker}"
        if ticker not in authorized_longs and weight > 1e-9:
            return f"unauthorized long weight for {ticker}"
        if not is_on_grid(weight, constraints.weight_increment_pct):
            return f"off-grid weight for {ticker}"
    if not math.isfinite(cash_pct):
        return "non-finite cash weight"
    if cash_pct < constraints.min_cash_pct - 1e-9:
        return "min cash breached"
    if not is_on_grid(cash_pct, constraints.weight_increment_pct):
        return "off-grid cash weight"
    gross = sum(max(0.0, w) for w in risky_pct.values())
    if gross > constraints.max_gross_pct + 1e-9:
        return "gross exposure cap breached"
    if abs((gross + cash_pct) - 100.0) > 1e-6:
        return "weights must sum to 100% including cash"
    return None


def robust_objective(
    *,
    risky_frac: dict[str, float],
    asset_order: tuple[str, ...],
    mu: dict[str, float],
    d_mu: dict[str, float],
    covariance: tuple[tuple[float, ...], ...],
    prior_frac: dict[str, float],
    cost_rates: dict[str, float],
    params: ShadowObjectiveParams,
) -> float:
    """Evaluate J(w) on risky fractions (cash excluded from μ/Σ terms)."""
    w = [float(risky_frac.get(ticker, 0.0)) for ticker in asset_order]
    mu_vec = [float(mu[ticker]) for ticker in asset_order]
    d_vec = [float(d_mu[ticker]) * w[idx] for idx, ticker in enumerate(asset_order)]

    expected = _dot(mu_vec, w)
    uncertainty = params.kappa * _l2(d_vec)
    variance = _quadratic_form(covariance, w)
    risk = 0.5 * params.lambda_risk * variance

    trade_cost = 0.0
    l1 = 0.0
    for ticker in asset_order:
        delta = float(risky_frac.get(ticker, 0.0)) - float(prior_frac.get(ticker, 0.0))
        abs_delta = abs(delta)
        l1 += abs_delta
        trade_cost += float(cost_rates.get(ticker, 0.0)) * abs_delta

    return expected - uncertainty - risk - trade_cost - params.gamma * l1


def evaluate_shadow_challenger(request: ShadowOptimizerRequest) -> ShadowChallengerResult:
    """Run the solver-free challenger or abstain with a typed reason.

    Never mutates production state. Repeated calls with identical inputs yield
    byte-identical :class:`ShadowChallengerResult` digests.
    """
    artifact = request.artifact
    abstain = _abstain_reason(request)
    if abstain is not None:
        return _abstained(artifact.artifact_content_hash, abstain)

    bundle = artifact.allocation_input_bundle
    asset_order = bundle.canonical_asset_order
    authorized = frozenset(item.ticker for item in bundle.mandates if item.direction == "long")
    mu = {
        item.ticker: float(item.expected_gross_return) * float(item.reliability_weight)
        for item in bundle.calibrated_returns
    }
    d_mu = {item.ticker: float(item.forecast_error_std) for item in bundle.calibrated_returns}
    prior_risky = {entry.ticker: entry.weight_pct / 100.0 for entry in bundle.prior_book.entries}
    prior_frac = {ticker: float(prior_risky.get(ticker, 0.0)) for ticker in asset_order}
    cost_rates = request.cost_schedule.rate_map()

    seed_book = artifact.incumbent_final_weights
    seed_risky = book_to_weight_map(seed_book)
    seed_cash = float(seed_book.cash_weight_pct)
    seed_reason = check_feasibility(
        risky_pct=seed_risky,
        cash_pct=seed_cash,
        constraints=request.constraints,
        authorized_longs=authorized,
    )
    if seed_reason is not None:
        return _abstained(artifact.artifact_content_hash, f"infeasible seed: {seed_reason}")

    def objective_for(risky_pct: dict[str, float]) -> float:
        risky_frac = {ticker: risky_pct.get(ticker, 0.0) / 100.0 for ticker in asset_order}
        return robust_objective(
            risky_frac=risky_frac,
            asset_order=asset_order,
            mu=mu,
            d_mu=d_mu,
            covariance=request.covariance_matrix,
            prior_frac=prior_frac,
            cost_rates=cost_rates,
            params=request.objective,
        )

    current_risky = dict(seed_risky)
    current_cash = seed_cash
    seed_obj = objective_for(current_risky)
    current_obj = seed_obj
    trace: list[ShadowMove] = []
    quantum = float(request.constraints.weight_increment_pct)
    if quantum <= 0:
        return _abstained(
            artifact.artifact_content_hash,
            "weight_increment_pct must be positive for coordinate search",
        )

    slots = (*asset_order, CASH_TOKEN)
    eps = float(request.objective.improvement_epsilon)

    for iteration in range(1, int(request.objective.max_iterations) + 1):
        best_candidate: tuple[dict[str, float], float, str, str] | None = None
        # Deterministic enumeration: donor then receiver in sorted slot order.
        for donor in slots:
            donor_weight = current_cash if donor == CASH_TOKEN else current_risky.get(donor, 0.0)
            if donor_weight + 1e-12 < quantum:
                continue
            for receiver in slots:
                if receiver == donor:
                    continue
                if receiver != CASH_TOKEN and receiver not in authorized:
                    continue
                candidate_risky, candidate_cash = _apply_quantum_move(
                    risky_pct=current_risky,
                    cash_pct=current_cash,
                    donor=donor,
                    receiver=receiver,
                    quantum_pct=quantum,
                )
                reason = check_feasibility(
                    risky_pct=candidate_risky,
                    cash_pct=candidate_cash,
                    constraints=request.constraints,
                    authorized_longs=authorized,
                )
                if reason is not None:
                    continue
                cand_obj = objective_for(candidate_risky)
                improvement = cand_obj - current_obj
                if improvement <= eps:
                    continue
                if best_candidate is None:
                    best_candidate = (candidate_risky, cand_obj, donor, receiver)
                    continue
                _, best_obj, best_donor, best_receiver = best_candidate
                if cand_obj > best_obj + 1e-15:
                    best_candidate = (candidate_risky, cand_obj, donor, receiver)
                elif abs(cand_obj - best_obj) <= 1e-15:
                    # Lexicographic tie-break on (donor, receiver).
                    if (donor, receiver) < (best_donor, best_receiver):
                        best_candidate = (candidate_risky, cand_obj, donor, receiver)

        if best_candidate is None:
            break

        next_risky, next_obj, donor, receiver = best_candidate
        next_cash = 100.0 - sum(next_risky.values())
        trace.append(
            ShadowMove(
                iteration=iteration,
                donor=donor,
                receiver=receiver,
                quantum_pct=quantum,
                objective_before=current_obj,
                objective_after=next_obj,
            )
        )
        current_risky = next_risky
        current_cash = _round_pct(next_cash)
        current_obj = next_obj

    challenger = build_book_weights(current_risky, current_cash)
    status = ShadowOptimizerStatus.IMPROVED if trace else ShadowOptimizerStatus.IDENTITY
    return _finished(
        status=status,
        artifact_hash=artifact.artifact_content_hash,
        seed_objective=seed_obj,
        challenger_objective=current_obj,
        challenger_weights=challenger,
        move_trace=tuple(trace),
    )


def _abstain_reason(request: ShadowOptimizerRequest) -> str | None:
    artifact = request.artifact
    bundle = artifact.allocation_input_bundle

    if bundle.covariance is None or bundle.source_hashes.covariance_hash is None:
        return "missing covariance binding"
    if bundle.cost_liquidity is None:
        return "missing cost/liquidity binding"

    for item in bundle.calibrated_returns:
        if item.status is not AssetInputStatus.AVAILABLE:
            return f"calibrated input not available for {item.ticker}"
        if item.expected_gross_return is None or item.forecast_error_std is None:
            return f"incomplete calibrated metrics for {item.ticker}"
        if float(item.forecast_error_std) <= 0:
            return f"non-positive uncertainty for {item.ticker}"

    order = bundle.canonical_asset_order
    matrix = request.covariance_matrix
    n = len(order)
    if len(matrix) != n:
        return "covariance matrix row count mismatch"
    for idx, row in enumerate(matrix):
        if len(row) != n:
            return f"covariance matrix row {idx} width mismatch"
        for value in row:
            if not math.isfinite(value):
                return "non-finite covariance entry"
        for jdx in range(n):
            if abs(matrix[idx][jdx] - matrix[jdx][idx]) > 1e-12:
                return "covariance matrix must be symmetric"

    rate_map = request.cost_schedule.rate_map()
    for ticker in order:
        if ticker not in rate_map:
            return f"missing cost rate for {ticker}"
        if not math.isfinite(rate_map[ticker]):
            return f"non-finite cost rate for {ticker}"

    return None


def _apply_quantum_move(
    *,
    risky_pct: dict[str, float],
    cash_pct: float,
    donor: str,
    receiver: str,
    quantum_pct: float,
) -> tuple[dict[str, float], float]:
    next_risky = dict(risky_pct)
    next_cash = cash_pct
    if donor == CASH_TOKEN:
        next_cash = _round_pct(next_cash - quantum_pct)
    else:
        next_risky[donor] = _round_pct(next_risky.get(donor, 0.0) - quantum_pct)
        if next_risky[donor] <= 1e-12:
            next_risky.pop(donor, None)
    if receiver == CASH_TOKEN:
        next_cash = _round_pct(next_cash + quantum_pct)
    else:
        next_risky[receiver] = _round_pct(next_risky.get(receiver, 0.0) + quantum_pct)
    # Recompute cash from risky to avoid drift when both legs are risky.
    if donor != CASH_TOKEN and receiver != CASH_TOKEN:
        next_cash = _round_pct(100.0 - sum(next_risky.values()))
    elif donor == CASH_TOKEN or receiver == CASH_TOKEN:
        next_cash = _round_pct(next_cash)
    return next_risky, next_cash


def _abstained(artifact_hash: str, reason: str) -> ShadowChallengerResult:
    draft = ShadowChallengerResult.model_construct(
        status=ShadowOptimizerStatus.ABSTAINED,
        artifact_content_hash=artifact_hash,
        result_content_hash="",
        abstain_reason=reason,
        seed_objective=None,
        challenger_objective=None,
        challenger_weights=None,
        move_trace=(),
    )
    digest = sha256_hex(draft._hash_payload())
    return ShadowChallengerResult.model_validate(
        {
            "status": ShadowOptimizerStatus.ABSTAINED,
            "artifact_content_hash": artifact_hash,
            "result_content_hash": digest,
            "abstain_reason": reason,
            "seed_objective": None,
            "challenger_objective": None,
            "challenger_weights": None,
            "move_trace": (),
        }
    )


def _finished(
    *,
    status: ShadowOptimizerStatus,
    artifact_hash: str,
    seed_objective: float,
    challenger_objective: float,
    challenger_weights: BookWeightsView,
    move_trace: tuple[ShadowMove, ...],
) -> ShadowChallengerResult:
    draft = ShadowChallengerResult.model_construct(
        status=status,
        artifact_content_hash=artifact_hash,
        result_content_hash="",
        abstain_reason=None,
        seed_objective=seed_objective,
        challenger_objective=challenger_objective,
        challenger_weights=challenger_weights,
        move_trace=move_trace,
    )
    digest = sha256_hex(draft._hash_payload())
    return ShadowChallengerResult.model_validate(
        {
            "status": status,
            "artifact_content_hash": artifact_hash,
            "result_content_hash": digest,
            "abstain_reason": None,
            "seed_objective": seed_objective,
            "challenger_objective": challenger_objective,
            "challenger_weights": challenger_weights,
            "move_trace": move_trace,
        }
    )


def _round_pct(value: float) -> float:
    return round(float(value), _WEIGHT_ROUND)


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _l2(values: list[float]) -> float:
    return math.sqrt(sum(v * v for v in values))


def _quadratic_form(matrix: tuple[tuple[float, ...], ...], vector: list[float]) -> float:
    acc = 0.0
    for i, row in enumerate(matrix):
        row_dot = 0.0
        for j, coeff in enumerate(row):
            row_dot += float(coeff) * vector[j]
        acc += vector[i] * row_dot
    return acc


__all__ = [
    "CASH_TOKEN",
    "FORBIDDEN_IMPORT_PREFIXES",
    "OBJECTIVE_EPS",
    "OBJECTIVE_TOLERANCE",
    "ShadowChallengerResult",
    "ShadowCostSchedule",
    "ShadowFeasibilityConstraints",
    "ShadowMove",
    "ShadowObjectiveParams",
    "ShadowOptimizerRequest",
    "ShadowOptimizerStatus",
    "book_to_weight_map",
    "build_book_weights",
    "check_feasibility",
    "evaluate_shadow_challenger",
    "is_on_grid",
    "robust_objective",
]
