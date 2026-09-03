"""Staging E2E — required secret inventory (names only; never log values).

Agent-runnable probes (``scripts/digiquant_staging_e2e.py``,
``tests/dq/dashboard/execution/test_staging_e2e.py``) call
:func:`missing_execution_staging_secrets` and **fail loudly** with the returned
names when any required vendor secret is empty. They must never substitute
fakes for Stripe / Mailgun / Alpaca OAuth and claim staging E2E pass.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from digiquant.dashboard.envcompat import STAGING_USER_JWT, env_lookup

# Ordered for human/agent checklists — keep in sync with
# docs/agent-backlog/kairos-tenancy/HUMAN-UNBLOCK.md and WAITING-ON-SECRETS.json.
STAGING_REQUIRED_SECRETS: tuple[str, ...] = (
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_BRIEF_MONTHLY",
    "STRIPE_PRICE_DESK_MONTHLY",
    "STRIPE_PRICE_STUDIO_MONTHLY",
    "MAILGUN_API_KEY",
    "MAILGUN_DOMAIN",
    "NOTIFY_FROM",
    "ALPACA_OAUTH_CLIENT_ID",
    "ALPACA_OAUTH_CLIENT_SECRET",
)

# Optional for signup path variety — Google Auth still Disabled on core.
STAGING_OPTIONAL_SECRETS: tuple[str, ...] = (
    "STRIPE_PRICE_BRIEF_ANNUAL",
    "STRIPE_PRICE_DESK_ANNUAL",
    "STRIPE_PRICE_STUDIO_ANNUAL",
    "AUTH_GOOGLE_CLIENT_ID",
    "AUTH_GOOGLE_CLIENT_SECRET",
    "SUPABASE_ACCESS_TOKEN",
)

# Runtime knobs for the live hops (not vendor secrets, but required when running).
STAGING_RUNTIME_ENV: tuple[str, ...] = (
    "CORE_SUPABASE_URL",
    "CORE_SUPABASE_ANON_KEY",
    STAGING_USER_JWT,
)


def _nonempty(value: str | None) -> bool:
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return stripped.upper() not in {"EMPTY", "NULL", "NONE", "UNDEFINED", "***"}


def missing_execution_staging_secrets(
    environ: Mapping[str, str] | None = None,
    *,
    include_runtime: bool = False,
) -> list[str]:
    """Return required secret *names* that are missing/empty (never values)."""
    env = os.environ if environ is None else environ
    names = list(STAGING_REQUIRED_SECRETS)
    if include_runtime:
        names.extend(STAGING_RUNTIME_ENV)
    missing: list[str] = []
    for name in names:
        if name == STAGING_USER_JWT:
            if not _nonempty(env_lookup(STAGING_USER_JWT, environ=env)):
                missing.append(name)
            continue
        if not _nonempty(env.get(name)):
            missing.append(name)
    return missing


def format_missing_secrets_failure(missing: list[str]) -> str:
    """Single-line failure message for pytest / CLI (names only)."""
    joined = ", ".join(missing)
    return (
        "digiquant staging E2E blocked — missing required secrets: "
        f"{joined}. Paste into Cursor Cloud env + core EF secrets; "
        "do not fake Stripe/Mailgun/Alpaca OAuth."
    )


__all__ = [
    "STAGING_OPTIONAL_SECRETS",
    "STAGING_REQUIRED_SECRETS",
    "STAGING_RUNTIME_ENV",
    "format_missing_secrets_failure",
    "missing_execution_staging_secrets",
]
