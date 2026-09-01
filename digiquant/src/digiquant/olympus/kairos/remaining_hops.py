"""Named EPIC.md staging hops that Settings reads can prove or leave unproven.

Exit 0 is allowed only when every hop here is proven from product state:

- Stripe: ``subscription_status=active`` **and** ``has_stripe_subscription``
  **and** ``plan_tier`` in ``{custom, enterprise}``. House is seeded
  ``enterprise``/``active`` without Stripe ids — that must not prove checkout.
  A Baseline Stripe subscription also must not: broker connect and overlay
  stay ``TIER_FORBIDDEN``. Ops grants with ``subscription_status=none`` do not.
- Alpaca: paper connection ``active`` with ``auth_kind=oauth``.
- Overlay: ``job_type=overlay_daily`` with status ``succeeded`` (not
  ``running`` / ``skipped`` / ``persist_disabled`` / ``not_entitled``). A
  stuck claim, persist-disabled finish, or ``legacy_book_unique`` fail
  (cutover 113 not applied) must not prove the EPIC overlay hop.
- Fill: at least one fingerprint with a symbol **and** an Alpaca paper
  ``auth_kind=oauth`` connection. An ``api_key`` row with fills must not prove
  the hop.
- Digest: a ``digest:`` notification_log key **and** an inbox confirmation
  (claim-ledger rows are inserted before Mailgun send) **and** the workspace
  ``daily_digest`` pref enabled. Dispatch skips prefs that are off.

Unproven hops carry a closed-vocabulary blocker code (never Stripe ids,
emails, or secrets) so Settings About and the staging harness can surface
the human-owned gate without claiming the hop.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.overlay.persist import LEGACY_BOOK_UNIQUE_CODE

REMAINING_LIVE_HOPS: tuple[str, ...] = (
    "browser_stripe_checkout",
    "alpaca_paper_oauth_connect",
    "overlay_daily_claimed",
    "paper_fill_mirrored",
    "digest_email_received",
)
EXIT_REMAINING_HOPS_UNPROVEN: int = 4
OVERLAY_RUN_STATUSES: frozenset[str] = frozenset({"succeeded"})
STRIPE_CHECKOUT_TIERS: frozenset[str] = frozenset({"custom", "enterprise"})
REMAINING_HOP_BLOCKER_CODES: tuple[str, ...] = (
    "plan_tier_not_custom",
    "missing_stripe_ids",
    "subscription_not_active",
    "alpaca_api_key_not_oauth",
    "no_alpaca_paper_oauth",
    "overlay_persist_disabled",
    "overlay_legacy_book_unique",
    "overlay_not_succeeded",
    "fill_without_oauth",
    "no_paper_fill",
    "digest_pref_off",
    "no_digest_log",
    "digest_inbox_unconfirmed",
)


class RemainingHopEvidence(BaseModel):
    """Sanitized Settings snapshots used to mark remaining hops proven."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subscription_status: str | None = None
    has_stripe_subscription: bool = False
    plan_tier: str | None = None
    connections: tuple[tuple[str, str, str, str], ...] = Field(default_factory=tuple)
    jobs: tuple[tuple[str, str], ...] = Field(default_factory=tuple)
    overlay_job_errors: tuple[str, ...] = Field(default_factory=tuple)
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


def _alpaca_paper_oauth(evidence: RemainingHopEvidence) -> bool:
    return any(
        broker == "alpaca" and env == "paper" and status == "active" and auth_kind == "oauth"
        for broker, env, status, auth_kind in evidence.connections
    )


def _alpaca_paper_api_key(evidence: RemainingHopEvidence) -> bool:
    return any(
        broker == "alpaca" and env == "paper" and status == "active" and auth_kind == "api_key"
        for broker, env, status, auth_kind in evidence.connections
    )


def _digest_log(evidence: RemainingHopEvidence) -> bool:
    return any(key.startswith("digest:") for key in evidence.digest_event_keys)


def proven_remaining_hops(evidence: RemainingHopEvidence) -> dict[str, bool]:
    """Map each remaining hop to whether product state proves it."""
    alpaca = _alpaca_paper_oauth(evidence)
    overlay = any(
        job_type == "overlay_daily" and status in OVERLAY_RUN_STATUSES
        for job_type, status in evidence.jobs
    )
    digest_log = _digest_log(evidence)
    return {
        "browser_stripe_checkout": (
            evidence.subscription_status == "active"
            and evidence.has_stripe_subscription
            and evidence.plan_tier in STRIPE_CHECKOUT_TIERS
        ),
        "alpaca_paper_oauth_connect": alpaca,
        "overlay_daily_claimed": overlay,
        "paper_fill_mirrored": evidence.fill_count > 0 and alpaca,
        "digest_email_received": (
            evidence.digest_inbox_confirmed and digest_log and evidence.daily_digest_enabled
        ),
    }


def remaining_hop_blockers(evidence: RemainingHopEvidence) -> dict[str, str]:
    """Closed-vocabulary reasons for unproven hops. Proven hops are omitted.

    Codes never include Stripe ids, emails, or secret values. Settings About
    and the staging harness print these next to ``proven=false``.
    """
    proven = proven_remaining_hops(evidence)
    blockers: dict[str, str] = {}
    if not proven["browser_stripe_checkout"]:
        if evidence.plan_tier not in STRIPE_CHECKOUT_TIERS:
            blockers["browser_stripe_checkout"] = "plan_tier_not_custom"
        elif not evidence.has_stripe_subscription:
            blockers["browser_stripe_checkout"] = "missing_stripe_ids"
        else:
            blockers["browser_stripe_checkout"] = "subscription_not_active"
    if not proven["alpaca_paper_oauth_connect"]:
        blockers["alpaca_paper_oauth_connect"] = (
            "alpaca_api_key_not_oauth"
            if _alpaca_paper_api_key(evidence)
            else "no_alpaca_paper_oauth"
        )
    if not proven["overlay_daily_claimed"]:
        overlay_statuses = {
            status for job_type, status in evidence.jobs if job_type == "overlay_daily"
        }
        if "persist_disabled" in overlay_statuses:
            blockers["overlay_daily_claimed"] = "overlay_persist_disabled"
        elif LEGACY_BOOK_UNIQUE_CODE in evidence.overlay_job_errors:
            blockers["overlay_daily_claimed"] = "overlay_legacy_book_unique"
        else:
            blockers["overlay_daily_claimed"] = "overlay_not_succeeded"
    if not proven["paper_fill_mirrored"]:
        blockers["paper_fill_mirrored"] = (
            "fill_without_oauth" if evidence.fill_count > 0 else "no_paper_fill"
        )
    if not proven["digest_email_received"]:
        if not evidence.daily_digest_enabled:
            blockers["digest_email_received"] = "digest_pref_off"
        elif not _digest_log(evidence):
            blockers["digest_email_received"] = "no_digest_log"
        else:
            blockers["digest_email_received"] = "digest_inbox_unconfirmed"
    return blockers


__all__ = [
    "EXIT_REMAINING_HOPS_UNPROVEN",
    "OVERLAY_RUN_STATUSES",
    "REMAINING_HOP_BLOCKER_CODES",
    "REMAINING_LIVE_HOPS",
    "STRIPE_CHECKOUT_TIERS",
    "RemainingHopEvidence",
    "format_remaining_hops_failure",
    "proven_remaining_hops",
    "remaining_hop_blockers",
    "remaining_hops_unproven",
]
