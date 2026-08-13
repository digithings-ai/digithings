"""Shared fixtures for tests/ds/."""

from __future__ import annotations

from collections.abc import Generator

import digisearch.indexes.backends.vectorize as vectorize_module
import pytest


@pytest.fixture(autouse=True)
def _reset_default_embedder_singleton() -> Generator[None]:
    """Reset `VectorizeBackend`'s process-wide default-embedder cache around every test.

    `_default_embedder_singleton` is deliberately module-level, not per-instance --
    `_vectorize_backend` builds a fresh `VectorizeBackend` on every query, so
    per-instance memoization alone would reload the ONNX model every call. Nothing
    resets that global between tests, though: a test that patches in a stub embedder
    (e.g. `test_query_constructs_default_embedder_at_most_once`) leaves that stub
    bound in the module for every test that runs afterward in the same process. This
    fixture is the reset -- so no individual test has to remember to do it, and the
    default embedder always looks freshly-unconstructed at the start of a test.

    Production behaviour (construct at most once *per process*) is untouched -- this
    only resets the test process's view of the cache between tests, the same as any
    other module-level test double.
    """
    vectorize_module._default_embedder_singleton = None
    try:
        yield
    finally:
        vectorize_module._default_embedder_singleton = None


#: Every name in the CLOUDFLARE_*/VECTORIZE_*/D1_* credential fallback chain
#: (digisearch.search._stub._first_env, used by `_vectorize_backend`,
#: `route_add_chunks`, and `server._require_real_search_backend`). Cleared before
#: every test so a real Cloudflare credential sitting in the host shell
#: (CLOUDFLARE_ACCOUNT_ID/CLOUDFLARE_API_TOKEN are wrangler-conventional names,
#: plausibly already exported for unrelated `wrangler` CLI use on a developer
#: machine) can never leak into a test that assumes Vectorize is unconfigured --
#: the #2239 credential rename widened the set of names that activate Vectorize, so
#: this fixture keeps the existing per-test `monkeypatch.delenv(...)` calls correct
#: without editing every one of them. Individual tests still opt in with their own
#: `monkeypatch.setenv`.
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
