"""Resolve incumbent H8 risk policy and covariance snapshots (#2692 / WP6.2).

Pure resolver — no Supabase I/O. Config/defaults/as-of correlation frames in;
fully provenanced :class:`RiskPolicy` and :class:`CovarianceSnapshot` out.
Never feeds new objects into ``size_portfolio`` in Phase 1; bridge helpers exist
for parity tests only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

import polars as pl

from digiquant.olympus.hermes.cost_liquidity import (
    COST_CONFIG_KEYS,
    DEFAULT_ADV_LOOKBACK_DAYS,
    DEFAULT_CONSERVATIVE_MULTIPLIER,
    DEFAULT_FEE_BPS,
    DEFAULT_IMPACT_ALPHA,
    DEFAULT_MAX_ADV_PARTICIPATION_PCT,
    DEFAULT_SPREAD_RANGE_FRACTION,
)
from digiquant.olympus.hermes.models.risk_policy import (
    CapabilityLimit,
    CorrelationBucketEntry,
    CovarianceSnapshot,
    PolicyArtifactStatus,
    ProvenanceSource,
    RankToConvictionEntry,
    ResolvedLeaf,
    RiskPolicy,
    VolFallbackEntry,
    covariance_snapshot_content_hash,
    covariance_snapshot_id,
    policy_hash_payload,
    risk_policy_content_hash,
    risk_policy_id,
    snapshot_hash_payload,
)
from digiquant.olympus.hermes.phases.phase7e_risk_sizing import (
    _VOL_LOOKBACK_DAYS,
    _rank_to_conviction,
)
from digiquant.olympus.hermes.risk_controls import BreakerConfig
from digiquant.olympus.hermes.sizing import (
    _ANNUALIZE,
    SizingCaps,
    TickerRisk,
    _bucket_corr,
    _vol_fraction,
)
from digiquant.olympus.hermes.turnover import _VALID_CADENCES

METHOD_VERSION = "incumbent-risk-policy@v2"
"""Implementation version stamped on every resolved policy.

v2: ``unavailable_reason`` participates in ``content_hash`` (#2803).
"""

COVARIANCE_METHOD_VERSION = "incumbent-covariance@v2"
"""Implementation version stamped on every covariance snapshot.

v2: incomplete Pearson pairs fail closed as ``unavailable`` (no silent identity
repair labeled ``degraded``); ``unavailable_reason`` is hashed (#2803).
"""

INCUMBENT_CONTROL_ORDER: tuple[str, ...] = (
    "select",
    "raw_weights",
    "position_caps",
    "sector_caps",
    "corr_dedup",
    "vol_target",
    "drawdown_breaker",
    "grid_rounding",
)

_CORR_LOOKBACK_DAYS = 63
"""Default Pearson return-correlation window (matches ``get_return_correlations``)."""

_ESTIMATOR = "pearson_daily_return"
_SHRINKAGE = "none"
_FALLBACK_POLICY = "asset_class_bucket@v1"

_PHASE1_UNAVAILABLE = "phase1_not_implemented"

_SIZING_CONFIG_KEYS: dict[str, str] = {
    "min_position_pct": "min_position_pct",
    "max_position_pct": "max_single_etf_pct",
    "max_sector_pct": "max_sector_pct",
    "weight_increment_pct": "weight_increment_pct",
    "target_portfolio_vol": "target_portfolio_vol",
    "max_gross_pct": "max_gross_pct",
    "corr_dedup_threshold": "corr_dedup_threshold",
    "kelly_fraction": "kelly_fraction",
    "kelly_annual_premium": "kelly_annual_premium",
    "sizing_mode": "sizing_mode",
    "min_conviction": "min_conviction",
    "default_annual_vol": "default_annual_vol",
}

_BREAKER_CONFIG_KEYS: dict[str, str] = {
    "soft_dd_pct": "breaker_soft_dd_pct",
    "hard_dd_pct": "breaker_hard_dd_pct",
    "max_reduction": "breaker_max_reduction",
    "lookback_days": "breaker_lookback_days",
}

_TURNOVER_CONFIG_KEYS: dict[str, str] = {
    "rebalance_threshold_pct": "rebalance_threshold_pct",
    "holding_days": "holding_days",
    "rebalance_rel_band_pct": "rebalance_rel_band_pct",
    "rebalancing_cadence": "rebalancing_cadence",
}

_COST_DEFAULTS: dict[str, float | int] = {
    "fee_bps": float(DEFAULT_FEE_BPS),
    "impact_alpha": float(DEFAULT_IMPACT_ALPHA),
    "spread_range_fraction": float(DEFAULT_SPREAD_RANGE_FRACTION),
    "adv_lookback_days": DEFAULT_ADV_LOOKBACK_DAYS,
    "max_adv_participation_pct": float(DEFAULT_MAX_ADV_PARTICIPATION_PCT),
    "conservative_multiplier": float(DEFAULT_CONSERVATIVE_MULTIPLIER),
}

_GOLDEN_BUCKET_LABELS: tuple[tuple[str, str, str], ...] = (
    ("equity_bond", "EQUITY", "FIXED_INCOME"),
    ("equity_equity", "EQUITY", "EQUITY"),
    ("equity_cash", "EQUITY", "CASH"),
    ("equity_unknown", "EQUITY", "UNKNOWN"),
    ("equity_commodity", "EQUITY", "COMMODITY"),
    ("equity_crypto", "EQUITY", "CRYPTO"),
    ("fixed_income_fixed_income", "FIXED_INCOME", "FIXED_INCOME"),
)


@dataclass(frozen=True)
class RiskPolicyResolution:
    """Resolver outcome — available policy or typed degradation."""

    policy: RiskPolicy
    sizing_caps: SizingCaps
    breaker_config: BreakerConfig


def _resolve_scalar(
    *,
    field: str,
    default: float | int | str | bool,
    preferences: Mapping[str, Any],
    config_keys: Mapping[str, str],
    normalizer: Any | None = None,
) -> ResolvedLeaf:
    config_key = config_keys.get(field, field)
    raw = preferences.get(config_key)
    if raw is None and config_key != field:
        raw = preferences.get(field)
    if raw is None:
        return ResolvedLeaf(
            value=default, source=ProvenanceSource.CODE_DEFAULT, config_key=config_key
        )
    try:
        if isinstance(default, bool):
            value: float | int | str | bool = bool(raw)
            source = ProvenanceSource.EXPLICIT_CONFIG
        elif isinstance(default, int):
            value = int(float(raw))
            source = ProvenanceSource.EXPLICIT_CONFIG
        elif isinstance(default, str):
            value = str(raw)
            source = ProvenanceSource.EXPLICIT_CONFIG
        else:
            value = float(raw)
            source = ProvenanceSource.EXPLICIT_CONFIG
        if normalizer is not None:
            value = normalizer(value)
            source = ProvenanceSource.NORMALIZED_CONFIG
        return ResolvedLeaf(value=value, source=source, config_key=config_key)
    except (TypeError, ValueError):
        return ResolvedLeaf(
            value=default,
            source=ProvenanceSource.CODE_DEFAULT,
            config_key=config_key,
            note="invalid_config_value",
        )


def _resolve_sizing_caps(preferences: Mapping[str, Any]) -> dict[str, ResolvedLeaf]:
    defaults = SizingCaps()
    leaves: dict[str, ResolvedLeaf] = {}
    for field, config_key in _SIZING_CONFIG_KEYS.items():
        default_val = getattr(defaults, field)
        normalizer = None
        if field == "sizing_mode":
            normalizer = lambda v, d=default_val: (  # noqa: E731
                str(v) if str(v) in ("conviction_vol", "kelly") else str(d)
            )
        leaves[field] = _resolve_scalar(
            field=field,
            default=default_val,
            preferences=preferences,
            config_keys={field: config_key},
            normalizer=normalizer,
        )
    return leaves


def _resolve_breaker(preferences: Mapping[str, Any]) -> dict[str, ResolvedLeaf]:
    defaults = BreakerConfig()
    leaves: dict[str, ResolvedLeaf] = {}
    for field, config_key in _BREAKER_CONFIG_KEYS.items():
        default_val = getattr(defaults, field)

        def _breaker_norm(
            value: float, *, f: str = field, d: float | int = default_val
        ) -> float | int:
            if f in ("soft_dd_pct", "hard_dd_pct"):
                return -abs(float(value))
            if f == "max_reduction":
                return min(1.0, max(0.0, float(value)))
            if f == "lookback_days":
                return max(1, int(float(value)))
            return float(value)

        leaves[field] = _resolve_scalar(
            field=field,
            default=default_val,
            preferences=preferences,
            config_keys={field: config_key},
            normalizer=_breaker_norm,
        )

    soft = float(leaves["soft_dd_pct"].value)
    hard = float(leaves["hard_dd_pct"].value)
    if hard > soft:
        leaves["hard_dd_pct"] = ResolvedLeaf(
            value=soft,
            source=ProvenanceSource.DERIVED_INVARIANT,
            config_key=_BREAKER_CONFIG_KEYS["hard_dd_pct"],
            note="hard_must_be_at_least_as_deep_as_soft",
        )
    return leaves


def _resolve_turnover(preferences: Mapping[str, Any]) -> dict[str, ResolvedLeaf]:
    defaults = {
        "rebalance_threshold_pct": 3.0,
        "holding_days": 5,
        "rebalance_rel_band_pct": 20.0,
        "rebalancing_cadence": "daily",
    }
    leaves: dict[str, ResolvedLeaf] = {}
    for field, config_key in _TURNOVER_CONFIG_KEYS.items():
        default_val = defaults[field]

        def _cadence_norm(value: str, d: str = str(default_val)) -> str:
            cleaned = str(value).strip().lower()
            return cleaned if cleaned in _VALID_CADENCES else d

        normalizer = _cadence_norm if field == "rebalancing_cadence" else None
        leaves[field] = _resolve_scalar(
            field=field,
            default=default_val,
            preferences=preferences,
            config_keys={field: config_key},
            normalizer=normalizer,
        )
    return leaves


def _incumbent_correlation_buckets() -> tuple[CorrelationBucketEntry, ...]:
    entries: list[CorrelationBucketEntry] = []
    seen: set[tuple[str, str]] = set()
    for _label, class_a, class_b in _GOLDEN_BUCKET_LABELS:
        key = tuple(sorted((class_a, class_b)))
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            CorrelationBucketEntry(
                class_a=class_a,
                class_b=class_b,
                rho=_bucket_corr(class_a, class_b),
            )
        )
    return tuple(entries)


def _incumbent_vol_fallback_chain() -> tuple[VolFallbackEntry, ...]:
    caps = SizingCaps()
    return (
        VolFallbackEntry(
            key="hist_vol_21",
            annualized_pct=round(_vol_fraction(TickerRisk("X", hist_vol_21=25.0), caps) * 100, 4),
        ),
        VolFallbackEntry(
            key="atr_pct",
            annualized_pct=round(_vol_fraction(TickerRisk("X", atr_pct=1.5), caps) * 100, 4),
        ),
        VolFallbackEntry(
            key="default_annual_vol",
            annualized_pct=round(_vol_fraction(TickerRisk("X"), caps) * 100, 4),
        ),
    )


def _incumbent_rank_to_conviction(*, floor: float = 2.0) -> tuple[RankToConvictionEntry, ...]:
    entries: list[RankToConvictionEntry] = []
    for n in (1, 2, 3, 5):
        mapping = {
            rank: round(_rank_to_conviction(rank, n, floor=floor), 4) for rank in range(1, n + 1)
        }
        entries.append(RankToConvictionEntry(n_long=n, mapping=mapping, floor=floor))
    return tuple(entries)


def _phase1_unavailable_capability() -> CapabilityLimit:
    return CapabilityLimit(
        available=False,
        enforced=False,
        limit=None,
        reason=_PHASE1_UNAVAILABLE,
    )


def _phase1_observational_cost_capability(*, limit: float) -> CapabilityLimit:
    return CapabilityLimit(available=True, enforced=False, limit=limit, reason=None)


def _resolve_cost_coefficients(preferences: Mapping[str, Any]) -> dict[str, ResolvedLeaf]:
    coeffs: dict[str, ResolvedLeaf] = {}
    for field, default in _COST_DEFAULTS.items():
        coeffs[field] = _resolve_scalar(
            field=field,
            default=default,
            preferences=preferences,
            config_keys=COST_CONFIG_KEYS,
        )
    return coeffs


def _validate_resolved_policy(
    *,
    sizing_caps: dict[str, ResolvedLeaf],
    breaker: dict[str, ResolvedLeaf],
) -> str | None:
    """Return degradation reason when incumbent invariants are contradicted."""
    max_gross = float(sizing_caps["max_gross_pct"].value)
    min_pos = float(sizing_caps["min_position_pct"].value)
    max_pos = float(sizing_caps["max_position_pct"].value)
    if max_gross < min_pos:
        return "max_gross_below_min_position"
    if max_pos > max_gross:
        return "max_position_exceeds_max_gross"
    if min_pos > max_pos:
        return "min_position_exceeds_max_position"
    soft = float(breaker["soft_dd_pct"].value)
    hard = float(breaker["hard_dd_pct"].value)
    if soft > 0 or hard > 0:
        return "drawdown_thresholds_must_be_non_positive"
    if hard > soft:
        return "hard_drawdown_shallower_than_soft"
    mode = str(sizing_caps["sizing_mode"].value)
    if mode not in ("conviction_vol", "kelly"):
        return "unsupported_sizing_mode"
    return None


def _policy_from_leaves(
    *,
    sizing_caps: dict[str, ResolvedLeaf],
    breaker: dict[str, ResolvedLeaf],
    turnover: dict[str, ResolvedLeaf],
    cost_coefficients: dict[str, ResolvedLeaf],
    effective_at: datetime,
    source_run_id: str | None,
    status: PolicyArtifactStatus,
    unavailable_reason: str | None,
) -> RiskPolicy:
    draft = RiskPolicy.model_construct(
        policy_id=risk_policy_id(method_version=METHOD_VERSION, content_hash="0" * 64),
        method_version=METHOD_VERSION,
        effective_at=effective_at,
        source_run_id=source_run_id,
        status=status,
        unavailable_reason=unavailable_reason,
        content_hash="0" * 64,
        sizing_caps=sizing_caps,
        breaker=breaker,
        turnover=turnover,
        horizons={
            "annualize_factor": ResolvedLeaf(
                value=_ANNUALIZE, source=ProvenanceSource.CODE_DEFAULT
            ),
            "vol_lookback_days": ResolvedLeaf(
                value=_VOL_LOOKBACK_DAYS, source=ProvenanceSource.CODE_DEFAULT
            ),
            "corr_lookback_days": ResolvedLeaf(
                value=_CORR_LOOKBACK_DAYS, source=ProvenanceSource.CODE_DEFAULT
            ),
        },
        control_order=INCUMBENT_CONTROL_ORDER,
        correlation_buckets=_incumbent_correlation_buckets(),
        vol_fallback_chain=_incumbent_vol_fallback_chain(),
        rank_to_conviction=_incumbent_rank_to_conviction(),
        annualize_factor=ResolvedLeaf(value=_ANNUALIZE, source=ProvenanceSource.CODE_DEFAULT),
        vol_lookback_days=ResolvedLeaf(
            value=_VOL_LOOKBACK_DAYS, source=ProvenanceSource.CODE_DEFAULT
        ),
        corr_lookback_days=ResolvedLeaf(
            value=_CORR_LOOKBACK_DAYS, source=ProvenanceSource.CODE_DEFAULT
        ),
        factor_limits=_phase1_unavailable_capability(),
        stress_limits=_phase1_unavailable_capability(),
        tail_limits=_phase1_unavailable_capability(),
        liquidity_limits=_phase1_observational_cost_capability(
            limit=float(cost_coefficients["max_adv_participation_pct"].value)
        ),
        cost_policy=_phase1_observational_cost_capability(limit=None),
        cost_coefficients=cost_coefficients,
    )
    content_hash = risk_policy_content_hash(payload=policy_hash_payload(draft))
    policy_id = risk_policy_id(method_version=METHOD_VERSION, content_hash=content_hash)
    return RiskPolicy.model_validate(
        {
            **draft.model_dump(),
            "content_hash": content_hash,
            "policy_id": policy_id,
        }
    )


def resolve_risk_policy(
    preferences: Mapping[str, Any] | None = None,
    *,
    effective_at: datetime | None = None,
    source_run_id: str | None = None,
) -> RiskPolicyResolution:
    """Resolve a fully provenanced incumbent risk policy from config/defaults."""
    prefs = preferences or {}
    at = effective_at or datetime.now(tz=UTC)
    if at.tzinfo is None or at.utcoffset() != UTC.utcoffset(at):
        raise ValueError("effective_at must be timezone-aware UTC")

    sizing_caps = _resolve_sizing_caps(prefs)
    breaker = _resolve_breaker(prefs)
    turnover = _resolve_turnover(prefs)
    cost_coefficients = _resolve_cost_coefficients(prefs)
    degrade_reason = _validate_resolved_policy(sizing_caps=sizing_caps, breaker=breaker)
    if degrade_reason:
        policy = _policy_from_leaves(
            sizing_caps=sizing_caps,
            breaker=breaker,
            turnover=turnover,
            cost_coefficients=cost_coefficients,
            effective_at=at,
            source_run_id=source_run_id,
            status=PolicyArtifactStatus.DEGRADED,
            unavailable_reason=degrade_reason,
        )
    else:
        policy = _policy_from_leaves(
            sizing_caps=sizing_caps,
            breaker=breaker,
            turnover=turnover,
            cost_coefficients=cost_coefficients,
            effective_at=at,
            source_run_id=source_run_id,
            status=PolicyArtifactStatus.AVAILABLE,
            unavailable_reason=None,
        )

    return RiskPolicyResolution(
        policy=policy,
        sizing_caps=sizing_caps_from_policy(policy),
        breaker_config=breaker_config_from_policy(policy),
    )


def sizing_caps_from_policy(policy: RiskPolicy) -> SizingCaps:
    """Bridge helper for parity tests — not wired into production H8 in Phase 1."""
    if policy.status is PolicyArtifactStatus.UNAVAILABLE:
        raise ValueError("cannot derive sizing caps from unavailable policy")
    return SizingCaps(
        **{field: leaf.value for field, leaf in policy.sizing_caps.items()},  # type: ignore[arg-type]
    )


def breaker_config_from_policy(policy: RiskPolicy) -> BreakerConfig:
    """Bridge helper for parity tests — not wired into production H8 in Phase 1."""
    if policy.status is PolicyArtifactStatus.UNAVAILABLE:
        raise ValueError("cannot derive breaker config from unavailable policy")
    return BreakerConfig(
        **{field: leaf.value for field, leaf in policy.breaker.items()},  # type: ignore[arg-type]
    )


def _canonical_tickers(tickers: Sequence[str]) -> tuple[str, ...]:
    cleaned = sorted({t.strip().upper() for t in tickers if t and t.strip().upper() != "CASH"})
    return tuple(cleaned)


def _corr_lookup(corr: pl.DataFrame) -> dict[tuple[str, str], float]:
    lookup: dict[tuple[str, str], float] = {}
    for row in corr.select(["a", "b", "corr"]).to_dicts():
        a = str(row["a"]).strip().upper()
        b = str(row["b"]).strip().upper()
        lookup[(a, b)] = float(row["corr"])
    return lookup


def _build_correlation_matrix(
    tickers: tuple[str, ...],
    lookup: Mapping[tuple[str, str], float],
) -> tuple[tuple[float, ...], ...]:
    matrix: list[tuple[float, ...]] = []
    for i, ti in enumerate(tickers):
        row: list[float] = []
        for j, tj in enumerate(tickers):
            if i == j:
                row.append(1.0)
                continue
            rho = lookup.get((ti, tj), lookup.get((tj, ti)))
            if rho is None:
                raise KeyError(f"missing correlation for pair ({ti}, {tj})")
            row.append(float(rho))
        matrix.append(tuple(row))
    return tuple(matrix)


def _finalize_covariance_snapshot(
    *,
    as_of_session: date,
    lookback_days: int,
    tickers: tuple[str, ...],
    matrix: tuple[tuple[float, ...], ...],
    observation_count: int | None,
    resolved_at: datetime,
    status: PolicyArtifactStatus,
    unavailable_reason: str | None,
) -> CovarianceSnapshot:
    draft = CovarianceSnapshot.model_construct(
        snapshot_id=covariance_snapshot_id(
            as_of_session=as_of_session,
            tickers=tickers,
            content_hash="0" * 64,
        ),
        method_version=COVARIANCE_METHOD_VERSION,
        as_of_session=as_of_session,
        lookback_days=lookback_days,
        estimator=_ESTIMATOR,
        shrinkage=_SHRINKAGE,
        fallback_policy=_FALLBACK_POLICY,
        tickers=tickers,
        matrix=matrix,
        observation_count=observation_count,
        source_table="price_history",
        resolved_at=resolved_at,
        status=status,
        unavailable_reason=unavailable_reason,
        content_hash="0" * 64,
    )
    content_hash = covariance_snapshot_content_hash(payload=snapshot_hash_payload(draft))
    snapshot_id = covariance_snapshot_id(
        as_of_session=as_of_session,
        tickers=tickers,
        content_hash=content_hash,
    )
    return CovarianceSnapshot.model_validate(
        {
            **draft.model_dump(),
            "content_hash": content_hash,
            "snapshot_id": snapshot_id,
        }
    )


def resolve_covariance_snapshot(
    *,
    tickers: Sequence[str],
    corr: pl.DataFrame | None,
    as_of_session: date,
    lookback_days: int = _CORR_LOOKBACK_DAYS,
    resolved_at: datetime | None = None,
    observation_count: int | None = None,
) -> CovarianceSnapshot:
    """Build a canonical correlation snapshot from an as-of returns frame."""
    at = resolved_at or datetime.now(tz=UTC)
    if at.tzinfo is None or at.utcoffset() != UTC.utcoffset(at):
        raise ValueError("resolved_at must be timezone-aware UTC")

    canonical = _canonical_tickers(tickers)
    if len(canonical) < 2:
        n = len(canonical)
        matrix = tuple(tuple(1.0 if i == j else 0.0 for j in range(n)) for i in range(n))
        return _finalize_covariance_snapshot(
            as_of_session=as_of_session,
            lookback_days=lookback_days,
            tickers=canonical,
            matrix=matrix,
            observation_count=observation_count,
            resolved_at=at,
            status=PolicyArtifactStatus.UNAVAILABLE,
            unavailable_reason="insufficient_tickers",
        )

    if corr is None or corr.is_empty():
        n = len(canonical)
        matrix = tuple(tuple(1.0 if i == j else 0.0 for j in range(n)) for i in range(n))
        return _finalize_covariance_snapshot(
            as_of_session=as_of_session,
            lookback_days=lookback_days,
            tickers=canonical,
            matrix=matrix,
            observation_count=observation_count,
            resolved_at=at,
            status=PolicyArtifactStatus.UNAVAILABLE,
            unavailable_reason="missing_correlation_frame",
        )

    lookup = _corr_lookup(corr)
    missing_pairs: list[tuple[str, str]] = []
    for i, ti in enumerate(canonical):
        for tj in canonical[i + 1 :]:
            if (ti, tj) not in lookup and (tj, ti) not in lookup:
                missing_pairs.append((ti, tj))

    if missing_pairs:
        # Fail closed: do not invent off-diagonal zeros / wipe observed pairs and
        # label the result ``degraded``. Structural identity is a placeholder only
        # (same shape as missing_frame), status ``unavailable`` (#2803).
        n = len(canonical)
        matrix = tuple(tuple(1.0 if i == j else 0.0 for j in range(n)) for i in range(n))
        return _finalize_covariance_snapshot(
            as_of_session=as_of_session,
            lookback_days=lookback_days,
            tickers=canonical,
            matrix=matrix,
            observation_count=observation_count,
            resolved_at=at,
            status=PolicyArtifactStatus.UNAVAILABLE,
            unavailable_reason=(
                "incomplete_pairs:" + ",".join(f"{a}/{b}" for a, b in missing_pairs)
            ),
        )

    matrix = _build_correlation_matrix(canonical, lookup)
    return _finalize_covariance_snapshot(
        as_of_session=as_of_session,
        lookback_days=lookback_days,
        tickers=canonical,
        matrix=matrix,
        observation_count=observation_count,
        resolved_at=at,
        status=PolicyArtifactStatus.AVAILABLE,
        unavailable_reason=None,
    )


__all__ = [
    "COVARIANCE_METHOD_VERSION",
    "INCUMBENT_CONTROL_ORDER",
    "METHOD_VERSION",
    "RiskPolicyResolution",
    "breaker_config_from_policy",
    "resolve_covariance_snapshot",
    "resolve_risk_policy",
    "sizing_caps_from_policy",
]
