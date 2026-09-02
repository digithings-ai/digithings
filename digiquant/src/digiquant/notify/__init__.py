"""Email notifications v0 (K5) — Mailgun digest, holding-change, execution alerts."""

from digiquant.notify.dispatch import dispatch_execution_alerts, dispatch_notifications, main
from digiquant.notify.entitlements import (
    ArtifactClass,
    PlanTier,
    can,
    required_tier_for,
)

__all__ = [
    "ArtifactClass",
    "PlanTier",
    "can",
    "dispatch_execution_alerts",
    "dispatch_notifications",
    "main",
    "required_tier_for",
]
