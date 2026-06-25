"""Thin client factory for the DigiQuant strategy store (#1064).

The strategy store lives in the unified DigiQuant **"core"** project — the project
historically used by Olympus/Atlas (`SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`),
repurposed as the suite-wide shared backend (free-tier 2-project limit; see
``docs/adr/0021-digiquant-supabase-project-topology.md``).

Credential resolution **prefers** the ``_DIGIQUANT``-suffixed vars and **falls back**
to the shared ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY``. Today both resolve to
the same project, so the store works with zero extra config; if the strategy store
ever graduates onto its own Supabase project, setting the ``_DIGIQUANT`` vars splits it
off with no code change.
"""

from __future__ import annotations

import os
from typing import Any, Protocol  # noqa: ANN401 — SupabaseLike.table returns the driver's dynamic type

SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"
DIGIQUANT_URL_ENV = "SUPABASE_URL_DIGIQUANT"
DIGIQUANT_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY_DIGIQUANT"


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
    """Return ``(url, service_role_key)`` for the DigiQuant ``core`` project.

    Prefers the ``_DIGIQUANT``-suffixed vars; falls back to the shared
    ``SUPABASE_URL`` / ``SUPABASE_SERVICE_ROLE_KEY``. Blank values normalize to
    ``None`` so callers get a single, unambiguous "creds missing" signal.
    """
    url = _first_env(DIGIQUANT_URL_ENV, SUPABASE_URL_ENV)
    key = _first_env(DIGIQUANT_SERVICE_ROLE_KEY_ENV, SUPABASE_SERVICE_ROLE_KEY_ENV)
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
    "DIGIQUANT_SERVICE_ROLE_KEY_ENV",
    "DIGIQUANT_URL_ENV",
    "SUPABASE_SERVICE_ROLE_KEY_ENV",
    "SUPABASE_URL_ENV",
    "SupabaseLike",
    "build_digiquant_client",
    "digiquant_credentials",
]
