"""Isolated exception type for Vectorize backend failures.

`VectorizeBackendError` lives in its own module, decoupled from `vectorize.py`, so it
stays importable even when importing the heavier `vectorize` module itself fails (a
missing optional dependency, a broken transitive import, etc.). `_stub.py`'s
`_vectorize_backend` needs to wrap exactly that failure mode -- an `ImportError`
raised while importing `VectorizeBackend` -- as `VectorizeBackendError`. If the error
class lived inside the module whose import just failed, it would be unavailable for
precisely the case it exists to handle: `from digisearch.indexes.backends.vectorize
import VectorizeBackend, VectorizeBackendError` fails atomically, so neither name gets
bound, and referencing `VectorizeBackendError` afterward in an `except` clause raises
`UnboundLocalError` instead of the intended wrapped error (verified empirically; a
failed `from module import a, b` binds neither `a` nor `b`).
"""

from __future__ import annotations


class VectorizeBackendError(Exception):
    """Raised when a configured Vectorize backend fails to serve a query.

    Deliberately NOT a subclass of ImportError/OSError/RuntimeError/TypeError/
    ValueError -- `_stub.py`'s `_BACKEND_ERRORS` tuple lists exactly those, and
    `query_index` catches that tuple to fall through to the next backend. Vectorize
    is the authoritative remote index once configured, so its failures must
    propagate to the caller instead of being swallowed and silently answered from
    Chroma (a different corpus). Azure/Chroma keep falling through on failure --
    they are optional local backends, not authoritative ones.
    """
