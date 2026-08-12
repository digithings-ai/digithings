"""Shared fixtures for tests/dv/."""

from __future__ import annotations

from collections.abc import Generator

import pytest

#: Every name in the CLOUDFLARE_*/VECTORIZE_*/D1_* credential fallback chain
#: (digivault.server._d1_credentials, via digivault.supabase_store._first_env).
#: Cleared before every test so a real Cloudflare credential sitting in the host
#: shell (CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN are wrangler-conventional names,
#: plausibly already exported for unrelated `wrangler` CLI use on a developer
#: machine) can never leak into a test that assumes D1 is unconfigured -- the
#: canonical-with-fallback lookup added by the #2239 credential rename widened the
#: set of env var names that can make `_d1_configured()` see "some but not all"
#: configured, so this fixture keeps the existing per-test `monkeypatch.delenv(...)`
#: calls throughout this module correct without editing every one of them. Individual
#: tests still opt in with their own `monkeypatch.setenv`.
_CLOUDFLARE_CREDENTIAL_ENV_VARS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "VECTORIZE_ACCOUNT_ID",
    "VECTORIZE_API_TOKEN",
    "D1_ACCOUNT_ID",
    "D1_API_TOKEN",
    "D1_DATABASE_MAP",
)


@pytest.fixture(autouse=True)
def _clear_cloudflare_credential_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    for name in _CLOUDFLARE_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
