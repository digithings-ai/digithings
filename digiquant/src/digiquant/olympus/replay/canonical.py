"""WP16.1 — canonical SHA-256 digests for policy replay manifests (#2979).

Centralizes stable hashing for shared replay inputs. Reuses
:func:`digiquant.olympus.hermes.allocation_hashes.sha256_hex` so portfolio
shadow comparison and policy replay share one dialect.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.replay.models import (
    POLICY_BUNDLE_FIELD_NAMES,
    ExecutionPolicy,
    InstrumentBarSeries,
    PolicyBundle,
    PolicyVersionRef,
    PortfolioReplayRequest,
    ReplayArmSpec,
    ReplayInputManifest,
    ReplayPairSpec,
    SharedInputIdentity,
    WalkForwardFold,
)

__all__ = [
    "cost_hash_from_execution",
    "data_hash_from_request",
    "data_hash_from_series",
    "execution_policy_hash",
    "fill_fraction_hash",
    "policy_bundle_content_hash",
    "random_seed_hash",
    "replay_arm_content_hash",
    "replay_input_manifest_content_hash",
    "replay_pair_content_hash",
    "shared_input_identity_hash",
    "walk_forward_fold_content_hash",
]


def execution_policy_hash(execution: ExecutionPolicy) -> str:
    """Stable digest of execution assumptions (venue, timing, commission, fill, seed)."""
    return sha256_hex(execution.model_dump(mode="json"))


def cost_hash_from_execution(execution: ExecutionPolicy) -> str:
    """Cost schedule identity derived from commission rate."""
    return sha256_hex({"commission_rate": str(execution.commission_rate)})


def fill_fraction_hash(fill_fraction: Decimal) -> str:
    """Fill-policy identity for partial-fill assumptions."""
    return sha256_hex({"fill_fraction": str(fill_fraction)})


def random_seed_hash(seed: int) -> str:
    """Deterministic seed identity (never Python ``hash()``)."""
    return sha256_hex({"random_seed": seed})


def data_hash_from_series(series: tuple[InstrumentBarSeries, ...]) -> str:
    """Market-data identity from synchronized bar series only."""
    payload = {"series": [s.model_dump(mode="json") for s in series]}
    return sha256_hex(payload)


def data_hash_from_request(request: PortfolioReplayRequest) -> str:
    """Market-data identity from one portfolio replay request."""
    return data_hash_from_series(request.series)


def shared_input_identity_hash(shared: SharedInputIdentity) -> str:
    """Digest of cross-arm shared inputs (excludes manifest hash field)."""
    return sha256_hex(
        {
            "data_hash": shared.data_hash,
            "cost_hash": shared.cost_hash,
            "execution_hash": shared.execution_hash,
            "random_seed_hash": shared.random_seed_hash,
            "fill_fraction_hash": shared.fill_fraction_hash,
            "starting_cash": shared.starting_cash,
        }
    )


def policy_version_ref_content_hash(ref: PolicyVersionRef) -> str:
    """Digest of one registered policy version reference."""
    return sha256_hex(
        {
            "family": ref.family.value,
            "version_id": ref.version_id,
            "content_hash": ref.content_hash,
        }
    )


def policy_bundle_content_hash(
    bundle: PolicyBundle,
    *,
    weights_fingerprint: str,
) -> str:
    """Digest of arm-specific policy refs plus weights fingerprint."""
    payload: dict[str, object] = {"weights_fingerprint": weights_fingerprint}
    for field_name in POLICY_BUNDLE_FIELD_NAMES:
        ref = getattr(bundle, field_name)
        if ref is not None:
            payload[field_name] = policy_version_ref_content_hash(ref)
    return sha256_hex(payload)


def walk_forward_fold_content_hash(fold: WalkForwardFold) -> str:
    """Digest of one walk-forward fold definition."""
    return sha256_hex(fold.model_dump(mode="json"))


def replay_input_manifest_content_hash(
    *,
    manifest_id: str,
    replay_as_of: datetime,
    shared: SharedInputIdentity,
    source_refs: tuple[PolicyVersionRef, ...],
    dataset_content_hash: str,
    fold: WalkForwardFold | None,
) -> str:
    """Digest of pinned replay inputs (excludes ``manifest_content_hash`` itself)."""
    payload = {
        "manifest_id": manifest_id,
        "replay_as_of": replay_as_of.isoformat(),
        "shared": shared.model_dump(mode="json"),
        "source_refs": [
            {
                "family": ref.family.value,
                "version_id": ref.version_id,
                "content_hash": ref.content_hash,
            }
            for ref in source_refs
        ],
        "dataset_content_hash": dataset_content_hash,
        "fold": fold.model_dump(mode="json") if fold is not None else None,
    }
    return sha256_hex(payload)


def replay_arm_content_hash(arm: ReplayArmSpec) -> str:
    """Digest of one replay arm spec (excludes ``arm_content_hash`` itself)."""
    return sha256_hex(
        {
            "arm": arm.arm.value,
            "arm_id": arm.arm_id,
            "manifest_content_hash": arm.manifest_content_hash,
            "policy_bundle": policy_bundle_content_hash(
                arm.policy_bundle,
                weights_fingerprint=arm.weights_fingerprint,
            ),
            "weights_fingerprint": arm.weights_fingerprint,
        }
    )


def replay_pair_content_hash(
    *,
    pair_id: str,
    shared_manifest: ReplayInputManifest,
    incumbent: ReplayArmSpec,
    challenger: ReplayArmSpec,
) -> str:
    """Digest of one paired replay specification."""
    return sha256_hex(
        {
            "pair_id": pair_id,
            "shared_manifest_content_hash": shared_manifest.manifest_content_hash,
            "incumbent": replay_arm_content_hash(incumbent),
            "challenger": replay_arm_content_hash(challenger),
        }
    )


def replay_pair_content_hash_from_spec(pair: ReplayPairSpec) -> str:
    """Digest helper when the pair model is already validated."""
    return replay_pair_content_hash(
        pair_id=pair.pair_id,
        shared_manifest=pair.shared_manifest,
        incumbent=pair.incumbent,
        challenger=pair.challenger,
    )
