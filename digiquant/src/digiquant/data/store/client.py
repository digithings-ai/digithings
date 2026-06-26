"""Thin client factory for the DigiQuant strategy store (#1064).

The strategy store lives in the unified DigiQuant **"core"** project — the project
historically used by Olympus/Atlas (`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`),
repurposed as the suite-wide shared backend (free-tier 2-project limit; see
``docs/adr/0021-digiquant-supabase-project-topology.md``).

Credential resolution uses the standardized ``CORE_SUPABASE_*`` names (#1090) first,
then the legacy ``_DIGIQUANT``-suffixed vars (#1064), then the original shared
``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY`` — read-new-fall-back-to-old so a
half-migrated environment keeps working until the legacy names are dropped.
"""

from __future__ import annotations

import os
from typing import Any, Protocol  # noqa: ANN401 — SupabaseLike.table returns the driver's dynamic type

CORE_URL_ENV = "CORE_SUPABASE_URL"
CORE_SERVICE_KEY_ENV = "CORE_SUPABASE_SERVICE_KEY"
SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
DIGIQUANT_URL_ENV = "SUPABASE_URL_DIGIQUANT"  # legacy (pre-#1090)
DIGIQUANT_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY_DIGIQUANT"  # legacy (pre-#1090)


class SupabaseLike(Protocol):
    """Structural type matching both ``supabase.Client`` and test fakes."""

    def table(self, name: str) -> Any:  # pragma: no cover - protocol
        ...


def _first_env(*names: str) -> str | None:
    """Return the first env var that is set to a non-blank value, else ``None``."""
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def digiquant_credentials() -> tuple[str | None, str | None]:
    """Return ``(url, service_key)`` for the DigiQuant ``core`` project.

    Resolution order (#1090): ``CORE_SUPABASE_*`` → legacy ``*_DIGIQUANT`` → original
    ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY``. Blank values normalize to ``None``
    so callers get a single, unambiguous "creds missing" signal.
    """
    url = _first_env(CORE_URL_ENV, DIGIQUANT_URL_ENV, SUPABASE_URL_ENV)
    key = _first_env(
        CORE_SERVICE_KEY_ENV, DIGIQUANT_SERVICE_ROLE_KEY_ENV, SUPABASE_SERVICE_ROLE_KEY_ENV
    )
    return url, key


def build_digiquant_client():  # pragma: no cover - thin wrapper over supabase SDK
    """Build a service-role client for the DigiQuant ``core`` project.

    Returns ``None`` when either credential is missing (matches the legacy
    ``build_supabase_client`` contract so callers can fail soft).
    """
    url, key = digiquant_credentials()
    if not url or not key:
        return None
    from supabase import create_client  # type: ignore[import-not-found]

    return create_client(url, key)


__all__ = [
    "CORE_SERVICE_KEY_ENV",
    "CORE_URL_ENV",
    "DIGIQUANT_SERVICE_ROLE_KEY_ENV",
    "DIGIQUANT_URL_ENV",
    "SUPABASE_SERVICE_ROLE_KEY_ENV",
    "SUPABASE_URL_ENV",
    "SupabaseLike",
    "build_digiquant_client",
    "digiquant_credentials",
]
