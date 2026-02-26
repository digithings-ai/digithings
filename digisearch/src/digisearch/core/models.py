"""DigiSearch core data contracts. Shared across DigiFlow, DigiGraph, and MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DigiDocument:
    """Document ingested into DigiSearch. Passed between modules (DigiFlow, DigiGraph)."""

    id: str
    content: str
    source: str  # file path, URL, or identifier
    doc_type: str  # "pdf", "html", "docx", etc.
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list["DigiChunk"] = field(default_factory=list)


@dataclass
class DigiChunk:
    """Chunk of a document. May carry embedding for vector search."""

    id: str
    content: str
    doc_id: str  # parent DigiDocument.id
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DigiQuery:
    """Search query. Mode: keyword | vector | hybrid."""

    text: str
    embedding: list[float] | None = None
    top_k: int = 10
    filters: dict[str, Any] = field(default_factory=dict)
    mode: str = "hybrid"
    columns: list[str] | None = None  # optional metadata columns to return (intersected with index config)
    facets: list[str] | None = None  # Azure: facet expressions e.g. ["sourceType", "itemType,count:20"]
    # Azure: hit highlighting (fields must be searchable)
    highlight_fields: list[str] | None = None
    highlight_pre_tag: str | None = None
    highlight_post_tag: str | None = None
    # Azure: sort (order_by: ["sentDateTime desc", "search.score() desc"])
    order_by: list[str] | None = None
    skip: int = 0  # pagination offset
    include_total_count: bool = False  # when True, total in response is full match count


@dataclass
class DigiResult:
    """Single search result with score and optional source doc."""

    chunk: DigiChunk
    score: float
    source_doc: DigiDocument | None = None
    rank: int | None = None


@dataclass
class SearchResponse:
    """Result of a search: hits and optional facet counts (Azure)."""

    results: list["DigiResult"]
    facets: dict[str, list[dict[str, Any]]] | None = None  # field -> [{value, count}, ...]
    total_count: int | None = None  # full match count when include_total_count was True (Azure get_count())
