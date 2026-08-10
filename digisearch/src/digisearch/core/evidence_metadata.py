"""Normative evidence metadata for digisearch / digiclone indexes.

Chunk and document metadata SHOULD include these keys when known so that
`Query.filters` (structured) can restrict by tier, venue, year, and tags.

ChromaDB accepts only str, int, float, and bool in metadata; list values are
joined with commas for storage and comparison uses the same serialized form.
"""

from __future__ import annotations

from typing import Any

from digisearch.core.models import Chunk, Document

# Evidence tier vocabulary (normative for digiclone research indexes).
EVIDENCE_TIER_PEER_REVIEWED = "peer_reviewed"
EVIDENCE_TIER_WORKING_PAPER = "working_paper"
EVIDENCE_TIER_INDUSTRY = "industry"
EVIDENCE_TIER_WEB = "web"

EVIDENCE_TIER_VALUES: frozenset[str] = frozenset(
    {
        EVIDENCE_TIER_PEER_REVIEWED,
        EVIDENCE_TIER_WORKING_PAPER,
        EVIDENCE_TIER_INDUSTRY,
        EVIDENCE_TIER_WEB,
    }
)

# Keys callers SHOULD use (document and chunk metadata).
NORMATIVE_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "evidence_tier",
        "peer_reviewed",
        "publication_year",
        "venue",
        "title",
        "doi_or_arxiv",
        "asset_class_tags",
        "methodology_tags",
        "language",
        "license_notes",
        "source_url",
    }
)


def _serialize_value_for_chroma(key: str, value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return ",".join(parts) if parts else None
    return str(value)


def normalize_metadata_for_chroma(
    metadata: dict[str, Any] | None,
) -> dict[str, str | int | float | bool]:
    """Return a copy of metadata safe for Chroma ``add`` / ``upsert`` metadatas."""
    if not metadata:
        return {}
    out: dict[str, str | int | float | bool] = {}
    for key, raw in metadata.items():
        if key is None:
            continue
        sk = str(key)
        sv = _serialize_value_for_chroma(sk, raw)
        if sv is not None:
            out[sk] = sv
    return out


def _title_from_source(source: str) -> str | None:
    """Best-effort title from a filesystem path or URL basename."""
    from pathlib import Path

    raw = (source or "").strip()
    if not raw or raw.startswith("<"):
        return None
    name = Path(raw.replace("\\", "/")).name
    if not name:
        return None
    stem = Path(name).stem if "." in name else name
    cleaned = stem.replace("_", " ").replace("-", " ").strip()
    return cleaned or None


def provenance_metadata_from_document(doc: Document) -> dict[str, Any]:
    """Build path/title provenance from ``Document.source`` for citation UIs.

    Parsers store the filesystem path on ``Document.source`` but historically left
    ``metadata`` empty, so Chroma hits only carried ``chunk_index`` / ``doc_id`` and
    digichat Sources fell back to opaque UUIDs or identical first-heading snippets.
    """
    out: dict[str, Any] = {}
    src = (doc.source or "").strip()
    if src and not src.startswith("<"):
        out.setdefault("source", src)
        out.setdefault("path", src)
        out.setdefault("source_url", src)
    title = (doc.metadata or {}).get("title")
    if not title:
        derived = _title_from_source(src)
        if derived:
            out["title"] = derived
    return out


def merge_document_metadata_into_chunks(doc: Document, chunks: list[Chunk]) -> None:
    """Merge document metadata into each chunk (chunk keys win on conflict).

    Always folds ``Document.source`` into chunk metadata as ``source`` / ``path`` /
    ``source_url`` when missing so retrieval citations stay human-readable.
    """
    base_doc = {**provenance_metadata_from_document(doc), **dict(doc.metadata or {})}
    for c in chunks:
        merged_raw = {**base_doc, **(c.metadata or {})}
        c.metadata = normalize_metadata_for_chroma(merged_raw)


def load_sidecar_yaml(sidecar_path: Any) -> dict[str, Any]:
    """Load optional sidecar YAML (path-like). Returns {} if missing or empty."""
    from pathlib import Path

    import yaml

    p = Path(sidecar_path)
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return {}
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def metadata_from_sidecar_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Extract metadata mapping from a sidecar root (may nest under 'metadata')."""
    meta = data.get("metadata")
    if isinstance(meta, dict):
        return dict(meta)
    # Allow flat document fields at root
    out: dict[str, Any] = {}
    for k in NORMATIVE_METADATA_KEYS | {"doc_type", "id", "title"}:
        if k in data and data[k] is not None:
            out[k] = data[k]
    if "title" in data and "title" not in out:
        out["title"] = data["title"]
    return out
