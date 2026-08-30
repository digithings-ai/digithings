"""Named EPIC.md staging hops that Settings reads can prove or leave unproven.

Exit 0 is allowed only when every hop here is proven from product state:

- Stripe: ``subscription_status=active`` **and** ``has_stripe_subscription``
  (workspace has a Stripe subscription id; the id is never returned). House is
  seeded ``enterprise``/``active`` without Stripe ids — that must not prove
  checkout. Ops grants with ``subscription_status=none`` also do not.
- Alpaca: paper connection ``active`` with ``auth_kind=oauth``.
- Overlay: ``job_type=overlay_daily`` with status ``succeeded`` (not
  ``running`` / ``skipped`` / ``persist_disabled`` / ``not_entitled``). A
  stuck claim or persist-disabled finish must not prove the EPIC overlay hop.
- Fill: at least one fingerprint with a symbol **and** an Alpaca paper
  ``auth_kind=oauth`` connection. An ``api_key`` row with fills must not prove
  the hop.
- Digest: a ``digest:`` notification_log key **and** an inbox confirmation
  (claim-ledger rows are inserted before Mailgun send) **and** the workspace
  ``daily_digest`` pref enabled. Dispatch skips prefs that are off.
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
OVERLAY_RUN_STATUSES: frozenset[str] = frozenset({"succeeded"})


class RemainingHopEvidence(BaseModel):
    """Sanitized Settings snapshots used to mark remaining hops proven."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subscription_status: str | None = None
    has_stripe_subscription: bool = False
    connections: tuple[tuple[str, str, str, str], ...] = Field(default_factory=tuple)
    jobs: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    fill_count: int = 0
    digest_event_keys: tuple[str, ...] = Field(default_factory=tuple)
    digest_inbox_confirmed: bool = False
    daily_digest_enabled: bool = False
    surface_http_ok: bool = True


def remaining_hops_unproven(proven: Mapping[str, object] | None = None) -> tuple[str, ...]:
    """Return remaining live hops that have not been marked proven."""
    done = proven or {}
    return tuple(name for name in REMAINING_LIVE_HOPS if not done.get(name))


def format_remaining_hops_failure(unproven: Sequence[str]) -> str:
    return f"KAIROS_STAGING_E2E_REMAINING_HOPS: {', '.join(unproven)}"


def proven_remaining_hops(evidence: RemainingHopEvidence) -> dict[str, bool]:
    """Map each remaining hop to whether product state proves it."""
    alpaca = any(
        broker == "alpaca" and env == "paper" and status == "active" and auth_kind == "oauth"
        for broker, env, status, auth_kind in evidence.connections
    )
    overlay = any(
        job_type == "overlay_daily" and status in OVERLAY_RUN_STATUSES
        for job_type, status in evidence.jobs
    )
    digest_log = any(key.startswith("digest:") for key in evidence.digest_event_keys)
    return {
        "browser_stripe_checkout": (
            evidence.subscription_status == "active" and evidence.has_stripe_subscription
        ),
        "alpaca_paper_oauth_connect": alpaca,
        "overlay_daily_claimed": overlay,
        "paper_fill_mirrored": evidence.fill_count > 0 and alpaca,
        "digest_email_received": (
            evidence.digest_inbox_confirmed and digest_log and evidence.daily_digest_enabled
        ),
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
