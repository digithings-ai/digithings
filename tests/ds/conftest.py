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
