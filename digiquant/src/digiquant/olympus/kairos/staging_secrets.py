"""Kairos staging E2E — required secret inventory (names only; never log values).

Agent-runnable probes (``scripts/kairos_staging_e2e.py``,
``tests/dq/olympus/kairos/test_staging_e2e.py``) call
:func:`missing_kairos_staging_secrets` and **fail loudly** with the returned
names when any required vendor secret is empty. They must never substitute
fakes for Stripe / Mailgun / Alpaca OAuth and claim staging E2E pass.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Ordered for human/agent checklists — keep in sync with
# docs/agent-backlog/kairos-tenancy/HUMAN-UNBLOCK.md and WAITING-ON-SECRETS.json.
KAIROS_STAGING_REQUIRED_SECRETS: tuple[str, ...] = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_BASELINE_MONTHLY",
    "STRIPE_PRICE_CUSTOM_MONTHLY",
    "MAILGUN_API_KEY",
    "MAILGUN_DOMAIN",
    "NOTIFY_FROM",
    "ALPACA_OAUTH_CLIENT_ID",
    "ALPACA_OAUTH_CLIENT_SECRET",
)

# Optional for signup path variety — Google Auth still Disabled on core.
KAIROS_STAGING_OPTIONAL_SECRETS: tuple[str, ...] = (
    "STRIPE_PRICE_BASELINE_ANNUAL",
    "STRIPE_PRICE_CUSTOM_ANNUAL",
    "AUTH_GOOGLE_CLIENT_ID",
    "AUTH_GOOGLE_CLIENT_SECRET",
    "SUPABASE_ACCESS_TOKEN",
)

# Runtime knobs for the live hops (not vendor secrets, but required when running).
KAIROS_STAGING_RUNTIME_ENV: tuple[str, ...] = (
    "CORE_SUPABASE_URL",
    "CORE_SUPABASE_ANON_KEY",
    "KAIROS_STAGING_USER_JWT",
)


def _nonempty(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.upper() not in {"EMPTY", "NULL", "NONE", "UNDEFINED", "***"}


def missing_kairos_staging_secrets(
    environ: Mapping[str, str] | None = None,
    *,
    include_runtime: bool = False,
) -> list[str]:
    """Return required secret *names* that are missing/empty (never values)."""
    env = os.environ if environ is None else environ
    names = list(KAIROS_STAGING_REQUIRED_SECRETS)
    if include_runtime:
        names.extend(KAIROS_STAGING_RUNTIME_ENV)
    return [name for name in names if not _nonempty(env.get(name))]


def format_missing_secrets_failure(missing: list[str]) -> str:
    """Single-line failure message for pytest / CLI (names only)."""
    joined = ", ".join(missing)
    return (
        "Kairos staging E2E blocked — missing required secrets: "
        f"{joined}. Paste into Cursor Cloud env + core EF secrets; "
        "do not fake Stripe/Mailgun/Alpaca OAuth."
    )


__all__ = [
    "KAIROS_STAGING_OPTIONAL_SECRETS",
    "KAIROS_STAGING_REQUIRED_SECRETS",
    "KAIROS_STAGING_RUNTIME_ENV",
    "format_missing_secrets_failure",
    "missing_kairos_staging_secrets",
]
