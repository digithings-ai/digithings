"""digisearch client - unified orchestrator. DigiSearch.from_config()."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from types import MappingProxyType
from typing import Any, Mapping

from digibase.art9 import ScreenResult, screen_request

from digisearch.core.config import DigiSearchConfig
from digisearch.core.models import Document, Query, Result

# --------------------------------------------------------------------------
# Art. 9 surface registry (DIG-1083 leaf 10; spec DIG-912 §5.4, tests 7 and 8)
#
# ``digibase.art9`` keys its floor by HTTP path, so a path-keyed registry is
# structurally unable to see a surface that has no path: the streamable-HTTP MCP
# server, the in-process SDK entry, and any HTTP route the auth layer exempts.
# Spec §5.4 therefore asks for "an explicit mechanism, not by path", and this
# is it: every such surface is declared here by an explicit id, and a surface
# that is *not* declared is refused rather than waved through (finding F11 -
# without that, forgetting to screen a surface is invisible).
#
# This module is the registry's home because it is the only digisearch module
# import-light enough for ``server.py`` (needs fastapi + digikey) and
# ``mcp_server.py`` (needs the optional ``mcp`` extra) to both reach; they must
# not import each other.
# --------------------------------------------------------------------------

SURFACE_KIND_HTTP = "http"
SURFACE_KIND_MCP = "mcp"
SURFACE_KIND_SDK = "sdk"

SURFACE_UNREGISTERED = "art9:surface_unregistered"

#: Surface ids of the two non-HTTP digisearch entry points.
SURFACE_MCP = "mcp"
SURFACE_SDK_INGEST = "sdk:ingest"


class Art9SurfaceRefusal(RuntimeError):
    """Raised when a payload trips Art. 9 on a registered surface."""

    def __init__(self, surface: str, result: ScreenResult) -> None:
        self.surface = surface
        self.result = result
        super().__init__(f"{result.reason} (surface {surface})")


_surfaces: dict[str, str] = {}


def declare_art9_surface(surface: str, kind: str) -> None:
    """Declare a digisearch entry point as Art. 9 screened.

    Idempotent. ``kind`` is one of the ``SURFACE_KIND_*`` constants and is
    informational: it names the transport, the screening does not vary by it.
    """
    _surfaces[surface] = kind


#: Read-only view. Declaring a surface mutates the registry in place so that a
#: module can declare at import time and callers always observe a live view.
ART9_SURFACES: Mapping[str, str] = MappingProxyType(_surfaces)

declare_art9_surface(SURFACE_MCP, SURFACE_KIND_MCP)
declare_art9_surface(SURFACE_SDK_INGEST, SURFACE_KIND_SDK)


def art9_surface_kind(surface: str) -> str | None:
    """Transport kind of a declared surface, or ``None`` when undeclared."""
    return ART9_SURFACES.get(surface)


def screen_art9_surface(
    surface: str, payload: Any, *, exception_ref: str | None = None
) -> ScreenResult:
    """Screen ``payload`` for the named surface.

    An undeclared surface is REFUSED with ``art9:surface_unregistered``, not
    allowed: a caller reaching a surface that no one registered is exactly the
    absence this registry exists to make visible.
    """
    if surface not in ART9_SURFACES:
        return ScreenResult(
            categories=(),
            redacted=None,
            decision="refuse",
            reason=f"{SURFACE_UNREGISTERED}:{surface}",
        )
    return screen_request(payload, exception_ref=exception_ref)


def require_art9_clear(
    surface: str, payload: Any, *, exception_ref: str | None = None
) -> ScreenResult:
    """Screen ``payload`` and raise :class:`Art9SurfaceRefusal` unless it is clear."""
    result = screen_art9_surface(surface, payload, exception_ref=exception_ref)
    if result.decision == "refuse":
        raise Art9SurfaceRefusal(surface, result)
    return result


def _as_screenable(value: Any) -> Any:
    """Plain-data view of a dataclass tree.

    ``screen_request`` walks mappings, sequences and strings. A ``Document`` is
    none of those, so screening the instance itself would find nothing - the
    guard would pass because the subject was empty, not because it was clean.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


class DigiSearch:
    """Unified DigiSearch client. Orchestrates indexes, embedding, search."""

    def __init__(self, config: DigiSearchConfig | None = None) -> None:
        self.config = config or DigiSearchConfig.from_env()
        self._indexes: dict[str, Any] = {}

    @classmethod
    def from_config(cls, path: str) -> "DigiSearch":
        """Load from YAML/TOML config file."""
        cfg = DigiSearchConfig.from_config(path)
        return cls(cfg)

    def get_index(self, name: str) -> Any | None:
        """Get configured index by name."""
        if name in self._indexes:
            return self._indexes[name]
        idx_cfg = self.config.get_index_config(name)
        if not idx_cfg:
            return None
        backend = idx_cfg.get("backend", "chroma")
        if backend == "chroma":
            try:
                from digisearch.indexes.backends.chroma import ChromaBackend

                persist = idx_cfg.get("persist_path")
                emb = self._get_embedder()
                idx = ChromaBackend(name=name, persist_path=persist, embedding_provider=emb)
                self._indexes[name] = idx
                return idx
            except ImportError:
                return None
        return None

    def _get_embedder(self) -> Any | None:
        """Resolve EmbeddingCache → BatchEmbedder → provider from config/env.

        Raises :class:`digisearch.embedding.factory.EmbeddingConfigError` when
        embed is explicitly configured but cannot be loaded (no silent no-op).
        """
        from digisearch.embedding.factory import resolve_embedding_pipeline

        return resolve_embedding_pipeline(self.config)

    def query(
        self, text: str, index_name: str = "default", top_k: int = 10, mode: str = "hybrid"
    ) -> list[Result]:
        """Search index. Uses configured backend or stub."""
        from digisearch.embedding.factory import normalize_query_mode

        mode = normalize_query_mode(mode)
        idx = self.get_index(index_name)
        if idx:
            q = Query(text=text, top_k=top_k, mode=mode)
            return idx.query(q)
        from digisearch.search._stub import query_index

        q = Query(text=text, top_k=top_k, mode=mode)
        return query_index(q, index_name=index_name).results

    def ingest(self, doc: Document, index_name: str = "default") -> int:
        """Index an already-chunked document. Returns chunks created.

        Filesystem parse → chunk → embed lives in
        :func:`digisearch.pipeline.ingest.ingest_source`. This method only
        writes ``doc.chunks`` to a configured DigiIndex or the backend router.

        This is the in-process SDK entry point and carries no digikey scope, so
        it is screened through the Art. 9 surface registry before the write.
        Leaf 6 screens the ``index_chunks`` seam below; screening here as well
        is deliberate - the SDK entry is reachable without ever reaching that
        seam (a configured index short-circuits at line below), and the two
        verdicts are the same detector's verdict on the same data.
        """
        require_art9_clear(SURFACE_SDK_INGEST, _as_screenable(doc))
        idx = self.get_index(index_name)
        if idx and doc.chunks:
            idx.add(doc.chunks)
            return len(doc.chunks)
        from digisearch.pipeline.ingest import index_chunks

        index_chunks(index_name, doc.chunks)
        return len(doc.chunks)

    def as_mcp_server(self) -> object:
        """Return MCP server exposing configured indexes. Use mcp.run() to start."""
        from digisearch.mcp_server import create_mcp_with_indexes

        return create_mcp_with_indexes(self)
