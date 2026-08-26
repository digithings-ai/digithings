"""WP16.3 — allowlisted registered policy resolution (#2987).

Resolves only :class:`~digiquant.olympus.replay.models.PolicyVersionRef`
entries registered in-memory (or injected store). Cutoff-bound reads filter
``known_at <= replay_as_of``. Missing research output is typed unavailable —
never fabricate H5/H6 counterfactuals. No network/provider calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from digiquant.olympus.replay.models import (
    POLICY_BUNDLE_FIELD_NAMES,
    PolicyBundle,
    PolicyFamily,
    PolicyVersionRef,
)
from digiquant.olympus.temporal import require_utc_datetime

__all__ = [
    "PolicyRegistry",
    "PolicyRegistryError",
    "PolicyRegistryMissingError",
    "PolicyRegistryUnavailableError",
    "RegisteredPolicyVersion",
]


class PolicyRegistryError(RuntimeError):
    """Registry refused resolution or registration."""


class PolicyRegistryMissingError(PolicyRegistryError, LookupError):
    """Exact registered version not found at cutoff."""


class PolicyRegistryUnavailableError(PolicyRegistryError):
    """Registered policy exists but declares unavailable research output."""


@dataclass(frozen=True)
class RegisteredPolicyVersion:
    """One immutable registered policy version with cutoff visibility."""

    family: PolicyFamily
    version_id: str
    content_hash: str
    known_at: datetime
    payload: dict[str, Any]  # score:allow untyped any — normalized policy JSON body
    review_required: bool = False

    def __post_init__(self) -> None:
        require_utc_datetime(self.known_at, field_name="known_at")


def _registry_key(family: PolicyFamily, version_id: str) -> tuple[str, str]:
    return (family.value, version_id)


def _payload_unavailable(payload: dict[str, Any]) -> str | None:
    status = payload.get("status")
    if status == "unavailable":
        reason = payload.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
        return "unavailable"
    return None


class PolicyRegistry:
    """In-memory allowlisted policy registry (fail closed)."""

    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], RegisteredPolicyVersion] = {}

    def register(self, version: RegisteredPolicyVersion) -> None:
        """Register one policy version; identical re-register is a no-op."""
        key = _registry_key(version.family, version.version_id)
        existing = self._versions.get(key)
        if existing is not None:
            if existing.content_hash == version.content_hash:
                return
            raise PolicyRegistryError(
                f"policy conflict for {version.family.value}/{version.version_id}"
            )
        self._versions[key] = version

    def resolve(
        self,
        ref: PolicyVersionRef,
        *,
        replay_as_of: datetime,
        review_pinned: bool = False,
    ) -> RegisteredPolicyVersion:
        """Resolve an exact registered ref visible at *replay_as_of*."""
        cutoff = require_utc_datetime(replay_as_of, field_name="replay_as_of")
        key = _registry_key(ref.family, ref.version_id)
        version = self._versions.get(key)
        if version is None:
            raise PolicyRegistryMissingError(
                f"unregistered policy {ref.family.value}/{ref.version_id}"
            )
        if version.review_required and not review_pinned:
            raise PolicyRegistryError(
                f"review-required policy {ref.family.value}/{ref.version_id} "
                "must be explicitly pinned"
            )
        if version.content_hash != ref.content_hash:
            raise PolicyRegistryError(
                f"content_hash mismatch for {ref.family.value}/{ref.version_id}"
            )
        if version.known_at > cutoff:
            raise PolicyRegistryError(
                f"future policy evidence for {ref.family.value}/{ref.version_id}"
            )
        unavailable = _payload_unavailable(version.payload)
        if unavailable is not None:
            raise PolicyRegistryUnavailableError(unavailable)
        return version

    def resolve_bundle(
        self,
        bundle: PolicyBundle,
        *,
        replay_as_of: datetime,
    ) -> dict[str, RegisteredPolicyVersion]:
        """Resolve every declared arm policy mode in *bundle*."""
        resolved: dict[str, RegisteredPolicyVersion] = {}
        for field_name in POLICY_BUNDLE_FIELD_NAMES:
            ref = getattr(bundle, field_name)
            if ref is None:
                continue
            resolved[field_name] = self.resolve(
                ref,
                replay_as_of=replay_as_of,
                review_pinned=True,
            )
        return resolved
