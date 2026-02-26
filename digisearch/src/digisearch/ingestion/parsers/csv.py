"""CSV parser. Uses Polars (AGENTS.md: no pandas)."""

from __future__ import annotations

import uuid
from pathlib import Path

from digisearch.core.models import DigiDocument
from digisearch.ingestion.base import Parser

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False


class CSVParser(Parser):
    """Parse CSV. Each row becomes document content (or chunk)."""

    def __init__(self, text_columns: list[str] | None = None) -> None:
        self.text_columns = text_columns

    def parse(self, source: str | Path | bytes) -> DigiDocument:
        if not _POLARS_AVAILABLE:
            raise ImportError("Install polars for CSV parsing")
        if isinstance(source, bytes):
            df = pl.read_csv(source)
            src_str = "<bytes>"
        else:
            path = Path(source)
            if path.exists():
                df = pl.read_csv(path)
                src_str = str(path)
            else:
                raise FileNotFoundError(f"CSV source not found: {source}")
        cols = self.text_columns or df.columns
        content_parts = []
        for row in df.iter_rows(named=True):
            parts = [str(row.get(c, "")) for c in cols if c in row]
            content_parts.append(" | ".join(parts))
        content = "\n".join(content_parts)
        doc_id = str(uuid.uuid4())
        return DigiDocument(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="csv",
            metadata={"rows": len(df), "columns": df.columns},
        )

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext == ".csv"
