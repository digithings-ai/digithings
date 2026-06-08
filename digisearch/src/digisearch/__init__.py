"""DigiSearch – RAG, vectorization, document search for Digi ecosystem.

Public client surface (``DigiSearch``, ``Chunk``, ``Document``, ``Query``,
``Result``) is resolved **lazily** via :pep:`562` ``__getattr__`` so that
importing a leaf submodule does not drag in the full RAG service stack.

Lazy-import contract
--------------------
``from digisearch import DigiSearch`` (and ``Chunk``/``Document``/``Query``/
``Result``) keeps working, but the underlying ``digisearch.client`` /
``digisearch.core.models`` modules are only imported on first attribute
access — never at ``import digisearch`` time. This means a consumer that only
wants ``digisearch.ingestion.parsers.pdf`` can import it without pulling in
``fastapi`` / ``uvicorn`` / ``mcp`` / ``typer`` / ``digikey`` (the ``[server]``
extra) or the ``DigiSearch`` client. See ``ARCHITECTURE.md`` §"Lazy package
surface and install extras".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__version__ = "0.1.0"

# Attribute name -> dotted module path it is resolved from. Kept tiny and pure
# so the mapping itself imports nothing heavy.
_LAZY: dict[str, str] = {
    "DigiSearch": "digisearch.client",
    "Chunk": "digisearch.core.models",
    "Document": "digisearch.core.models",
    "Query": "digisearch.core.models",
    "Result": "digisearch.core.models",
}

__all__ = [
    "DigiSearch",
    "Chunk",
    "Document",
    "Query",
    "Result",
    "__version__",
]

if TYPE_CHECKING:  # static type-checkers / IDEs resolve the real symbols
    from digisearch.client import DigiSearch
    from digisearch.core.models import Chunk, Document, Query, Result


def __getattr__(name: str) -> object:
    """:pep:`562` lazy attribute resolution for the public client surface.

    Only the names in :data:`_LAZY` are resolved here; everything else raises
    ``AttributeError`` so normal submodule import (``digisearch.ingestion...``)
    and missing-attribute errors behave exactly as before. Resolved values are
    cached into module ``globals()`` so the import cost is paid at most once.
    """
    module_path = _LAZY.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value  # cache: subsequent access skips __getattr__
    return value


def __dir__() -> list[str]:
    """Include the lazily-exported names in ``dir(digisearch)``."""
    return sorted(set(globals()) | set(__all__))
