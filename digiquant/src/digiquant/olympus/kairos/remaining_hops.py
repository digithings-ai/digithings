"""Named EPIC.md staging hops that Settings reads can prove or leave unproven.

Exit 0 is allowed only when every hop here is proven from product state
(Stripe ``subscription_status=active``, Alpaca paper connection, overlay
``job_runs`` succeeded/running, a broker fill, a digest event key). Ops grants
with ``subscription_status=none`` do not prove checkout.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

REMAINING_LIVE_HOPS: tuple[str, ...] = (
    "browser_stripe_checkout",
    "alpaca_paper_oauth_connect",
    "overlay_daily_claimed",
    "paper_fill_mirrored",
    "digest_email_received",
)
EXIT_REMAINING_HOPS_UNPROVEN: int = 4
OVERLAY_RUN_STATUSES: frozenset[str] = frozenset({"running", "succeeded"})


class RemainingHopEvidence(BaseModel):
    """Sanitized Settings snapshots used to mark remaining hops proven."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subscription_status: str | None = None
    connections: tuple[tuple[str, str, str], ...] = Field(default_factory=tuple)
    jobs: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    fill_count: int = 0
    digest_event_keys: tuple[str, ...] = Field(default_factory=tuple)


def remaining_hops_unproven(proven: Mapping[str, object] | None = None) -> tuple[str, ...]:
    """Return remaining live hops that have not been marked proven."""
    done = proven or {}
    return tuple(name for name in REMAINING_LIVE_HOPS if not done.get(name))


def format_remaining_hops_failure(unproven: Sequence[str]) -> str:
    return f"KAIROS_STAGING_E2E_REMAINING_HOPS: {', '.join(unproven)}"


def proven_remaining_hops(evidence: RemainingHopEvidence) -> dict[str, bool]:
    """Map each remaining hop to whether product state proves it."""
    alpaca = any(
        broker == "alpaca" and env == "paper" and status == "active"
        for broker, env, status in evidence.connections
    )
    overlay = any(
        job_type == "overlay_daily" and status in OVERLAY_RUN_STATUSES
        for job_type, status in evidence.jobs
    )
    digest = any(key.startswith("digest:") for key in evidence.digest_event_keys)
    return {
        "browser_stripe_checkout": evidence.subscription_status == "active",
        "alpaca_paper_oauth_connect": alpaca,
        "overlay_daily_claimed": overlay,
        "paper_fill_mirrored": evidence.fill_count > 0,
        "digest_email_received": digest,
    }


__all__ = [
    "EXIT_REMAINING_HOPS_UNPROVEN",
    "OVERLAY_RUN_STATUSES",
    "REMAINING_LIVE_HOPS",
    "RemainingHopEvidence",
    "format_remaining_hops_failure",
    "proven_remaining_hops",
    "remaining_hops_unproven",
]
