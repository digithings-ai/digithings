"""Isolated exception type for D1 store failures.

``D1StoreError`` lives in its own module, decoupled from ``d1_store.py``, so it stays
importable even when importing the heavier ``d1_store`` module itself fails. A failing
``from digivault.d1_store import D1Store, D1StoreError`` binds NEITHER name, so an
``except D1StoreError`` afterwards would raise ``NameError`` instead of the intended
wrapped error. Mirrors ``digisearch/src/digisearch/indexes/backends/vectorize_errors.py``.
"""

from __future__ import annotations


class D1StoreError(RuntimeError):
    """Raised when D1 is unconfigured, or a query fails.

    Subclasses ``RuntimeError`` to match ``SupabaseStoreError`` so
    ``digivault/src/digivault/server.py``'s existing 503 handler covers both stores.
    """
