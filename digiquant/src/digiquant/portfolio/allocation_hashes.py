"""Stable SHA-256 identities for H8 allocation inputs and WP9 risk reports.

Canonical JSON uses sorted keys, compact separators, UTF-8, normalized UTC
timestamps in payloads, ``allow_nan=False``, and SHA-256 digests. Never use
Python ``hash()`` for cross-run identity.

``weights_fingerprint`` is the sole authoritative implementation —
:mod:`digiquant.portfolio.writers.commit_io` delegates here so H9
idempotency bytes stay stable. Pre-trade report digests live beside the
allocation bundle helpers so H9 can bind book + report without a second hash
dialect (#2742 / WP9.1).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes

_HASH_HEX_LEN = 64


def canonical_json(payload: object) -> str:
    """Serialize ``payload`` for deterministic SHA-256 input."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        allow_nan=False,
    )


def sha256_hex(payload: object) -> str:
    """SHA-256 hex digest of canonical JSON for ``payload``."""
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    if len(digest) != _HASH_HEX_LEN:
        raise ValueError("sha256 hex digest must be 64 characters")
    return digest


def weights_fingerprint(weights: dict[str, float]) -> str:
    """Stable hash for idempotency comparisons on risky weight maps."""
    canonical = {k: round(v, 4) for k, v in sorted(weights.items())}
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def prior_weights_from_entries(entries: tuple[tuple[str, float], ...]) -> dict[str, float]:
    """Build the risky-weight map used by ``weights_fingerprint``."""
    return {ticker: weight for ticker, weight in entries}


def allocation_bundle_content_hash(*, payload: dict[str, Any]) -> str:
    """SHA-256 over canonical allocation bundle identity fields."""
    return sha256_hex(payload)


def h7_memo_hash_payload(
    *,
    session_date: str,
    roster: list[dict[str, object]],
) -> dict[str, object]:
    """Ticker-keyed mandate identity for bundle hashing (order-independent)."""
    keyed: dict[str, object] = {}
    for row in roster:
        ticker = str(row["ticker"])
        keyed[ticker] = {
            "direction": row["direction"],
            "conviction_rank": row["conviction_rank"],
            "effective_forecast_id": row.get("effective_forecast_id"),
            "forecast_reference_hash": row.get("forecast_reference_hash"),
            "degradation_reason": row.get("degradation_reason"),
        }
    return {"session_date": session_date, "mandates": keyed}


def calibrated_slice_hash_payload(slice_payload: dict[str, object]) -> dict[str, object]:
    """Per-asset calibrated return identity for bundle hashing."""
    return {
        "horizon_sessions": slice_payload["horizon_sessions"],
        "expected_gross_return": slice_payload.get("expected_gross_return"),
        "forecast_error_std": slice_payload.get("forecast_error_std"),
        "reliability_weight": slice_payload["reliability_weight"],
        "calibrated_forecast_content_hash": slice_payload.get("calibrated_forecast_content_hash"),
        "status": slice_payload["status"],
        "unavailable_reason": slice_payload.get("unavailable_reason"),
    }


def allocation_bundle_hash_payload(
    *,
    schema_version: str,
    run: dict[str, object],
    canonical_asset_order: tuple[str, ...],
    mandates: tuple[dict[str, object], ...],
    calibrated_returns: tuple[dict[str, object], ...],
    prior_book: dict[str, object],
    control_settings: dict[str, object],
    covariance: dict[str, object] | None,
    cost_liquidity: dict[str, object] | None,
    source_hashes: dict[str, object],
) -> dict[str, object]:
    """Build order-independent bundle hash input keyed by ticker."""
    mandate_by_ticker = {str(m["ticker"]): m for m in mandates}
    calibrated_by_ticker = {str(c["ticker"]): c for c in calibrated_returns}
    assets: dict[str, object] = {}
    for ticker in sorted(canonical_asset_order):
        mandate = mandate_by_ticker[ticker]
        calibrated = calibrated_by_ticker[ticker]
        assets[ticker] = {
            "mandate": {
                "direction": mandate["direction"],
                "conviction_rank": mandate["conviction_rank"],
                "effective_forecast_id": mandate.get("effective_forecast_id"),
                "forecast_reference_hash": mandate.get("forecast_reference_hash"),
                "degradation_reason": mandate.get("degradation_reason"),
            },
            "calibrated": calibrated_slice_hash_payload(calibrated),
        }
    covariance_payload = covariance
    if covariance is not None and "tickers" in covariance:
        covariance_payload = {
            **covariance,
            "tickers": sorted(covariance["tickers"]),
        }
    source_payload = source_hashes
    if source_hashes:
        source_payload = dict(source_hashes)
        if "calibrated_hashes" in source_payload:
            source_payload["calibrated_hashes"] = sorted(source_payload["calibrated_hashes"])
        if "cost_hashes" in source_payload:
            source_payload["cost_hashes"] = sorted(source_payload["cost_hashes"])
    cost_payload = cost_liquidity
    if cost_liquidity is not None and "entries" in cost_liquidity:
        cost_payload = {
            **cost_liquidity,
            "entries": sorted(cost_liquidity["entries"]),
        }
    return {
        "schema_version": schema_version,
        "run": run,
        "assets": assets,
        "prior_book": prior_book,
        "control_settings": control_settings,
        "covariance": covariance_payload,
        "cost_liquidity": cost_payload,
        "source_hashes": source_payload,
    }


def pretrade_risk_report_content_hash(*, payload: dict[str, Any]) -> str:
    """SHA-256 over canonical pre-trade risk report identity fields."""
    return sha256_hex(payload)


def pretrade_risk_report_hash_payload(
    *,
    schema_version: str,
    run_id: str,
    session_date: str,
    status: str,
    unavailable_reason: str | None,
    allocation_input_bundle_hash: str,
    final_book_weights_fingerprint: str,
    prior_weights: dict[str, object],
    final_weights: dict[str, object],
    trade_deltas: tuple[dict[str, object], ...] | list[dict[str, object]],
    exposures: dict[str, object],
    portfolio_risk: dict[str, object],
    concentration: dict[str, object],
    name_sector_factor_scenario: dict[str, object],
    cost_liquidity: dict[str, object],
    forecast_quality: dict[str, object],
    controls: dict[str, object],
    risk_policy_hash: str,
    covariance_hash: str | None,
) -> dict[str, object]:
    """Build order-independent report hash input."""
    trade_by_ticker = {str(row["ticker"]): row for row in trade_deltas}
    contributions = portfolio_risk.get("contributions", ())
    contrib_by_ticker = {str(row["ticker"]): row for row in contributions}
    binding = controls.get("binding_constraints", ())
    altered = controls.get("altered_targets", ())
    rejected = controls.get("rejected_targets", ())
    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "session_date": session_date,
        "status": status,
        "unavailable_reason": unavailable_reason,
        "allocation_input_bundle_hash": allocation_input_bundle_hash,
        "final_book_weights_fingerprint": final_book_weights_fingerprint,
        "prior_weights": prior_weights,
        "final_weights": final_weights,
        "trade_deltas": {ticker: trade_by_ticker[ticker] for ticker in sorted(trade_by_ticker)},
        "exposures": exposures,
        "portfolio_risk": {
            "variance": portfolio_risk.get("variance"),
            "volatility_annualized_pct": portfolio_risk.get("volatility_annualized_pct"),
            "contributions": {
                ticker: contrib_by_ticker[ticker] for ticker in sorted(contrib_by_ticker)
            },
        },
        "concentration": concentration,
        "name_sector_factor_scenario": name_sector_factor_scenario,
        "cost_liquidity": cost_liquidity,
        "forecast_quality": forecast_quality,
        "controls": {
            "binding_constraints": sorted(
                binding,
                key=lambda row: (
                    str(row.get("constraint_id", "")),
                    str(row.get("ticker") or ""),
                ),
            ),
            "altered_targets": {
                str(row["ticker"]): row for row in sorted(altered, key=lambda r: str(r["ticker"]))
            },
            "rejected_targets": {
                str(row["ticker"]): row for row in sorted(rejected, key=lambda r: str(r["ticker"]))
            },
        },
        "risk_policy_hash": risk_policy_hash,
        "covariance_hash": covariance_hash,
    }


def shadow_allocation_artifact_content_hash(*, payload: dict[str, Any]) -> str:
    """SHA-256 over canonical shadow allocation artifact identity fields."""
    return sha256_hex(payload)


def shadow_allocation_artifact_hash_payload(
    *,
    schema_version: str,
    run_id: str,
    session_date: str,
    commit_id: str | None,
    commit_status: str | None,
    allocation_input_bundle_hash: str,
    pre_trade_risk_report_hash: str,
    incumbent_final_weights_fingerprint: str,
) -> dict[str, object]:
    """Build order-independent shadow artifact hash input.

    Nested bundle/report bodies are bound by their content hashes only — the
    artifact identity must not embed prose, clients, or secrets.
    """
    return {
        "schema_version": schema_version,
        "run_id": run_id,
        "session_date": session_date,
        "commit_id": commit_id,
        "commit_status": commit_status,
        "allocation_input_bundle_hash": allocation_input_bundle_hash,
        "pre_trade_risk_report_hash": pre_trade_risk_report_hash,
        "incumbent_final_weights_fingerprint": incumbent_final_weights_fingerprint,
    }


__all__ = [
    "allocation_bundle_content_hash",
    "allocation_bundle_hash_payload",
    "calibrated_slice_hash_payload",
    "canonical_json",
    "h7_memo_hash_payload",
    "pretrade_risk_report_content_hash",
    "pretrade_risk_report_hash_payload",
    "prior_weights_from_entries",
    "sha256_hex",
    "shadow_allocation_artifact_content_hash",
    "shadow_allocation_artifact_hash_payload",
    "weights_fingerprint",
]
