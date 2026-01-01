"""Shared fixtures for tests/ds/."""

from __future__ import annotations

from collections.abc import Generator

import digisearch.embedding.providers.minilm as minilm_module
import digisearch.indexes.backends.vectorize as vectorize_module
import pytest

#: Cloudflare credential env vars — shared definition in tests.digi_test_env.
#: Re-export the autouse fixture so it remains active for this suite; rationale
#: for clearing (host-shell wrangler credentials) is documented there.
from tests.digi_test_env import (  # noqa: F401
    clear_cloudflare_credential_env as _clear_cloudflare_credential_env,
)


@pytest.fixture(autouse=True)
def _reset_default_embedder_singleton() -> Generator[None]:
    """Reset the process-wide MiniLM default-embedder cache around every test.

    Chroma and Vectorize share ``get_default_minilm_embedder()`` (module-level in
    ``minilm.py``). Nothing resets that global between tests, so a stub left
    bound by one test would leak into the next. This fixture clears the cache
    before and after each test.
    """
    minilm_module._default_minilm_singleton = None
    # Legacy attribute retained as a no-op clear for older patches/tests.
    if hasattr(vectorize_module, "_default_embedder_singleton"):
        vectorize_module._default_embedder_singleton = None  # type: ignore[attr-defined]
    try:
        yield
    finally:
        minilm_module._default_minilm_singleton = None
        if hasattr(vectorize_module, "_default_embedder_singleton"):
            vectorize_module._default_embedder_singleton = None  # type: ignore[attr-defined]
