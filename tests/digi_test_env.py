"""Shared Cloudflare credential env clearing for unit tests.

Canonical CLOUDFLARE_*/VECTORIZE_*/D1_* names can leak from a developer shell
into tests that assume those backends are unconfigured. Suites import the
shared tuple/fixture and add suite-specific extras (D1_DATABASE_MAP,
DIGI_TENANT_CORPUS_MAP, …) in their own conftest.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

CLOUDFLARE_CREDENTIAL_ENV_VARS = (
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "VECTORIZE_ACCOUNT_ID",
    "VECTORIZE_API_TOKEN",
    "D1_ACCOUNT_ID",
    "D1_API_TOKEN",
)


@pytest.fixture(autouse=True)
def clear_cloudflare_credential_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    for name in CLOUDFLARE_CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
