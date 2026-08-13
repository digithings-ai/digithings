"""Shared fixtures for tests/dv/."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from tests.digi_test_env import CLOUDFLARE_CREDENTIAL_ENV_VARS as _SHARED_CF_ENV_VARS

#: Every name in the CLOUDFLARE_*/VECTORIZE_*/D1_* credential fallback chain
#: (digivault.server._d1_credentials, via digivault.supabase_store._first_env),
#: plus digivault suite-specific maps. Cleared before every test so a real
#: Cloudflare credential sitting in the host shell can never leak into a test
#: that assumes D1 is unconfigured. Individual tests still opt in with their
#: own `monkeypatch.setenv`.
_CLOUDFLARE_CREDENTIAL_ENV_VARS = (
    *_SHARED_CF_ENV_VARS,
    "D1_DATABASE_MAP",
    # Same leakage concern: digivault.tenant_scope reads DIGI_TENANT_CORPUS_MAP
    # (added alongside the #2265/PR #2293 tenant-prefix-binding fix).
    "DIGI_TENANT_CORPUS_MAP",
)


@pytest.fixture(autouse=True)
def _clear_cloudflare_credential_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    for name in _CLOUDFLARE_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
