"""Shared fixtures for tests/scripts/."""

from __future__ import annotations

from collections.abc import Generator

import pytest

#: Every name in the CLOUDFLARE_*/VECTORIZE_*/D1_* credential fallback chain read by
#: scripts/d1_sync.py and scripts/vectorize_sync.py (both via
#: digivault.supabase_store._first_env). Cleared before every test so a real
#: Cloudflare credential sitting in the host shell (CLOUDFLARE_ACCOUNT_ID/
#: CLOUDFLARE_API_TOKEN are wrangler-conventional names, plausibly already exported
#: for unrelated `wrangler` CLI use on a developer machine) can never leak into a
#: test that assumes no credentials are configured -- the #2239 credential rename
#: widened the set of names each script's "are credentials set?" check reads.
#: Individual tests still opt in with their own `monkeypatch.setenv`.
_CLOUDFLARE_CREDENTIAL_ENV_VARS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "VECTORIZE_ACCOUNT_ID",
    "VECTORIZE_API_TOKEN",
    "D1_ACCOUNT_ID",
    "D1_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _clear_cloudflare_credential_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    for name in _CLOUDFLARE_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
